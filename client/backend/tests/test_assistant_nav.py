"""c-agent-nav 钉：switch_tab 工具＋effect 契约＋域封闭。

三层覆盖：
- 注册表/域封闭：switch_tab 七章节域可见、卷纲/设定/预览/默认域不可见（spec 硬契约）；
- 工具真身：白名单校验（坏值失败列可选项）＋非章节线程拒绝（诚实话术）；
- loop 链：真工具走 _emit_step → step_end 携带 args（effect target 来源）。

route 层（SSE effect 事件下发/不入库）在 test_assistant_chat_stream_http.py。
"""

import pytest

from assistant.scopes import tools_for_thread
from assistant.tools import ToolContext, get_tool, run_tool

CH_THREADS = ["ch:og", "ch:prose", "ch:settings", "ch:relations", "ch:hooks", "ch:actions", "ch:style"]


def test_switch_tab_visible_only_in_chapter_domains():
    for t in CH_THREADS:
        assert "switch_tab" in tools_for_thread(t), f"{t} 应可见 switch_tab"
    for t in ["vol", "set:", "preview", ""]:
        assert "switch_tab" not in tools_for_thread(t), f"{t} 不应可见 switch_tab"


def test_switch_tab_registered_as_free_read():
    tool = get_tool("switch_tab")
    assert tool is not None
    assert tool.kind == "read"  # 免授权梯度（读类恒放行）
    assert tool.effect_action == "navigate"
    assert tool.effect_domain == "ui"
    assert tool.effect_target_from == "tab"
    assert "不要说「已切」" in tool.description  # 话术契约钉


@pytest.mark.asyncio
async def test_switch_tab_bad_tab_fails_with_options():
    ctx = ToolContext(novel_id="n", root_path="/tmp", user_id="u", page="chapter", thread="ch:og")
    r = await run_tool(ctx, "switch_tab", {"tab": "nope"})
    assert r.ok is False
    assert "正文" in r.summary and "章纲" in r.summary  # 列出可选页签


@pytest.mark.asyncio
async def test_switch_tab_outside_chapter_scope_fails_honest():
    ctx = ToolContext(novel_id="n", root_path="/tmp", user_id="u", page="volume", thread="vol")
    r = await run_tool(ctx, "switch_tab", {"tab": "prose"})
    assert r.ok is False
    assert "打开" in r.summary  # 带出口话术（§13）


@pytest.mark.asyncio
async def test_switch_tab_ok_summary():
    ctx = ToolContext(novel_id="n", root_path="/tmp", user_id="u", page="chapter", thread="ch:prose")
    r = await run_tool(ctx, "switch_tab", {"tab": "og"})
    assert r.ok is True
    assert "章纲" in r.summary


@pytest.mark.asyncio
async def test_loop_step_end_carries_args_for_effect_target(monkeypatch):
    """真工具走 _emit_step：step_end 携带 args（navigate effect 的 target 来源）。"""
    import json

    from assistant import loop as loop_mod
    from assistant.loop import AgentLoop, LoopConfig

    real_tool = get_tool("switch_tab")
    assert real_tool is not None
    monkeypatch.setattr(loop_mod, "get_tool", lambda n: real_tool if n == "switch_tab" else None)
    monkeypatch.setattr(loop_mod, "run_tool", lambda *a, **k: _run_real(a))

    async def _run_real(a):
        ctx, _name, args = a[0], a[1], a[2]
        return await real_tool.fn(ctx, **args)

    class FakeClient:
        def __init__(self, outs):
            self.outs = list(outs)

        async def chat_stream(self, **kwargs):
            from ai_client import StreamEvent

            yield StreamEvent(text=self.outs.pop(0), is_done=True, tokens=1, tokens_in=1)

    def _tool_json(name, args):
        return json.dumps(
            {"thought": "", "action": "tool", "tool": name, "args": args, "reply": ""},
            ensure_ascii=False,
        )

    def _final(reply):
        return json.dumps(
            {"thought": "", "action": "final", "reply": reply}, ensure_ascii=False
        )

    client = FakeClient([
        _tool_json("switch_tab", {"tab": "prose"}),
        _final("切过去了。"),
    ])
    loop = AgentLoop(
        client=client,
        system="sys",
        transcript=[],
        tool_ctx=ToolContext(novel_id="n", root_path="/tmp", user_id="u", page="chapter", thread="ch:og"),
        config=LoopConfig(),
    )
    events = [e async for e in loop.run("切到正文")]
    step_end = next(e for e in events if e.get("type") == "step_end")
    assert step_end["tool"] == "switch_tab"
    assert step_end["ok"] is True
    assert step_end["args"] == {"tab": "prose"}
