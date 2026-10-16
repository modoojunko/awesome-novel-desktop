"""拆书输入解析（c-deconstruct-book 2.1）——txt 纯文本专用，不复用 importer。

`novels/importer.py` 的解析按 markdown `##` 标题识章且 utf-8 硬编码，真实网文 txt
（「第X章」纯文本行、GBK/GB18030 编码）走那条路会整本丢弃。本模块为其新建：

- 编码探测链 utf-8(-sig) → gb18030 → big5，全失败抛 ValueError（点名引导转码）；
  UTF-16/32（带 BOM 或解出大量空字节）单列报错——混进 GBK 探测链只会静默乱码；
- 「第X卷 / 第X章」纯文本行正则分卷分章（章优先，无章标题→整本单章＋解析提示）；
- 字数口径与 importer 对齐（去空白计数）；
- structure_verdict 入口结构判定（ok/warn/risk＋问题清单），与前端 lib/deconstructStructure
  同规则（阈值由 test_shared_constants_parity 对拍钉死）。

只做纯函数，不做 IO；夹具用真实网文形态样本（tests/test_deconstruct_textparse.py）。
"""

from __future__ import annotations

import re

MAX_SOURCE_BYTES = 50 * 1024 * 1024

_ENCChain = ("utf-8-sig", "gb18030", "big5")

# 无 BOM 的 UTF-16/32 被当 GBK/Big5 解出来会满屏空字节——按「解失败」处理落到专用文案，
# 不让乱码静默进库。正常文本空字节占比为 0，阈值取千分之二已远高于任何合法形态。
# 与前端 lib/deconstructStructure 的 NUL_RATIO_LIMIT parity 对拍（test_shared_constants_parity）。
NUL_RATIO_LIMIT = 0.002

# 入口结构判定阈值（与前端 lib/deconstructStructure 同规则，test_shared_constants_parity 对拍）：
# 无章节标题且全书超 3 万字 → risk（拆卡单章只喂头 4000＋尾 2000，大部头几乎读不到）；
# 平均章长超 2 万 → 章标题疑似漏识别；极短章达 max(5, 30%) → 目录行误识别嫌疑。
SINGLE_CHAPTER_RISK_CHARS = 30_000
AVG_CHAPTER_WARN_CHARS = 20_000
TINY_CHAPTER_CHARS = 200
TINY_CHAPTER_MIN_COUNT = 5

# 章标题行：第X章/回/节（支持汉字/阿拉伯数字），行内 ≤40 字符，行首可有空格。
_CHAPTER_RE = re.compile(r"^\s*(第[0-9零一二两三四五六七八九十百千]+[章回节][^\n]{0,40})\s*$", re.MULTILINE)
# 卷标题行：第X卷（组内含卷名后缀）
_VOLUME_RE = re.compile(r"^\s*(第[0-9零一二两三四五六七八九十百千]+卷[^\n]{0,40})\s*$", re.MULTILINE)
_WS_RE = re.compile(r"\s+")


def detect_encoding(raw: bytes) -> str:
    """按探测链返回编码名；全失败抛 ValueError（引导换文件/转码，不静默乱码）。

    UTF-16/32 先按 BOM 直判（Windows「Unicode」格式常见，走 GBK 探测链只会出乱码）；
    无 BOM 但解出大量空字节同样视为解失败——宁可拦下引导转码，不吞静默乱码。
    """
    if not raw:
        raise ValueError("文件为空，请重新选择文件")
    if raw.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        raise ValueError("文件是 UTF-32 编码，请在编辑器中另存为 UTF-8 后重试")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ValueError("文件是 UTF-16 编码（Windows「Unicode」格式），请另存为 UTF-8 后重试")
    nul_seen = False
    for enc in _ENCChain:
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if text.count("\x00") > len(text) * NUL_RATIO_LIMIT:
            nul_seen = True  # 解出来也是乱码（典型：无 BOM UTF-16 被当 GBK），试下一条
            continue
        return enc
    if nul_seen:
        raise ValueError("文件内容疑似 UTF-16 等宽字节编码（解出大量空字节），请另存为 UTF-8 后重试")
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


def structure_verdict(parse: dict) -> dict:
    """入口结构判定 → {"level": ok|warn|risk, "issues": [str], "chapter_count", "avg_chapter_chars"}。

    risk＝未识别到章标题（整本单章回退）且全书超 3 万字——拆卡单章只喂头尾 6000 字，
    大部头几乎读不到；带章标题的单章不算（容量与章长另有提示口径）。
    warn＝平均章长异常（章标题疑似漏识别）或极短章扎堆（目录行误识别嫌疑）。
    只判定不拦截：risk 由前端「仍要创建」确认闸放行，问题清单随 parse_warnings 落库展示。
    """
    chapters = parse.get("chapters") or []
    n = len(chapters)
    total = int(parse.get("total_chars") or 0)
    avg = total // n if n else 0
    chapterless = any("未识别到" in w for w in (parse.get("warnings") or []))
    risk = chapterless and n <= 1 and total >= SINGLE_CHAPTER_RISK_CHARS
    issues: list[str] = []
    if risk:
        issues.append(
            f"未识别到章节标题：全书 {total} 字将按单章拆解，而拆卡只分析每章开头/结尾约 6000 字——"
            "大部头几乎不会被读到，质量会很差。建议规范章节标题（每章一行「第X章 标题」）后重传"
        )
    else:
        if avg > AVG_CHAPTER_WARN_CHARS and n >= 3:
            issues.append(f"平均每章约 {avg} 字，远超常见网文章长——部分章标题可能漏识别，章节切分可能不准")
        tiny = sum(1 for c in chapters if count_chars(c.get("text") or "") < TINY_CHAPTER_CHARS)
        if tiny >= max(TINY_CHAPTER_MIN_COUNT, n * 3 // 10):
            issues.append(f"{tiny}/{n} 章不足 {TINY_CHAPTER_CHARS} 字——可能把目录行误认为章标题，建议删除目录后重传")
    return {
        "level": "risk" if risk else ("warn" if issues else "ok"),
        "issues": issues,
        "chapter_count": n,
        "avg_chapter_chars": avg,
    }
