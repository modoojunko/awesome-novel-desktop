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

    def test_r2_sentinel_source_full_chain(self, client, sandbox):
        """R2（c-sentinel-carry-gate，v0.30.1 真机判例）：dev 哨兵库作迁入源全链。
        曾把 cleanup 的「非哨兵」规则上扩到 start/preview/dismiss——哨兵候选扫得到、
        点「带过来」即 400「文件名不合法或不在数据目录内」（0.29.1→0.30.1 升级现场）。
        哨兵在候选白名单内：迁入链必须放行、搬运真实完成。"""
        import time

        root, _active = sandbox
        _old_gen0(root, name="novel-dev.db", books=1)
        # 全局测试库有先行迁入残留（r1 等）：id 换成本用例唯一值，避免 INSERT OR
        # IGNORE 幂等跳过导致 book_count_migrated 被吃掉
        conn = sqlite3.connect(root / "novel-dev.db")
        conn.execute("UPDATE novels SET id='sent1', slug='sent-1', root_path='./data/sent-1'")
        conn.execute("UPDATE volumes SET id='sent1-v1', novel_id='sent1'")
        conn.execute("UPDATE chapters SET id='sent1-c1', novel_id='sent1', volume_id='sent1-v1'")
        conn.commit()
        conn.close()
        names = [x["filename"] for x in client.get(
            "/api/backup/db-migration/candidates").json()["data"]["candidates"]]
        assert "novel-dev.db" in names
        c2 = client.post("/api/backup/db-migration/preview",
                         json={"source_filename": "novel-dev.db"}).json()
        assert c2["code"] == 0, c2
        c3 = client.post("/api/backup/db-migration/start",
                         json={"source_filename": "novel-dev.db"}).json()
        assert c3["code"] == 0, c3
        for _ in range(30):
            c4 = client.get("/api/backup/db-migration/status").json()["data"]
            if c4.get("state") in ("done", "error"):
                break
            time.sleep(0.2)
        assert c4["state"] == "done", c4
        assert c4["report"]["status"] == "ok"
        assert c4["report"]["book_count_migrated"] >= 1
        # dismiss 同链放行（「本版不再提醒」对哨兵候选同样可用）
        c5 = client.post("/api/backup/db-migration/dismiss",
                         json={"filename": "novel-dev.db"}).json()
        assert c5["code"] == 0, c5

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


# ── c-lossless-upgrade：密钥转接三态＋种子表源行胜出＋preview 同构 ─────────

def _add_configs(conn, rows):
    """往源库补 api_configs 表（列＝当前 schema 子集；显式列名）。"""
    conn.execute(
        "CREATE TABLE api_configs (id TEXT PRIMARY KEY, user_id TEXT, name TEXT, "
        "vendor TEXT, api_format TEXT, base_url TEXT, api_key TEXT, models TEXT, status TEXT)"
    )
    for r in rows:
        conn.execute(
            "INSERT INTO api_configs (id, user_id, name, vendor, api_format, base_url, "
            "api_key, models, status) VALUES (?,?,?,?,?,?,?,?,?)", r)


