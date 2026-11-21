"""动作协议解析测试（c-writing-agent 批A 1.4；c-agent-chat-memory 升 v2 哨兵分节）。

v2 口径：叙述正文＋===ACT=== 哨兵＋动作 JSON（reply 字段退役）。
兼容链：v2 哨兵分节 → 旧版单 JSON → 纯文本兜底（无哨兵非 JSON＝模型直接回答，
整段按 final 交付，degraded 供遥测）。
"""

from assistant.actions import ACT_SENTINEL, parse_action, stream_slice

# ── v2 哨兵分节 ──────────────────────────────────────────────────


def test_v2_sentinel_tool_action():
    raw = (
        "我先看看这本书的设定再答。\n"
        f"{ACT_SENTINEL}\n"
        '{"action": "tool", "tool": "read_settings", "args": {"area": "premise"}}'
    )
    a = parse_action(raw)
    assert a.kind == "tool"
    assert a.tool == "read_settings"
    assert a.args == {"area": "premise"}
    assert a.reply == "我先看看这本书的设定再答。"
    assert a.degraded is False


def test_v2_sentinel_final_action():
    raw = f"主线还差一句收束，我建议在海边收。{ACT_SENTINEL}\n" + '{"action": "final"}'
    a = parse_action(raw)
    assert a.kind == "final"
    assert a.reply == "主线还差一句收束，我建议在海边收。"
    assert a.degraded is False


def test_v2_sentinel_garbage_tail_with_narration_is_final():
    # 尾部 JSON 烂了但有正文——正文完整交付（自愿收口），不拦作家内容
    raw = f"这章节奏没问题。{ACT_SENTINEL}\n不是json的一段"
    a = parse_action(raw)
    assert a.kind == "final"
    assert "这章节奏没问题" in a.reply
    assert a.degraded is True


def test_v2_sentinel_garbage_tail_with_stray_prose_keeps_content():
    # 哨兵误触发、哨兵后还有散文——内容不丢，并入回答
    raw = f"前半句。{ACT_SENTINEL}\n后半句散文。"
    a = parse_action(raw)
    assert a.kind == "final"
    assert "前半句" in a.reply and "后半句散文" in a.reply


def test_v2_sentinel_only_no_narration_tool():
    raw = f"{ACT_SENTINEL}\n" + '{"action": "tool", "tool": "read_outline", "args": {}}'
    a = parse_action(raw)
    assert a.kind == "tool"
    assert a.tool == "read_outline"
    assert a.reply == ""


# ── 旧版单 JSON 兼容（提示词包未升级时模型仍走旧格式） ─────────────


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


# ── 纯文本兜底（无哨兵非 JSON＝模型直接回答） ─────────────────────


def test_plain_text_is_final_narration():
    # v2 语义翻转：纯文本＝模型自愿收口的回答，整段交付（不再包降级外壳）
    raw = "今天天气不错，我们聊聊人生吧。"
    a = parse_action(raw)
    assert a.kind == "final"
    assert "今天天气不错" in a.reply


def test_empty_degrades():
    a = parse_action("")
    assert a.kind == "degraded"
    assert a.degraded is True


# ── stream_slice（流式切分纯函数） ────────────────────────────────


def test_stream_slice_legacy_json_freezes_at_zero():
    # 旧版纯 JSON：首字符 { → 一字不发、冻结（批次交付，同旧口径）
    pos, frozen = stream_slice('{"thought": "收口"', 0, False)
    assert pos == 0 and frozen is True


def test_stream_slice_streams_before_sentinel():
    buf = "叙述正文足够长才能越过扣尾窗口继续流式。"
    pos, frozen = stream_slice(buf, 0, False)
    # 无哨兵无花括号：发到 len-扣尾（哨兵跨 chunk 扣留）
    assert 0 < pos < len(buf) and frozen is False


def test_stream_slice_freezes_at_sentinel():
    buf = f"正文前半。{ACT_SENTINEL}" + '{"action": "final"}'
    pos, frozen = stream_slice(buf, 0, False)
    assert pos == len("正文前半。") and frozen is True


