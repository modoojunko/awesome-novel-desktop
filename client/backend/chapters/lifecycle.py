"""章节生命周期谓词单源（c-import-direct）。

历史章＝origin=import 且未归档；完本分母只数 origin!=import 的 archived 章。
所有跨模块判断都应调用这里，禁止各写一套 status == "archived"。
"""

from __future__ import annotations

from typing import Any


def _get(ch: Any, key: str, default: Any = None) -> Any:
    if isinstance(ch, dict):
        return ch.get(key, default)
    return getattr(ch, key, default)


def is_archived(ch: Any) -> bool:
    return _get(ch, "status") == "archived"


def is_imported(ch: Any) -> bool:
    return _get(ch, "origin") == "import"


def is_historical(ch: Any) -> bool:
    """导入的既有章（未归档）：可编辑、跳 frontier、不计完本。"""
    return is_imported(ch) and not is_archived(ch)


def is_imported_archived(ch: Any) -> bool:
    return is_imported(ch) and is_archived(ch)


def counts_toward_completion(ch: Any) -> bool:
    """完本分子/分母口径：作者章且已归档。"""
    return is_archived(ch) and not is_imported(ch)
