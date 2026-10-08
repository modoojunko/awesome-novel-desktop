"""db_lifecycle 状态机测试（c-db-per-version）——specs 场景逐一对应。

V1 每版新建自己的库：当前版本库不存在、盘上有第 0 代 `novel.db` → fresh_boot
   ＋旧文件原位不动＋候选检出
V2 current 态直接启动（指纹匹配）
V3 形状不符分流：可读而异形 → `.mismatch-<stamp>` 且**可作候选带回**（同 tag
   重打包/删 tag 重打/dev 连续开发三种事故的出口——原 tolerant/additive 两态已退役）
V4 损坏库 → `.corrupt-<stamp>` 隔离＋不进候选＋只读可见
V5 空壳（0 表无 schema_id）→ fresh_boot 复用，不积隔离件
V6 候选扫描白名单形状枚举：边车/`.bak`/磁盘残件/空库/空壳/`migration-staging` 全排除
V7 排序：语义化版本降序 → 遗留代数名 → 第 0 代 → dev 哨兵；遗留名不得被版本过滤排除
另：指纹稳定性（自旧套迁移）。
"""

import sqlite3
import time
from pathlib import Path

import pytest
from sqlalchemy import Column, MetaData, String, Table

import db_lifecycle
import legacy_archive  # 兼容薄层：re-export 校验
from db import Base
from schema_version import db_filename_for

CUR = db_filename_for("0.25")          # 被测「当前版本」库名
LEGACY = "novel-v1.db"                 # 遗留代数名（本 change 之前的落地形态）


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

    def test_v1_fresh_boot_old_untouched(self, tmp_path):
        """V1：当前版本库不存在、盘上有第 0 代 → fresh_boot，旧文件原位不动。"""
        old = tmp_path / "novel.db"
        _write_db(old, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]},
                  rows={"novels": [("b1", "书一"), ("b2", "书二"), ("b3", "书三")]})
        before = old.read_bytes()

        result = db_lifecycle.boot_lifecycle(tmp_path / CUR, self._simple_meta(), "fp1")
        assert result["boot"] == "fresh_boot"
        assert old.read_bytes() == before, "旧库必须字节不变"
        cands = db_lifecycle.scan_migration_candidates(tmp_path, "0.25", tmp_path / CUR)
        assert [c["filename"] for c in cands] == ["novel.db"]
        assert cands[0]["book_count"] == 3
        assert cands[0]["recommended"] is True

    def test_v2_current_direct_boot(self, tmp_path):
        db = tmp_path / CUR
        fp = _fp(self._simple_meta())
        _write_db(db, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]}, schema_id=fp)
        result = db_lifecycle.boot_lifecycle(db, self._simple_meta(), fp)
        assert result["boot"] == "current"

    @pytest.mark.parametrize("cols", [
        ["id TEXT PRIMARY KEY", "name TEXT", "extra_col TEXT"],   # 超集（旧 tolerant 场景）
        ["id TEXT PRIMARY KEY"],                                   # 子集（旧 additive 场景）
    ])
    def test_v3_shape_mismatch_bringable(self, tmp_path, cols):
        """V3：形状不符（无论超集还是子集）→ `.mismatch-<stamp>`＋**可带回**。

        tolerant/additive 两态随「代内就地补列」退役：同名库只能来自「同一版本的
        另一份构建」，此时数据必须仍可达（改名前字节不变、改名后进候选）。
        """
        db = tmp_path / CUR
        _write_db(db, {"novels": cols}, rows={"novels": [(f"b{i}",) + ("x",) * (len(cols) - 1)
                                                        for i in range(3)]})
        before = db.read_bytes()
        result = db_lifecycle.boot_lifecycle(db, self._simple_meta(), "fp-not-matching")
        assert result["boot"] == "mismatch_renamed", result
        moved = Path(result["renamed_to"])
        assert moved.is_file() and ".mismatch-" in moved.name
        assert moved.read_bytes() == before, "分流不得改字节"
        assert not db.exists(), "当前版本库位已让出（由空库顶上）"

        cands = db_lifecycle.scan_migration_candidates(tmp_path, "0.25", tmp_path / CUR)
        assert [c["filename"] for c in cands] == [moved.name], cands
        assert cands[0]["kind"] == "mismatch" and cands[0]["version"] == "0.25"
        assert cands[0]["book_count"] == 3

    def test_v4_unreadable_quarantined_not_candidate(self, tmp_path):
        """V4：损坏库 → `.corrupt-<stamp>` 隔离；不进候选；只读可见。"""
        db = tmp_path / CUR
        db.write_bytes(b"not a sqlite file at all" * 100)
        result = db_lifecycle.boot_lifecycle(db, self._simple_meta(), "fp")
        assert result["boot"] == "quarantined_new"
        assert result["quarantined_to"] and ".corrupt-" in result["quarantined_to"]
        assert not db.exists()
        cands = db_lifecycle.scan_migration_candidates(tmp_path, "0.25", tmp_path / CUR)
        assert all(".corrupt" not in c["filename"] for c in cands)
        quarantined = db_lifecycle.list_quarantined(tmp_path)
        assert [q["filename"] for q in quarantined] == [Path(result["quarantined_to"]).name]
        assert quarantined[0]["size_bytes"] > 0 and quarantined[0]["mtime"] > 0

    def test_v5_empty_shell_reused_not_quarantined(self, tmp_path):
        """V5：0 表且无 schema_id 的空壳 → fresh_boot 复用（不积隔离件）。"""
        db = tmp_path / CUR
        sqlite3.connect(db).close()  # 合法 SQLite 文件但无表
        result = db_lifecycle.boot_lifecycle(db, self._simple_meta(), "fp")
        assert result["boot"] == "fresh_boot" and result.get("empty_shell") is True
        assert db.exists(), "空壳必须原位复用"
        assert db_lifecycle.list_quarantined(tmp_path) == []


