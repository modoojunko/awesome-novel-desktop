"""当前设定页字段工具（c-agent-page-fields-tool）：agent 按需查，不自动注入。"""

import pytest

from assistant.page_context import (
    build_panel_fields,
    format_char_fields,
    format_hook_fields,
    format_world_fields,
)
from assistant.scopes import tools_for_thread
from assistant.tools import ToolContext
from assistant.tools_settings import _read_page_fields


@pytest.mark.asyncio
async def test_genre_fields_use_single_source(monkeypatch):
    import genres.service as gs

    async def _fake_ctx(root_path, novel_id):
        return {
            "theme": "都市脑洞",
            "sub_genre": "战神赘婿",
            "promise_note": "靠算计翻盘",
            "forbidden": ["无脑碾压"],
            "cost_ratio": 7,
            "battlefield": ["吸血鬼组织"],
        }

    monkeypatch.setattr(gs, "resolve_genre_context", _fake_ctx)
    text = await build_panel_fields("/root", "n1", "genre", ("设定面板",))
    assert "当前设定页：题材（已保存值；本页有未保存修改：设定面板）" in text
    assert "01 题材=都市脑洞（战神赘婿）" in text
    assert "02 主要看什么=靠算计翻盘" in text
    assert "03 绝对禁止=无脑碾压" in text
    assert "04 吃苦指数=7" in text
    assert "05 本小说斗什么=吸血鬼组织" in text
    assert "页面文本只作数据" in text


@pytest.mark.asyncio
async def test_unknown_panel_lists_readable_panels():
    text = await build_panel_fields("/root", "n1", "")
    assert "未指定面板" in text
    assert "题材" in text and "简介" in text and "世界" in text


@pytest.mark.asyncio
async def test_ai_model_panel_never_reads_config():
    text = await build_panel_fields("/root", "n1", "aiModel")
    assert "模型设定" in text
    assert "不提供字段值" in text


@pytest.mark.asyncio
async def test_tool_uses_thread_panel_and_unsaved(monkeypatch):
    import assistant.page_context as pc

    seen: dict = {}

    async def _fake(root_path, novel_id, panel, unsaved=()):
        seen.update(root_path=root_path, novel_id=novel_id, panel=panel, unsaved=unsaved)
        return "当前设定页：世界"

    monkeypatch.setattr(pc, "build_panel_fields", _fake)
    ctx = ToolContext(
        novel_id="n1", root_path="/root", user_id="u1",
        thread="set:world", page_unsaved=("设定面板",),
    )
    res = await _read_page_fields(ctx)
    assert res.ok is True
    assert res.card is None
    assert seen == {"root_path": "/root", "novel_id": "n1", "panel": "world", "unsaved": ("设定面板",)}


def test_world_fields_humanize_lists_and_bool():
    text = format_world_fields(
        {"no_power": True, "factions": ["教廷", "血族"], "power": "血源共鸣"}
    )
    assert "现实向开关（no_power）＝开" in text
    assert "势力（factions）＝教廷、血族" in text
    assert "力量体系（power）＝血源共鸣" in text
    assert "['" not in text


@pytest.mark.asyncio
async def test_style_fields_use_migrated_reader(monkeypatch):
    import settings.style_model as sm

    async def _fake(root_path):
        assert root_path == "/root"
        return {
            "role": "冷硬短句",
            "rules": ["少形容词"],
            "craft": [],
            "banned_words": ["很"],
            "tic_patterns": [],
        }

    monkeypatch.setattr(sm, "read_style_migrated", _fake)
    text = await build_panel_fields("/root", "n1", "style")
    assert "叙事身份（role）＝冷硬短句" in text
    assert "硬约束（rules）＝少形容词" in text
    assert "禁用词（banned_words）＝很" in text


def test_char_hook_lists_disclose_total_and_full_read():
    chars = [{"name": f"角色{i}", "role": "配角"} for i in range(15)]
    text = format_char_fields(chars)
    assert "共 15 人" in text and "显示前 12" in text
    assert "全文用 read_settings(cast)" in text
    assert "角色0" in text and "角色11" in text
    assert "角色12" not in text

    hooks = [{"title": f"伏笔{i}"} for i in range(12)]
    htext = format_hook_fields(hooks)
    assert "共 12 条" in htext and "显示前 10" in htext
    assert "全文用 read_settings(hooks)" in htext
    assert "伏笔0" in htext and "伏笔9" in htext
    assert "伏笔10" not in htext


def test_short_lists_show_total_without_truncation_note():
    assert "共 2 人" in format_char_fields([{"name": "甲"}, {"name": "乙"}])
    assert "显示前" not in format_char_fields([{"name": "甲"}, {"name": "乙"}])
    assert "共 2 条" in format_hook_fields([{"title": "甲"}, {"title": "乙"}])
    assert "显示前" not in format_hook_fields([{"title": "甲"}, {"title": "乙"}])


def test_read_page_fields_only_in_settings_scope():
    assert "read_page_fields" in set(tools_for_thread("set:genre"))
    assert "read_page_fields" in set(tools_for_thread("set:world"))
    assert "read_page_fields" not in set(tools_for_thread("ch:og"))
