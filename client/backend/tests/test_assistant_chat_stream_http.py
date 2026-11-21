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


def _patch_loop(monkeypatch, events, crash_after: int | None = None):
    """替换 AgentLoop.run 为脚本化事件流；crash_after=N 表示第 N 个事件后抛。"""
    import ai_state
    import assistant.router as router_mod

    async def _fake_get_client(project_id):
        return _FakeClient()

    async def _fake_has_key(db, user_id):
        return True

    async def _fake_run(self, user_input, prime=None):
        yielded = 0
        for ev in events:
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


def _read_sse(bid: str, message: str) -> list[dict]:
    """带超时读取 SSE 全流——永挂形态超时即失败（回归信号）。"""

    def _consume() -> list[dict]:
        out: list[dict] = []
        with client.stream(
            "POST",
            f"/api/novels/{bid}/assistant/chat",
            json={"message": message, "page": "ch:og", "thread": "ch:og"},
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
        async for ev in self.gate_fn(
            "write_settings_field",
            {"stype": "story", "field": "premise", "value": "授权卡先到的回归前提"},
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
