"""router 装配级钉子（review 判例 2026-11-14）。

- _history_transcript：本轮用户消息按 id 排除——loop.run() 会再 append 一次
  user_input，不排除＝每轮双注入模型窗口（单测的 transcript 约定是不含当前消息）。
- 采纳回执定位口径：payload.cardId 匹配产物卡行（gate 行排除）。
"""

from types import SimpleNamespace

import pytest

from assistant.router import _history_transcript, _resume_gap_note


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


# ── 记忆时序（c-agent-chat-memory 批8：跨天标记＋恢复聚焦） ─────────────


def _row_ts(id: str, role: str, content: str, created_at: str):
    return SimpleNamespace(
        id=id, role=role, content=content, card_kind="",
        payload_json="{}", created_at=created_at,
    )


def test_history_transcript_inserts_day_gap_marker():
    rows = [
        _row_ts("m1", "user", "昨天的话", "2026-11-17 10:00:00"),
        _row_ts("m2", "assistant", "昨天的答", "2026-11-17 10:01:00"),
        _row_ts("m3", "user", "今天的话", "2026-11-18 09:30:00"),
    ]
    out = _history_transcript(rows)
    assert len(out) == 4
    assert "[system] ── 时间跳到 11 月 18 日 ──" == out[2]["content"]
    assert out[3] == {"role": "user", "content": "今天的话"}


def test_history_transcript_same_day_no_marker():
    rows = [
        _row_ts("m1", "user", "上午的话", "2026-11-17 10:00:00"),
        _row_ts("m2", "assistant", "下午的话", "2026-11-17 15:00:00"),
    ]
    out = _history_transcript(rows)
    assert len(out) == 2
    assert not any("[system]" in o["content"] for o in out)


