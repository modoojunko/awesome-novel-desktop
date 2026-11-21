"""AgentLoop 契约测试（c-writing-agent 批A 1.5）。

假客户端（脚本化 StreamEvent 流）＋monkeypatch 工具表——覆盖：final 收口／
工具步（step 事件＋轨迹＋观察写回）／degraded 降级／未知工具按 final 降级／
步数耗尽收尾／compact 触发持久化。护栏常量在 loop 模块级，测试用 config 覆盖。
"""

import logging
import time

import pytest

import ai_client as ai_client_mod
from assistant import loop as loop_mod
from assistant.loop import AgentLoop, LoopConfig
from assistant.tools import Tool, ToolResult


class FakeClient:
    """脚本化客户端：chat_stream 按 step 序吐文本；chat 兜 compact 摘要。"""

    def __init__(self, step_outputs: list[str], summary: str = "压缩摘要"):
        self.step_outputs = list(step_outputs)
        self.summary = summary
        self.calls: list[dict] = []

    async def chat_stream(self, **kwargs):
        from ai_client import StreamEvent

        text = self.step_outputs.pop(0) if self.step_outputs else (
            '{"thought": "收口", "action": "final", "reply": "先到这里。"}'
        )
        self.calls.append({
            "messages": kwargs.get("messages"),
            "thinking": kwargs.get("thinking"),
            "max_tokens": kwargs.get("max_tokens"),
        })
        # 思考先行一步，正文一条事件交付
        yield StreamEvent(thinking="我在想……")
        yield StreamEvent(text=text, is_done=True, tokens=10, tokens_in=20)

    async def chat(self, **kwargs):
        self.calls.append({"compact": kwargs.get("messages")})
        return self.summary


def _final(text: str) -> str:
    import json

    return json.dumps(
        {"thought": "收口", "action": "final", "tool": "", "args": {}, "reply": text},
        ensure_ascii=False,
    )