class TestCandidateScan:
    def test_v6_shape_whitelist_excludes_noise(self, tmp_path):
        """V6：白名单形状枚举——边车/`.bak`/磁盘残件/空库/空壳/staging 全排除。"""
        good = tmp_path / "novel.db"
        _write_db(good, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]},
                  rows={"novels": [("b1", "书一")]})
        (tmp_path / "novel.db-wal").write_bytes(b"\x00" * 64)
        (tmp_path / "novel.db-shm").write_bytes(b"\x00" * 32)
        (tmp_path / "novel.db.bak-20260919").write_bytes(b"\x00" * 16)
        # 真实磁盘残件（本机 .docker-data/client 实存同名形态）——不得成为候选
        (tmp_path / "novel.db.e2e-20260909-223352").write_bytes(b"\x00" * 64)
        (tmp_path / "novel.db.fresh-20260906-guard").write_bytes(b"\x00" * 64)
        (tmp_path / "novel.db.recovered-20260917-052608").write_bytes(b"\x00" * 64)
        (tmp_path / "novels.db").write_bytes(b"")
        _write_db(tmp_path / "novel-v0.9.db", {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]})
        _write_db(tmp_path / "novel-v0.8.db", {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]})
        sqlite3.connect(tmp_path / "novel-v0.7.db").close()  # 空壳
        staging = tmp_path / "migration-staging" / "20260922-000000"
        staging.mkdir(parents=True)
        (staging / "novel-v0.6.db").write_bytes(b"\x00" * 32)
        cands = db_lifecycle.scan_migration_candidates(tmp_path, "0.25", tmp_path / CUR)
        assert [c["filename"] for c in cands] == ["novel.db"], cands

    def test_v7_order_and_legacy_not_filtered(self, tmp_path):
        """V7：语义化版本降序 → 遗留代数名 → 第 0 代 → dev 哨兵；遗留名不被排除。

        `novel-v1.db` 若按语义化比较是 `1 > 0.25`，用「版本 ≥ 当前不收」会把它
        静默排除（本机 1213 本的真实形态）——必须走遗留分支进候选。
        """
        for name, books in [("novel-v0.24.db", 2), ("novel-v0.23.db", 5),
                            (LEGACY, 7), ("novel.db", 1), ("novel-dev.db", 9)]:
            _write_db(tmp_path / name, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]},
                      rows={"novels": [(f"b{i}", "书") for i in range(books)]})
        cands = db_lifecycle.scan_migration_candidates(tmp_path, "0.25", tmp_path / CUR)
        assert [c["filename"] for c in cands] == [
            "novel-v0.24.db", "novel-v0.23.db", LEGACY, "novel.db", "novel-dev.db"]
        assert cands[0]["recommended"] is True, "推荐位＝第一个不新于当前的候选"
        assert [c["kind"] for c in cands] == ["semver", "semver", "legacy", "gen0", "sentinel"]
        assert cands[2]["legacy_generation"] == 1

    def test_v7b_newer_versions_listed_but_not_recommended(self, tmp_path):
        """新于当前版本的候选列出但不推荐（排除会让它们彻底不可达）。"""
        for name in ("novel-v0.99.db", "novel-v0.24.db"):
            _write_db(tmp_path / name, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]},
                      rows={"novels": [("b1", "书")]})
        cands = db_lifecycle.scan_migration_candidates(tmp_path, "0.25", tmp_path / CUR)
        names = [c["filename"] for c in cands]
        assert names == ["novel-v0.99.db", "novel-v0.24.db"]
        assert [c["recommended"] for c in cands] == [False, True]

    def test_v7c_active_db_excluded_by_path(self, tmp_path):
        """活跃库按**路径**排除（不靠版本比较）：版本相等的两份不同文件。"""
        active = tmp_path / CUR            # 0.25
        same_version_sibling = tmp_path / "novel-v0.24.db"
        for name in (CUR, "novel-v0.24.db"):
            _write_db(tmp_path / name, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]},
                      rows={"novels": [("b1", "书")]})
        cands = db_lifecycle.scan_migration_candidates(tmp_path, "0.25", active)
        assert [c["filename"] for c in cands] == ["novel-v0.24.db"]
        assert same_version_sibling.exists()

    def test_v7d_three_file_mtime_ordering(self, tmp_path):
        """同族排序按三件套 max(mtime)：只看主文件会被 WAL 滞后骗到。"""
        older = tmp_path / "novel-v0.21.db"
        newer = tmp_path / "novel-v0.22.db"
        for p in (older, newer):
            _write_db(p, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]},
                      rows={"novels": [("b1", "书")]})
        base = time.time()
        import os

        os.utime(older, (base + 10, base + 10))            # 主文件 mtime 更新
        os.utime(newer, (base, base))
        (Path(f"{newer}-wal")).write_bytes(b"\x00" * 8)     # 但 v0.22 的 WAL 刚写过
        os.utime(Path(f"{newer}-wal"), (base + 100, base + 100))
        cands = db_lifecycle.scan_migration_candidates(tmp_path, "0.25", tmp_path / CUR)
        # 同族（同为 semver、不同版本）先按版本降序：0.22 在前；此处只钉 mtime 参与
        assert [c["filename"] for c in cands] == ["novel-v0.22.db", "novel-v0.21.db"]
        assert cands[0]["mtime"] == int(base + 100), "mtime 取三件套 max"

    def test_v6b_stale_staging_cleaned(self, tmp_path):
        """staging 残留清理（硬杀/断电遗留的整份副本）。"""
        staging = tmp_path / "migration-staging" / "20260922-000000"
        staging.mkdir(parents=True)
        (staging / "novel-v0.6.db").write_bytes(b"\x00" * 32)
        assert db_lifecycle.clean_stale_staging(tmp_path) == 1
        assert not staging.exists()


