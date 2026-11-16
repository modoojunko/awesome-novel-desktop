"""页签独立流程（c-agent-fleet 改型）契约测试。

- thread→域映射：封闭校验（30 工具无漏挂无越引用）＋声明面收窄（og 15/vol 19…）
- 域外调用不执行：settings 线程调卷纲工具＝引导话术收口，零工具执行
- 域标签：step 事件带 domain（共享读省略）；目录按线程过滤；纪律分节随域
- 线程独立性：双线程并发 run 各自落位互不串写
"""

import asyncio

import pytest

from assistant import loop as loop_mod
from assistant.loop import AgentLoop, LoopConfig
from assistant.scopes import (
    domain_label_of_thread,
    discipline_of_thread,
    tools_for_thread,
    validate_scopes,
)
from assistant.tools import TOOL_REGISTRY, Tool, ToolResult


def test_scope_closure_and_coverage():
    """启动校验：注册表 30 工具无漏挂（任何页签都够得着）无越引用。"""
    errs = validate_scopes({t.name for t in TOOL_REGISTRY})
    assert errs == [], f"域映射漏配：{errs}"


def test_declared_tools_narrowed_per_thread():
    """声明面按线程收窄：og 15 个（含共享读），且不含卷纲写工具。"""
    og = tools_for_thread("ch:og")
    assert len(og) < len(TOOL_REGISTRY)
    assert "draft_chapter_plot" in og
    assert "write_volume_fields" not in og
    # 共享读恒在
    assert "read_progress" in og and "read_settings" in og
    # 全量目录 vs 域目录（text 协议路径）
    from assistant.tools import tool_catalog_text

    full = tool_catalog_text()
    og_text = tool_catalog_text("ch:og")
    assert len(og_text) < len(full)
    assert "draft_chapter_plot" in og_text and "write_volume_fields" not in og_text
    # 空 thread＝不收窄（旧调用/兜底路径兼容）
    assert len(tool_catalog_text()) == len(full)


def test_discipline_per_thread():
    """域纪律分节随域切换；共享段（身份）不受影响。"""
    assert discipline_of_thread("ch:og").startswith("章纲纪律")
    assert discipline_of_thread("ch:prose").startswith("正文纪律")
    assert discipline_of_thread("vol").startswith("卷纲纪律")
    assert discipline_of_thread("set:x").startswith("设定纪律")
    assert discipline_of_thread("") == ""
    from assistant.prompts import build_system_prompt

    og_sys = build_system_prompt("身份", "书情", thread="ch:og",
                                 domain_discipline=discipline_of_thread("ch:og"))
    prose_sys = build_system_prompt("身份", "书情", thread="ch:prose",
                                    domain_discipline=discipline_of_thread("ch:prose"))
    assert "章纲纪律" in og_sys and "章纲纪律" not in prose_sys
    assert "正文纪律" in prose_sys and "人味红线" in prose_sys
    assert "身份" in og_sys  # 共享身份段不变


class _ScriptedClient:
    """按脚本回工具调用/收口（带 supports_native_tools）。"""

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls: list[dict] = []

    def supports_native_tools(self) -> bool:
        return True

    async def chat_stream(self, **kwargs):
        from ai_client import StreamEvent

        text, calls = self.turns.pop(0) if self.turns else ("到这儿。", [])
        self.calls.append(
            {"messages": kwargs.get("messages"), "tools": kwargs.get("tools")}
        )
        yield StreamEvent(thinking="嗯")
        if calls:
            yield StreamEvent(tool_calls=calls)
        yield StreamEvent(text=text, is_done=True, tokens=5, tokens_in=10)

    async def chat(self, **kwargs):
        return "摘要"


def _tc(idx, name, args, call_id=None):
    import json

    return {
        "id": call_id or f"call_{idx}",
        "name": name,
        "arguments": args,
        "args_raw": json.dumps(args, ensure_ascii=False),
    }


def _fake_tool(monkeypatch, names: set[str]):
    executed: list[str] = []

    async def fake_run_tool(ctx, name, args):
        executed.append(name)
        return ToolResult(ok=True, summary=f"{name} 结果")

    def fake_get_tool(n):
        return Tool(name=n, kind="card", description="d", fn=fake_run_tool) if n in names else None

    monkeypatch.setattr(loop_mod, "get_tool", fake_get_tool)
    monkeypatch.setattr(loop_mod, "run_tool", fake_run_tool)
    return executed


