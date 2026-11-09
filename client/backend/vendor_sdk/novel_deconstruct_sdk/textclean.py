"""文本清洗纯函数（章锚剥除；SDK 自包含——C 端 kb/migrate_library 同源维护）。"""

from __future__ import annotations

import re
from typing import Any

# 嵌套感知的章锚：尾括号组内含「第N章」字样即整组算锚，全局替换；
# 「（泛指）」等不含章号的括号不动。
_KB_CHAPTER_ANCHOR_RE = re.compile(
    r"（(?=[^（）]*第[\d零一二三四五六七八九十百]+章)[^（）]*(?:（[^（）]*）[^（）]*)*）"
)


def strip_chapter_anchor(value: str) -> str:
    """剥字符串内的章节锚（含嵌套形，全局替换）；无锚原样返回。"""
    return _KB_CHAPTER_ANCHOR_RE.sub("", str(value or "")).strip()


def strip_anchors_deep(value: Any) -> Any:
    """递归剥：dict/list 逐值下探，str 剥锚。"""
    if isinstance(value, str):
        return strip_chapter_anchor(value)
    if isinstance(value, list):
        return [strip_chapter_anchor(x) if isinstance(x, str) else x for x in value]
    return value
