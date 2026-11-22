"""页面字段上下文（c-agent-page-context）：设定面板字段名＋当前值注入。"""

import pytest

from assistant.page_context import (
    build_page_field_note,
    format_genre_fields,
)


def test_genre_fields_include_all_five_sections():
    text = format_genre_fields(
        {
            "core_promise": "以弱破强的痛快",
            "promise_note": "靠算计翻盘",
            "forbidden_list": [{"text": "无脑碾压"}, {"tagId": "forbidden:free-powerup"}],
            "cost_ratio": 7,
            "battlefield": ["吸血鬼组织", "教廷"],
        },
        {"genre": "都市脑洞", "sub_genre": "战神赘婿"},
    )
    assert "01 题材＝都市脑洞 / 战神赘婿" in text
    assert "02 主要看什么＝以弱破强的痛快；靠算计翻盘" in text
    assert "03 绝对禁止＝无脑碾压、forbidden:free-powerup" in text
    assert "04 吃苦指数＝7" in text
    assert "05 本小说斗什么＝吸血鬼组织、教廷" in text


def test_genre_fields_empty_show_unfilled():
    text = format_genre_fields({}, {})
    assert "01 题材＝未填" in text
    assert "02 主要看什么＝未填" in text
    assert "04 吃苦指数＝未填" in text


@pytest.mark.asyncio
async def test_unknown_panel_returns_empty():
    assert await build_page_field_note(None, "nope") == ""


@pytest.mark.asyncio
async def test_model_panel_returns_panel_label_only():
    text = await build_page_field_note(None, "aiModel")
    assert "模型设定" in text
