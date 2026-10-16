"""拆书输入解析（c-deconstruct-book 2.1/11）：编码探测链、纯文本分卷分章、上限常量、入口结构判定。

真实网文形态样本：GBK 编码、「第X章」纯文本行、章内空行、卷标题行；
编码守卫夹具：UTF-16/32（带 BOM 与无 BOM 空字节两种形态）。
"""

import pytest

from deconstruct.textparse import (
    MAX_SOURCE_BYTES,
    decode_text,
    detect_encoding,
    parse_novel,
    structure_verdict,
)

_GBKA_SAMPLE = "第一卷 风起\n第1章 开端\n张三出门买药。\n\n第2章 遇敌\n李四拦路。\n".encode("gb18030")
_UTF_SAMPLE = "序\n第1章 初见\n林晚在渡口。\n第2章 重逢\n阿蓟归来。\n第3章 决裂\n雪落。\n"


def test_detect_encoding_gb18030():
    assert detect_encoding(_GBKA_SAMPLE) == "gb18030"


def test_detect_utf8_sig():
    assert detect_encoding("你好".encode("utf-8-sig")) == "utf-8-sig"


def test_detect_failure_raises():
    # latin-1 下非法的字节序列（GBK 双字节残片）三条链都解不开
    garbage = b"\xff\xff\xfe\xff"
    with pytest.raises(ValueError):
        detect_encoding(garbage)


def test_decode_returns_text_and_encoding():
    text, enc = decode_text(_GBKA_SAMPLE)
    assert enc == "gb18030"
    assert "张三出门买药" in text


def test_parse_chapters_and_volumes():
    text = _UTF_SAMPLE
    result = parse_novel(text)
    assert [c["no"] for c in result["chapters"]] == [1, 2, 3]
    assert result["chapters"][0]["title"] == "第1章 初见"
    assert "林晚在渡口" in result["chapters"][0]["text"]
    assert result["volumes"] == []  # 无卷标题
    assert result["total_chars"] > 0


def test_parse_gbk_chapters():
    text, _ = decode_text(_GBKA_SAMPLE)
    result = parse_novel(text)
    assert [c["title"] for c in result["chapters"]] == ["第1章 开端", "第2章 遇敌"]
    assert result["volumes"][0]["title"] == "第一卷 风起"
    assert result["volumes"][0]["ch_start"] == 1 and result["volumes"][0]["ch_end"] == 2


def test_parse_no_chapter_headings_falls_back_single_chapter():
    result = parse_novel("就是一段没有章节标题的长文。")
    assert len(result["chapters"]) == 1
    assert any("未识别到" in w for w in result["warnings"])


def test_chinese_numeral_chapters():
    text = "第一章 甲\n文一。\n第二章 乙\n文二。\n第十二章 丙\n文三。\n"
    result = parse_novel(text)
    assert [c["no"] for c in result["chapters"]] == [1, 2, 3]


def test_max_source_bytes_constant():
    assert MAX_SOURCE_BYTES == 50 * 1024 * 1024


# ── 编码守卫：UTF-16/32（c-deconstruct-book 11）──────────────────────────────────


def test_utf16_bom_rejected():
    # Python utf-16 codec 带 BOM（Windows 记事本「Unicode」格式）——走 GBK 链只会出乱码
    with pytest.raises(ValueError, match="UTF-16"):
        detect_encoding("第1章 试\n正文".encode("utf-16"))


def test_utf32_bom_rejected():
    raw = b"\xff\xfe\x00\x00" + "第1章 试".encode("utf-32-le")
    with pytest.raises(ValueError, match="UTF-32"):
        detect_encoding(raw)


def test_bomless_utf16_rejected_via_nul_density():
    # 无 BOM 的 UTF-16LE：探测链解得开但满屏空字节（ASCII 形态隔字节即 \x00）——拒收不吞乱码
    raw = ("abc\n" * 2000).encode("utf-16-le")
    with pytest.raises(ValueError, match="空字节"):
        detect_encoding(raw)


def test_nul_below_limit_still_accepted():
    # 偶发空字节不误伤（合法文本空字节占比为 0，千分之二阈值为乱码专用）
    text = "正文" * 5000 + "\x00"
    assert detect_encoding(text.encode("utf-8")) == "utf-8-sig"  # 探测链首位（无 BOM 亦命中）


# ── 入口结构判定（c-deconstruct-book 11）────────────────────────────────────────


def test_verdict_risk_chapterless_large_book():
    parse = parse_novel("这是一本没有章节标题的书。" + "内容" * 20000)  # 4 万字整本单章
    v = structure_verdict(parse)
    assert v["level"] == "risk"
    assert v["chapter_count"] == 1
    assert "未识别到章节标题" in v["issues"][0] and "第X章" in v["issues"][0]


def test_verdict_ok_when_chapterless_below_risk_line():
    # 3 万字线下：拆卡头尾 6000 字尚有覆盖，降级为解析提示（parse warnings 已有），判定不报
    v = structure_verdict(parse_novel("没有章节标题。" + "内容" * 14000))
    assert v["level"] == "ok" and v["issues"] == []


def test_verdict_titled_single_chapter_not_risk():
    # 带章标题的单章大部头不算 risk（超线提示走容量口径，创建不被结构闸拦）
    v = structure_verdict(parse_novel("第1章 试\n" + "字" * 610_000))
    assert v["level"] == "ok" and v["issues"] == []


def test_verdict_warn_avg_chapter_too_long():
    body = "很长的正文。\n" * 4000  # 单章 2.8 万字
    text = "".join(f"第{i}章 标题\n{body}" for i in range(1, 5))
    v = structure_verdict(parse_novel(text))
    assert v["level"] == "warn"
    assert any("远超常见网文章长" in i for i in v["issues"])


def test_verdict_warn_tiny_chapters_toc_like():
    # 6 章里 5 章不足 200 字＝目录行误识别形态
    text = "第1章 甲\n短\n第2章 乙\n短\n第3章 丙\n短\n第4章 丁\n短\n第5章 戊\n短\n第6章 己\n" + "正常正文。" * 300
    v = structure_verdict(parse_novel(text))
    assert v["level"] == "warn"
    assert any("目录" in i for i in v["issues"])


def test_verdict_ok_normal_structure():
    text = "".join(f"第{i}章 标题\n{'正文内容。' * 50}\n" for i in range(1, 12))  # 11 章 × 250 字
    v = structure_verdict(parse_novel(text))
    assert v["level"] == "ok"
    assert v["issues"] == []
    assert v["chapter_count"] == 11
