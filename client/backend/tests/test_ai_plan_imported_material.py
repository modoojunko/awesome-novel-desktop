"""拆章素材：导入章原文短摘录块（最近优先、≤2000 字、不混入摘要槽）。"""

from types import SimpleNamespace

from chapters.ai_plan import _imported_excerpt_block


def _row(no: int, title: str, text: str, origin: str = "import", ref: str = ""):
    return SimpleNamespace(
        chapter_no=no,
        title=title,
        origin=origin,
        ref=ref,
        content=SimpleNamespace(prose=text),
    )


def test_excerpt_block_includes_historical_only_and_budget():
    rows = [
        _row(1, "开端", "开" * 80),
        _row(2, "遇敌", "遇" * 80),
        _row(3, "归乡", "归" * 80),
        _row(4, "作者章", "作" * 80, origin="authored"),
    ]
    out = _imported_excerpt_block(rows)
    assert "第1章 开端" in out
    assert "第2章 遇敌" in out
    assert "第3章 归乡" in out
    assert "作者章" not in out
    assert len(out) <= 2000


def test_excerpt_block_keeps_recent_when_over_budget():
    rows = [_row(i, f"第{i}章", "字" * 200) for i in range(1, 31)]
    out = _imported_excerpt_block(rows, total_limit=500)
    assert len(out) <= 500
    assert "第30章" in out
    assert "第1章" not in out


def test_excerpt_block_skips_empty_prose():
    rows = [_row(1, "空章", ""), _row(2, "有字", "字" * 10)]
    out = _imported_excerpt_block(rows)
    assert "空章" not in out
    assert "第2章 有字" in out


def test_excerpt_block_uses_global_number():
    rows = [_row(19, "归乡", "雪落。", ref="vol-2-ch-19")]
    out = _imported_excerpt_block(rows, global_map={"vol-2-ch-19": 43})
    assert "第43章 归乡" in out
