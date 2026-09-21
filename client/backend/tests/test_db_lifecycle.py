"""db_lifecycle 状态机测试（db-generation）——specs 场景逐一对应。

D1 破坏性升代首启：v1 代码首启、无 novel-v1.db、有 novel.db → fresh_boot
   ＋旧文件原位不动＋候选检出（specs：库文件代数与首启状态机）
D2 同代 additive 后退旧 build：超集库 → tolerant 放行（现状为误判 breaking
   清空——本测试钉死回归）
D3 隔离件不自动迁入：损坏 v1 库 → .corrupt 隔离＋不进候选
D4 候选扫描排除 -wal/-shm/.bak/空库（现行扫描器实 bug 回归钉死）
D5 current 态直接启动；breaking → 隔离
另：指纹稳定性（自旧套迁移）。
"""

import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import Column, MetaData, String, Table

import db_lifecycle
import legacy_archive  # 兼容薄层：re-export 校验
from db import Base


def _fp(metadata) -> str:
    return db_lifecycle.compute_schema_fingerprint(metadata)


def _write_db(path: Path, tables: dict[str, list[str]], rows: dict[str, list[tuple]] | None = None,
              schema_id: str | None = None):
    conn = sqlite3.connect(path)
    for t, cols in tables.items():
        conn.execute(f"CREATE TABLE {t} ({', '.join(cols)})")
    if schema_id is not None:
        conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO app_meta VALUES ('schema_id', ?)", (schema_id,))
    for t, rs in (rows or {}).items():
        conn.executemany(f"INSERT INTO {t} VALUES ({','.join('?' * len(rs[0]))})", rs)
    conn.commit()
    conn.close()


class TestFingerprint:
    def test_stable(self):
        assert _fp(Base.metadata) == _fp(Base.metadata)

    def test_sensitive(self):
        md1 = MetaData(); Table("a", md1, Column("x", String))
        md2 = MetaData(); Table("a", md2, Column("x", String)); Table("b", md2, Column("y", String))
        assert _fp(md1) != _fp(md2)

    def test_legacy_archive_reexports(self):
        """兼容薄层 re-export 校验（既有 import 面不破）。"""
        assert legacy_archive.SCHEMA_ID_KEY == db_lifecycle.SCHEMA_ID_KEY
        assert legacy_archive.compute_schema_fingerprint is db_lifecycle.compute_schema_fingerprint


class TestBootStateMachine:
    def _simple_meta(self) -> MetaData:
        md = MetaData()
        Table("novels", md, Column("id", String, primary_key=True), Column("name", String))
        return md

    def test_d1_fresh_boot_old_untouched(self, tmp_path):
        """D1：v1 首启无 novel-v1.db（有 novel.db 旧命名）→ fresh_boot，
        旧文件原位不动、候选检出。"""
        old = tmp_path / "novel.db"
        _write_db(old, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]},
                  rows={"novels": [("b1", "书一"), ("b2", "书二"), ("b3", "书三")]})
        before = old.read_bytes()

        result = db_lifecycle.boot_lifecycle(tmp_path / "novel-v1.db", self._simple_meta(), "fp1")
        assert result["boot"] == "fresh_boot"
        assert old.read_bytes() == before, "旧库必须字节不变"
        cands = db_lifecycle.scan_migration_candidates(tmp_path, 1)
        assert [c["filename"] for c in cands] == ["novel.db"]
        assert cands[0]["book_count"] == 3

    def test_current_direct_boot(self, tmp_path):
        db = tmp_path / "novel-v1.db"
        fp = _fp(self._simple_meta())
        _write_db(db, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]}, schema_id=fp)
        result = db_lifecycle.boot_lifecycle(db, self._simple_meta(), fp)
        assert result["boot"] == "current"

    def test_d2_tolerant_superset_not_quarantined(self, tmp_path):
        """D2：库为超集（多一列）→ tolerant 放行不隔离（现状回归钉死：
        旧 classify_drift 判 breaking→整库留档清空）。"""
        md = self._simple_meta()
        db = tmp_path / "novel-v1.db"
        # 无 schema_id（指纹必不符）＋多 extra_col 列（metadata 没有）
        _write_db(db, {"novels": ["id TEXT PRIMARY KEY", "name TEXT", "extra_col TEXT"]},
                  rows={"novels": [("b1", "书一", "x")]})
        result = db_lifecycle.boot_lifecycle(db, md, "fp-not-matching")
        assert result["boot"] == "tolerant_booted", result
        assert db.exists(), "tolerant 不得隔离/改名"
        assert "extra_col" in result["extra_cols"]["novels"]

    def test_additive_subset(self, tmp_path):
        """库为子集（缺列）→ additive_booted 带补列计划。"""
        md = MetaData()
        Table("novels", md, Column("id", String, primary_key=True),
              Column("name", String), Column("source", String))
        db = tmp_path / "novel-v1.db"
        _write_db(db, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]})
        result = db_lifecycle.boot_lifecycle(db, md, "fp")
        assert result["boot"] == "additive_booted"
        assert result["additive_tables"]["novels"] == ["source"]

    def test_d3_unreadable_quarantined_not_candidate(self, tmp_path):
        """D3：损坏 v1 库 → .corrupt 隔离；隔离件不进迁入候选。"""
        db = tmp_path / "novel-v1.db"
        db.write_bytes(b"not a sqlite file at all" * 100)
        result = db_lifecycle.boot_lifecycle(db, self._simple_meta(), "fp")
        assert result["boot"] == "quarantined_new"
        assert result["quarantined_to"] and ".corrupt-" in result["quarantined_to"]
        cands = db_lifecycle.scan_migration_candidates(tmp_path, 1)
        # 损坏件（.corrupt-*）不进候选（generation_of 返回 None——带 .corrupt 后缀）
        assert all(".corrupt" not in c["filename"] for c in cands)

    def test_breaking_quarantined(self, tmp_path):
        """列类型/集合既非子集也非安全超集 → breaking 隔离。"""
        md = self._simple_meta()
        db = tmp_path / "novel-v1.db"
        # novels 列改名（id→pk）：子集不成立（metadata 的 id 缺）；超集不成立（pk 不在 metadata）
        _write_db(db, {"novels": ["pk TEXT PRIMARY KEY", "name TEXT", "other TEXT"]})
        result = db_lifecycle.boot_lifecycle(db, md, "fp")
        assert result["boot"] == "quarantined_new"


