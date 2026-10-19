"""A 路 txt manifest：冻结解析事实、正文区间、标题归一。"""

import hashlib

from deconstruct.textparse import (
    build_manifest,
    normalize_chapter_title,
    normalize_volume_title,
)
from novels.import_writer import slice_import_prose


def test_manifest_freezes_source_and_ranges():
    text = "序言\n第一卷 风起\n第1章 开端\n张三出门买药。\n\n第2章 遇敌\n李四拦路。\n"
    raw = text.encode("utf-8")
    m = build_manifest(raw, "长夜灯.txt")
    assert m["schema"] == 1
    assert m["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert m["encoding"] in ("utf-8", "utf-8-sig")
    assert m["filename"] == "长夜灯.txt"
    assert len(m["chapters"]) == 2
    ch1 = m["chapters"][0]
    assert ch1["source_no"] == 1 and ch1["idx"] == 1
    assert ch1["title"] == "开端" and ch1["title_raw"] == "第1章 开端"
    assert ch1["char_start"] == 0
    rebuilt = "".join(text[a:b] for a, b in ch1["body_ranges"]).strip()
    assert "序言" in rebuilt and "张三出门买药" in rebuilt
    assert "第1章" not in rebuilt
    assert m["volumes"] == [{"title": "风起", "title_raw": "第一卷 风起", "chapter_from": 1, "chapter_to": 2}]
    assert len(m["volume_heading_ranges"]) == 1
    assert m["risk"]["chapter_count"] == 2


def test_manifest_without_volume_title_keeps_empty_volumes():
    m = build_manifest("第1章 初见\n林晚在渡口。\n第2章 重逢\n阿蓟归来。\n".encode())
    assert m["volumes"] == []
    assert [c["title"] for c in m["chapters"]] == ["初见", "重逢"]
    assert m["chapters"][1]["volume_title"] == ""


def test_title_normalizers_strip_numbering_once():
    assert normalize_chapter_title("第十二章 灯下") == "灯下"
    assert normalize_chapter_title("第3回：归乡") == "归乡"
    assert normalize_chapter_title("没有序号") == "没有序号"
    assert normalize_volume_title("第二卷 · 灯下") == "灯下"
    assert normalize_volume_title("没有卷名") == "没有卷名"


def test_prose_line_starting_with_volume_is_not_stripped():
    """正文里恰好以「第一卷…」开头的短句不是卷标题，不得静默删掉。"""
    text = (
        "第1章 开端\n"
        "第一卷已经写完，我们该出发了。\n"
        "他把门带上。\n"
        "第2章 出发\n"
        "天还没亮。\n"
    )
    m = build_manifest(text.encode())
    assert m["volumes"] == []
    assert m["volume_heading_ranges"] == []
    ch1 = m["chapters"][0]
    prose = slice_import_prose(
        text, ch1["body_ranges"], m["volume_heading_ranges"]
    )
    assert "第一卷已经写完，我们该出发了。" in prose
    assert "他把门带上。" in prose


def test_slice_removes_only_frozen_volume_heading_ranges():
    text = "第一卷 风起\n第1章 开端\n张三出门。\n第二卷 雨落\n第2章 遇敌\n李四拦路。\n"
    m = build_manifest(text.encode())
    first = slice_import_prose(
        text, m["chapters"][0]["body_ranges"], m["volume_heading_ranges"]
    )
    assert first.strip() == "张三出门。"
    second = slice_import_prose(
        text, m["chapters"][1]["body_ranges"], m["volume_heading_ranges"]
    )
    assert second.strip() == "李四拦路。"


def test_manifest_rejects_absurd_chapter_density():
    import pytest

    from deconstruct.textparse import MAX_CHAPTERS

    text = "\n".join(f"第{i}章 x" for i in range(MAX_CHAPTERS + 1))
    with pytest.raises(ValueError, match="章节标题超过"):
        build_manifest(text.encode())


def test_manifest_240_chapters():
    text = "第一卷 大书\n" + "\n".join(
        f"第{i}章 第{i}节\n" + "内容" * 50 for i in range(1, 241)
    )
    m = build_manifest(text.encode("utf-8"), "大书.txt")
    assert len(m["chapters"]) == 240
    assert m["chapters"][0]["source_no"] == 1
    assert m["chapters"][-1]["source_no"] == 240
    assert m["volumes"][0]["chapter_to"] == 240