def test_stream_slice_freezes_at_inline_brace():
    # 叙述后混入 JSON/围栏（旧版抢救形态）→ 从 { 处冻结
    buf = "好的，我来看一下。\n{\"thought\""
    pos, frozen = stream_slice(buf, 0, False)
    assert pos == buf.find("{") and frozen is True


def test_stream_slice_frozen_is_terminal():
    pos, frozen = stream_slice("更多文本", 5, True)
    assert pos == 5 and frozen is True


def test_stream_slice_emitted_only_advances():
    buf = "一二三四五六七八九十"
    p1, _ = stream_slice(buf, 0, False)
    p2, _ = stream_slice(buf + "更多", p1, False)
    assert p2 > p1


# ── 协议形状裸片段（c-agent-action-contract）─────────────────────


def _tool_exists(name: str) -> bool:
    return name in {"draft_arc", "read_settings"}


def test_no_sentinel_fragment_without_narration_is_protocol_error():
    raw = '"action": "draft_arc", "tool": "", "args": {}}'
    a = parse_action(raw)
    assert a.kind == "protocol_error"
    assert a.reply == ""


def test_no_sentinel_fragment_with_narration_keeps_prefix():
    raw = '抱歉，上面那行格式错了。\n"action": "draft_arc", "tool": "", "args": {}}'
    a = parse_action(raw, tool_exists=_tool_exists)
    assert a.kind == "tool"
    assert a.tool == "draft_arc"
    assert a.reply == "抱歉，上面那行格式错了。"
    assert a.args == {}


def test_no_sentinel_fragment_unknown_tool_is_protocol_error():
    raw = '先这样。\n"action": "not_a_tool", "args": {}}'
    a = parse_action(raw, tool_exists=_tool_exists)
    assert a.kind == "protocol_error"
    assert a.reply == "先这样。"


def test_sentinel_action_slot_tool_name_is_repaired():
    raw = (
        f"我起草主线。{ACT_SENTINEL}\n"
        '{"action": "draft_arc", "args": {"action": "draft", "input": "素材"}}'
    )
    a = parse_action(raw, tool_exists=_tool_exists)
    assert a.kind == "tool"
    assert a.tool == "draft_arc"
    assert a.args == {"action": "draft", "input": "素材"}
    assert a.reply == "我起草主线。"


def test_sentinel_invalid_action_is_protocol_error_not_final():
    raw = f"我这就去写。{ACT_SENTINEL}\n" + '{"action": "write_prose", "args": {}}'
    a = parse_action(raw)
    assert a.kind == "protocol_error"
    assert a.reply == "我这就去写。"


def test_sentinel_protocol_shaped_garbage_tail_is_protocol_error():
    raw = f"前半句。{ACT_SENTINEL}\n" + '"action": "draft_arc", "args": {}}'
    a = parse_action(raw, tool_exists=_tool_exists)
    assert a.kind == "tool"
    assert a.tool == "draft_arc"


def test_stream_slice_freezes_at_protocol_fragment():
    buf = '抱歉，上面那行写错了。\n"action": "draft_arc", "args": {}}'
    pos, frozen = stream_slice(buf, 0, False)
    assert pos == buf.find('"action"') and frozen is True


def test_stream_slice_freezes_at_fragment_from_first_char():
    buf = '"action": "draft_arc", "args": {}}'
    pos, frozen = stream_slice(buf, 0, False)
    assert pos == 0 and frozen is True


def test_wrapped_legacy_json_after_narration_still_parses():
    raw = (
        "我先把卷纲读出来再回答。\n"
        '{"action": "tool", "tool": "read_settings", "args": {"area": "premise"}}'
    )
    a = parse_action(raw, tool_exists=_tool_exists)
    assert a.kind == "tool"
    assert a.tool == "read_settings"
    assert a.reply == "我先把卷纲读出来再回答。"


def test_code_fence_prefix_is_stripped_from_narration():
    raw = (
        "好的，我来看一下。\n```json\n"
        '{"action": "tool", "tool": "read_settings", "args": {}}'
    )
    a = parse_action(raw, tool_exists=_tool_exists)
    assert a.kind == "tool"
    assert a.reply == "好的，我来看一下。"
