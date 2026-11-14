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
        self.calls.append({"messages": kwargs.get("messages")})
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
        config=LoopConfig(max_steps=4),
    )
    events = [e async for e in loop.run("帮我看看主线")]
    kinds = [e["type"] for e in events]
    assert kinds[0] == "run_start"
    assert "thinking" in kinds
    assert "narration" in kinds
    assert kinds[-1] == "run_end"
    assert loop.result.final_reply == "主线还差一句结局。"
    assert loop.result.degraded is False
    # 转写追加了 user 输入与 assistant 输出
    assert loop.transcript[0]["role"] == "user"
    assert loop.transcript[-1]["role"] == "assistant"


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
        config=LoopConfig(max_steps=4),
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
        config=LoopConfig(max_steps=4),
    )
    events = [e async for e in loop.run("炸了它")]
    # 工具箱里没有 → 按收口降级，不假装调过
    assert not any(e["type"] == "step_start" for e in events)
    assert loop.result.tool_calls == 0
    assert loop.result.final_reply  # 有收口话术


@pytest.mark.asyncio
async def test_degraded_after_retry(monkeypatch):
    # 两步都是坏输出：第一步触发纠错重试，第二步仍坏 → degraded 收口
    client = FakeClient(["这不是JSON，是闲聊。", "还是闲聊。"])
    loop = AgentLoop(
        client=client,
        system="sys",
        transcript=[],
        tool_ctx=None,
        config=LoopConfig(max_steps=4),
    )
    events = [e async for e in loop.run("随便说点什么")]
    assert loop.result.degraded is True
    assert any(e["type"] == "narration" for e in events)
    # 纠错 nudge 进过转写（两次模型调用）
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_max_steps_exhaustion_tail(monkeypatch):
    async def fake_run_tool(ctx, name, args):
        return ToolResult(ok=True, summary="ok")

    fake = Tool(name="read_progress", kind="read", args_hint="{}", description="读进度", fn=fake_run_tool)
    monkeypatch.setattr(loop_mod, "get_tool", lambda n: fake)
    monkeypatch.setattr(loop_mod, "run_tool", fake_run_tool)

    client = FakeClient([_tool("read_progress", {})] * 5)  # 每步都是工具动作
    loop = AgentLoop(
        client=client,
        system="sys",
        transcript=[],
        tool_ctx=None,
        config=LoopConfig(max_steps=3, max_tool_calls=99),
    )
    events = [e async for e in loop.run("一直读下去")]
    tail = next(e for e in events if e["type"] == "narration" and "步数用完" in e.get("text", ""))
    assert tail
    assert loop.result.steps == 3
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
        config=LoopConfig(max_steps=4),
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
        config=LoopConfig(max_steps=4),
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
    loop = AgentLoop(client=client, system="sys", transcript=[], tool_ctx=None, config=LoopConfig(max_steps=4))
    events = [e async for e in loop.run("铺一下")]

    step_end = next(e for e in events if e["type"] == "step_end")
    calls = step_end.get("apiCalls")
    assert calls and calls[0]["op"] == "draft_expand" and calls[0]["ok"] is True
    assert calls[0]["tokens_in"] == 9 and calls[0]["tokens_out"] == 4

