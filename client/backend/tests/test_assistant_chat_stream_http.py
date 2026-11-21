"""chat SSE 流HTTP级回归钉（c-agent-effects 2026-11-18 boss 走查实锤）。

事故：router._drive 只写了 effects 消费（run_end 注入）没写收集（run_effects
未定义）→ NameError 在 drive task 里静默炸掉 → _STOP 永不入队 → SSE 永挂，
前端「进行中」卡死且零遥测。3303 个后端测试全绿没拦住——因为没有任何测试
真正驱动 /assistant/chat 到 run_end。

钉子三条（HTTP 级，走真实 route＋queue＋drive 链路）：
1. 成功写步 → run_end 携带 effects（收集＋注入成对）；
2. drive 中途崩溃 → 流仍收口且 error 事件显式下发（SHALL NOT 静默永挂）；
3. 失败写步 → 不触发 effect（刷新＝假反馈）。

读取统一走带超时的线程 future：回归形态是「永挂」——无界读取会把 CI 挂死，
超时兜底让失败形态可判（timeout＝回归信号）。
"""

import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix="_chat_http.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_root = tempfile.mkdtemp(prefix="chat_http_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_root

from db import Base, engine  # noqa: E402

_CFG = os.path.join(_tmp_root, "config.json")

from fastapi.testclient import TestClient  # noqa: E402

import auth_local.middleware as _mw  # noqa: E402
import auth_local.service as _service  # noqa: E402
from main import app  # noqa: E402


async def _setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


import asyncio  # noqa: E402
import json  # noqa: E402

asyncio.run(_setup())

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def _startup():
    _orig = _mw.CONFIG_FILE
    with client:
        yield
    _mw.CONFIG_FILE = _orig


def _set_session():
    _mw.CONFIG_FILE = _CFG
    _service.CONFIG_FILE = _CFG
    cfg = _service.get_local_config()
    cfg.update({
        "tier": "max",
        "token": "tok-chathttp",
        "username": "chathttp",
        "last_login_at": datetime.now(UTC).isoformat(),
    })
    _service.save_local_config(cfg)


@pytest.fixture(autouse=True)
def _fresh_config():
    _orig = _mw.CONFIG_FILE
    _set_session()
    yield
    if os.path.exists(_CFG):
        os.remove(_CFG)
    _mw.CONFIG_FILE = _orig


def _mk_book() -> str:
    r = client.post(
        "/api/novels",
        json={"name": f"chat-http-{datetime.now(UTC).timestamp()}", "source": "manual"},
        headers={"Authorization": "Bearer tok-chathttp"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


class _FakeClient:
    """最小客户端面：AgentLoop 构造只碰 resolve/supports_native_tools。"""

    def resolve(self, alias: str) -> str:
        return "fake-model"

    def supports_native_tools(self) -> bool:
        return False


def _patch_loop(monkeypatch, events, crash_after: int | None = None, client_factory=None):
    """替换 AgentLoop.run 为脚本化事件流；crash_after=N 表示第 N 个事件后抛。

    返回 client 构造调用账（project_id/kwargs）——按次模型覆盖对断言用。
    """
    import ai_state
    import assistant.router as router_mod

    client_calls: list[dict] = []
    run_calls: list[dict] = []

    async def _fake_get_client(project_id, **kwargs):
        client_calls.append({"project_id": project_id, **kwargs})
        return client_factory() if client_factory else _FakeClient()

    async def _fake_has_key(db, user_id):
        return True

    async def _fake_run(self, user_input, prime=None):
        run_calls.append({
            "thinking": getattr(self.cfg, "thinking", None),
            "input": user_input,
        })
        yielded = 0
        for ev in events:
            if (
                isinstance(ev, dict)
                and ev.get("type") == "plan"
                and isinstance(ev.get("plan"), dict)
            ):
                # 与真实循环一致：plan 事件同步记进 result（断连收口要用）
                self.result.plan = ev["plan"]
            if crash_after is not None and yielded >= crash_after:
                raise RuntimeError("boom——桩注入的 drive 崩溃")
            yielded += 1
            yield ev
        # 事件耗尽后的崩溃位：crash_after==len(events) 时循环内检查点永远够不着
        if crash_after is not None and yielded >= crash_after:
            raise RuntimeError("boom——桩注入的 drive 崩溃")

    import ai_client

    monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_get_client)
    monkeypatch.setattr(ai_state, "user_has_ai_key", _fake_has_key)
    monkeypatch.setattr(router_mod.AgentLoop, "run", _fake_run)
    return {"clients": client_calls, "runs": run_calls}


def _read_sse(bid: str, message: str, body_extra: dict | None = None) -> list[dict]:
    """带超时读取 SSE 全流——永挂形态超时即失败（回归信号）。"""

    def _consume() -> list[dict]:
        out: list[dict] = []
        body = {"message": message, "page": "ch:og", "thread": "ch:og"}
        if body_extra:
            body.update(body_extra)
        with client.stream(
            "POST",
            f"/api/novels/{bid}/assistant/chat",
            json=body,
            headers={"Authorization": "Bearer tok-chathttp"},
        ) as resp:
            assert resp.status_code == 200, resp.status_code
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    out.append(json.loads(line[len("data: "):]))
                except ValueError:
                    pass
        return out

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_consume).result(timeout=30)


