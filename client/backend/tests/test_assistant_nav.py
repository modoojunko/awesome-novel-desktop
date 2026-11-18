"""c-agent-nav 钉：switch_tab 工具＋effect 契约＋域封闭。

三层覆盖：
- 注册表/域封闭：switch_tab 七章节域可见、卷纲/设定/预览/默认域不可见（spec 硬契约）；
- 工具真身：白名单校验（坏值失败列可选项）＋非章节线程拒绝（诚实话术）；
- loop 链：真工具走 _emit_step → step_end 携带 args（effect target 来源）。

route 层（SSE effect 事件下发/不入库）在 test_assistant_chat_stream_http.py。
"""

import json

import pytest

from assistant.router import nav_prime_hint
from assistant.scopes import discipline_of_thread, tools_for_thread
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


def test_nav_prime_hint_hits_switch_intents():
    """走查实锤补刀钉：窄意图 prime——flash 长历史服从 0/3 的结构兜底。"""
    assert nav_prime_hint("ch:og", "把页面切到正文") == {"tool": "switch_tab", "args": {"tab": "prose"}}
    assert nav_prime_hint("ch:prose", "切换到章纲") == {"tool": "switch_tab", "args": {"tab": "og"}}
    assert nav_prime_hint("ch:og", "看看伏笔") == {"tool": "switch_tab", "args": {"tab": "hooks"}}
    assert nav_prime_hint("ch:og", "切到文风") == {"tool": "switch_tab", "args": {"tab": "style"}}


def test_nav_prime_hint_guards():
    """守卫面：同页签不 prime／显式 tool_hint 优先／域外不 prime／意图外不 prime。"""
    assert nav_prime_hint("ch:prose", "把页面切到正文") is None  # 已在正文
    assert nav_prime_hint("ch:og", "把页面切到正文", {"tool": "read_chapter", "args": {}}) == {
        "tool": "read_chapter", "args": {}
    }
    assert nav_prime_hint("vol", "把页面切到正文") is None  # 域外工具不可见
    assert nav_prime_hint("ch:og", "续写正文") is None  # 意图外不命中
    assert nav_prime_hint("ch:og", "帮我看看第七章") is None


def test_ch_discipline_carries_switch_tab_rule():
    """域纪律补刀钉：章节页签纪律含 switch_tab 强制调用口径；卷纲纪律不含。"""
    d = discipline_of_thread("ch:og")
    assert "switch_tab" in d
    assert "不许只用话术说切了" in d
    assert "switch_tab" not in discipline_of_thread("vol")


@pytest.mark.asyncio
async def test_world_card_draft_peels_dict_and_json_string():
    """世界卡 draft 三态剥壳钉（走查实锤：dict 形态漏剥＝产物卡裸 JSON）。"""
    from unittest.mock import AsyncMock


    ctx = ToolContext(novel_id="n", root_path="/tmp", user_id="u", page="settings", thread="set:default")

    async def _cap(result):
        with __import__("unittest").mock.patch(
            "assistant.caps.world.draft_world_cap", AsyncMock(return_value=result)
        ):
            return await run_tool(ctx, "draft_worldbuilding", {"topic": "力量体系"})

    r1 = await _cap({"draft": {"value": "血源共鸣", "note": "x"}})
    assert r1.card["payload"]["draft"] == "血源共鸣"  # dict 形态（走查实锤漏剥）
    r2 = await _cap({"draft": json.dumps({"value": "文本B"})})
    assert r2.card["payload"]["draft"] == "文本B"  # 字符串单层
    r3 = await _cap({"draft": "纯文本草稿"})
    assert r3.card["payload"]["draft"] == "纯文本草稿"  # 纯文本原样
