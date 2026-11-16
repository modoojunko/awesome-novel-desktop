"""动作协议解析测试（c-writing-agent 批A 1.4）。

三级兜底口径：严格 json → 修复（中文标点/尾逗号/单引号/字面量）→ 抢救
（代码围栏/首尾花括号截取）→ 降级 degraded（reply 取文本前段）。
"""

from assistant.actions import parse_action


def test_strict_tool_action():
    a = parse_action(
        '{"thought": "先读主线", "action": "tool", "tool": "read_settings", '
        '"args": {"area": "premise"}, "reply": ""}'
    )
    assert a.kind == "tool"
    assert a.tool == "read_settings"
    assert a.args == {"area": "premise"}
    assert a.degraded is False


def test_strict_final_action():
    a = parse_action(
        '{"thought": "收口", "action": "final", "reply": "主线还差一句。"}'
    )
    assert a.kind == "final"
    assert a.reply == "主线还差一句。"


def test_repair_chinese_punctuation_and_single_quotes():
    raw = "{'thought'：'看看名册'，'action'：'tool'，'tool'：'read_settings'，'args'：{'area'：'cast'}，'reply'：''}"
    a = parse_action(raw)
    assert a.kind == "tool"
    assert a.tool == "read_settings"
    assert a.args == {"area": "cast"}


def test_code_fence_extraction():
    raw = (
        "好的，我来看一下。\n```json\n{\"thought\": \"读进度\", \"action\": \"tool\", "
        "\"tool\": \"read_progress\", \"args\": {}, \"reply\": \"\"}\n```"
    )
    a = parse_action(raw)
    assert a.kind == "tool"
    assert a.tool == "read_progress"


def test_salvage_wrapped_in_prose():
    raw = (
        "我先把卷纲读出来再回答。\n"
        "{\"thought\": \"读卷纲\", \"action\": \"tool\", \"tool\": \"read_outline\", "
        "\"args\": {\"scope\": \"volume\"}, \"reply\": \"\"}\n"
        "稍等。"
    )
    a = parse_action(raw)
    assert a.kind == "tool"
    assert a.tool == "read_outline"


def test_final_without_action_field_but_reply():
    raw = '{"reply": "这一卷可以收在海边。"}'
    a = parse_action(raw)
    assert a.kind == "final"
    assert a.reply == "这一卷可以收在海边。"


def test_tool_without_name_with_reply_becomes_final():
    raw = '{"thought": "想调个不存在的", "action": "tool", "tool": "", "reply": "做不了。"}'
    a = parse_action(raw)
    assert a.kind == "final"
    assert a.reply == "做不了。"


def test_garbage_degrades_with_snippet_reply():
    raw = "今天天气不错，我们聊聊人生吧。"
    a = parse_action(raw)
    assert a.kind == "degraded"
    assert a.degraded is True
    assert "今天天气不错" in a.reply


def test_empty_degrades():
    a = parse_action("")
    assert a.kind == "degraded"
    assert a.degraded is True
