"""拆书输入解析（c-deconstruct-book 2.1）：编码探测链、纯文本分卷分章、上限常量。

真实网文形态样本：GBK 编码、「第X章」纯文本行、章内空行、卷标题行。
"""

import pytest

from deconstruct.textparse import (
    MAX_SOURCE_BYTES,
    decode_text,
    detect_encoding,
    parse_novel,
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
