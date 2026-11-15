"""AgentLoop native 分支契约（c-agent-harness tasks 5.1/5.2/5.4）。

假 native 客户端（脚本化 StreamEvent(tool_calls) 流）——覆盖：路由（自动/env
强制）／单工具→收口／同轮多调用批／未知工具回喂自纠／gate 拒绝回喂／native
外发形态（tool_calls+tool 行原样下发）／GeneratorExit 干净关闭／墙钟收尾。
文本协议分支的行为锚点在 test_assistant_loop.py（原样保留）。
"""

import json

import pytest

import ai_client as ai_client_mod

from assistant import loop as loop_mod
from assistant.loop import AgentLoop, LoopConfig
from assistant.tools import Tool, ToolResult


class FakeNativeClient:
    """脚本化 native 客户端：每轮 = (正文, [tool_calls])；supports_native_tools=True。"""

    def __init__(self, turns: list[tuple[str, list[dict]]]):
        self.turns = list(turns)
        self.calls: list[dict] = []

    def supports_native_tools(self) -> bool:
        return True

    async def chat_stream(self, **kwargs):
        from ai_client import StreamEvent

        text, calls = (
            self.turns.pop(0) if self.turns else ("先到这里。", [])
        )
        self.calls.append(
            {"messages": kwargs.get("messages"), "tools": kwargs.get("tools")}
        )
        yield StreamEvent(thinking="嗯")
        if calls:
            yield StreamEvent(tool_calls=calls)
        yield StreamEvent(text=text, is_done=True, tokens=10, tokens_in=20)

    async def chat(self, **kwargs):
        self.calls.append({"compact": kwargs.get("messages")})
        return "压缩摘要"


def _tc(idx, name, args: dict, call_id=None):
    return {
        "id": call_id or f"call_{idx}",
        "name": name,
        "arguments": args,
        "args_raw": json.dumps(args, ensure_ascii=False),
    }


def _fake_tool(monkeypatch, summary="frontier 章：第1章（待写）"):
    async def fake_run_tool(ctx, name, args):
        return ToolResult(ok=True, summary=summary)

    fake = Tool(name="read_progress", kind="read", description="读进度", fn=fake_run_tool)
    monkeypatch.setattr(
        loop_mod, "get_tool", lambda n: fake if n == "read_progress" else None
    )
    monkeypatch.setattr(loop_mod, "run_tool", fake_run_tool)
    return fake


@pytest.mark.asyncio
async def test_auto_route_and_native_step(monkeypatch):
    """路由自动判定＋单工具步→自然收口：native 全链最小闭环。"""
    _fake_tool(monkeypatch)
    client = FakeNativeClient(
        [
            ("我先看看进度。", [_tc(0, "read_progress", {})]),
            ("书还在第1章待写。", []),
        ]
    )
    loop = AgentLoop(
        client=client, system="sys", transcript=[], tool_ctx=None, config=LoopConfig()
    )
    assert loop.harness == "native"  # supports_native_tools → 自动 native
    events = [e async for e in loop.run("写到哪了？")]
    kinds = [e["type"] for e in events]
    assert kinds[0] == "run_start" and kinds[-1] == "run_end"
    assert "step_start" in kinds and "step_end" in kinds
    assert loop.result.final_reply == "书还在第1章待写。"
    assert loop.result.degraded is False
    assert loop.result.trace == [{"tool": "read_progress", "ok": True, "note": "frontier 章：第1章（待写）"}]
    # tools 下发供应商（每轮都带）
    assert client.calls[0]["tools"], "native 轮必须下发工具 schema"
    # 转写为 openai 原生形态：assistant(tool_calls) + role=tool 结果行
    assert any(m.get("tool_calls") for m in loop.transcript)
    assert any(m["role"] == "tool" for m in loop.transcript)


@pytest.mark.asyncio
async def test_native_outbound_shapes_preserved(monkeypatch):
    """native 外发形态：第二轮 messages 必须携带 assistant.tool_calls 与 tool 行
    （tool_call_id 对齐）——API 校验链所需。"""
    _fake_tool(monkeypatch)
    client = FakeNativeClient(
        [
            ("", [_tc(0, "read_progress", {"x": 1})]),
            ("好的。", []),
        ]
    )
    loop = AgentLoop(
        client=client, system="sys", transcript=[], tool_ctx=None, config=LoopConfig()
    )
    _ = [e async for e in loop.run("hi")]
    assert len(client.calls) == 2
    second = client.calls[1]["messages"]
    roles = [m["role"] for m in second]
    assert roles == ["user", "assistant", "tool"]  # native 口径：tool 行原样保留
    asst = second[1]
    assert asst["tool_calls"][0]["function"]["name"] == "read_progress"
    assert json.loads(asst["tool_calls"][0]["function"]["arguments"]) == {"x": 1}
    assert second[2]["tool_call_id"] == asst["tool_calls"][0]["id"]
    assert "frontier" in second[2]["content"]


