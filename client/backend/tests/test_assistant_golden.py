"""黄金指令集 v0 离线评测（c-writing-agent 批G 7.2）。

用例集：tests/golden/assistant_golden_v0.json（14 条起步，扩集走同 schema）。
FakeClient 按 stub 标记回动作 JSON（模拟服从度良好的模型）；断言循环的
**行为**（选中工具/收口文本/越界拒答），不依赖真实模型。真实发散质量另测
（采纳率埋点）——本集测的是「结构行为不变量」：
  - 书内指令 → 对应工具被调用（一次）；
  - 书外/越界/注入 → 不执行任何写类动作，收口不冒充；
  - 空输入不崩。
"""

import json
import pytest

from assistant.loop import AgentLoop, LoopConfig
from assistant.tools import TOOL_REGISTRY, Tool, ToolResult

GOLDEN = json.load(open("tests/golden/assistant_golden_v0.json"))["cases"]

# 指令关键词 → 工具名（与 e2e stub 同款分支语义）
KEYWORD_TOOL = [
    ("名册", "read_settings"),
    ("硬伤", "check_consistency"),
    ("铺", "draft_volume_expand"),
    ("卷纲", "draft_volume_expand"),
    ("知识库", "kb_search"),
    ("体检", "check_consistency"),
    ("剧情清单", "draft_chapter_plot"),
    ("主线", "draft_arc"),
    ("名字", "draft_names"),
    ("反派", "diverge_character_group"),
    ("添", "diverge_character_group"),
    ("查", "read_progress"),
]


class ScriptedClient:
    """按规则回动作 JSON：命中关键词→工具；否则 final。"""

    def __init__(self, keyword: str, tool: str):
        self.keyword = keyword
        self.tool = tool
        self.calls = 0

    async def chat_stream(self, **kwargs):
        from ai_client import StreamEvent

        self.calls += 1
        prompt = kwargs.get("messages", [{}])[-1].get("content", "") + " " + (kwargs.get("system") or "")
        if self.calls > 1:
            content = '{"thought": "收口", "action": "final", "reply": "给你答复。"}'
        elif self.keyword in prompt:
            content = json_dumps_action(self.tool)
        else:
            content = '{"thought": "不认识", "action": "final", "reply": "收到。"}'
        yield StreamEvent(text=content, is_done=True, tokens=8, tokens_in=12)

    async def chat(self, **kwargs):
        return "{}"


def json_dumps_action(tool: str) -> str:
    import json

    return json.dumps(
        {"thought": "干活", "action": "tool", "tool": tool, "args": {}, "reply": ""},
        ensure_ascii=False,
    )


_TOOL_CASES = [c for c in GOLDEN if "expect_tool" in c]

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    _TOOL_CASES,
    ids=[c["id"] for c in _TOOL_CASES],
)
async def test_golden_routes_to_expected_tool(case, monkeypatch):
    """书内指令 → 循环第一动作命中期望工具（且只调一次工具）。"""
    keyword = next((k for k, t in KEYWORD_TOOL if k in case["input"]), case["stub"])
    executed: list[str] = []

    async def fake_run_tool(ctx, name, args):
        executed.append(name)
        return ToolResult(ok=True, summary="（工具结果占位）")

    fake = next(t for t in TOOL_REGISTRY if t.name == case["expect_tool"])
    monkeypatch.setattr("assistant.loop.run_tool", fake_run_tool)
    monkeypatch.setattr("assistant.loop.get_tool", lambda n: fake if n == case["expect_tool"] else None)

    client = ScriptedClient(keyword, case["expect_tool"])
    loop = AgentLoop(
        client=client,
        system="system-with-动作协议-and-tool-catalog",
        transcript=[{"role": "user", "content": case["input"]}],
        tool_ctx=None,
        config=LoopConfig(max_steps=4),
    )
    events = [e async for e in loop.run(case["input"])]
    assert executed == [case["expect_tool"]], f"G{case['id']} 期望 {case['expect_tool']}，实际 {executed}"
    assert events[-1]["type"] == "run_end"
    assert loop.result.degraded is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [c for c in GOLDEN if c.get("expect") == "out_of_scope" or c.get("expect") == "final_no_tool"],
    ids=[c["id"] for c in GOLDEN if c.get("expect") in ("out_of_scope", "final_no_tool")],
)
async def test_golden_out_of_scope_and_chat(case, monkeypatch):
    """书外/注入/闲聊：循环不调用任何写类/发散工具，走收口。"""
    tool_calls: list[str] = []

    async def fake_run_tool(ctx, name, args):
        tool_calls.append(name)
        return ToolResult(ok=True, summary="不应到达")

    client = ScriptedClient("", "")
    loop = AgentLoop(
        client=client,
        system="system-with-动作协议",
        transcript=[{"role": "user", "content": case["input"]}],
        tool_ctx=None,
        config=LoopConfig(max_steps=3),
    )
    events = [e async for e in loop.run(case["input"])]
    assert tool_calls == [], "书外/注入请求不得触发任何工具"
    assert loop.result.final_reply  # 收口有话（含「没能力做」或正常闲聊答复）
    assert events[-1]["type"] == "run_end"