def _fake_run_events(tool: str = "confirm_chapter", ok: bool = True) -> list[dict]:
    return [
        {"type": "run_start", "runId": "fx1"},
        {
            "type": "step_end",
            "runId": "fx1",
            "stepId": "fx1-1",
            "tool": tool,
            "resultNote": "已确认《第1章》的章纲。",
            "ok": ok,
        },
        {"type": "narration", "text": "确认好了，树里第一章已经变绿。"},
        {"type": "run_end", "runId": "fx1", "steps": 1, "toolCalls": 1, "degraded": False, "error": ""},
    ]


def test_run_end_carries_effects_and_stream_terminates(monkeypatch):
    """成功写步：run_end 携带 effects（chapters 域）且流正常收口。"""
    bid = _mk_book()
    _patch_loop(monkeypatch, _fake_run_events(ok=True))
    events = _read_sse(bid, "确认第一章章纲")
    run_end = [e for e in events if e.get("type") == "run_end"]
    assert len(run_end) == 1, events
    effects = run_end[0].get("effects")
    assert effects, f"run_end 缺 effects：{run_end[0]}"
    assert effects[0]["domain"] == "chapters"
    assert effects[0]["action"] == "refresh"


def test_drive_crash_emits_error_and_terminates(monkeypatch):
    """drive 崩溃：流必须收口且显式 error 事件下发——SHALL NOT 静默永挂。"""
    bid = _mk_book()
    _patch_loop(
        monkeypatch,
        [
            {"type": "run_start", "runId": "cx1"},
            {"type": "narration", "text": "我看一下这本书的第一章……"},
        ],
        crash_after=2,
    )
    events = _read_sse(bid, "看看第一章")
    errs = [e for e in events if e.get("type") == "error"]
    assert errs, f"drive 崩溃后无 error 事件：{events}"
    assert errs[0].get("message"), "error 事件缺人话文案"
    # 流已收口（_read_sse 正常返回即收口；收不到会 timeout 失败）


def test_failed_write_step_no_effect(monkeypatch):
    """失败写步不触发 effect——数据没变，刷新＝假反馈。"""
    bid = _mk_book()
    _patch_loop(monkeypatch, _fake_run_events(ok=False))
    events = _read_sse(bid, "确认第一章章纲")
    run_end = [e for e in events if e.get("type") == "run_end"]
    assert len(run_end) == 1
    assert not run_end[0].get("effects"), f"失败写步不应带 effects：{run_end[0]}"


def test_read_only_step_no_effect(monkeypatch):
    """读类工具（effect_domain 空声明）不触发 effect。"""
    bid = _mk_book()
    _patch_loop(monkeypatch, _fake_run_events(tool="read_chapter", ok=True))
    events = _read_sse(bid, "看看第一章")
    run_end = [e for e in events if e.get("type") == "run_end"]
    assert len(run_end) == 1
    assert not run_end[0].get("effects"), f"读步不应带 effects：{run_end[0]}"