def _tool(name: str, args: dict) -> str:
    import json

    return json.dumps(
        {"thought": "干一票", "action": "tool", "tool": name, "args": args, "reply": ""},
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_final_reply_path():
    client = FakeClient([_final("主线还差一句结局。")])
    loop = AgentLoop(
        client=client,
        system="sys",
        transcript=[{"role": "user", "content": "帮我看看主线"}],
        tool_ctx=None,
        config=LoopConfig(),
    )
    events = [e async for e in loop.run("帮我看看主线")]
    kinds = [e["type"] for e in events]
    assert kinds[0] == "run_start"
    assert "thinking" in kinds
    # 旧版单 JSON 输出（本测试的 fake 脚本）＝批次交付，无 delta（哨兵流式另钉）
    assert "narration_delta" not in kinds
    assert kinds[-1] == "run_end"
    assert loop.result.final_reply == "主线还差一句结局。"
    assert loop.result.degraded is False
    # 转写追加了 user 输入与 assistant 输出
    assert loop.transcript[0]["role"] == "user"
    assert loop.transcript[-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_thinking_override_reaches_chat_stream():
    """c-agent-thinking-bubbles：底栏深度思考开关要透传到模型调用。

    None＝沿用配置；enabled/disabled＝显式按次覆盖（压过 API 配置）。
    """
    for override in (None, {"type": "enabled"}, {"type": "disabled"}):
        client = FakeClient([_final("好。")])
        loop = AgentLoop(
            client=client,
            system="sys",
            transcript=[{"role": "user", "content": "说句话"}],
            tool_ctx=None,
            config=LoopConfig(thinking=override),
        )
        _ = [e async for e in loop.run("说句话")]
        assert client.calls[0]["thinking"] == override


@pytest.mark.asyncio
async def test_tool_step_path_with_trace_and_observation(monkeypatch):
    async def fake_run_tool(ctx, name, args):
        assert name == "read_progress"
        return ToolResult(ok=True, summary="frontier 章：第1章（待写）")

    fake = Tool(
        name="read_progress", kind="read", args_hint="{}", description="读进度",
        fn=fake_run_tool,
    )
    monkeypatch.setattr(loop_mod, "get_tool", lambda n: fake if n == "read_progress" else None)
    monkeypatch.setattr(loop_mod, "run_tool", fake_run_tool)

    client = FakeClient([_tool("read_progress", {}), _final("书还在第1章待写。")])
    loop = AgentLoop(
        client=client,
        system="sys",
        transcript=[],
        tool_ctx=None,
        config=LoopConfig(),
    )
    events = [e async for e in loop.run("写到哪了？")]
    kinds = [e["type"] for e in events]
    assert "step_start" in kinds and "step_end" in kinds
    step_end = next(e for e in events if e["type"] == "step_end")
    assert step_end["tool"] == "read_progress"
    assert "第1章" in step_end["resultNote"]
    assert loop.result.trace == [
        {"tool": "read_progress", "ok": True, "note": "frontier 章：第1章（待写）"}
    ]
    # 观察行进转写（tool result 观察行）
    assert any(m["role"] == "user" and m["content"].startswith("[tool result]") for m in loop.transcript)
    # assistant 行带 _tool 元数据（compact 机械抽取用）
    assert any(m.get("_tool", {}).get("name") == "read_progress" for m in loop.transcript)
    assert loop.result.final_reply == "书还在第1章待写。"


@pytest.mark.asyncio
async def test_unknown_tool_falls_back_to_final():
    client = FakeClient([_tool("nuke_everything", {})])
    loop = AgentLoop(
        client=client,
        system="sys",
        transcript=[],
        tool_ctx=None,
        config=LoopConfig(),
    )
    events = [e async for e in loop.run("炸了它")]
    # 工具箱里没有 → 按收口降级，不假装调过
    assert not any(e["type"] == "step_start" for e in events)
    assert loop.result.tool_calls == 0
    assert loop.result.final_reply  # 有收口话术


@pytest.mark.asyncio
async def test_plain_text_finalizes_without_retry(monkeypatch):
    """v2 语义：无哨兵非 JSON＝模型直接回答，整段按 final 交付（不重试、
    不包降级外壳）；degraded 遥测标记协议未服从。"""
    client = FakeClient(["这不是JSON，是闲聊。"])
    loop = AgentLoop(
        client=client,
        system="sys",
        transcript=[],
        tool_ctx=None,
        config=LoopConfig(),
    )
    events = [e async for e in loop.run("随便说点什么")]
    assert loop.result.degraded is True
    assert loop.result.final_reply == "这不是JSON，是闲聊。"
    assert any(e["type"] == "narration" for e in events)
    # 纯文本即收口——纠错重试不再触发（一次模型调用）
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_degraded_after_retry(monkeypatch):
    """坏输出重试链仍在：哨兵＋烂尾部且无正文（真协议服从失败）→ 纠错重试
    一次，仍坏 → degraded 收口。"""
    bad = "===ACT===\n不是json"
    client = FakeClient([bad, "还是坏输出"])
    loop = AgentLoop(
        client=client,
        system="sys",
        transcript=[],
        tool_ctx=None,
        config=LoopConfig(),
    )
    events = [e async for e in loop.run("随便说点什么")]
    assert loop.result.degraded is True
    assert any(e["type"] == "narration" for e in events)
    # 纠错 nudge 进过转写（两次模型调用）
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_wall_clock_tail(monkeypatch):
    """boss 拍板 2026-11-15：SHALL NOT 设步数/工具次数上限——护栏只剩墙钟
    （到点明确收尾话术、已产出卡保留）＋作家停止钮。"""
    async def fake_run_tool(ctx, name, args):
        import asyncio as _asyncio

        await _asyncio.sleep(0.01)  # 每步 10ms——墙钟必然在脚本耗尽前截停
        return ToolResult(ok=True, summary="ok")

    fake = Tool(name="read_progress", kind="read", args_hint="{}", description="读进度", fn=fake_run_tool)
    monkeypatch.setattr(loop_mod, "get_tool", lambda n: fake)
    monkeypatch.setattr(loop_mod, "run_tool", fake_run_tool)

    # 异参序列（去重守卫会拦同参连调——墙钟用例要每步真执行，每步 10ms×200）
    client = FakeClient([_tool("read_progress", {"n": i}) for i in range(200)])
    loop = AgentLoop(
        client=client,
        system="sys",
        transcript=[],
        tool_ctx=None,
        config=LoopConfig(wall_clock=0.15),
    )
    events = [e async for e in loop.run("一直读下去")]
    tail = next(e for e in events if e["type"] == "narration" and "跑得太久" in e.get("text", ""))
    assert tail
    assert loop.result.steps > 3  # 不设步数上限——步数只到墙钟为止
    assert kinds_last(events) == "run_end"


def kinds_last(events):
    return events[-1]["type"]


@pytest.mark.asyncio
async def test_compaction_triggered_and_persisted(monkeypatch):
    # 强制触发 compact；complete_fn 走 FakeClient.chat
    monkeypatch.setattr(loop_mod.compact_mod, "should_compact", lambda *a, **k: True)
    saved: dict = {}

    async def on_compaction(state):
        saved["state"] = state

    client = FakeClient([_final("好。")], summary="这是压缩后的摘要。")
    loop = AgentLoop(
        client=client,
        system="sys",
        transcript=[{"role": "user", "content": "历史一"}, {"role": "assistant", "content": "历史一答"}],
        tool_ctx=None,
        config=LoopConfig(),
        on_compaction=on_compaction,
        context_window=10,  # 窗口极小→触发线极低→边界落在首轮之后
    )
    events = [e async for e in loop.run("继续")]
    assert "state" in saved
    assert saved["state"].summary_text == "这是压缩后的摘要。"
    assert events[0]["type"] == "run_start"


@pytest.mark.asyncio
async def test_generator_close_is_clean():
    """消费端中途断开（aclose，review 判例 2026-11-14）：finally 不得在
    GeneratorExit 期间再 yield（否则 RuntimeError ignored-GeneratorExit）。"""
    client = FakeClient([_final("好。")])
    loop = AgentLoop(
        client=client,
        system="sys",
        transcript=[],
        tool_ctx=None,
        config=LoopConfig(),
    )
    agen = loop.run("读到一半就关")
    first = await agen.asend(None)
    assert first["type"] == "run_start"
    # 主动关闭——修复前此处抛 RuntimeError("async generator ignored GeneratorExit")
    await agen.aclose()

@pytest.mark.asyncio
async def test_step_end_carries_api_calls(monkeypatch):
    """boss 拍板 2026-11-15：反馈流像 coding agent——本步内的模型 API 调用
    （归集器记录）随 step_end.apiCalls 全量可见；读类无模型调用则不带。"""
    async def fake_run_tool(ctx, name, args):
        # 工具核心不自行 begin/drain——loop 已 begin，同任务内 _log_call 自归集
        class _C:
            logger = logging.getLogger("t")
            _base_url = "https://e.com/v1"

        ai_client_mod.AIClient._log_call(
            _C(), "draft_expand", "glm-5.3", time.perf_counter(), tokens_in=9, tokens_out=4
        )
        from assistant.tools import ToolResult

        return ToolResult(ok=True, summary="出卡")

    fake = Tool(name="draft_volume_expand", kind="card", args_hint="{}", description="d", fn=fake_run_tool)
    monkeypatch.setattr(loop_mod, "get_tool", lambda n: fake)
    monkeypatch.setattr(loop_mod, "run_tool", fake_run_tool)

    client = FakeClient([_tool("draft_volume_expand", {}), _final("好")])
    loop = AgentLoop(client=client, system="sys", transcript=[], tool_ctx=None, config=LoopConfig())
    events = [e async for e in loop.run("铺一下")]

    step_end = next(e for e in events if e["type"] == "step_end")
    calls = step_end.get("apiCalls")
    assert calls and calls[0]["op"] == "draft_expand" and calls[0]["ok"] is True
    assert calls[0]["tokens_in"] == 9 and calls[0]["tokens_out"] == 4



# ── 哨兵分节流式（c-agent-chat-memory 批2） ─────────────────────────


class _ChunkedClient:
    """逐小片吐文本的假客户端（模拟 token 级流）。"""

    def __init__(self, full: str, chunk: int = 3):
        self._full = full
        self._chunk = chunk
        self.calls = 0

    async def chat_stream(self, **kwargs):
        from ai_client import StreamEvent

        s = self._full
        for i in range(0, len(s), self._chunk):
            yield StreamEvent(text=s[i : i + self._chunk])
        yield StreamEvent(text="", is_done=True, tokens=10, tokens_in=20)

    async def chat(self, **kwargs):
        return "压缩摘要"


@pytest.mark.asyncio
async def test_sentinel_streaming_deltas_are_narration_only():
    """哨兵前逐片直通；哨兵与动作 JSON 永不出现在任何 narration_delta。"""
    full = (
        "我先讲两句给你听。\n第二行也在流式。\n"
        "===ACT===\n"
        '{"action": "final"}'
    )
    loop = AgentLoop(
        client=_ChunkedClient(full),
        system="sys",
        transcript=[{"role": "user", "content": "答我"}],
        tool_ctx=None,
        config=LoopConfig(),
    )
    deltas = []
    async for e in loop.run("答我"):
        if e["type"] == "narration_delta":
            deltas.append(e["text"])
    joined = "".join(deltas)
    assert "===ACT===" not in joined
    assert '"action"' not in joined
    assert joined.startswith("我先讲两句给你听。")


@pytest.mark.asyncio
async def test_legacy_pure_json_leaks_nothing_as_delta():
    """旧版纯 JSON 输出（提示词包未升级）：一字 delta 不漏（批次交付同旧口径）。"""
    import json as _json

    full = _json.dumps(
        {"thought": "收口", "action": "final", "reply": "旧协议整段交付。"},
        ensure_ascii=False,
    )
    loop = AgentLoop(
        client=_ChunkedClient(full),
        system="sys",
        transcript=[{"role": "user", "content": "答我"}],
        tool_ctx=None,
        config=LoopConfig(),
    )
    deltas = []
    async for e in loop.run("答我"):
        if e["type"] == "narration_delta":
            deltas.append(e["text"])
    assert deltas == []
    assert loop.result.final_reply == "旧协议整段交付。"


class _InfiniteStreamClient:
    """永不收口的流式假客户端（取消语义测试用）。"""

    def __init__(self) -> None:
        self.chunks = 0

    async def chat_stream(self, **kwargs):
        from ai_client import StreamEvent

        while True:
            self.chunks += 1
            yield StreamEvent(text=f"第{self.chunks}片。")
            await __import__("asyncio").sleep(0.01)

    async def chat(self, **kwargs):
        return "压缩摘要"


@pytest.mark.asyncio
async def test_cancel_event_stops_run_mid_stream():
    """停止/打断协同取消：事件置位后循环在最近 chunk 检查点收口——
    收口话术照发、interrupted 标记为真、run_end 正常落（已产出保留）。"""
    import asyncio as _asyncio

    cancel_event = _asyncio.Event()
    client = _InfiniteStreamClient()
    loop = AgentLoop(
        client=client,
        system="sys",
        transcript=[{"role": "user", "content": "一直说下去"}],
        tool_ctx=None,
        config=LoopConfig(),
        cancel_event=cancel_event,
    )
    kinds: list[str] = []
    async for e in loop.run("一直说下去"):
        kinds.append(e["type"])
        if client.chunks >= 3:
            cancel_event.set()
    assert "narration" in kinds
    assert kinds[-1] == "run_end"
    assert loop.result.interrupted is True
    assert client.chunks < 50  # 没有跑飞


@pytest.mark.asyncio
async def test_no_cancel_event_runs_normally():
    """未置位取消＝行为与旧口径一致（final 收口、interrupted 恒 False）。"""
    loop = AgentLoop(
        client=FakeClient([_final("正常收口。")]),
        system="sys",
        transcript=[{"role": "user", "content": "答我"}],
        tool_ctx=None,
        config=LoopConfig(),
    )
    async for _ in loop.run("答我"):
        pass
    assert loop.result.interrupted is False
    assert loop.result.final_reply == "正常收口。"


class _SlowFirstChunkClient:
    """首 chunk 前长等待（慢 TTFB 桩——停止必须打断等待本身）。"""

    def __init__(self) -> None:
        self.chunks = 0

    async def chat_stream(self, **kwargs):
        import asyncio as _a

        from ai_client import StreamEvent

        await _a.sleep(3)  # 慢桩窗口
        self.chunks += 1
        yield StreamEvent(text="第一片。")
        while True:
            self.chunks += 1
            yield StreamEvent(text="后续片。")
            await _a.sleep(0.01)

    async def chat(self, **kwargs):
        return "压缩摘要"


@pytest.mark.asyncio
async def test_cancel_interrupts_slow_ttfb_wait():
    """停止打断「等模型首 chunk」的等待本身——3s 慢桩窗口内收口（<1.5s）。"""
    import asyncio as _asyncio2
    import time as _time

    cancel_event = _asyncio2.Event()
    loop = AgentLoop(
        client=_SlowFirstChunkClient(),
        system="sys",
        transcript=[{"role": "user", "content": "慢慢来"}],
        tool_ctx=None,
        config=LoopConfig(),
        cancel_event=cancel_event,
    )
    t0 = _time.monotonic()
    kinds: list[str] = []
    async for e in loop.run("慢慢来"):
        kinds.append(e["type"])
        if not cancel_event.is_set():
            cancel_event.set()  # 首个事件（run_start）后立即停止
    elapsed = _time.monotonic() - t0
    assert elapsed < 1.5, f"停止未打断慢等待（{elapsed:.2f}s）"
    assert "narration" in kinds
    assert loop.result.interrupted is True


@pytest.mark.asyncio
async def test_final_streamed_tail_completion_delta():
    """收口尾巴补发（c-agent-narration-tail-loss）：stream_slice 在 `{` 冻结，
    扣尾窗不进 delta；收口时未流部分 MUST 补发 delta——否则 dock（seenDelta
    去重吞整段 narration）显示缺尾（实锤：存档完整、界面缺尾 8 字）。"""
    narration = (
        "就一个卡点：第 7 章到底算完了没。正文 4,199 字、未归档。"
        "示例含 { 花括号冻结点，尾巴你说走哪条，我跟着动。"
    )
    full = narration + "\n===ACT===\n" + _final(narration)
    client = FakeClient([full])
    loop = AgentLoop(
        client=client,
        system="sys",
        transcript=[{"role": "user", "content": "现在我要做什么"}],
        tool_ctx=None,
        config=LoopConfig(),
    )
    events = [e async for e in loop.run("现在我要做什么")]
    deltas = "".join(e["text"] for e in events if e["type"] == "narration_delta")
    narrations = [e["text"] for e in events if e["type"] == "narration"]
    # 冻结点在叙述体内的 `{`——流式 delta 停在冻结点；收口补发未流尾巴到整段
    assert deltas == narration, f"delta 拼接应等于完整叙述：{deltas!r}"
    # 整段 narration 事件照发（协议兼容；dock 去重口径不变）
    assert narration in narrations
    assert loop.result.final_reply == narration