def test_resume_gap_note_thresholds():
    from datetime import datetime, timedelta
    now = datetime.now()
    old_rows = [_row_ts("m1", "user", "昨天的事", (now - timedelta(hours=30)).strftime("%Y-%m-%d %H:%M:%S"))]
    note = _resume_gap_note(old_rows)
    assert "1 天" in note and "聚焦" in note
    fresh_rows = [_row_ts("m2", "user", "刚刚", (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"))]
    assert _resume_gap_note(fresh_rows) == ""
    assert _resume_gap_note([]) == ""


@pytest.mark.asyncio
async def test_read_progress_summary_is_human(monkeypatch):
    """read_progress 摘要人话口径（boss 走查 2026-11-17：frontier/draft 内部词禁出模型口）。

    三态真值（c-agent-writing-flow-context）：「草稿」改「正文已写 N 字·未归档」；
    摘要尾部给「再往后是 第 N+1 章」——一次调用给全「下一章落点」决策依据。"""
    import chapters.frontier as _fr

    async def _fake_frontier(db, novel_id):
        return {
            "chapters": [
                {"ref": f"vol-1-ch-{i}", "has_prose": True, "archived": i < 6,
                 "word_count": 700 if i < 6 else 4199}
                for i in range(1, 8)
            ],
            "frontier": {"ref": "vol-1-ch-7", "global_no": 7, "state": "draft",
                         "has_prose": True, "word_count": 4199, "writable": True},
        }

    monkeypatch.setattr(_fr, "frontier_info", _fake_frontier)
    from assistant.tools import ToolContext, run_tool

    r = await run_tool(ToolContext(novel_id="n", root_path="", user_id="u"), "read_progress", {})
    assert "frontier" not in r.summary
    assert "draft" not in r.summary
    assert "全书 7 章" in r.summary and "已归档 5" in r.summary
    assert "第 7 章" in r.summary and "正文已写 4,199 字·未归档" in r.summary
    assert "草稿" not in r.summary  # 单一「草稿」掩盖已写完——三态真值禁用
    assert "再往后是 第 8 章" in r.summary


@pytest.mark.asyncio
async def test_read_progress_pending_and_planned_states(monkeypatch):
    """read_progress 三态口径：planned＝没写、pending＝全归档待拆纲（不与 draft 混）。"""
    import chapters.frontier as _fr
    from assistant.tools import ToolContext, run_tool

    async def _planned(db, novel_id):
        return {
            "chapters": [
                {"ref": f"vol-1-ch-{i}", "has_prose": True, "archived": i < 6,
                 "word_count": 700}
                for i in range(1, 8)
            ],
            "frontier": {"ref": "vol-1-ch-7", "global_no": 7, "state": "planned",
                         "has_prose": False, "word_count": 0, "writable": True},
        }

    monkeypatch.setattr(_fr, "frontier_info", _planned)
    r = await run_tool(ToolContext(novel_id="n", root_path="", user_id="u"), "read_progress", {})
    assert "已排定·正文未写·未归档" in r.summary

    async def _pending(db, novel_id):
        return {
            "chapters": [
                {"ref": f"vol-1-ch-{i}", "has_prose": True, "archived": True,
                 "word_count": 700}
                for i in range(1, 8)
            ],
            "frontier": {"ref": "vol-1-ch-8", "global_no": 8, "state": "pending",
                         "has_prose": False, "word_count": 0, "writable": True,
                         "pending": True},
        }

    monkeypatch.setattr(_fr, "frontier_info", _pending)
    r = await run_tool(ToolContext(novel_id="n", root_path="", user_id="u"), "read_progress", {})
    assert "各章均已归档，下一章是 第 8 章（待拆纲，可以开写）" in r.summary


# ── 书级 brief 进度行三态真值（c-agent-writing-flow-context）─────────────────────


class _BriefNovel:
    """build_book_brief 入参最小桩：name/id/root_path；题材解析失败即静默跳过。"""

    name = "夜行录"
    id = "n"
    root_path = ""


async def _brief_with_frontier(monkeypatch, info: dict) -> str:
    import chapters.frontier as _fr
    from assistant.context import build_book_brief

    async def _fake_frontier(db, novel_id):
        return info

    monkeypatch.setattr(_fr, "frontier_info", _fake_frontier)
    return await build_book_brief(_BriefNovel(), None)


@pytest.mark.asyncio
async def test_book_brief_draft_state_carries_words_and_unarchived(monkeypatch):
    """前沿章有正文未归档：brief 说「正文已写 N 字·未归档」，不再压成「草稿」。"""
    brief = await _brief_with_frontier(
        monkeypatch,
        {
            "chapters": [
                {"ref": f"vol-1-ch-{i}", "has_prose": True, "archived": i < 6,
                 "word_count": 700 if i < 6 else 4199}
                for i in range(1, 8)
            ],
            "frontier": {"ref": "vol-1-ch-7", "global_no": 7, "state": "draft",
                         "has_prose": True, "word_count": 4199, "writable": True},
        },
    )
    assert "全书 7 章（已归档 5）" in brief
    assert "正文已写 4,199 字·未归档" in brief
    assert "草稿" not in brief


@pytest.mark.asyncio
async def test_book_brief_planned_and_pending_states(monkeypatch):
    """planned＝已排定没写；pending＝全归档、下一章待拆纲——三态可区分。"""
    planned = await _brief_with_frontier(
        monkeypatch,
        {
            "chapters": [
                {"ref": f"vol-1-ch-{i}", "has_prose": True, "archived": i < 6,
                 "word_count": 700}
                for i in range(1, 8)
            ],
            "frontier": {"ref": "vol-1-ch-7", "global_no": 7, "state": "planned",
                         "has_prose": False, "word_count": 0, "writable": True},
        },
    )
    assert "第 7 章 已排定·正文未写·未归档" in planned

    pending = await _brief_with_frontier(
        monkeypatch,
        {
            "chapters": [
                {"ref": f"vol-1-ch-{i}", "has_prose": True, "archived": True,
                 "word_count": 700}
                for i in range(1, 8)
            ],
            "frontier": {"ref": "vol-1-ch-8", "global_no": 8, "state": "pending",
                         "has_prose": False, "word_count": 0, "writable": True,
                         "pending": True},
        },
    )
    assert "各章均已归档；下一章 第 8 章（待拆纲）" in pending