def test_navigate_effect_emitted_immediately_and_not_persisted(monkeypatch):
    """c-agent-nav 钉：switch_tab 成功步 → effect 事件即时下发（紧随 step_end）
    ＋run_end 不带 effects（导航不进收尾汇总）＋不入库（回放安全）。"""
    bid = _mk_book()
    _patch_loop(monkeypatch, [
        {"type": "run_start", "runId": "nx1"},
        {
            "type": "step_end",
            "runId": "nx1",
            "stepId": "nx1-1",
            "tool": "switch_tab",
            "resultNote": "已切到正文页签。",
            "ok": True,
            "args": {"tab": "prose"},
        },
        {"type": "narration", "text": "我切过去了，你看正文。"},
        {"type": "run_end", "runId": "nx1", "steps": 1, "toolCalls": 1, "degraded": False, "error": ""},
    ])
    events = _read_sse(bid, "把页面切到正文")
    types = [e.get("type") for e in events]
    assert "effect" in types, f"SSE 缺 effect 事件：{types}"
    effect = next(e for e in events if e.get("type") == "effect")
    assert effect["action"] == "navigate"
    assert effect["domain"] == "ui"
    assert effect["target"] == "prose"
    # 即时性：effect 在 run_end 之前到达
    assert types.index("effect") < types.index("run_end")
    # 紧随 step_end（中途翻页——顺序契约）
    assert types.index("effect") == types.index("step_end") + 1
    # run_end 不携带 effects（navigate 不进收尾汇总）
    run_end = next(e for e in events if e.get("type") == "run_end")
    assert not run_end.get("effects"), f"navigate 不应进 run_end effects：{run_end}"
    # 不入库：会话回看无 navigate 载荷（回放安全）
    r = client.get(
        f"/api/novels/{bid}/assistant/session?thread=ch:og",
        headers={"Authorization": "Bearer tok-chathttp"},
    )
    assert r.status_code == 200
    payloads = [m.get("payload") or {} for m in r.json().get("messages", [])]
    assert all(p.get("action") != "navigate" for p in payloads)


def test_failed_switch_tab_no_effect(monkeypatch):
    """失败 switch_tab（坏页签 ok=False）→ 无 effect 事件——模型如实转告。"""
    bid = _mk_book()
    _patch_loop(monkeypatch, [
        {"type": "run_start", "runId": "bx1"},
        {
            "type": "step_end",
            "runId": "bx1",
            "stepId": "bx1-1",
            "tool": "switch_tab",
            "resultNote": "没有「nope」这个页签——可选的是：og（章纲）、prose（正文）。",
            "ok": False,
            "args": {"tab": "nope"},
        },
        {"type": "narration", "text": "这个页签我不认识，可以从章纲、正文这些里挑。"},
        {"type": "run_end", "runId": "bx1", "steps": 1, "toolCalls": 1, "degraded": False, "error": ""},
    ])
    events = _read_sse(bid, "切到不存在的页")
    assert all(e.get("type") != "effect" for e in events), events


