"""指纹门禁纯增量迁移（chapter-rewrite 前置能力）与产物归属单源测试。

- inspect_schema / classify_drift / archive_if_legacy 三分支：
  指纹一致→current；纯新增→additive_migration（不改名）；破坏性→留档改名。
- belongs_to_ref：边界感知（主线 ref 不得吞 `-r{8hex}` 旧稿产物）。
"""

import sqlite3
from pathlib import Path

import pytest

import legacy_archive
from backup.format import belongs_to_ref


class _FakeCol:
    def __init__(self, name, type_="TEXT"):
        self.name = name
        self.type = type_

    def __str__(self):
        return self.name


class _FakeTable:
    def __init__(self, name, cols):
        self.name = name
        self.columns = [_FakeCol(c) for c in cols]


class _FakeMeta:
    def __init__(self, tables):
        self.tables = {t.name: t for t in tables}


def _make_db(path: Path, tables: dict[str, list[str]], *, app_meta: bool = True):
    conn = sqlite3.connect(path)
    try:
        for name, cols in tables.items():
            conn.execute(f'CREATE TABLE "{name}" ({", ".join(f"{c} TEXT" for c in cols)})')
        if app_meta:
            conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES ('schema_id', 'oldfingerprint')"
            )
        conn.commit()
    finally:
        conn.close()


META = _FakeMeta([
    _FakeTable("novels", ["id", "name"]),
    _FakeTable("chapters", ["id", "ref", "ghost_of", "stale"]),
    _FakeTable("app_meta", ["key", "value"]),
])


class TestClassifyDrift:
    def test_additive_subset(self):
        old = {"novels": ["id", "name"], "chapters": ["id", "ref"]}
        assert legacy_archive.classify_drift(old, META) == "additive"

    def test_missing_table_is_breaking(self):
        old = {"projects": ["id"]}
        assert legacy_archive.classify_drift(old, META) == "breaking"

    def test_unknown_column_is_breaking(self):
        old = {"chapters": ["id", "ref", "removed_col"]}
        assert legacy_archive.classify_drift(old, META) == "breaking"


class TestArchiveIfLegacy:
    def test_current_fingerprint_noop(self, tmp_path):
        db = tmp_path / "x.db"
        _make_db(db, {"novels": ["id"]})
        # 直接写当前指纹
        conn = sqlite3.connect(db)
        conn.execute("UPDATE app_meta SET value='fp-now' WHERE key='schema_id'")
        conn.commit()
        conn.close()
        info = legacy_archive.archive_if_legacy(db, "fp-now", metadata=META)
        assert info == {"archived": False, "reason": "current"}

    def test_additive_migrates_in_place(self, tmp_path):
        db = tmp_path / "x.db"
        _make_db(db, {"novels": ["id"], "chapters": ["id", "ref"]})
        info = legacy_archive.archive_if_legacy(db, "fp-new", metadata=META)
        assert info["archived"] is False
        assert info["reason"] == "additive_migration"
        assert info["needs_migration"] is True
        # 数据未被动过：库文件仍在原路径、无 legacy 副本
        assert db.exists()
        assert not list(tmp_path.glob("*.legacy-*"))

    def test_breaking_still_archives(self, tmp_path):
        db = tmp_path / "x.db"
        _make_db(db, {"projects": ["id"]})  # 旧表不在新 schema → 破坏性
        info = legacy_archive.archive_if_legacy(db, "fp-new", metadata=META)
        assert info["archived"] is True
        assert info["reason"] == "fingerprint_mismatch"
        assert Path(info["archived_path"]).exists()

    def test_unreadable_archives(self, tmp_path):
        db = tmp_path / "x.db"
        db.write_bytes(b"not a sqlite db")
        info = legacy_archive.archive_if_legacy(db, "fp-new", metadata=META)
        assert info["archived"] is True


class TestBelongsToList:
    def test_boundary_rewrite_ghost_not_swallowed(self):
        assert belongs_to_ref("vol-1-ch-2-note.md", "vol-1-ch-2") is True
        # 旧稿产物（余段 r{8hex}-）不属于主线 ref
        assert belongs_to_ref("vol-1-ch-2-rabcd1234-note.md", "vol-1-ch-2") is False
        # 但属于旧稿自身 ref
        assert belongs_to_ref("vol-1-ch-2-rabcd1234-note.md", "vol-1-ch-2-rabcd1234") is True

    def test_prefix_collision(self):
        # 第 1 章不得吞第 12 章产物（前缀带边界）
        assert belongs_to_ref("vol-1-ch-12-note.md", "vol-1-ch-1") is False
        assert belongs_to_ref("vol-1-ch-1-note.md", "vol-1-ch-1") is True

    def test_archive_naming(self):
        assert belongs_to_ref("vol-1-ch-1-标题-2026.md", "vol-1-ch-1") is True
        assert (
            belongs_to_ref("vol-1-ch-1-rdeadbeef-标题.md", "vol-1-ch-1") is False
        )


pytest.importorskip("sqlite3")