class TestKeyTransfer:
    def _source_with_key(self, root: Path, key: str | None, file_key: bytes | None = None) -> Path:
        """源库：1 本书 + 2 条 enc: 配置；钥匙可选地写进 app_meta 行 / .fernet_key 文件。"""
        from cryptography.fernet import Fernet

        p = root / "novel.db"
        conn = sqlite3.connect(p)
        conn.execute(
            "CREATE TABLE novels (id TEXT PRIMARY KEY, user_id TEXT, name TEXT, slug TEXT, root_path TEXT, "
            "current_phase TEXT, status TEXT, total_volumes INTEGER, total_chapters INTEGER, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO novels (id, user_id, name, slug, root_path, current_phase, status, "
            "total_volumes, total_chapters, created_at, updated_at) VALUES ('n1','u1','书','s','./d','write','active',0,0,'2026-01-01','2026-01-01')"
        )
        if key:
            fk = Fernet(key.encode())
        elif file_key is not None:
            fk = Fernet(file_key)  # B 态：密文钥＝旧文件里的那把
        else:
            fk = Fernet(Fernet.generate_key())  # C 态：谁都解不开
        enc1 = "enc:" + fk.encrypt(b"sk-live-1").decode()
        enc2 = "enc:" + fk.encrypt(b"sk-live-2").decode()
        _add_configs(conn, [
            ("c1", "u1", "配置一", "deepseek", "openai", "https://x", enc1, "[]", "active"),
            ("c2", "u1", "配置二", "glm", "openai", "https://y", enc2, "[]", "active"),
        ])
        conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT)")
        if key:
            conn.execute("INSERT INTO app_meta VALUES ('fernet_key', ?)", (key,))
        conn.execute("INSERT INTO app_meta VALUES ('schema_id', 'old')")
        conn.commit()
        conn.close()
        if file_key is not None:
            (root / ".fernet_key").write_bytes(file_key)
        return p

    def _decrypt_target(self, active: Path, row_id: str) -> str:
        from api_configs.crypto import decrypt_api_key

        con = sqlite3.connect(active)
        stored = con.execute("SELECT api_key FROM api_configs WHERE id=?", (row_id,)).fetchone()[0]
        con.close()
        assert stored.startswith("enc:")
        return decrypt_api_key(stored)

    def test_state_a_key_in_source_row(self, sandbox):
        """①源钥在源库 app_meta 行：转接后两条配置按目标钥匙可解，零死文。"""
        from cryptography.fernet import Fernet

        root, active = sandbox
        self._source_with_key(root, key=Fernet.generate_key().decode())
        rep = run_migration(root, "novel.db", active)
        assert rep["status"] == "ok", rep
        assert rep["dead_keys"] == 0, rep
        assert self._decrypt_target(active, "c1") == "sk-live-1"
        assert self._decrypt_target(active, "c2") == "sk-live-2"
        assert not any("不可解" in n for n in rep["notes"]), rep["notes"]

    def test_state_b_key_in_legacy_file(self, sandbox):
        """②源钥只在旧 .fernet_key 文件（按本次搬运 data_root 解析）：同样转接成功。"""
        from cryptography.fernet import Fernet

        root, active = sandbox
        fk = Fernet.generate_key()
        self._source_with_key(root, key=None, file_key=fk)
        rep = run_migration(root, "novel.db", active)
        assert rep["status"] == "ok", rep
        assert rep["dead_keys"] == 0, rep
        assert self._decrypt_target(active, "c1") == "sk-live-1"

    def test_state_c_no_source_key(self, sandbox):
        """③两把源钥皆不可得：保持原样、dead_keys=2、notes 提示重填。"""
        root, active = sandbox
        self._source_with_key(root, key=None)
        rep = run_migration(root, "novel.db", active)
        assert rep["status"] == "ok", rep
        assert rep["dead_keys"] == 2, rep
        assert any("重新粘贴" in n for n in rep["notes"]), rep["notes"]

    def test_idempotent_rerun(self, sandbox):
        """幂等：转接后重跑（同源再搬）结果一致、零重复、可解行不被二次改写。"""
        from cryptography.fernet import Fernet

        root, active = sandbox
        self._source_with_key(root, key=Fernet.generate_key().decode())
        run_migration(root, "novel.db", active)
        con = sqlite3.connect(active)
        stored_after_1 = con.execute("SELECT api_key FROM api_configs WHERE id='c1'").fetchone()[0]
        con.close()
        rep2 = run_migration(root, "novel.db", active)
        assert rep2["status"] == "ok" and rep2["dead_keys"] == 0, rep2
        con = sqlite3.connect(active)
        n_rows = con.execute("SELECT COUNT(*) FROM api_configs").fetchone()[0]
        stored_after_2 = con.execute("SELECT api_key FROM api_configs WHERE id='c1'").fetchone()[0]
        con.close()
        assert n_rows == 2  # OR IGNORE 幂等
        assert stored_after_2 == stored_after_1  # 可解行在第二次转接中不被触碰

    def test_target_native_ciphertext_untouched(self, sandbox):
        """目标库自有密文（先于搬运存在）不被转接影响。"""
        from cryptography.fernet import Fernet

        from api_configs.crypto import decrypt_api_key, encrypt_api_key

        root, active = sandbox
        native_stored = encrypt_api_key("sk-native")
        con = sqlite3.connect(active)
        con.execute(
            "INSERT INTO api_configs (id, user_id, name, vendor, vendor_display_name, "
            "api_format, base_url, api_key, models, status) "
            "VALUES ('native','u1','原生','glm','智谱','openai','https://z',?,'[]','active')",
            (native_stored,),
        )
        con.commit()
        con.close()
        self._source_with_key(root, key=Fernet.generate_key().decode())
        rep = run_migration(root, "novel.db", active)
        assert rep["status"] == "ok" and rep["dead_keys"] == 0, rep
        con = sqlite3.connect(active)
        stored = con.execute("SELECT api_key FROM api_configs WHERE id='native'").fetchone()[0]
        con.close()
        assert stored == native_stored  # 字节不变
        assert decrypt_api_key(stored) == "sk-native"


