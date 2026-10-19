"""A 路结构契约：活动章序、连续卷范围、每卷非空。

前端与后端共用同一组 fixtures 口径；后端在落库前必须再校验一次。
"""

from __future__ import annotations

from typing import Any


class StructureError(ValueError):
    """结构不合法：缺口/重叠/空卷/越界/没有活动章。"""


def active_chapters(manifest: dict, excluded_source_nos: list[int] | None) -> list[dict]:
    """manifest 的章按 source_no 去掉「不导入」章，返回活动章序。"""
    chapters = list(manifest.get("chapters") or [])
    known = {int(c["source_no"]) for c in chapters}
    excluded = {int(n) for n in (excluded_source_nos or [])}
    unknown = excluded - known
    if unknown:
        raise StructureError(f"忽略列表包含未知章：{sorted(unknown)}")
    active = [c for c in chapters if int(c["source_no"]) not in excluded]
    if not active:
        raise StructureError("至少保留一章")
    return active


def _get(vol: Any, key: str) -> Any:
    if isinstance(vol, dict):
        return vol.get(key)
    return getattr(vol, key, None)


def validate_structure(volumes: list[Any], chapter_count: int) -> list[dict]:
    """校验并归一化卷结构；返回 [{title, chapter_from, chapter_to}]。

    规则：首卷从 1、末卷到 chapter_count、相邻卷首尾相接、每卷至少 1 章。
    卷名允许空（落库时回落「第N卷」）。
    """
    if chapter_count <= 0:
        raise StructureError("没有可导入的章节")
    if not volumes:
        raise StructureError("至少需要一卷")

    out: list[dict] = []
    expected = 1
    for i, vol in enumerate(volumes, start=1):
        try:
            start = int(_get(vol, "chapter_from"))
            end = int(_get(vol, "chapter_to"))
        except (TypeError, ValueError):
            raise StructureError(f"第{i}卷的章范围不是整数") from None
        if start != expected:
            raise StructureError(f"第{i}卷应从第 {expected} 章开始，实际为第 {start} 章")
        if end < start:
            raise StructureError(f"第{i}卷的结束章不能早于开始章")
        if end > chapter_count:
            raise StructureError(f"第{i}卷结束章 {end} 超出总章数 {chapter_count}")
        out.append({
            "title": str(_get(vol, "title") or "").strip(),
            "chapter_from": start,
            "chapter_to": end,
        })
        expected = end + 1

    if expected != chapter_count + 1:
        raise StructureError(
            f"分卷未覆盖全部章：最后一卷到第 {expected - 1} 章，共 {chapter_count} 章"
        )
    return out
