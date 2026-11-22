"""题材目录选择（c-agent-genre-pick）：读目录 -> 出采纳卡，校验封闭目录。"""

import pytest

# 先完成注册表装配，避免 tools_settings 循环导入
import assistant.tools  # noqa: F401
from assistant.scopes import tools_for_thread
from assistant.tools_settings import _read_genre_catalog, _settings_genre_pick


@pytest.mark.asyncio
async def test_read_genre_catalog_lists_closed_catalog():
    res = await _read_genre_catalog(None)
    assert res.ok is True
    assert res.card is None
    assert "都市" in res.summary
    assert "都市职场" in res.summary
    assert "只能从这里选" in res.summary


@pytest.mark.asyncio
async def test_pick_emits_catalog_card_without_writing():
    res = await _settings_genre_pick(
        None, theme="都市", sub_genre="都市职场", note="书名带夜班"
    )
    assert res.ok is True
    assert res.card == {
        "kind": "text",
        "payload": {
            "stype": "genre",
            "field": "catalog",
            "value": {"theme": "都市", "sub_genre": "都市职场", "note": "书名带夜班"},
        },
    }
    assert "01 题材" in res.summary


@pytest.mark.asyncio
async def test_pick_allows_theme_only():
    res = await _settings_genre_pick(None, theme="都市", sub_genre="", note="")
    assert res.ok is True
    assert res.card["payload"]["value"] == {"theme": "都市", "sub_genre": "", "note": ""}


@pytest.mark.asyncio
async def test_pick_rejects_unknown_theme_with_readable_list():
    res = await _settings_genre_pick(None, theme="不存在的题材")
    assert res.ok is False
    assert res.card is None
    assert "只能从目录" in res.summary


@pytest.mark.asyncio
async def test_pick_rejects_sub_not_under_theme():
    res = await _settings_genre_pick(None, theme="都市", sub_genre="都市职场2")
    assert res.ok is False
    assert res.card is None
    assert "可选" in res.summary


def test_both_tools_declared_in_genre_scope():
    names = set(tools_for_thread("set:genre"))
    assert {"read_genre_catalog", "settings_genre_pick"} <= names


def test_genre_prime_hint_reads_catalog_on_narrow_intent():
    from assistant.router import genre_prime_hint

    want = {"tool": "read_genre_catalog", "args": {}}
    assert genre_prime_hint("set:genre", "根据标题，帮我选定题材") == want
    assert genre_prime_hint("set:genre", "帮我选个题材") == want
    assert genre_prime_hint("set:genre", "这本书算什么题材") == want
    # 显式 tool_hint 优先；域外/非选题材不 prime
    explicit = {"tool": "settings_intro", "args": {"action": "draft"}}
    assert genre_prime_hint("set:genre", "根据标题帮我选题材", explicit) == explicit
    assert genre_prime_hint("ch:og", "根据标题帮我选题材") is None
    assert genre_prime_hint("set:genre", "给我几个爽点") is None