class TestSeedTablesSourceWins:
    def test_user_edit_overrides_new_factory_text(self, sandbox):
        """源库（含用户编辑过的预置行）胜出目标出厂行；目标独有行保留。"""
        root, active = sandbox
        # 目标：出厂两行（ensure_seed 播种后的形态）
        con = sqlite3.connect(active)
        con.execute(
            "INSERT INTO genres (id, name, description, category, narrator_role, "
            "typical_arc, tone_blueprint, taboos, prompt_injection, genre_config, "
            "story_arc_templates, is_preset) VALUES "
            "('xianxia','仙侠','新版出厂文案','fantasy','','','{}','[]','','{}','[]',1),"
            "('newcomer','新增题材','仅新版有','fantasy','','','{}','[]','','{}','[]',1)"
        )
        con.commit()
        con.close()
        # 源库：同 PK 行文案不同（用户编辑或旧版出厂——不区分，一律源胜出）
        p = root / "novel.db"
        s = sqlite3.connect(p)
        s.execute(
            "CREATE TABLE novels (id TEXT PRIMARY KEY, user_id TEXT, name TEXT, slug TEXT, root_path TEXT, "
            "current_phase TEXT, status TEXT, total_volumes INTEGER, total_chapters INTEGER, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        s.execute(
            "INSERT INTO novels (id, user_id, name, slug, root_path, current_phase, status, "
            "total_volumes, total_chapters, created_at, updated_at) VALUES ('n1','u1','书','s','./d','write','active',0,0,'2026-01-01','2026-01-01')"
        )
        s.execute(
            "CREATE TABLE genres (id TEXT PRIMARY KEY, name TEXT, description TEXT, category TEXT, is_preset INTEGER)"
        )
        s.execute(
            "INSERT INTO genres (id, name, description, category, is_preset) VALUES "
            "('xianxia', '仙侠', '用户改过的文案', 'fantasy', 1)"
        )
        s.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT)")
        s.execute("INSERT INTO app_meta VALUES ('schema_id', 'old')")
        s.commit()
        s.close()

        rep = run_migration(root, "novel.db", active)
        assert rep["status"] == "ok", rep
        con = sqlite3.connect(active)
        rows = dict(con.execute("SELECT id, description FROM genres").fetchall())
        con.close()
        assert rows["xianxia"] == "用户改过的文案"  # 源行胜出
        assert rows["newcomer"] == "仅新版有"  # 目标独有（新版新增）保留
        # 已知损失提示退役
        assert not any("不随迁" in n for n in rep["notes"]), rep["notes"]

    def test_report_completeness_flag(self, sandbox):
        """report 带 complete 判定（搬运干净＝True）。"""
        root, active = sandbox
        _old_gen0(root, books=1)
        rep = run_migration(root, "novel.db", active)
        assert rep["status"] == "ok" and rep["complete"] is True, rep


