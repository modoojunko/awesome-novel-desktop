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


async def _brief_parts_with_frontier(monkeypatch, info: dict):
    import chapters.frontier as _fr
    from assistant.context import build_book_brief_parts

    async def _fake_frontier(db, novel_id):
        return info

    monkeypatch.setattr(_fr, "frontier_info", _fake_frontier)
    return await build_book_brief_parts(_BriefNovel(), None)


@pytest.mark.asyncio
async def test_book_brief_parts_stable_progress_separated(monkeypatch):
    """c-agent-prompt-cache：书名/题材（稳定）与进度（动态）分段——进度变化
    不改稳定段，稳定段才能留在系统前缀吃缓存。"""
    info_a = {
        "chapters": [
            {"ref": f"vol-1-ch-{i}", "has_prose": True, "archived": i < 6,
             "word_count": 700 if i < 6 else 1000}
            for i in range(1, 7)
        ],
        "frontier": {"ref": "vol-1-ch-6", "global_no": 6, "state": "draft",
                     "has_prose": True, "word_count": 1000, "writable": True},
    }
    stable, dynamic = await _brief_parts_with_frontier(monkeypatch, info_a)
    assert stable.startswith("书名：夜行录")
    assert "进度" not in stable
    assert dynamic.startswith("进度：")
    assert "正文已写 1,000 字" in dynamic

    info_b = {
        **info_a,
        "chapters": [
            {"ref": f"vol-1-ch-{i}", "has_prose": True, "archived": i < 6,
             "word_count": 700 if i < 6 else 2000}
            for i in range(1, 7)
        ],
        "frontier": {**info_a["frontier"], "word_count": 2000},
    }
    stable_b, dynamic_b = await _brief_parts_with_frontier(monkeypatch, info_b)
    assert stable_b == stable
    assert dynamic_b != dynamic
    assert "2,000 字" in dynamic_b


