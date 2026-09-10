"""旧库留档机制测试（c-novel-export-roundtrip PR0）。

覆盖：指纹稳定性与灵敏度 / 留档四态（全新、旧库、当前、损坏）/
status 端点（有留档、无留档、未登录 401）。
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, MetaData, String, Table

import legacy_archive
from db import Base


def _fp(metadata) -> str:
    return legacy_archive.compute_schema_fingerprint(metadata)


def _make_legacy_db(path, books: int = 3):
    """老版本形态：有 projects 表（含数据），无 app_meta。"""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE novels (id TEXT PRIMARY KEY, name TEXT)")
    conn.executemany(
        "INSERT INTO novels VALUES (?, ?)", [(f"b{i}", f"书{i}") for i in range(books)]
    )
    conn.commit()
    conn.close()


def _make_current_db(path, fingerprint: str):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        "INSERT INTO app_meta VALUES ('schema_id', ?)", (fingerprint,)
    )
    conn.execute("CREATE TABLE novels (id TEXT PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()


class TestFingerprint:
    def test_stable(self):

        assert _fp(Base.metadata) == _fp(Base.metadata)

    def test_sensitive_to_schema_change(self):
        md1 = MetaData()
        Table("a", md1, Column("x", String))
        md2 = MetaData()
        Table("a", md2, Column("x", String))
        Table("b", md2, Column("y", String))
        assert _fp(md1) != _fp(md2)


class TestArchiveIfLegacy:
    def test_fresh_no_file(self, tmp_path):
        result = legacy_archive.archive_if_legacy(tmp_path / "novel.db", "fp123")
        assert result["archived"] is False
        assert result["reason"] == "fresh"

    def test_legacy_db_archived(self, tmp_path):
        db = tmp_path / "novel.db"
        _make_legacy_db(db, books=3)
        result = legacy_archive.archive_if_legacy(db, "target_fp")
        assert result["archived"] is True
        archived = Path(result["archived_path"])
        assert archived.exists() and "legacy-" in archived.name
        # 原位文件已搬走
        assert not db.exists()
        # 留档内容完好
        conn = sqlite3.connect(archived)
        assert conn.execute("SELECT COUNT(*) FROM novels").fetchone()[0] == 3
        conn.close()

    def test_current_db_not_archived(self, tmp_path):
        db = tmp_path / "novel.db"
        _make_current_db(db, "target_fp")
        result = legacy_archive.archive_if_legacy(db, "target_fp")
        assert result["archived"] is False
        assert db.exists()

    def test_unreadable_archived_as_legacy(self, tmp_path):
        db = tmp_path / "novel.db"
        db.write_bytes(b"not a sqlite file at all")
        result = legacy_archive.archive_if_legacy(db, "target_fp")
        assert result["archived"] is True
        assert result["reason"] == "unreadable"


class TestLegacyDbStatusEndpoint:
    @pytest.fixture
    def client(self):
        from auth_local.middleware import get_current_user
        from main import app

        app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1",
            "username": "tester",
        }
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()

    def test_no_archive(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("backup.router.DATA_ROOT", str(tmp_path))
        r = client.get("/api/backup/legacy-db/status")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["present"] is False

    def test_archive_listed_latest_first(self, client, tmp_path, monkeypatch):
        for name in ["novel.db.legacy-20260901-120000", "novel.db.legacy-20260902-090000"]:
            conn = sqlite3.connect(tmp_path / name)
            conn.execute("CREATE TABLE novels (id TEXT PRIMARY KEY, name TEXT)")
            conn.executemany("INSERT INTO novels VALUES (?, ?)", [(f"b{i}", f"书{i}") for i in range(2)])
            conn.commit()
            conn.close()
        monkeypatch.setattr("backup.router.DATA_ROOT", str(tmp_path))
        r = client.get("/api/backup/legacy-db/status")
        d = r.json()["data"]
        assert d["present"] is True
        assert d["book_count"] == 2  # 最新留档为主报告
        assert len(d["all"]) == 2
        assert "20260902" in d["filename"]  # 最新在前

    def test_unauthorized_401(self, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient as _TC

        from main import app

        monkeypatch.setattr("backup.router.DATA_ROOT", str(tmp_path))
        with _TC(app) as c:
            r = c.get("/api/backup/legacy-db/status")
        assert r.status_code == 401
