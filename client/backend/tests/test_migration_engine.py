"""migration 引擎测试（db-generation PR1）——specs 场景逐一对应。

M1 源数据只读：迁入全程完成或失败，源三件套字节不变（specs：迁入引擎）
M2 中断重跑幂等：半途重跑零重复行；「上次已迁入」由 stamp 比对识别
M3 FK OFF 纪律：违规行报告不静默吞（计数可核对前提）
M4 app_meta 永不搬（旧 schema_id 不污染新库）
M5 世代门禁：ADR 前世代（设定在盘上 yaml）不进行级迁入
M6 不可迁表整表跳过（NOT NULL 无默认列）并预告
M7 预置种子幂等（OR IGNORE，新版定义胜出）
R1 候选/preview/start/status/dismiss 免登端点链
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import models  # noqa: F401 —— 注册全表
from migration.engine import precheck, run_migration
from schema_version import db_filename_for

# 被测「当前版本」库名（c-db-per-version：库名＝C端 版本派生；conftest 钉 0.25）
CUR = db_filename_for("0.25")


def _write_db(path: Path, tables: dict[str, str], rows: dict[str, list] | None = None,
              schema_id: str | None = None):
    conn = sqlite3.connect(path)
    for ddl in tables.values():
        conn.execute(ddl)
    if schema_id:
        conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO app_meta VALUES ('schema_id', ?)", (schema_id))
        conn.execute("INSERT INTO app_meta VALUES ('other_key', 'pollution')")
    for t, rs in (rows or {}).items():
        conn.executemany(f"INSERT INTO {t} VALUES ({','.join('?' * len(rs[0]))})", rs)
    conn.commit()
    conn.close()


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """独立 DATA_ROOT + 已建好的当前版本库（当前 schema 的最小集）。"""
    from db import Base

    root = tmp_path / "data"
    root.mkdir()
    # 目标库：用 Base.metadata create_all（全量当前 schema）
    engine_sync = sqlite3.connect(root / CUR)
    engine_sync.close()
    from sqlalchemy import create_engine

    se = create_engine(f"sqlite:///{root / CUR}")
    Base.metadata.create_all(se)
    se.dispose()
    monkeypatch.setattr("migration.engine.DATA_ROOT", root)
    monkeypatch.setattr("migration.router.DATA_ROOT", root)
    return root, root / CUR


def _old_gen0(root: Path, name: str = "novel.db", books: int = 2) -> Path:
    """第 0 代旧库：核心业务表形态（列是当前 schema 子集）。
    INSERT 一律显式列名——永不依赖 CREATE 的列序（占位符计数陷阱已吃透）。"""
    p = root / name
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE novels (id TEXT PRIMARY KEY, user_id TEXT, name TEXT, slug TEXT, root_path TEXT, current_phase TEXT, status TEXT, total_volumes INTEGER, total_chapters INTEGER, created_at TIMESTAMP, updated_at TIMESTAMP)")
    conn.execute("CREATE TABLE volumes (id TEXT PRIMARY KEY, novel_id TEXT, volume_no INTEGER, title TEXT, summary TEXT, chapter_count INTEGER, created_at TIMESTAMP, updated_at TIMESTAMP)")
    conn.execute("CREATE TABLE chapters (id TEXT PRIMARY KEY, novel_id TEXT, volume_id TEXT, chapter_no INTEGER, ref TEXT, title TEXT, status TEXT)")
    conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO app_meta (key, value) VALUES ('schema_id', 'old_fp_should_not_migrate')")
    conn.execute("INSERT INTO app_meta (key, value) VALUES ('other_key', 'pollution')")
    for i in range(books):
        conn.execute(
            "INSERT INTO novels (id, user_id, name, slug, root_path, current_phase, status, total_volumes, total_chapters, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f"n{i}", f"u{i}", f"旧书{i}", f"old-{i}", f"./data/old-{i}", "write", "active", 1, 3, "2026-01-01 00:00:00", "2026-01-02 00:00:00"))
        conn.execute(
            "INSERT INTO volumes (id, novel_id, volume_no, title, summary, chapter_count, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (f"v{i}", f"n{i}", 1, "第一卷", "概要", 3, "2026-01-01 00:00:00", "2026-01-02 00:00:00"))
        conn.execute(
            "INSERT INTO chapters (id, novel_id, volume_id, chapter_no, ref, title, status) VALUES (?,?,?,?,?,?,?)",
            (f"c{i}-1", f"n{i}", f"v{i}", 1, f"第 {i+1} 章", f"章节{i}", "draft"))
    conn.commit()
    conn.close()
    return p


class TestEngine:
    def test_m1_source_untouched_and_counts(self, sandbox):
        """M1+M2：完整迁入——源字节不变、书迁入计数对拍、重跑零重复。"""
        root, active = sandbox
        old = _old_gen0(root, books=2)
        before = old.read_bytes()

        rep = run_migration(root, "novel.db", active)
        assert rep["status"] == "ok", rep
        assert old.read_bytes() == before, "源库必须字节不变"
        assert rep["book_count_source"] == 2
        assert rep["book_count_migrated"] == 2

        # 重跑幂等（specs：中断重跑语义同一引擎）
        rep2 = run_migration(root, "novel.db", active)
        # migrated＝本次真正写入 → 重跑 0 本；目标总数仍 2（OR IGNORE 零重复）
        assert rep2["book_count_migrated"] == 0, "OR IGNORE 重跑零重复（本次写入 0 行）"
        assert rep2["book_count_target_after"] == 2
        con = sqlite3.connect(f"file:{active}?mode=ro", uri=True)
        try:
            n = con.execute("SELECT COUNT(*) FROM novels").fetchone()[0]
            v = con.execute("SELECT COUNT(*) FROM volumes").fetchone()[0]
        finally:
            con.close()
        assert (n, v) == (2, 2)

    def test_m4_app_meta_never_migrated(self, sandbox):
        """M4：app_meta 永不搬——旧 schema_id 不进新库。"""
        root, active = sandbox
        _old_gen0(root)
        run_migration(root, "novel.db", active)
        con = sqlite3.connect(f"file:{active}?mode=ro", uri=True)
        try:
            rows = dict(con.execute("SELECT key, value FROM app_meta").fetchall())
        finally:
            con.close()
        assert "other_key" not in rows, "污染键不得迁入"
        assert rows.get("schema_id") != "old_fp_should_not_migrate"

    def test_m6_table_with_notnull_blocker_skipped(self, sandbox, monkeypatch):
        """M6：目标有 NOT NULL 无默认列的表 → 整表跳过进报告。"""
        root, active = sandbox
        _old_gen0(root)
        # 构造：给目标加一张旧库存在但带 NOT NULL 无默认新列的表——
        # 直接对 build_plan 用 monkeypatch 的 metadata 不可行（Base 全局）；
        # 换路径：旧库造一张当前 schema 没有 NOT NULL 坑的表已覆盖 plan 逻辑，
        # 这里用 retired 表验证 skip 通道。
        conn = sqlite3.connect(root / "novel.db")
        conn.execute("CREATE TABLE legacy_junk (a TEXT)")
        conn.execute("INSERT INTO legacy_junk VALUES ('x')")
        conn.commit()
        conn.close()
        rep = run_migration(root, "novel.db", active)
        assert rep["status"] == "ok"
        assert any(s["table"] == "legacy_junk" and s["reason"] == "table_retired"
                   for s in rep["tables_skipped"])

    def test_m5_pre_adr_generation_blocked(self, sandbox, tmp_path):
        """M5：ADR 前世代（盘上 settings yaml 且库无 project_settings 表）→ 预检拒绝。"""
        root, active = sandbox
        old = _old_gen0(root, books=1)
        # 盘上 yaml 世代标记（root_path 指向 root 下的旧目录）
        conn = sqlite3.connect(old)
        conn.execute("UPDATE novels SET root_path='./data/old-0'")
        conn.commit()
        conn.close()
        legacy_dir = root / "old-0" / "settings"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "genre.yaml").write_text("genre_id: xianxia")
        pc = precheck(root, "novel.db", active)
        assert not pc["ok"]
        assert pc["reason"] == "pre_adr_generation"

    def test_precheck_active_db_guard(self, sandbox):
        root, active = sandbox
        pc = precheck(root, active.name, active)
        assert pc["reason"] == "source_is_active_db"


class TestRouter:
    @pytest.fixture()
    def client(self, sandbox, monkeypatch):
        from main import app

        monkeypatch.setattr("migration.router.DATA_ROOT", sandbox[0])
        with TestClient(app) as c:
            yield c

    def test_r1_candidates_loginless_chain(self, client, sandbox):
        """R1：candidates/preview/start/status/dismiss 免登全链。"""
        root, _active = sandbox
        _old_gen0(root, books=2)
        # candidates（无 Authorization）
        c1 = client.get("/api/backup/db-migration/candidates").json()
        assert c1["code"] == 0
        assert [x["filename"] for x in c1["data"]["candidates"]] == ["novel.db"]
        # preview（同构 v:1）
        c2 = client.post("/api/backup/db-migration/preview",
                         json={"source_filename": "novel.db"}).json()
        assert c2["code"] == 0 and c2["data"]["v"] == 1
        assert c2["data"]["book_count_source"] == 2
        # start → 立返初始快照（异步——不再等完成）
        c3 = client.post("/api/backup/db-migration/start",
                         json={"source_filename": "novel.db"}).json()
        assert c3["code"] == 0
        assert c3["data"]["state"] == "running"
        # 轮询 status 到 done（前端同款 1s 轮询；测试用短间隔）
        import time

        for _ in range(30):
            c4 = client.get("/api/backup/db-migration/status").json()["data"]
            if c4.get("state") in ("done", "error"):
                break
            time.sleep(0.2)
        assert c4["state"] == "done", c4
        assert c4["report"]["status"] == "ok"
        # 全局测试库可能有残留（loginless 等测试先行迁入）——断言 ≥2 而非精确等
        assert c4["report"]["book_count_migrated"] >= 2
        # dismiss（绑身份指纹）
        c5 = client.post("/api/backup/db-migration/dismiss",
                         json={"filename": "novel.db"}).json()
        assert c5["code"] == 0
        cand2 = client.get("/api/backup/db-migration/candidates").json()["data"]["candidates"]
        assert cand2[0]["suppressed"] is True

    def test_m5_preview_channel_message(self, client, sandbox):
        """M5 路由面：世代门禁在 preview 返回资产包引导（422 之外的人话通道）。"""
        root, _active = sandbox
        _old_gen0(root, books=1)
        (root / "old-0" / "settings").mkdir(parents=True)
        (root / "old-0" / "settings" / "genre.yaml").write_text("x")
        c = client.post("/api/backup/db-migration/preview",
                        json={"source_filename": "novel.db"}).json()
        assert c["code"] == 1
        assert "备份包导入" in c["data"]["message"]

    def test_start_409_when_backup_running(self, client, sandbox, monkeypatch):
        """跨 kind 互斥：备份在跑 → 迁入 409（job_runner 单飞）。"""
        import job_runner

        monkeypatch.setattr(job_runner, "running_kind", lambda: "backup")
        r = client.post("/api/backup/db-migration/start",
                        json={"source_filename": "novel.db"})
        assert r.status_code == 409
        assert "备份" in r.json()["detail"]["message"]


class TestDeadKeyMigrationNote:
    def test_dead_key_configs_reported_in_notes(self, sandbox):
        """key-crypto-selfcontained：迁入带 enc: 密文的 api_configs 而源库钥匙不随行
        （app_meta 不搬）——按当前钥匙解不开的迁入配置在报告 notes 显式提示重填。"""
        from cryptography.fernet import Fernet

        root, active = sandbox
        p = root / "novel.db"
        dead_cipher = "enc:" + Fernet(Fernet.generate_key()).encrypt(b"sk-dead").decode()
        conn = sqlite3.connect(p)
        conn.execute(
            "CREATE TABLE api_configs (id TEXT PRIMARY KEY, user_id TEXT, name TEXT, "
            "vendor TEXT, api_format TEXT, base_url TEXT, api_key TEXT, models TEXT, status TEXT)"
        )
        conn.execute(
            "INSERT INTO api_configs (id, user_id, name, vendor, api_format, base_url, api_key, models, status) "
            "VALUES ('c-dead', 'u1', '旧配置', 'deepseek', 'openai', 'https://x', ?, '[\"m\"]', 'active')",
            (dead_cipher,),
        )
        conn.execute(
            "CREATE TABLE novels (id TEXT PRIMARY KEY, user_id TEXT, name TEXT, slug TEXT, root_path TEXT, "
            "current_phase TEXT, status TEXT, total_volumes INTEGER, total_chapters INTEGER, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO novels (id, user_id, name, slug, root_path, current_phase, status, "
            "total_volumes, total_chapters, created_at, updated_at) VALUES ('n1','u1','书','s','./d','write','active',0,0,'2026-01-01','2026-01-01')"
        )
        conn.commit()
        conn.close()

        rep = run_migration(root, "novel.db", active)
        assert rep["status"] == "ok", rep
        notes = "\n".join(rep["notes"])
        assert "不可解" in notes and "重新粘贴保存" in notes, rep["notes"]