def test_latest_reminder_text_fixed_date():
    """c-agent-latest-reminder：日期/星期按 Asia/Shanghai、中文星期、空 location。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from assistant.context import latest_reminder_text

    text = latest_reminder_text(
        datetime(2026, 11, 9, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    )
    assert text == "2026-11-09,星期一,,App,中文"


def test_outbound_window_inserts_reminder_before_last_user():
    """提醒只插在最后一条 user 前；历史 user 不补插；无提醒零变化。"""
    from assistant.context import build_outbound_window

    transcript = [
        {"role": "user", "content": "旧问题"},
        {"role": "assistant", "content": "旧回答"},
        {"role": "user", "content": "新问题"},
    ]
    msgs, _ = build_outbound_window(
        transcript, compaction_state=None, reminder="2026-11-09,星期一,,App,中文"
    )
    assert [m["role"] for m in msgs] == [
        "user", "assistant", "latest_reminder", "user"
    ]
    assert msgs[2]["content"] == "2026-11-09,星期一,,App,中文"

    native_msgs, _ = build_outbound_window(
        transcript, compaction_state=None, native=True, reminder="R"
    )
    assert [m["role"] for m in native_msgs] == [
        "user", "assistant", "latest_reminder", "user"
    ]

    plain, _ = build_outbound_window(transcript, compaction_state=None)
    assert all(m["role"] != "latest_reminder" for m in plain)


# ── 授权卡 preview 装配（2026-11-21 实锤：builder 少传 project → TypeError 被吞
#    → 作家看到写工具裸 JSON）────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gate_preview_passes_project_to_builder(monkeypatch):
    """preview_builder 契约是 (args, project)；漏传 project 曾让整条对比链失效。"""
    import assistant.caps.settings as caps_settings
    from assistant.router import _build_gate_preview
    from assistant.tools import get_tool

    async def _fake_read(novel_id: str, stype: str, field: str, user_id: str) -> str:
        assert (novel_id, stype, field) == ("n1", "story", "synopsis")
        return "旧简介"

    monkeypatch.setattr(caps_settings, "read_settings_field", _fake_read)
    tool = get_tool("write_settings_field")
    assert tool is not None
    pv = await _build_gate_preview(
        tool,
        {"stype": "story", "field": "synopsis", "value": "新简介"},
        SimpleNamespace(id="n1"),
        {"tool": "write_settings_field", "summary": "改设定"},
    )
    assert pv["changes"] == [
        {"field": "synopsis", "label": "简介", "before": "旧简介", "after": "新简介"}
    ]


@pytest.mark.asyncio
async def test_gate_preview_settings_page_labels_and_overlong_guard(monkeypatch):
    """授权卡字段名＝设定页小标题；超 60 字的「标签」不弹卡，引导写 promise_note。"""
    import assistant.caps.settings as caps_settings
    from assistant.router import _build_gate_preview
    from assistant.tools import PreviewRejected, get_tool

    async def _fake_read(novel_id: str, stype: str, field: str, user_id: str) -> str:
        return "旧值"

    monkeypatch.setattr(caps_settings, "read_settings_field", _fake_read)
    tool = get_tool("write_settings_field")
    pv = await _build_gate_preview(
        tool,
        {"stype": "genre", "field": "promise_note", "value": "主角用脑子翻盘"},
        SimpleNamespace(id="n1"),
        {},
    )
    assert pv["changes"][0]["label"] == "主要看什么"

    with pytest.raises(PreviewRejected) as ei:
        await _build_gate_preview(
            tool,
            {"stype": "genre", "field": "core_promise", "value": "长" * 61},
            SimpleNamespace(id="n1"),
            {},
        )
    msg = str(ei.value)
    assert "60" in msg and "promise_note" in msg


@pytest.mark.asyncio
async def test_gate_preview_rejects_unknown_setting_field():
    """字段名不存在→不弹卡（PreviewRejected），回喂模型可选字段改对再来。"""
    from assistant.router import _build_gate_preview
    from assistant.tools import PreviewRejected, get_tool

    with pytest.raises(PreviewRejected) as ei:
        await _build_gate_preview(
            get_tool("write_settings_field"),
            {"stype": "story", "field": "premise", "value": "长文"},
            SimpleNamespace(id="n1"),
            {},
        )
    msg = str(ei.value)
    assert "premise" in msg
    assert "synopsis" in msg and "简介" in msg


@pytest.mark.asyncio
async def test_gate_preview_falls_back_when_builder_fails_or_missing():
    """读现值之外的意外失败仍走兜底（闸不受影响）；无 builder 直接用兜底。"""
    from assistant.router import _build_gate_preview

    def _boom(args, project):
        raise RuntimeError("db down")

    fallback = {"tool": "write_settings_field", "summary": "改设定"}
    assert await _build_gate_preview(
        SimpleNamespace(preview_builder=_boom), {}, None, fallback
    ) == fallback
    assert await _build_gate_preview(SimpleNamespace(), {}, None, fallback) == fallback


@pytest.mark.asyncio
async def test_gate_preview_rejects_unknown_chapter_field():
    """章纲字段名不在白名单同样不弹卡（回喂可用字段名，模型自纠）。"""
    from assistant.router import _build_gate_preview
    from assistant.tools import PreviewRejected, get_tool

    with pytest.raises(PreviewRejected) as ei:
        await _build_gate_preview(
            get_tool("write_chapter_fields"),
            {"chapter_ref": "vol-1-ch-2", "fields": {"premise": "x"}},
            SimpleNamespace(id="n1"),
            {},
        )
    assert "premise" in str(ei.value)
    assert "概要" in str(ei.value)


# ── 页面字段真值（c-agent-page-field-truth）─────────────────────────────────


@pytest.mark.asyncio
async def test_book_brief_genre_line_reads_theme_keys(monkeypatch):
    """题材行真值：resolve 返回键是 theme/sub_genre——旧代码读 genre/genre_name
    ＝死代码，「题材：X」从未注入过（键名回归钉）。"""
    import genres.service as _gs
    from assistant.context import build_book_brief_parts

    async def _fake_ctx(root_path, novel_id):
        return {"theme": "玄幻", "sub_genre": "凡人流"}

    monkeypatch.setattr(_gs, "resolve_genre_context", _fake_ctx)
    stable, _ = await build_book_brief_parts(_BriefNovel(), None)
    assert "题材：玄幻（凡人流）" in stable


@pytest.mark.asyncio
async def test_book_brief_genre_line_theme_only(monkeypatch):
    import genres.service as _gs
    from assistant.context import build_book_brief_parts

    async def _fake_ctx(root_path, novel_id):
        return {"theme": "都市"}

    monkeypatch.setattr(_gs, "resolve_genre_context", _fake_ctx)
    stable, _ = await build_book_brief_parts(_BriefNovel(), None)
    assert "题材：都市" in stable


@pytest.mark.asyncio
async def test_book_brief_genre_line_skips_when_empty(monkeypatch):
    """五格全空（resolve 返回 None）：brief 不给空题材行——未填点名归 set:genre 真值。"""
    import genres.service as _gs
    from assistant.context import build_book_brief_parts

    async def _none_ctx(root_path, novel_id):
        return None

    monkeypatch.setattr(_gs, "resolve_genre_context", _none_ctx)
    stable, _ = await build_book_brief_parts(_BriefNovel(), None)
    assert stable.startswith("书名：夜行录")
    assert "题材" not in stable


def test_settings_tab_label_panels():
    """set:* 面板真值标签：已知面板带后缀；default/未知回退「设定」；
    非 set: 线程空串（ch:/vol 走各自分支，不串味）。"""
    from assistant.router import settings_tab_label

    assert settings_tab_label("set:genre") == "设定·题材"
    assert settings_tab_label("set:world") == "设定·世界"
    assert settings_tab_label("set:foreshadow") == "设定·伏笔"
    assert settings_tab_label("set:default") == "设定"
    assert settings_tab_label("set:mystery") == "设定"
    assert settings_tab_label("ch:og") == ""
    assert settings_tab_label("vol") == ""
    assert settings_tab_label("") == ""


@pytest.mark.asyncio
async def test_read_settings_genre_area_lists_truth(monkeypatch):
    """read_settings genre 区：五格现值＋未填点名（与题材目录工具分工：
    本区读「这本书现在填了什么」）。"""
    import genres.service as _gs
    from assistant.tools import ToolContext, run_tool

    async def _fake_ctx(root_path, novel_id):
        return {
            "theme": "玄幻",
            "sub_genre": "凡人流",
            "cost_ratio": 7,
            "forbidden": ["禁天降外援"],
            "battlefield": ["抢资源"],
        }

    monkeypatch.setattr(_gs, "resolve_genre_context", _fake_ctx)
    r = await run_tool(
        ToolContext(novel_id="n", root_path="/r", user_id="u"), "read_settings", {"area": "genre"}
    )
    assert "01 题材=玄幻（凡人流）" in r.summary
    assert "03 绝对禁止=禁天降外援" in r.summary
    assert "04 吃苦指数=7" in r.summary
    assert "05 本小说斗什么=抢资源" in r.summary


@pytest.mark.asyncio
async def test_read_settings_genre_area_all_unfilled(monkeypatch):
    import genres.service as _gs
    from assistant.tools import ToolContext, run_tool

    async def _none_ctx(root_path, novel_id):
        return None

    monkeypatch.setattr(_gs, "resolve_genre_context", _none_ctx)
    r = await run_tool(
        ToolContext(novel_id="n", root_path="/r", user_id="u"), "read_settings", {"area": "genre"}
    )
    assert "01 题材=未填" in r.summary
    assert "04 吃苦指数=未定" in r.summary


@pytest.mark.asyncio
async def test_read_settings_intro_area(monkeypatch):
    """read_settings intro 区：简介现值；空给「还没有内容」（同区空态口径）。"""
    import filesystem.storage as _st
    from assistant.tools import ToolContext, run_tool

    class _Storage:
        def __init__(self, files: dict):
            self.files = files

        async def read_yaml(self, root, path):
            return self.files.get(path, {}) or {}

    monkeypatch.setattr(
        _st, "get_storage",
        lambda: _Storage({"story.yaml": {"synopsis": "一个夜班守护者的故事"}}),
    )
    r = await run_tool(
        ToolContext(novel_id="n", root_path="/r", user_id="u"), "read_settings", {"area": "intro"}
    )
    assert r.summary == "一个夜班守护者的故事"

    monkeypatch.setattr(_st, "get_storage", lambda: _Storage({}))
    r = await run_tool(
        ToolContext(novel_id="n", root_path="/r", user_id="u"), "read_settings", {"area": "intro"}
    )
    assert r.summary == "（简介还没有内容）"
