"""router 装配级钉子（review 判例 2026-11-14）。

- _history_transcript：本轮用户消息按 id 排除——loop.run() 会再 append 一次
  user_input，不排除＝每轮双注入模型窗口（单测的 transcript 约定是不含当前消息）。
- 采纳回执定位口径：payload.cardId 匹配产物卡行（gate 行排除）。
"""

from types import SimpleNamespace

from assistant.router import _history_transcript


def _row(id: str, role: str, content: str, card_kind: str = ""):
    return SimpleNamespace(
        id=id, role=role, content=content, card_kind=card_kind, payload_json="{}"
    )


def test_history_transcript_excludes_current_user_message():
    rows = [
        _row("m1", "user", "第一问"),
        _row("m2", "assistant", "第一答"),
        _row("m3", "user", "第二问"),  # 本轮刚落库的消息
    ]
    transcript = _history_transcript(rows, exclude_message_id="m3")
    assert transcript == [
        {"role": "user", "content": "第一问"},
        {"role": "assistant", "content": "第一答"},
    ]


def test_history_transcript_without_exclude_keeps_all():
    rows = [
        _row("m1", "user", "第一问"),
        _row("m2", "assistant", "第一答"),
        _row("m3", "user", "第二问"),
    ]
    transcript = _history_transcript(rows)
    assert len(transcript) == 3


def test_history_transcript_drops_tool_event_and_empty_rows():
    rows = [
        _row("m1", "user", "问"),
        _row("m2", "tool", "工具结果"),  # 不进转写
        _row("m3", "event", ""),  # 空 content 不进转写
        _row("m4", "assistant", "答"),
    ]
    transcript = _history_transcript(rows, exclude_message_id="")
    assert transcript == [
        {"role": "user", "content": "问"},
        {"role": "assistant", "content": "答"},
    ]