@pytest.mark.asyncio
async def test_native_multi_call_batch(monkeypatch):
    """同轮多调用批：逐个执行→逐行 tool 结果回填（无并行批，openworker 同款串行）。"""
    _fake_tool(monkeypatch, summary="ok结果")
    client = FakeNativeClient(
        [
            ("", [_tc(0, "read_progress", {}), _tc(1, "read_progress", {})]),
            ("两处都看过了。", []),
        ]
    )
    loop = AgentLoop(
        client=client, system="sys", transcript=[], tool_ctx=None, config=LoopConfig()
    )
    events = [e async for e in loop.run("hi")]
    assert loop.result.tool_calls == 2
    assert [e["type"] for e in events].count("step_end") == 2
    tool_rows = [m for m in loop.transcript if m.get("role") == "tool"]
    assert len(tool_rows) == 2
    ids = [m["tool_call_id"] for m in tool_rows]
    assert ids == ["call_0", "call_1"]


@pytest.mark.asyncio
async def test_native_unknown_tool_feed_back(monkeypatch):
    """未知工具：tool 结果行回喂错误→模型自纠收口（native 协议语义；文本协议
    的「按 final 降级」口径不适用）。"""
    _fake_tool(monkeypatch)
    client = FakeNativeClient(
        [
            ("", [_tc(0, "nuke_everything", {})]),
            ("那个工具确实没有，我直接说：做不了。", []),
        ]
    )
    loop = AgentLoop(
        client=client, system="sys", transcript=[], tool_ctx=None, config=LoopConfig()
    )
    events = [e async for e in loop.run("hi")]
    assert loop.result.final_reply == "那个工具确实没有，我直接说：做不了。"
    # 未产出 step 事件（没假装调过），回喂行落转写
    assert not [e for e in events if e["type"] == "step_start"]
    row = next(m for m in loop.transcript if m.get("role") == "tool")
    assert "不在工具箱" in row["content"]


@pytest.mark.asyncio
async def test_native_denied_gate_feed_back(monkeypatch):
    """gate 拒绝：refusal 走叙述＋[denied] tool 行回喂（模型可改道或收口）。"""
    _fake_tool(monkeypatch)

    async def deny_gate(tool, args):
        return [{"type": "gate", "approved": False, "refusal": "作家没有授权这个操作。"}]

    client = FakeNativeClient(
        [
            ("", [_tc(0, "read_progress", {})]),
            ("好吧，不做了。", []),
        ]
    )
    loop = AgentLoop(
        client=client, system="sys", transcript=[], tool_ctx=None,
        config=LoopConfig(), gate_fn=deny_gate,
    )
    events = [e async for e in loop.run("hi")]
    assert any(e["type"] == "gate" for e in events)
    assert any(e["type"] == "narration" and e["text"] == "作家没有授权这个操作。" for e in events)
    row = next(m for m in loop.transcript if m.get("role") == "tool")
    assert row["content"].startswith("[denied]")
    assert loop.result.tool_calls == 0  # 被拒不计数


@pytest.mark.asyncio
async def test_routing_force_overrides(monkeypatch):
    """env 强制路由（tasks 4.1）：ASSISTANT_HARNESS=native 把文本客户端抬进
    native；=text 把 native 客户端压回 text。"""
    monkeypatch.setenv("ASSISTANT_HARNESS", "native")
    plain = loop_mod.FakeClient if hasattr(loop_mod, "FakeClient") else None
    client = _PlainClient()
    loop = AgentLoop(client=client, system="s", transcript=[], tool_ctx=None, config=LoopConfig())
    assert loop.harness == "native"
    monkeypatch.setenv("ASSISTANT_HARNESS", "text")
    native_client = FakeNativeClient([])
    loop2 = AgentLoop(client=native_client, system="s", transcript=[], tool_ctx=None, config=LoopConfig())
    assert loop2.harness == "text"


