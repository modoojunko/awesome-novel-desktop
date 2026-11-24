"""页面字段说明书（read_page_schema，c-agent-field-write-parity）。

agent 先看本页字段元数据（页面说法/别名 → 字段键｜类型/上限｜写入口），再按
作家说法精确/语义匹配；本测试钉住各页内容与页签可见性。
"""

import asyncio
from types import SimpleNamespace

from assistant.page_schema import render_page_schema
from assistant.scopes import tools_for_thread
from assistant.tools import TOOL_REGISTRY, ToolContext, get_tool


def test_genre_schema_maps_page_words_to_keys():
    text = render_page_schema("set:genre")
    assert "当前页面：设定 · 题材" in text
    assert "01 题材" in text and "theme/sub_genre" in text
    assert "主要看什么" in text and "promise_note" in text and "≤200 字" in text
    assert "主要看什么 · 标签" in text and "core_promise" in text and "≤60 字" in text
    assert "不直接写" in text  # 02 标签只走采纳卡
    # 旧叫法「核心承诺」不挂标签：它历史上指主字段，挂标签会重演写错槽
    assert "核心承诺" not in text
    assert "write_settings_field" in text
    assert "read_page_fields" in text  # 现值另查


def test_world_schema_documents_native_types():
    text = render_page_schema("set:world")
    assert "现实向开关" in text and "no_power" in text and "布尔" in text
    assert "历史与旧账" in text and "history" in text and "{key,value}" in text
    assert "势力" in text and "factions" in text and "{name,note}" in text
    assert "≤100 条" in text and "≤6 条" in text


def test_chapter_schema_matches_outline_page():
    text = render_page_schema("ch:og")
    assert "当前页面：章纲" in text
    assert "章纲概要" in text and "summary" in text
    assert "禁止事项" in text and "prohibitions" in text
    assert "剧情" in text and "plot_items" in text
    assert "六档" in text and "plot_stage" in text
    assert "write_chapter_fields" in text


def test_volume_schema_lists_writable_fields():
    text = render_page_schema("vol")
    assert "本卷主旨" in text and "summary" in text
    assert "主要冲突" in text and "core_conflict" in text
    assert "章数目标" in text and "chapter_target" in text
    assert "write_volume_fields" in text

    from assistant.page_schema import volume_field_labels

    labels = volume_field_labels()
    assert labels["title"] == "卷名"
    assert labels["chapter_target"] == "章数目标"


def test_read_chapter_renders_all_chapter_fields(monkeypatch):
    """章纲读值逐格人话：memo/情绪/剧情等此前完全不出现（review P2）。"""
    import chapters.store as store_mod

    async def _fake_load(root, ref):
        return {
            "title": "第2章",
            "outline": {"summary": "新概要", "characters": ["林野"]},
            "memo": {"required_changes": ["必须变"], "prohibitions": ["别这样"]},
            "emotional_design": {"primary_mood": "紧绷"},
            "challenge": "旧挑战",
            "plot_stage": "冲突初现",
            "ladder_exit": "停在门口",
            "plot_items": ["场景一"],
            "word_target": 3000,
            "prose": "",
        }

    monkeypatch.setattr(store_mod, "load_chapter", _fake_load)
    tool = get_tool("read_chapter")
    ctx = ToolContext(novel_id="n1", root_path="/tmp/book", user_id="u1")
    res = asyncio.run(tool.fn(ctx, "vol-1-ch-2"))
    text = res.summary
    for label in (
        "章纲概要", "出场角色", "碰到的挑战", "阶段", "章末落点",
        "剧情", "必须完成的变化", "禁止事项", "主情绪", "本章目标字数",
    ):
        assert label in text, label
    assert "必须完成的变化：必须变" in text
    assert "禁止事项：别这样" in text
    assert "主情绪：紧绷" in text
    assert "本章目标字数：3000" in text


def test_read_outline_volume_renders_all_fields(monkeypatch):
    """卷纲读值包含卷名与章数目标（此前 read_outline 漏这两格）。"""
    import db as db_mod
    import repositories.volume_repo as vrepo

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    async def _fake_list(session, novel_id):
        return [
            SimpleNamespace(
                volume_no=1, title="第一卷", summary="本卷主旨",
                core_conflict="主要冲突", ending="卷末结局", chapter_target=12,
                antagonist_type="人物", antagonist_line="反派的一句话",
            )
        ]

    monkeypatch.setattr(db_mod, "async_session", lambda: _Session())
    monkeypatch.setattr(vrepo, "list_by_project", _fake_list)
    tool = get_tool("read_outline")
    ctx = ToolContext(novel_id="n1", root_path="/tmp/book", user_id="u1")
    res = asyncio.run(tool.fn(ctx, "volume"))
    text = res.summary
    assert "卷名：第一卷" in text
    assert "章数目标：12" in text
    assert "本卷主旨：本卷主旨" in text
    assert "坎的类型：人物" in text


def test_unsupported_pages_say_so():
    text = render_page_schema("set:chars")
    assert "设定 · 角色" in text
    assert "没有字段级写入口" in text
    assert "read_page_fields" in text


def test_read_page_schema_tool_reads_current_thread():
    tool = get_tool("read_page_schema")
    assert tool is not None and tool.fn is not None and tool.kind == "read"
    ctx = ToolContext(novel_id="n1", root_path="/tmp/book", user_id="u1", thread="set:world")
    res = asyncio.run(tool.fn(ctx))
    assert res.ok and "世界舞台" in res.summary and "no_power" in res.summary


def test_read_page_schema_scoped_to_field_pages():
    assert "read_page_schema" in tools_for_thread("set:genre")
    assert "read_page_schema" in tools_for_thread("set:world")
    assert "read_page_schema" in tools_for_thread("ch:og")
    assert "read_page_schema" in tools_for_thread("vol")
    assert "read_page_schema" not in tools_for_thread("ch:prose")


def test_every_registered_tool_is_reachable():
    from assistant.scopes import validate_scopes

    assert validate_scopes({t.name for t in TOOL_REGISTRY}) == []