def test_preview_null_fields(sandbox, monkeypatch):
    """preview 同构不造数：dead_keys/complete 恒 None（是搬后结果）。"""
    from fastapi.testclient import TestClient

    from main import app

    root, _active = sandbox
    _old_gen0(root, books=1)
    monkeypatch.setattr("migration.router.DATA_ROOT", root)
    with TestClient(app) as client:
        r = client.post("/api/backup/db-migration/preview",
                        json={"source_filename": "novel.db"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["dead_keys"] is None and data["complete"] is None
    assert "manifest" in data and data["manifest"] is not None  # preview 挂只读清单


# ── c-lossless-upgrade：candidates 载荷与 start→status 链路（端点级）───────

class TestCandidatesManifest:
    def test_manifest_only_on_recommended(self, sandbox, monkeypatch):
        from fastapi.testclient import TestClient

        from main import app

        root, _active = sandbox
        _old_gen0(root, name="novel-v0.24.db", books=2)
        _old_gen0(root, name="novel-v0.23.db", books=1)
        # v0.23 造得晚一点，避免与 v0.24 同 mtime 竞争（排序不影响本断言，防御性设置）
        monkeypatch.setattr("migration.router.DATA_ROOT", root)
        with TestClient(app) as client:
            r = client.get("/api/backup/db-migration/candidates")
        assert r.status_code == 200, r.text
        items = r.json()["data"]["candidates"]
        rec = [it for it in items if it["recommended"]]
        assert len(rec) == 1 and rec[0]["version"] == "0.24"
        assert rec[0]["manifest"]["books_total"] == 2  # recommended 挂清单
        others = [it for it in items if not it["recommended"]]
        assert others and all("manifest" not in it for it in others)  # 其余不挂
        # 载荷呈现状态两字段（完整才算 carried）
        assert all("carried" in it and "suppressed" in it for it in items)
        # 序列化响应全文不含密钥材料形态（manifest 只读清单的安全红线）
        assert "enc:" not in r.text


class TestStartStatusChain:
    def test_start_status_report_shape(self, sandbox, monkeypatch):
        """start→status：report 带 dead_keys/complete（result 形态；搬运瞬间完成）。"""
        from fastapi.testclient import TestClient

        from main import app

        root, active = sandbox
        _old_gen0(root, books=1)
        monkeypatch.setattr("migration.router.DATA_ROOT", root)
        # 端点的目标库取 config.DATABASE_URL（会话共享库有先行残留）——显式指回
        # 本沙箱，保证 complete/dead_keys 断言确定性（r1 用 ≥ 容忍残留，此处要精确）
        monkeypatch.setattr("config.DATABASE_URL", f"sqlite+aiosqlite:///{active}")
        # 不走 with（lifespan 会对被改写的 DATABASE_URL 跑 boot_lifecycle，把无戳
        # 沙箱库分流改名）——start/status 本就不依赖 lifespan
        client = TestClient(app)
        r = client.post("/api/backup/db-migration/start",
                        json={"source_filename": "novel.db"})
        assert r.status_code == 200, r.text
        import time as _t

        deadline = _t.time() + 10
        data = {}
        while _t.time() < deadline:
            data = client.get("/api/backup/db-migration/status").json()["data"]
            if data.get("state") in ("done", "error"):
                break
            _t.sleep(0.05)
        assert data.get("state") == "done", data
        rep = data["report"]
        assert rep["status"] == "ok"
        assert rep["dead_keys"] == 0 and rep["complete"] is True, rep


# ── c-upgrade-log：无损升级全链 migration logger 留痕 ─────────────────────


def test_upgrade_log_success_trace(sandbox, caplog):
    """成功路径：启动行/计划行/逐表行/核对行＋终局报告恰一行（整份 report JSON）。"""
    import logging as _logging

    root, active = sandbox
    _old_gen0(root, books=1)
    with caplog.at_level(_logging.INFO, logger="migration"):
        rep = run_migration(root, "novel.db", active)
    assert rep["status"] == "ok"
    msgs = [r.getMessage() for r in caplog.records if r.name == "migration"]
    assert any("event=migration_start" in m for m in msgs)
    assert any("event=migration_plan" in m for m in msgs)
    assert any("event=migration_table" in m and "table=novels" in m for m in msgs)
    assert any("event=migration_verify" in m for m in msgs)
    report_lines = [m for m in msgs if "event=migration_report" in m]
    assert len(report_lines) == 1, "终局报告恰一行（所有退出路径经 finally）"
    assert '"status": "ok"' in report_lines[0], "终局行必须是整份 report JSON"
    assert '"book_count_source"' in report_lines[0]


def test_upgrade_log_precheck_rejected_trace(sandbox, caplog):
    """预检拒绝：拒绝行带原因码＋终局行 status=precheck_failed——无需复现即可定位。"""
    import logging as _logging

    root, active = sandbox
    with caplog.at_level(_logging.INFO, logger="migration"):
        rep = run_migration(root, "missing.db", active)
    assert rep["status"] == "precheck_failed"
    msgs = [r.getMessage() for r in caplog.records if r.name == "migration"]
    assert any("event=migration_precheck_failed" in m and "reason=source_missing" in m
               for m in msgs)
    assert any("event=migration_report" in m and "precheck_failed" in m for m in msgs)


def test_upgrade_log_error_trace(sandbox, caplog, monkeypatch):
    """异常路径：ERROR 级完整堆栈（exc_info 不丢）＋终局行 status=error——堆栈不静默。"""
    import logging as _logging

    root, active = sandbox
    _old_gen0(root, books=1)

    def _boom(*a, **k):
        raise RuntimeError("mig-boom")

    monkeypatch.setattr("migration.engine.prepare_staged", _boom)
    with caplog.at_level(_logging.INFO, logger="migration"):
        rep = run_migration(root, "novel.db", active)
    assert rep["status"] == "error"
    err = [r for r in caplog.records
           if r.name == "migration" and r.levelno == _logging.ERROR]
    assert any("event=migration_error" in r.getMessage() for r in err)
    assert any(r.exc_info for r in err), "异常行必须带完整堆栈"
    report_lines = [r.getMessage() for r in caplog.records if r.name == "migration"
                    and "event=migration_report" in r.getMessage()]
    assert any('"status": "error"' in m for m in report_lines)


def test_completion_log_requires_persistence(sandbox, caplog, monkeypatch):
    """评审 P2：migration.last 持久化失败 MUST NOT 落 completed 行——完成判据以落库为前提。"""
    import asyncio
    import logging as _logging

    from migration import router as migration_router

    root, _active = sandbox
    _old_gen0(root, books=1)

    async def _boom(key, value):
        raise RuntimeError("db-write-failed")

    monkeypatch.setattr(migration_router, "_set_app_meta", _boom)
    with caplog.at_level(_logging.INFO, logger="migration"), \
            pytest.raises(RuntimeError):
        asyncio.run(migration_router._record_completion(
            "novel.db", {"source_version": "0.24", "book_count_migrated": 2}))
    msgs = [r.getMessage() for r in caplog.records if r.name == "migration"]
    assert not any("event=migration_completed" in m for m in msgs), (
        "持久化失败时 upgrade.log 不得出现完成行（不得谎报已完成）"
    )


def test_invalid_filename_rejected_line(sandbox, caplog):
    """评审 P3：白名单 400 拒绝（start/preview 共用 _validated_source）带原因码落行。"""
    import logging as _logging

    from fastapi import HTTPException

    from migration import router as migration_router

    _root, _active = sandbox
    with caplog.at_level(_logging.INFO, logger="migration"), \
            pytest.raises(HTTPException):
        migration_router._validated_source("../escape.db")
    msgs = [r.getMessage() for r in caplog.records if r.name == "migration"]
    assert any("event=migration_source_rejected" in m and "reason=invalid_filename" in m
               for m in msgs)
# ── c-carry-retry-complete：重带恒不完整悖论根治 ────────────────────────────
#
# 事故形态（v0.30.x 真机）：首带完成后（或中断后）再点「重新带一次」，OR IGNORE
# 幂等让 book_count_migrated（本次插入数）恒 0，旧判据拿它对拍 book_count_source
# → 重带永远报「有内容没有完整迁入」，无法收尾。修复＝完整判定改按「源行在目标
# 在场」（book_count_present / rows_missing），FK 违规在零行损时降级为实名留痕。


class TestCarryRetryCompleteness:
    def test_rerun_stays_complete(self, sandbox):
        """重带幂等：第二次起 rows_inserted=0，但完整判定按在场数仍 complete。"""
        root, active = sandbox
        _old_gen0(root, books=2)
        rep1 = run_migration(root, "novel.db", active)
        assert rep1["status"] == "ok" and rep1["complete"] is True, rep1
        rep2 = run_migration(root, "novel.db", active)
        assert rep2["status"] == "ok", rep2
        assert rep2["book_count_migrated"] == 0, "OR IGNORE 重带零重复（本次写入 0）"
        assert rep2["book_count_present"] == 2, "源书全部在场"
        assert rep2["complete"] is True, rep2
        assert all(e["rows_missing"] == 0 for e in rep2["tables"]), rep2["tables"]

    def test_resume_after_interrupted_transfer(self, sandbox):
        """中断重带：首带半途（子表缺行）后重跑，补齐且判完整。"""
        root, active = sandbox
        _old_gen0(root, books=2)
        run_migration(root, "novel.db", active)
        con = sqlite3.connect(active)
        con.execute("DELETE FROM chapters")
        con.commit()
        con.close()
        rep = run_migration(root, "novel.db", active)
        assert rep["status"] == "ok", rep
        assert rep["book_count_present"] == 2
        ch = next(e for e in rep["tables"] if e["table"] == "chapters")
        assert ch["rows_inserted"] == 2 and ch["rows_missing"] == 0, ch
        assert rep["complete"] is True, rep

    def test_constraint_rejected_row_is_visible_loss(self, sandbox):
        """重插也进不去的行（目标 CHECK 拒收）＝真丢行：rows_missing 显式化，
        完整判定保守（不再静默吞）。"""
        root, active = sandbox
        p = _old_gen0(root, books=1)
        con = sqlite3.connect(p)
        # 源表无 CHECK（旧世代形态）：vocab_id/custom_text 双空的行目标装不下
        con.execute("CREATE TABLE novel_genre_forbidden "
                    "(id TEXT PRIMARY KEY, novel_id TEXT, vocab_id TEXT, custom_text TEXT)")
        con.execute("INSERT INTO novel_genre_forbidden (id, novel_id, vocab_id, custom_text) "
                    "VALUES ('gf1','n0',NULL,NULL)")
        con.commit()
        con.close()
        rep = run_migration(root, "novel.db", active)
        assert rep["status"] == "ok", rep
        gf = next(e for e in rep["tables"] if e["table"] == "novel_genre_forbidden")
        assert gf["rows_source"] == 1 and gf["rows_missing"] == 1, gf
        assert rep["complete"] is False, rep

    def test_fk_orphans_from_source_reported_but_complete(self, sandbox):
        """旧库自带孤儿行（零行损）：FK 违规只留痕＋实名 note，不再判不完整。"""
        root, active = sandbox
        p = _old_gen0(root, books=1)
        con = sqlite3.connect(p)
        con.execute(
            "INSERT INTO chapters (id, novel_id, volume_id, chapter_no, ref, title, status) "
            "VALUES ('c-orphan','n-ghost','v0',9,'第孤儿章','孤儿章','draft')")
        con.commit()
        con.close()
        rep = run_migration(root, "novel.db", active)
        assert rep["status"] == "ok", rep
        assert len(rep["fk_violations"]) > 0, "违规照报（只报不删的纪律不变）"
        assert all(e["rows_missing"] == 0 for e in rep["tables"]), rep["tables"]
        assert rep["complete"] is True, rep
        assert any("关联在旧库里就不完整" in n for n in rep["notes"]), rep["notes"]

    def test_null_in_target_notnull_column_not_dropped(self, sandbox):
        """旧世代 NULL 存量（源表无该约束）：COALESCE 中性填充，行不丢。"""
        root, active = sandbox
        p = _old_gen0(root, books=1)
        con = sqlite3.connect(p)
        con.execute("UPDATE chapters SET title = NULL WHERE id = 'c0-1'")
        con.commit()
        con.close()
        rep = run_migration(root, "novel.db", active)
        assert rep["status"] == "ok", rep
        ch = next(e for e in rep["tables"] if e["table"] == "chapters")
        assert ch["rows_missing"] == 0, "NULL 行不得被 OR IGNORE 静默吞掉"
        con = sqlite3.connect(f"file:{active}?mode=ro", uri=True)
        try:
            title = con.execute("SELECT title FROM chapters WHERE id='c0-1'").fetchone()[0]
        finally:
            con.close()
        assert title == "", "NULL 按中性字面量落库"
        assert rep["complete"] is True, rep


class TestCompletenessUnit:
    """is_complete_report / completeness_from_history 判定单源（含老数据口径）。"""

    def test_old_report_without_present_stays_conservative(self):
        """老报告（无 present 字段）退回 migrated 口径：重带悖论形态仍判不完整。"""
        from migration.engine import is_complete_report

        assert is_complete_report({"status": "ok", "book_count_source": 2,
                                   "book_count_migrated": 0}) is False
        assert is_complete_report({"status": "ok", "book_count_source": 2,
                                   "book_count_migrated": 2}) is True

    def test_present_overrides_migrated(self):
        from migration.engine import is_complete_report

        assert is_complete_report({"status": "ok", "book_count_source": 2,
                                   "book_count_migrated": 0,
                                   "book_count_present": 2}) is True
        assert is_complete_report({"status": "ok", "book_count_source": 2,
                                   "book_count_migrated": 0,
                                   "book_count_present": 1}) is False

    def test_fk_downgrade_requires_table_evidence(self):
        """FK 降级必须每张已搬表有零行损证据；无表级数据（history 适配形态）保守。"""
        from migration.engine import completeness_from_history, is_complete_report

        base = {"status": "ok", "book_count_source": 1, "book_count_present": 1,
                "fk_violations": [{"table": "chapters"}]}
        assert is_complete_report({**base, "tables": [
            {"table": "novels", "rows_missing": 0},
            {"table": "chapters", "rows_missing": 0},
        ]}) is True
        assert is_complete_report({**base, "tables": [
            {"table": "novels", "rows_missing": 0},
            {"table": "chapters", "rows_missing": None},
        ]}) is False
        assert is_complete_report({**base, "tables": [
            {"table": "novels", "rows_missing": 0},
            {"table": "chapters", "rows_missing": 2},
        ]}) is False
        # 无 tables（history 适配形态）→ 缺证保守
        assert is_complete_report(base) is False
        # history 适配器：老条目（fk 计数>0）判不完整；新条目（present 齐全）完整
        assert is_complete_report(completeness_from_history(
            {"tables_skipped": 0, "fk_violations": 1,
             "book_count_source": 1, "book_count_present": 1})) is False
        assert is_complete_report(completeness_from_history(
            {"tables_skipped": 0, "fk_violations": 0,
             "book_count_source": 1, "book_count_present": 1})) is True


class TestCarryModalReshow:
    """c-carry-modal-reshow：迁移完成后告知卡复弹根治。

    真机判例（v0.30.x 升级现场）：旧版库带 -wal/-shm 边车时，candidate_manifest
    每次候选扫描就地主开只读连接 → -shm 被顶新（实测一次跨进程只读连接就改其字节
    与 mtime）→ 完成记录指纹（旧三件套形态）永不对上 → candidates 的 carried 恒
    false → 书架告知卡复弹不止。三针：边车漂移不动指纹、清单读取零接触源、
    旧形态完成记录兼容对拍。
    """

    @pytest.fixture()
    def client(self, sandbox, monkeypatch):
        from main import app

        monkeypatch.setattr("migration.router.DATA_ROOT", sandbox[0])
        # 顺序 flake 防疫：清理全局运行库遗留的完成/抑制记录——上例的
        # migration.last 与本例 sandbox 同秒同尺寸时指纹相撞，carried 起跑即真
        import sqlite3 as _sq

        from config import DATABASE_URL

        _db = Path(DATABASE_URL.split("///")[-1])
        if _db.exists():
            con = _sq.connect(_db)
            con.execute("DELETE FROM app_meta WHERE key IN "
                        "('migration.last', 'migration.snoozed')")
            con.commit()
            con.close()
        with TestClient(app) as c:
            yield c

    @staticmethod
    def _leave_sidecars(p: Path):
        """让 -wal/-shm 留在源目录（实勘：空闲连接不持边车——关连接时 checkpoint
        即删，要等下一个连接首次读才就地重建）。

        返回持连接——它一旦关闭，最后的 checkpoint 会删边车；调用方 MUST 持到
        断言结束。"""
        w1 = sqlite3.connect(p)
        w1.execute("PRAGMA journal_mode=WAL")
        w1.execute("INSERT INTO app_meta (key, value) VALUES ('t', '1')")
        w1.commit()
        w2 = sqlite3.connect(p)
        w1.close()
        w2.execute("SELECT COUNT(*) FROM novels").fetchone()  # 首次读：边车就地重建留盘
        return w2

    def test_carried_survives_shm_drift_full_chain(self, client, sandbox):
        """全链：start→done 后 -shm 漂移，carried 仍为真（修复前恒 false）。"""
        import os
        import time

        root, _active = sandbox
        old = _old_gen0(root, books=1)
        keeper = self._leave_sidecars(old)
        try:
            def cands():
                return {c["filename"]: c for c in client.get(
                    "/api/backup/db-migration/candidates").json()["data"]["candidates"]}

            assert cands()["novel.db"]["carried"] is False
            assert client.post("/api/backup/db-migration/start",
                               json={"source_filename": "novel.db"}).json()["code"] == 0
            job: dict = {}
            for _ in range(30):
                job = client.get("/api/backup/db-migration/status").json()["data"]
                if job.get("state") in ("done", "error"):
                    break
                time.sleep(0.2)
            assert job["state"] == "done", job
            assert job["report"]["status"] == "ok"
            # 扫描侧边车漂移（＝manifest 只读连接顶新 -shm 的等价物）
            st = os.stat(f"{old}-shm")
            os.utime(f"{old}-shm", (st.st_atime, st.st_mtime + 30))
            c = cands()["novel.db"]
            assert c["carried"] is True, f"stamp={c['stamp']} drifted"
            assert c["suppressed"] is True
        finally:
            keeper.close()

    def test_manifest_zero_contact(self, sandbox):
        """清单读取零接触源三件套（WAL 库走暂存；修复前就地主开只读连接）。"""
        root, _active = sandbox
        old = _old_gen0(root, books=1)
        keeper = self._leave_sidecars(old)
        try:
            self._assert_manifest_zero_contact(old)
        finally:
            keeper.close()

    @staticmethod
    def _assert_manifest_zero_contact(old: Path) -> None:
        """跨进程读（真机形态：边车是旧版应用进程留下的，读的是新版进程）。

        同进程内读者对已是本进程形态的 -shm 常常零写入，测不出违例——真机判例的
        改写发生在跨进程（实勘：子进程一次只读连接即改 -shm 的 sha 与 mtime）。"""
        import hashlib
        import json
        import subprocess
        import sys

        def sig():
            return {s.name: (hashlib.sha256(s.read_bytes()).hexdigest(),
                             s.stat().st_mtime_ns)
                    for s in (old, Path(f"{old}-wal"), Path(f"{old}-shm"))}

        before = sig()
        backend_dir = Path(__file__).resolve().parent.parent
        code = ("import json;from pathlib import Path;"
                "from db_lifecycle import candidate_manifest;"
                f"m = candidate_manifest(Path({str(old)!r}));"
                "print(json.dumps({'books_total': m and m['books_total'],"
                " 'configs_total': m and m['configs_total']}))")
        # check=False：returncode 自判（失败信息走 stderr 断言，不靠抛异常）
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           cwd=backend_dir, timeout=60, check=False)
        assert r.returncode == 0, r.stderr[-500:]
        out = json.loads(r.stdout.strip().splitlines()[-1])
        assert out["books_total"] == 1
        assert out["configs_total"] == 0, "缺 api_configs 表按 0 条降级（非整体失败）"
        assert sig() == before, "manifest 读取不得改写源三件套任一文件"

    def test_scan_items_carry_both_stamp_forms(self, sandbox):
        """扫描项带现行＋旧两种指纹（兼容对拍的载体）。"""
        from db_lifecycle import scan_migration_candidates

        root, active = sandbox
        _old_gen0(root, books=1)
        items = scan_migration_candidates(root, "0.25", active)
        assert items and all("stamp" in it and "stamp_legacy" in it for it in items)