class _PlainClient:
    """无 supports_native_tools 的最小文本客户端（模拟旧 FakeClient 路由形态）。"""

    def supports_native_tools(self) -> bool:
        return False

    async def chat_stream(self, **kwargs):
        from ai_client import StreamEvent

        yield StreamEvent(text="好。", is_done=True, tokens=1, tokens_in=1)

    async def chat(self, **kwargs):
        return "摘要"


@pytest.mark.asyncio
async def test_native_wall_clock_tail(monkeypatch):
    """墙钟到点：native 分支同样以收尾话术结束＋run_end（纪律两模式同构）。"""
    _fake_tool(monkeypatch)

    async def slow_tool(ctx, name, args):
        import asyncio

        await asyncio.sleep(0.05)
        return ToolResult(ok=True, summary="慢结果")

    fake = Tool(name="read_progress", kind="read", description="读进度", fn=slow_tool)
    monkeypatch.setattr(loop_mod, "get_tool", lambda n: fake)
    monkeypatch.setattr(loop_mod, "run_tool", slow_tool)
    client = FakeNativeClient(
        [
            ("", [_tc(0, "read_progress", {})]),
            ("", [_tc(1, "read_progress", {})]),
            ("", [_tc(2, "read_progress", {})]),
        ]
    )
    loop = AgentLoop(
        client=client, system="sys", transcript=[], tool_ctx=None,
        config=LoopConfig(wall_clock=0.08),
    )
    events = [e async for e in loop.run("hi")]
    texts = [e["text"] for e in events if e["type"] == "narration"]
    assert any("跑得太久" in t for t in texts)
    assert [e["type"] for e in events][-1] == "run_end"


@pytest.mark.asyncio
async def test_native_generator_exit_clean(monkeypatch):
    """消费端断开（aclose）：GeneratorExit 干净关闭，run_end 不发（断开态），
    已执行的工具行留转写（半截落库由调用方接管）。"""
    _fake_tool(monkeypatch)

    async def slow_tool(ctx, name, args):
        import asyncio

        await asyncio.sleep(0.03)
        return ToolResult(ok=True, summary="半截")

    fake = Tool(name="read_progress", kind="read", description="读进度", fn=slow_tool)
    monkeypatch.setattr(loop_mod, "get_tool", lambda n: fake)
    monkeypatch.setattr(loop_mod, "run_tool", slow_tool)
    client = FakeNativeClient(
        [
            ("", [_tc(0, "read_progress", {})]),
            ("", [_tc(1, "read_progress", {})]),
        ]
    )
    loop = AgentLoop(
        client=client, system="sys", transcript=[], tool_ctx=None, config=LoopConfig()
    )
    gen = loop.run("hi")
    got = []
    async for ev in gen:
        got.append(ev)
        if ev["type"] == "step_end":
            break  # 第一步完成后断开
    await gen.aclose()
    # 断开点＝step_end yield 挂起：assistant(tool_calls) 行已落转写（崩溃留轨迹）；
    # tool 结果行在 step_end 消费后才追加（与 text 分支断开语义一致，不在此断言）
    assert any(m.get("tool_calls") for m in loop.transcript)
    assert not any(e["type"] == "run_end" for e in got)


@pytest.mark.asyncio
async def test_native_compact_trigger_keeps_native_shapes(monkeypatch):
    """native 压缩触发：_maybe_compact 按 native 形态装配——tool_calls/tool 行
    进摘要 span（compact 的 _iter_tool_calls 原生认识），状态经 on_compaction
    持久化，收口不受影响。"""
    _fake_tool(monkeypatch)
    client = FakeNativeClient(
        [
            ("", [_tc(0, "read_progress", {})]),
            ("看完了，主线还稳。", []),
        ]
    )
    saved: list = []

    async def _save(st):
        saved.append(st)

    loop = AgentLoop(
        client=client, system="sys",
        transcript=[
            {"role": "user", "content": "之前的讨论：" + "背景" * 3000},
        ],
        tool_ctx=None, config=LoopConfig(),
        on_compaction=_save,
        context_window=2000,  # 极小窗口逼出压缩判定
    )
    events = [e async for e in loop.run("继续看进度")]
    assert saved, "压缩状态必须持久化"
    assert loop.compaction_state is saved[0]
    # 压缩后 native 循环照常走完：工具步＋自然收口（外发形态经 apply_to_outbound
    # 边界切割后仍合法——remap/边界护栏在 compact 模块自测）
    assert loop.result.tool_calls == 1
    kinds = [e["type"] for e in events]
    assert kinds.count("step_end") == 1
    assert kinds[-1] == "run_end"
    assert loop.result.final_reply == "看完了，主线还稳。"