def test_write_gate_card_reaches_client_before_approval(monkeypatch):
    """授权卡必须先到客户端再停车等批复（2026-11-21 真机「进行中」空等实锤）。

    旧实现把 permission_required 攒在 gate_fn 返回值里、等批复完才交给 SSE：
    客户端永远看不到卡 → 没法批 → 默认档每写必确认只能空等 300s 超时，界面
    一直「进行中」。这里钉死：卡在批复之前到达（批复动作必须由「看到卡」驱动）。
    """
    import threading

    bid = _mk_book()
    import ai_client
    import ai_state
    import assistant.router as router_mod

    async def _fake_get_client(project_id):
        return _FakeClient()

    async def _fake_has_key(db, user_id):
        return True

    async def _fake_run(self, user_input, prime=None):
        yield {"type": "run_start", "runId": "gw1"}
        # field 须合法（synopsis）：#1106 起非法字段（如 premise）不弹卡直接拒，
        # 「卡先到」路径只能用真实可写的字段驱动
        async for ev in self.gate_fn(
            "write_settings_field",
            {"stype": "story", "field": "synopsis", "value": "授权卡先到的回归前提"},
        ):
            yield ev
        yield {
            "type": "run_end",
            "runId": "gw1",
            "steps": 0,
            "toolCalls": 0,
            "degraded": False,
            "error": "",
        }

    monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_get_client)
    monkeypatch.setattr(ai_state, "user_has_ai_key", _fake_has_key)
    monkeypatch.setattr(router_mod.AgentLoop, "run", _fake_run)

    events: list[dict] = []
    card_seen = threading.Event()
    gate_id: dict[str, str] = {}

    def _consume():
        with client.stream(
            "POST",
            f"/api/novels/{bid}/assistant/chat",
            json={"message": "把前提写进去", "page": "set:genre", "thread": "set:genre"},
            headers={"Authorization": "Bearer tok-chathttp"},
        ) as resp:
            assert resp.status_code == 200, resp.status_code
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    ev = json.loads(line[len("data: "):])
                except ValueError:
                    continue
                events.append(ev)
                if ev.get("type") == "permission_required":
                    gate_id["id"] = str(ev.get("gateId") or "")
                    card_seen.set()

    reader = threading.Thread(target=_consume, daemon=True)
    reader.start()
    try:
        # 卡必须在停车等待期间就到（批复只能由「看到卡」驱动）；旧实现这里超时
        assert card_seen.wait(10), f"授权卡没有在批复前到达：{events}"
        assert gate_id["id"]
        r = client.post(
            f"/api/novels/{bid}/assistant/approve",
            json={"gateId": gate_id["id"], "decision": "denied"},
            headers={"Authorization": "Bearer tok-chathttp"},
        )
        assert r.status_code == 200, r.text
    finally:
        # 失败兜底：停止在跑 run，避免停车 300s 拖住测试
        client.post(
            f"/api/novels/{bid}/assistant/stop",
            json={"thread": "set:genre"},
            headers={"Authorization": "Bearer tok-chathttp"},
        )
        reader.join(15)
    types = [e.get("type") for e in events]
    assert "permission_required" in types
    assert "gate_result" in types
    assert types.index("permission_required") < types.index("gate_result")
    assert "run_end" in types


def test_tool_step_narration_persisted(monkeypatch):
    """工具步叙述入账（c-agent-narration-persist）：text harness 的流式正文
    必须在会话里落盘——真机实锤「截图有、存档无」；走真实 loop＋落盘链路。"""
    bid = _mk_book()
    import ai_client
    import ai_state
    import assistant.loop as loop_mod
    from ai_client import StreamEvent
    from assistant.tools import ToolResult

    class _ScriptedClient(_FakeClient):
        """先吐 v2 工具动作、再收口；正文走 delta（与生产几何同形）。"""

        def __init__(self):
            self.turns = [
                "我先看一眼设定。\n===ACT===\n"
                + json.dumps({"action": "tool", "tool": "read_progress", "args": {}}),
                json.dumps(
                    {"action": "final", "tool": "", "args": {}, "reply": "设定是空的，我来搭。"},
                    ensure_ascii=False,
                ),
            ]

        async def chat_stream(self, **kwargs):
            text = self.turns.pop(0) if self.turns else ""
            yield StreamEvent(text=text, is_done=True, tokens=5, tokens_in=5)

        async def chat(self, **kwargs):
            return "摘要"

    async def _fake_get_client(project_id):
        return _ScriptedClient()

    async def _fake_has_key(db, user_id):
        return True

    async def fake_run_tool(ctx, name, args):
        return ToolResult(ok=True, summary="（主线还没有内容）")

    monkeypatch.setattr(loop_mod, "tools_for_thread", lambda thread: None)
    monkeypatch.setattr(loop_mod, "run_tool", fake_run_tool)
    monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_get_client)
    monkeypatch.setattr(ai_state, "user_has_ai_key", _fake_has_key)

    events = _read_sse(bid, "看看设定")
    assert any(e.get("type") == "step_end" for e in events), events
    r = client.get(
        f"/api/novels/{bid}/assistant/session?thread=ch:og",
        headers={"Authorization": "Bearer tok-chathttp"},
    )
    assert r.status_code == 200
    contents = [m.get("content") or "" for m in r.json().get("messages", [])]
    joined = "\n".join(contents)
    assert "我先看一眼设定。" in joined, joined
    assert "设定是空的，我来搭。" in joined, joined