class TestCandidateScan:
    def test_d4_excludes_wal_shm_bak_and_empty(self, tmp_path):
        """D4：-wal/-shm/.bak 不进候选（现行扫描器实 bug：WAL 常是 mtime
        最新→book_count 取自不可读文件）；空库剔除。"""
        good = tmp_path / "novel.db"
        _write_db(good, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]},
                  rows={"novels": [("b1", "书一")]})
        (tmp_path / "novel.db-wal").write_bytes(b"\x00" * 64)
        (tmp_path / "novel.db-shm").write_bytes(b"\x00" * 32)
        (tmp_path / "novel.db.bak-20260919").write_bytes(b"\x00" * 16)
        empty = tmp_path / "novel-v0.db"
        _write_db(empty, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]})
        cands = db_lifecycle.scan_migration_candidates(tmp_path, 1)
        names = [c["filename"] for c in cands]
        assert names == ["novel.db"], names
        assert all(not n.endswith(("-wal", "-shm")) and ".bak" not in n for n in names)

    def test_generation_priority(self, tmp_path):
        """v3>v2>novel.db 排序；.legacy-* 计第 0 代。"""
        for name, books in [("novel-v2.db", 2), ("novel-v3.db", 5),
                            ("novel.db.legacy-20260901-0", 7)]:
            _write_db(tmp_path / name, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]},
                      rows={"novels": [(f"b{i}", "书") for i in range(books)]})
        cands = db_lifecycle.scan_migration_candidates(tmp_path, 4)
        assert [c["generation"] for c in cands] == [3, 2, 0]

# ── 补列自检（检视 P2-9）─────────────────────────────────────────────────


class TestUnregisteredMissingColumns:
    """现有库缺列 × 未登记 → 点名（空＝健康）。"""

    def test_clean_when_registry_complete(self, tmp_path):
        import asyncio

        from sqlalchemy.ext.asyncio import create_async_engine

        import models  # noqa: F401 —— 注册 metadata
        from db import Base
        from db_lifecycle import unregistered_missing_columns

        db_path = tmp_path / "gen.db"

        async def run():
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            missing = await unregistered_missing_columns(engine)
            await engine.dispose()
            return missing

        assert asyncio.run(run()) == []

    def test_points_at_unregistered_missing_column(self, tmp_path):
        import asyncio

        from sqlalchemy.ext.asyncio import create_async_engine

        import models  # noqa: F401
        from db import Base
        from db_lifecycle import unregistered_missing_columns

        db_path = tmp_path / "gen2.db"

        async def run():
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                # 模拟「库缺列且注册表没登记」：造一个不带 volume 列的 volumes 表
                await conn.exec_driver_sql("DROP TABLE volumes")
                await conn.exec_driver_sql(
                    "CREATE TABLE volumes (id VARCHAR(36) PRIMARY KEY, novel_id VARCHAR(36))"
                )
            missing = await unregistered_missing_columns(engine)
            await engine.dispose()
            return missing

        found = asyncio.run(run())
        # 未登记的缺列被点名
        assert "volumes.title" in found
        assert "volumes.core_conflict" in found
        # 已登记的两列不算（注册表里就有 → 由 apply_additive_columns 负责补）
        assert "volumes.antagonist_type" not in found
        assert "volumes.antagonist_line" not in found
