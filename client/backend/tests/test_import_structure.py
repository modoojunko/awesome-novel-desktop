"""A 路结构契约：连续卷范围校验与活动章序。"""

from novels.import_structure import StructureError, active_chapters, validate_structure


def test_valid_structure_normalizes_titles():
    out = validate_structure([
        {"title": "沉船", "chapter_from": 1, "chapter_to": 24},
        {"title": "灯下", "chapter_from": 25, "chapter_to": 42},
    ], 42)
    assert out == [
        {"title": "沉船", "chapter_from": 1, "chapter_to": 24},
        {"title": "灯下", "chapter_from": 25, "chapter_to": 42},
    ]


def test_gap_rejected():
    try:
        validate_structure([
            {"title": "一", "chapter_from": 1, "chapter_to": 12},
            {"title": "二", "chapter_from": 14, "chapter_to": 42},
        ], 42)
    except StructureError as e:
        assert "第 13 章" in str(e)
    else:
        raise AssertionError("gap should be rejected")


def test_overlap_rejected():
    try:
        validate_structure([
            {"title": "一", "chapter_from": 1, "chapter_to": 12},
            {"title": "二", "chapter_from": 12, "chapter_to": 42},
        ], 42)
    except StructureError as e:
        assert "第 13 章" in str(e)
    else:
        raise AssertionError("overlap should be rejected")


def test_empty_volume_rejected():
    try:
        validate_structure([{"title": "一", "chapter_from": 2, "chapter_to": 2}], 2)
    except StructureError:
        pass
    else:
        raise AssertionError("first volume must start at 1")


def test_missing_tail_rejected():
    try:
        validate_structure([{"title": "一", "chapter_from": 1, "chapter_to": 41}], 42)
    except StructureError as e:
        assert "42" in str(e)
    else:
        raise AssertionError("tail gap should be rejected")


def test_active_chapters_excludes_source_numbers():
    manifest = {"chapters": [
        {"source_no": 1, "title": "a"},
        {"source_no": 2, "title": "b"},
        {"source_no": 3, "title": "c"},
    ]}
    assert [c["source_no"] for c in active_chapters(manifest, [2])] == [1, 3]
    assert [c["source_no"] for c in active_chapters(manifest, None)] == [1, 2, 3]


def test_active_chapters_rejects_unknown_exclusion():
    try:
        active_chapters({"chapters": [{"source_no": 1}]}, [9])
    except StructureError as e:
        assert "9" in str(e)
    else:
        raise AssertionError("unknown exclusion should be rejected")