def test_chat_body_model_override_and_thinking_passthrough(monkeypatch):
    """c-agent-thinking-bubbles：body 的按次模型覆盖对与深度思考开关要真的进
    客户端构造与 LoopConfig——底栏控件不是摆设。"""
    bid = _mk_book()
    rec = _patch_loop(monkeypatch, [
        {"type": "run_start", "runId": "ov1"},
        {"type": "narration", "text": "好。"},
        {"type": "run_end", "runId": "ov1", "steps": 0, "toolCalls": 0, "degraded": False, "error": ""},
    ])
    _read_sse(
        bid,
        "用这个模型答",
        {"api_config_id": "cfg-x", "model": "m-y", "thinking": True},
    )
    assert rec["clients"][0] == {
        "project_id": bid,
        "api_config_id": "cfg-x",
        "model": "m-y",
    }
    assert rec["runs"][0]["thinking"] == {"type": "enabled"}

    # 关思考：显式 disabled 进 LoopConfig
    bid2 = _mk_book()
    rec2 = _patch_loop(monkeypatch, [
        {"type": "run_start", "runId": "ov2"},
        {"type": "narration", "text": "好。"},
        {"type": "run_end", "runId": "ov2", "steps": 0, "toolCalls": 0, "degraded": False, "error": ""},
    ])
    _read_sse(bid2, "别想了", {"thinking": False})
    assert rec2["clients"][0] == {"project_id": bid2}
    assert rec2["runs"][0]["thinking"] == {"type": "disabled"}

    # 缺省：沿用 API 配置（不传覆盖）
    bid3 = _mk_book()
    rec3 = _patch_loop(monkeypatch, [
        {"type": "run_start", "runId": "ov3"},
        {"type": "narration", "text": "好。"},
        {"type": "run_end", "runId": "ov3", "steps": 0, "toolCalls": 0, "degraded": False, "error": ""},
    ])
    _read_sse(bid3, "默认就好")
    assert rec3["clients"][0] == {"project_id": bid3}
    assert rec3["runs"][0]["thinking"] is None


def test_process_persisted_and_replayed_in_order(monkeypatch):
    """思考与工具过程按发生顺序并入 assistant 行 payload.process——重开书回看
    要能原样复原（不再是「只发 SSE、回看就丢」）。"""
    bid = _mk_book()
    _patch_loop(monkeypatch, [
        {"type": "run_start", "runId": "pc1"},
        {"type": "thinking", "text": "先看看主线"},
        {"type": "step_start", "runId": "pc1", "stepId": "pc1-1", "tool": "read_settings", "label": "先读主线设定"},
        {
            "type": "step_end",
            "runId": "pc1",
            "stepId": "pc1-1",
            "tool": "read_settings",
            "resultNote": "主线还没有内容",
            "ok": True,
            "args": {"area": "premise"},
            "apiCalls": [{"op": "assistant_step", "model": "m", "ms": 12, "tokens_in": 1, "tokens_out": 2, "ok": True}],
        },
        {"type": "thinking", "text": "再顺手看看卷纲"},
        {"type": "narration", "text": "看完了。"},
        {"type": "run_end", "runId": "pc1", "steps": 1, "toolCalls": 1, "degraded": False, "error": ""},
    ])
    _read_sse(bid, "看看主线")

    r = client.get(
        f"/api/novels/{bid}/assistant/session?thread=ch:og",
        headers={"Authorization": "Bearer tok-chathttp"},
    )
    assert r.status_code == 200
    rows = r.json().get("messages", [])
    assistant = next(m for m in rows if m["role"] == "assistant" and m["content"] == "看完了。")
    process = assistant["payload"]["process"]
    assert [item["kind"] for item in process] == ["thinking", "tool", "thinking"]
    assert process[0]["text"] == "先看看主线"
    assert process[1] == {
        "kind": "tool",
        "stepId": "pc1-1",
        "tool": "read_settings",
        "running": False,
        "note": "主线还没有内容",
        "ok": True,
        "label": "先读主线设定",
        "args": '{"area": "premise"}',
        "apiCalls": [{"op": "assistant_step", "model": "m", "ms": 12, "tokens_in": 1, "tokens_out": 2, "ok": True}],
    }
    assert process[2]["text"] == "再顺手看看卷纲"