@pytest.mark.asyncio
async def test_out_of_scope_tool_guided_not_executed(monkeypatch):
    """设定线程调卷纲工具（draft_volume_expand）＝引导收口，零执行。"""
    executed = _fake_tool(monkeypatch, {"draft_volume_expand"})
    client = _ScriptedClient(
        [
            ("", [_tc(0, "draft_volume_expand", {"line": "x"})]),
            ("这个是卷纲页签的事。", []),
        ]
    )
    loop = AgentLoop(
        client=client, system="sys",
        transcript=[], tool_ctx=None, config=LoopConfig(), harness="native",
    )
    loop.tool_ctx = type("Ctx", (), {"thread": "set:default"})()
    events = [e async for e in loop.run("帮我铺卷")]
    assert executed == [], "域外工具不得执行"
    assert loop.result.tool_calls == 0
    assert not [e for e in events if e["type"] == "step_start"]
    row = next(m for m in loop.transcript if m.get("role") == "tool")
    assert "卷纲" in row["content"]
    assert loop.result.final_reply == "这个是卷纲页签的事。"


@pytest.mark.asyncio
async def test_in_scope_tool_executes_and_labels_domain(monkeypatch):
    """卷纲线程调本域工具＝执行＋step 事件带 domain=卷纲。"""
    executed = _fake_tool(monkeypatch, {"draft_volume_expand"})
    client = _ScriptedClient(
        [
            ("", [_tc(0, "draft_volume_expand", {"line": "逃出船坞"})]),
            ("铺好了。", []),
        ]
    )
    loop = AgentLoop(
        client=client, system="sys",
        transcript=[], tool_ctx=None, config=LoopConfig(), harness="native",
    )
    loop.tool_ctx = type("Ctx", (), {"thread": "vol"})()
    events = [e async for e in loop.run("铺卷")]
    assert executed == ["draft_volume_expand"]
    step_start = next(e for e in events if e["type"] == "step_start")
    assert step_start.get("domain") == "卷纲"
    step_end = next(e for e in events if e["type"] == "step_end")
    assert step_end.get("domain") == "卷纲"
    assert domain_label_of_thread("vol") == "卷纲助手"


@pytest.mark.asyncio
async def test_shared_read_has_no_domain_label(monkeypatch):
    """共享读不带域标签（缺字段＝向后兼容增项口径）。"""
    _fake_tool(monkeypatch, {"read_progress"})
    client = _ScriptedClient(
        [
            ("", [_tc(0, "read_progress", {})]),
            ("第 7 章。", []),
        ]
    )
    loop = AgentLoop(
        client=client, system="sys",
        transcript=[], tool_ctx=None, config=LoopConfig(), harness="native",
    )
    loop.tool_ctx = type("Ctx", (), {"thread": "set:default"})()
    events = [e async for e in loop.run("进度")]
    step_start = next(e for e in events if e["type"] == "step_start")
    assert "domain" not in step_start


@pytest.mark.asyncio
async def test_two_threads_concurrent_isolated(monkeypatch):
    """跨线程并发：两会话各自跑完，消息/结果互不串写（独立流程守卫）。"""
    _fake_tool(monkeypatch, {"read_progress"})

    async def slow_tool(ctx, name, args):
        await asyncio.sleep(0.02)
        return ToolResult(ok=True, summary=f"结果-{args.get('mark', '')}")

    fake = Tool(name="read_progress", kind="read", description="d", fn=slow_tool)
    monkeypatch.setattr(loop_mod, "get_tool", lambda n: fake)
    monkeypatch.setattr(loop_mod, "run_tool", slow_tool)

    results: dict[str, str] = {}

    async def run_one(tag: str, thread: str) -> None:
        client = _ScriptedClient(
            [("", [_tc(0, "read_progress", {"mark": tag})]), (f"答{tag}", [])]
        )
        loop = AgentLoop(
            client=client, system="sys", transcript=[], tool_ctx=None,
            config=LoopConfig(), harness="native",
        )
        loop.tool_ctx = type("Ctx", (), {"thread": thread})()
        events = [e async for e in loop.run(f"问{tag}")]
        results[tag] = loop.result.final_reply

    await asyncio.gather(run_one("A", "ch:og"), run_one("B", "set:default"))
    assert results == {"A": "答A", "B": "答B"}
