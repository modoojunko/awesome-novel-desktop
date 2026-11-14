"""兜底提示词钉子（review 判例 2026-11-14：ACT_PROTOCOL 的 f-string 曾把函数对象
插进提示词——`{tool_catalog_text}` 少调用括号，兜底路径下模型拿到的是
`<function … at 0x…>` 而非工具清单，第一次调工具即被 unknown-tool 收口）。

兜底路径＝提示词包缺 assistant_act 模板时（旧包用户/包加载失败）——本文件把
「兜底协议必须含真实工具名、不得含函数 repr」钉死。
"""

from assistant import prompts


def test_fallback_act_protocol_contains_real_tool_names():
    assert "read_progress" in prompts.ACT_PROTOCOL
    assert "draft_volume_plan" in prompts.ACT_PROTOCOL
    assert "kb_update_entry" in prompts.ACT_PROTOCOL
    assert "<function" not in prompts.ACT_PROTOCOL


def test_build_system_prompt_fallback_path_has_tools(monkeypatch):
    monkeypatch.setattr(prompts, "_layer_or_none", lambda *a, **k: None)
    system = prompts.build_system_prompt("", "书名：测试")
    assert "read_progress" in system
    assert "<function" not in system


def test_build_system_prompt_pack_path_still_has_tools(monkeypatch):
    """包在位路径（assistant_act 模板经 tool_catalog 注入）同样必须带真实清单。"""
    monkeypatch.setattr(
        prompts,
        "_layer_or_none",
        lambda name, **values: (
            f"包内协议（工具清单：\n{values['tool_catalog']}）"
            if name == "assistant_act"
            else None
        ),
    )
    system = prompts.build_system_prompt("身份段", "书名：测试")
    assert "read_progress" in system
    assert "<function" not in system