def test_unfinished_step_marked_interrupted_on_finalize(monkeypatch):
    """步已开始但没等到 step_end（停止/断连）→ 落盘标 interrupted，回看如实。"""
    bid = _mk_book()
    _patch_loop(
        monkeypatch,
        [
            {"type": "run_start", "runId": "ic1"},
            {"type": "step_start", "runId": "ic1", "stepId": "ic1-1", "tool": "draft_volume_expand"},
        ],
        crash_after=2,
    )
    events = _read_sse(bid, "铺一下")
    assert any(e.get("type") == "error" for e in events), events

    r = client.get(
        f"/api/novels/{bid}/assistant/session?thread=ch:og",
        headers={"Authorization": "Bearer tok-chathttp"},
    )
    assistant = next(m for m in r.json()["messages"] if m["role"] == "assistant")
    item = assistant["payload"]["process"][0]
    assert item["kind"] == "tool"
    assert item["running"] is False and item["interrupted"] is True


def test_system_prefix_stable_and_progress_in_user_tail(monkeypatch):
    """c-agent-prompt-cache：系统前缀只放稳定书情（书名/题材），动态进度拼在
    当前 user 消息尾部——进度变化不废前缀缓存。"""
    import assistant.router as router_mod

    bid = _mk_book()
    rec = _patch_loop(monkeypatch, [
        {"type": "run_start", "runId": "pc1"},
        {"type": "narration", "text": "好。"},
        {"type": "run_end", "runId": "pc1", "steps": 0, "toolCalls": 0, "degraded": False, "error": ""},
    ])
    captured: dict = {}
    orig_init = router_mod.AgentLoop.__init__

    def _capture_init(self, **kwargs):
        captured.update(kwargs)
        orig_init(self, **kwargs)

    monkeypatch.setattr(router_mod.AgentLoop, "__init__", _capture_init)
    _read_sse(bid, "看看主线")

    system = str(captured.get("system") or "")
    assert "书名：" in system
    assert "进度：" not in system, "动态进度不得进系统前缀"
    user_input = str(rec["runs"][0]["input"])
    assert "进度：空书" in user_input, "动态进度应拼在当前 user 消息尾部"


class _ReminderClient(_FakeClient):
    def supports_latest_reminder(self) -> bool:
        return True


def test_router_sets_latest_reminder_for_deepseek(monkeypatch):
    """c-agent-latest-reminder：能力位为真时 router 生成当前日期提醒并进 LoopConfig。"""
    import re

    import assistant.router as router_mod

    bid = _mk_book()
    _patch_loop(
        monkeypatch,
        [
            {"type": "run_start", "runId": "lr1"},
            {"type": "narration", "text": "好。"},
            {"type": "run_end", "runId": "lr1", "steps": 0, "toolCalls": 0,
             "degraded": False, "error": ""},
        ],
        client_factory=_ReminderClient,
    )
    captured: dict = {}
    orig_init = router_mod.AgentLoop.__init__

    def _capture_init(self, **kwargs):
        captured.update(kwargs)
        orig_init(self, **kwargs)

    monkeypatch.setattr(router_mod.AgentLoop, "__init__", _capture_init)
    _read_sse(bid, "看看主线")

    reminder = captured["config"].latest_reminder
    assert "latest_reminder" in str(captured.get("system") or "")
    assert re.match(
        r"^\d{4}-\d{2}-\d{2},星期[一二三四五六日],,App,中文$", reminder
    ), reminder


def test_plan_events_persist_and_latest_wins(monkeypatch):
    """计划事件走真实 route/queue/落盘：SSE 下发＋会话回看取最新快照。"""
    bid = _mk_book()
    plan_live = {
        "id": "pl1",
        "items": [
            {"id": "a", "title": "主线前提", "status": "done"},
            {"id": "b", "title": "主角陆沉", "status": "active"},
        ],
        "updatedAt": "2026-11-21T10:00:00+08:00",
    }
    plan_final = {
        "id": "pl1",
        "items": [
            {"id": "a", "title": "主线前提", "status": "done"},
            {"id": "b", "title": "主角陆沉", "status": "pending"},
        ],
        "updatedAt": "2026-11-21T10:00:01+08:00",
    }
    _patch_loop(
        monkeypatch,
        [
            {"type": "run_start", "runId": "fx2"},
            {"type": "plan", "plan": plan_live, "runId": "fx2"},
            {"type": "narration", "text": "计划列好了，第一件做完了。"},
            {
                "type": "run_end",
                "runId": "fx2",
                "steps": 0,
                "toolCalls": 0,
                "degraded": False,
                "error": "",
                "plan": plan_final,
                "planIncomplete": 1,
            },
        ],
    )
    events = _read_sse(bid, "三件事")
    plans = [e for e in events if e.get("type") == "plan"]
    assert len(plans) == 1 and plans[0]["plan"]["id"] == "pl1"
    r = client.get(
        f"/api/novels/{bid}/assistant/session?thread=ch:og",
        headers={"Authorization": "Bearer tok-chathttp"},
    )
    assert r.status_code == 200
    rows = [m for m in r.json().get("messages", []) if m.get("cardKind") == "plan"]
    assert rows, "计划快照必须逐步落盘"
    latest = rows[-1]["payload"]["plan"]
    assert latest["items"][1]["status"] == "pending"
    assert rows[-1]["role"] == "event" and rows[-1]["content"] == ""


