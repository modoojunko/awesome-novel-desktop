"""拆书输入解析（c-deconstruct-book 2.1）——txt 纯文本专用，不复用 importer。

`novels/importer.py` 的解析按 markdown `##` 标题识章且 utf-8 硬编码，真实网文 txt
（「第X章」纯文本行、GBK/GB18030 编码）走那条路会整本丢弃。本模块为其新建：

- 编码探测链 utf-8(-sig) → gb18030 → big5，全失败抛 ValueError（点名引导转码）；
- 「第X卷 / 第X章」纯文本行正则分卷分章（章优先，无章标题→整本单章＋解析提示）；
- 字数口径与 importer 对齐（去空白计数）。

只做纯函数，不做 IO；夹具用真实网文形态样本（tests/test_deconstruct_textparse.py）。
"""

from __future__ import annotations

import re

MAX_SOURCE_BYTES = 50 * 1024 * 1024

_ENCChain = ("utf-8-sig", "gb18030", "big5")

# 章标题行：第X章/回/节（支持汉字/阿拉伯数字），行内 ≤40 字符，行首可有空格。
_CHAPTER_RE = re.compile(r"^\s*(第[0-9零一二两三四五六七八九十百千]+[章回节][^\n]{0,40})\s*$", re.MULTILINE)
# 卷标题行：第X卷（组内含卷名后缀）
_VOLUME_RE = re.compile(r"^\s*(第[0-9零一二两三四五六七八九十百千]+卷[^\n]{0,40})\s*$", re.MULTILINE)
_WS_RE = re.compile(r"\s+")


def detect_encoding(raw: bytes) -> str:
    """按探测链返回编码名；全失败抛 ValueError（引导换文件/转码，不静默乱码）。"""
    if not raw:
        raise ValueError("文件为空，请重新选择文件")
    for enc in _ENCChain:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文件编码（已尝试 UTF-8/GBK/Big5），请转码为 UTF-8 后重试")


def decode_text(raw: bytes) -> tuple[str, str]:
    """→ (文本, 实际使用的编码名)。"""
    enc = detect_encoding(raw)
    return raw.decode(enc), enc


def count_chars(text: str) -> int:
    """字数口径与 importer 对齐：去除全部空白后计数。"""
    return len(_WS_RE.sub("", text or ""))


def parse_novel(text: str) -> dict:
    """纯文本分卷分章 → 解析结果。

    返回 {"total_chars", "chapters": [{no, title, text}], "volumes": [{title, ch_start, ch_end}],
          "warnings": [str]}。无章标题行 → 整本作为单章（no=1），warning 说明；
    章前序文（封面/简介）并入第 1 章开头。
    """
    warnings: list[str] = []
    chapter_matches = list(_CHAPTER_RE.finditer(text))
    volume_matches = list(_VOLUME_RE.finditer(text))

    if not chapter_matches:
        warnings.append("未识别到「第X章」标题行，按整本单章处理")
        chapters = [{"no": 1, "title": "全本", "text": text}]
    else:
        chapters = []
        # 首章前的前序文（若有）并入第 1 章
        preface = text[: chapter_matches[0].start()].strip()
        for i, m in enumerate(chapter_matches):
            start = m.end()
            end = chapter_matches[i + 1].start() if i + 1 < len(chapter_matches) else len(text)
            body = (preface if i == 0 and preface else "") + text[start:end]
            chapters.append({"no": i + 1, "title": m.group(1).strip(), "text": body})
        if len(chapters) < 3:
            warnings.append(f"仅识别到 {len(chapters)} 章，章节标题可能不规范（按现状拆解）")

    # 卷归属：卷标题行落在哪些章之间
    volumes: list[dict] = []
    if volume_matches:
        for i, vm in enumerate(volume_matches):
            pos = vm.start()
            ch_start = sum(1 for cm in chapter_matches if cm.start() < pos) + 1
            next_pos = volume_matches[i + 1].start() if i + 1 < len(volume_matches) else len(text)
            ch_end = sum(1 for cm in chapter_matches if cm.start() < next_pos)
            if ch_end >= ch_start:
                volumes.append({"title": vm.group(1).strip(), "ch_start": ch_start, "ch_end": ch_end})
        if not volumes:
            warnings.append("识别到卷标题但未能归属章节，已忽略分卷")

    return {
        "total_chars": count_chars(text),
        "chapters": chapters,
        "volumes": volumes,
        "warnings": warnings,
    }