class TestSentinelDisposedShapes:
    """dev 哨兵分流件形状（c-dev-sentinel-migration-candidate）。

    实锤盲区：relocate 对哨兵库产出 `novel-dev.db.mismatch-*`（本机版本为 dev、
    无 {X} 可代入），旧形状枚举判 None → 候选扫描永不可见——书只能靠手工改名找回。
    """

    def _simple_meta(self) -> MetaData:
        md = MetaData()
        Table("novels", md, Column("id", String, primary_key=True), Column("name", String))
        return md

    def test_v8_parse_sentinel_disposed(self):
        from schema_version import parse_db_filename

        mm = parse_db_filename("novel-dev.db.mismatch-20260924-091835")
        assert mm.kind == "mismatch" and mm.is_candidate and mm.version is None
        co = parse_db_filename("novel-dev.db.corrupt-20260924-091835")
        assert co.kind == "corrupt" and not co.is_candidate
        # 哨兵残件（非分流 stamp 形态）仍排除
        assert parse_db_filename("novel-dev.db.e2e-20260909-223352").kind is None
        # 版本构建路径逐字回归
        old = parse_db_filename("novel-v0.25.db.mismatch-20260924-091835")
        assert old.kind == "mismatch" and old.version == "0.25"

    def test_v8b_sentinel_mismatch_boot_and_scan(self, tmp_path):
        """哨兵库指纹不符 → 分流件可被候选扫描（boot→scan 端到端）。"""
        db = tmp_path / "novel-dev.db"
        _write_db(db, {"novels": ["id TEXT PRIMARY KEY", "name TEXT"]},
                  rows={"novels": [("b1", "我在夜晚打吸血鬼")]})
        result = db_lifecycle.boot_lifecycle(db, self._simple_meta(), "fp-not-matching")
        assert result["boot"] == "mismatch_renamed", result
        moved = Path(result["renamed_to"])
        assert moved.name.startswith("novel-dev.db.mismatch-")
        cands = db_lifecycle.scan_migration_candidates(tmp_path, "dev", tmp_path / "novel-dev.db")
        assert [c["filename"] for c in cands] == [moved.name], cands
        assert cands[0]["kind"] == "mismatch" and cands[0]["version"] is None
        assert cands[0]["book_count"] == 1

    def test_v8c_sentinel_corrupt_quarantined_not_candidate(self, tmp_path):
        db = tmp_path / "novel-dev.db"
        db.write_bytes(b"not a sqlite file at all" * 100)
        result = db_lifecycle.boot_lifecycle(db, self._simple_meta(), "fp")
        assert result["boot"] == "quarantined_new"
        assert "novel-dev.db.corrupt-" in result["quarantined_to"]
        cands = db_lifecycle.scan_migration_candidates(tmp_path, "dev", tmp_path / "novel-dev.db")
        assert all(".corrupt" not in c["filename"] for c in cands)
        quarantined = db_lifecycle.list_quarantined(tmp_path)
        assert [q["filename"] for q in quarantined] == [Path(result["quarantined_to"]).name]