def test_disconnect_finalizes_plan_snapshot(monkeypatch):
    """断连/停止没有 run_end：_finalize 补最终快照，active 降为 pending。"""
    bid = _mk_book()
    live = {
        "id": "pl3",
        "items": [{"id": "a", "title": "主线前提", "status": "active"}],
        "updatedAt": "2026-11-21T10:00:00+08:00",
    }
    _patch_loop(
        monkeypatch,
        [
            {"type": "run_start", "runId": "dc1"},
            {"type": "plan", "plan": live, "runId": "dc1"},
            {"type": "narration", "text": "我先做这一件。"},
            # 故意不发 run_end——模拟断连/停止收口
        ],
    )
    _read_sse(bid, "做一下")
    deadline = time.time() + 3
    latest = None
    while time.time() < deadline:
        r = client.get(
            f"/api/novels/{bid}/assistant/session?thread=ch:og",
            headers={"Authorization": "Bearer tok-chathttp"},
        )
        rows = [m for m in r.json().get("messages", []) if m.get("cardKind") == "plan"]
        if rows:
            latest = rows[-1]["payload"]["plan"]
            if latest["items"][0]["status"] == "pending":
                break
        time.sleep(0.05)
    assert latest is not None, "断连也必须留下计划快照"
    assert latest["items"][0]["status"] == "pending"


def test_write_gate_invalid_field_no_card_and_no_wait(monkeypatch):
    """非法字段不弹卡、不等批复（#1106 port 钉，review P1）。

    PreviewRejected 在异步闸（#1105）下必须 yield 裸 gate_result＋return：
    - 写成 `return [...]` ＝ async generator 里 SyntaxError（文本合并零冲突也
      炸，实编译实锤）；
    - 漏 yield 或误等批复 ＝ 本用例挂起（_read_sse 30s 超时即红）。
    语义：拒绝语回喂模型/作家，permission_required 永不出现在流里。"""
    bid = _mk_book()
    import ai_client
    import ai_state
    import assistant.router as router_mod

    async def _fake_get_client(project_id):
        return _FakeClient()

    async def _fake_has_key(db, user_id):
        return True

    async def _fake_run(self, user_input, prime=None):
        yield {"type": "run_start", "runId": "gx1"}
        async for ev in self.gate_fn(
            "write_settings_field",
            {"stype": "story", "field": "premise", "value": "不该弹卡的前提"},
        ):
            yield ev
        yield {
            "type": "run_end",
            "runId": "gx1",
            "steps": 0,
            "toolCalls": 0,
            "degraded": False,
            "error": "",
        }

    monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_get_client)
    monkeypatch.setattr(ai_state, "user_has_ai_key", _fake_has_key)
    monkeypatch.setattr(router_mod.AgentLoop, "run", _fake_run)

    events = _read_sse(bid, "把 premise 写进去", {"page": "set:genre", "thread": "set:genre"})
    types = [e.get("type") for e in events]
    assert "run_end" in types, f"流未收口：{types}"
    assert "permission_required" not in types, f"非法字段不该弹卡：{types}"
    result = next(e for e in events if e.get("type") == "gate_result")
    assert result.get("approved") is False
    assert "premise" in str(result.get("refusal") or "")
    assert types.index("gate_result") < types.index("run_end")
