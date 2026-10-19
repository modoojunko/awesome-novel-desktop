"""全书章号派生（c-import-direct）：卷序累计，不落库、不重排 ref。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _vol_no(ref: str) -> int:
    try:
        return int((ref or "").split("-")[1])
    except (IndexError, ValueError):
        return 0


def global_number_map(chapters: Iterable[Any]) -> dict[str, int]:
    """按 (卷号, 卷内章号) 排序，返回 ref → 全书第 N 章。"""
    rows = list(chapters)
    rows.sort(key=lambda c: (_vol_no(getattr(c, "ref", "") if not isinstance(c, dict) else c.get("ref", "")),
                             getattr(c, "chapter_no", 0) if not isinstance(c, dict) else c.get("chapter_no", 0)))
    out: dict[str, int] = {}
    for i, c in enumerate(rows, start=1):
        ref = getattr(c, "ref", None) if not isinstance(c, dict) else c.get("ref")
        if ref:
            out[str(ref)] = i
    return out


def global_no_of(ref: str, chapters: Iterable[Any]) -> int:
    return global_number_map(chapters).get(ref, 0)