# ── c-lossless-upgrade：候选只读清单（candidate_manifest）─────────────────

class TestCandidateManifest:
    def _lib(self, path: Path, books=3, with_configs=True):
        tables = {
            "novels": ["id TEXT PRIMARY KEY", "name TEXT", "created_at TEXT"],
            "chapters": ["id TEXT PRIMARY KEY", "novel_id TEXT", "word_count INTEGER"],
        }
        rows = {
            "novels": [(f"n{i}", f"书{i}", "2026-01-01") for i in range(books)],
            "chapters": [(f"c{i}", f"n{i}", 1000 + i) for i in range(books)],
        }
        if with_configs:
            tables["api_configs"] = ["id TEXT PRIMARY KEY", "name TEXT", "created_at TEXT"]
            rows["api_configs"] = [("a1", "DeepSeek", "2026-01-01"),
                                   ("a2", "朱雀 AI 检测", "2026-01-02")]
        _write_db(path, tables, rows)

    def test_manifest_books_and_configs(self, tmp_path):
        db = tmp_path / "novel-v0.24.db"
        self._lib(db)
        m = db_lifecycle.candidate_manifest(db)
        assert m is not None
        assert m["books_total"] == 3
        assert [b["name"] for b in m["books"]] == ["书0", "书1", "书2"]
        assert m["books"][0]["words"] == 1000  # 每书 1 章，字数随章
        assert [c["name"] for c in m["configs"]] == ["DeepSeek", "朱雀 AI 检测"]
        assert m["configs_total"] == 2

    def test_manifest_book_cap(self, tmp_path):
        db = tmp_path / "novel-v0.24.db"
        self._lib(db, books=55)
        m = db_lifecycle.candidate_manifest(db)
        assert m["books_total"] == 55
        assert len(m["books"]) == db_lifecycle.MANIFEST_BOOK_CAP  # 封顶 50，total 说真话

    def test_manifest_without_configs_table(self, tmp_path):
        """老库无 api_configs 表：配置清单为空而非整体失败（降级契约）。"""
        db = tmp_path / "novel-v0.24.db"
        self._lib(db, books=1, with_configs=False)
        m = db_lifecycle.candidate_manifest(db)
        assert m is not None and m["configs"] == [] and m["configs_total"] == 0

    def test_manifest_broken_db_returns_none(self, tmp_path):
        db = tmp_path / "junk.db"
        db.write_bytes(b"\x00" * 512)
        assert db_lifecycle.candidate_manifest(db) is None

    def test_manifest_never_reads_api_key(self, tmp_path):
        """密钥永不返回：响应序列化后全文不得出现密钥材料。"""
        import json as _json

        db = tmp_path / "novel-v0.24.db"
        self._lib(db, books=1)
        con = sqlite3.connect(db)
        con.execute("ALTER TABLE api_configs ADD COLUMN api_key TEXT")
        con.execute("UPDATE api_configs SET api_key = 'enc:AAAAdeadbeefsecret'")
        con.commit()
        con.close()
        m = db_lifecycle.candidate_manifest(db)
        payload = _json.dumps({"candidates": [{"manifest": m}]}, ensure_ascii=False)
        assert "enc:" not in payload and "deadbeefsecret" not in payload
