"""c-carry-completion-robust —— 完成记录与候选指纹在不可靠 FS 上的健壮性。

demo 栈实锤（2026-10-24，Docker Desktop virtiofs）：迁移完成记录（migration.last）
三写三丢（引擎子进程删 WAL 后应用池连接写进孤儿 inode），且候选 mtime 指纹的
`-wal` 分量随触碰漂移——「已迁移」状态失效，告知卡每次首页复弹。

修复：完成记录走 sqlite 直连写＋mode=ro 回读校验（丢写大声报错）；完成/抑制/
回执对拍增加**内容哈希**第三形态（mtime 漂移不打翻 carried）。
"""

import asyncio
import json
import os
import sqlite3

from migration import router
from schema_version import candidate_stamp, candidate_stamp_legacy


def test_candidate_stamp_legacy_formula_includes_shm(tmp_path):
    """legacy 公式逐字保真（main+wal+shm 三件套 mtime＋合计 size）——
    c-carry-modal-reshow 兼容对拍的根基。本 PR 曾无意把 three_file_mtime 的
    `-shm` 分量删掉（review P2），此钉防回潮。"""
    p = tmp_path / "novel-v0.24.db"
    p.write_bytes(b"12345")                                     # 5 字节
    (tmp_path / "novel-v0.24.db-wal").write_bytes(b"")           # 0
    shm = tmp_path / "novel-v0.24.db-shm"
    shm.write_bytes(b"x")                                       # 1 字节
    os.utime(p, (100, 100))
    os.utime(tmp_path / "novel-v0.24.db-wal", (300, 300))
    os.utime(shm, (200, 200))
    # legacy 公式 = 名字:max(三件套 mtime):(三件套 size 合计) = :300:6
    assert candidate_stamp_legacy(p.name, p) == f"{p.name}:300:6"


def _make_lib(path, books=2, schema_id="s-0.24"):
    """最小可读库（与 test_version_upgrade_acceptance._make_lib 同构）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(
        f"""
        PRAGMA journal_mode=WAL;
        CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO app_meta VALUES ('schema_id', '{schema_id}');
        CREATE TABLE novels (id TEXT PRIMARY KEY, name TEXT, status TEXT DEFAULT 'normal');
        CREATE TABLE chapters (id TEXT PRIMARY KEY, novel_id TEXT, ref TEXT);
        CREATE TABLE api_configs (id TEXT PRIMARY KEY, name TEXT);
        """
    )
    for i in range(books):
        con.execute("INSERT INTO novels VALUES (?, ?, 'normal')", (f"bk-{i}", f"书{i}"))
        con.execute("INSERT INTO chapters VALUES (?, ?, ?)", (f"ch-{i}", f"bk-{i}", f"vol-1-ch-{i + 1}"))
    con.commit()
    con.close()
    return path


def _drift_wal_mtime(path):
    """推动 `-wal` mtime 而不动字节（模拟 virtiofs 读侧触碰：时间漂、内容不变）。"""
    wal = path.parent / (path.name + "-wal")
    if not wal.exists():
        wal.write_bytes(b"")  # 空 wal＝无未落主数据，字节对哈希零贡献
    future = 1792808691
    os.utime(wal, (future, future))


def test_completion_record_uses_content_hash(tmp_path, monkeypatch):
    """完成记录的 source_stamp＝内容哈希形态；mtime 被推走后哈希不变。"""
    root = tmp_path / "data"
    root.mkdir()
    src = _make_lib(root / "novel-v0.38.db", books=5, schema_id="s-0.38")
    stamp = router.candidate_stamp_hash(src.name, src)
    assert stamp.startswith("novel-v0.38.db:h") and len(stamp) > len(src.name) + 2

    _drift_wal_mtime(src)
    assert router.candidate_stamp_hash(src.name, src) == stamp  # 哈希不随 mtime 漂
    assert candidate_stamp(src.name, src) != stamp  # mtime 形态确已漂（对照）


def test_set_app_meta_direct_write_roundtrip(tmp_path, monkeypatch):
    """直连写＋回读校验：写完用 mode=ro 新连接能读回；重写覆盖同键。"""
    root = tmp_path / "data"
    root.mkdir()
    src = _make_lib(root / "novel-v0.39.db", books=1, schema_id="s-0.39")
    monkeypatch.setattr(router, "_active_db_path", lambda: src)

    asyncio.run(router._set_app_meta("migration.last", json.dumps({"source_stamp": "s1"})))
    asyncio.run(router._set_app_meta("migration.last", json.dumps({"source_stamp": "s2"})))
    raw = router._app_meta_value("migration.last")
    assert json.loads(raw)["source_stamp"] == "s2"

    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    row = con.execute("SELECT value FROM app_meta WHERE key='migration.last'").fetchone()
    con.close()
    assert json.loads(row[0])["source_stamp"] == "s2"  # 真落盘，非会话内可见


def test_carried_survives_wal_mtime_drift(tmp_path, monkeypatch):
    """事故回归钉：完成记录（哈希 stamp）在 `-wal` mtime 被推走后仍判 carried。

    修复前形态——完成记录按 mtime 指纹落笔＋mtime 漂移→carried 恒 False→
    告知卡每次首页复弹。"""
    root = tmp_path / "data"
    root.mkdir()
    src = _make_lib(root / "novel-v0.38.db", books=5, schema_id="s-0.38")
    active = _make_lib(root / "novel-v0.39.db", books=0, schema_id="s-0.39")
    monkeypatch.setattr(router, "_active_db_path", lambda: active)
    monkeypatch.setattr(router, "DATA_ROOT", root)

    stamp = router.candidate_stamp_hash(src.name, src)
    con = sqlite3.connect(active)
    con.execute(
        "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('migration.last', ?)",
        (json.dumps({"source_filename": src.name, "source_stamp": stamp,
                     "source_version": "0.38",
                     "report": {"status": "ok", "tables_skipped": [], "fk_violations": [],
                                "book_count_source": 5, "book_count_present": 5}}),),
    )
    con.commit()
    con.close()

    _drift_wal_mtime(src)  # 迁移完成之后，读侧把 -wal mtime 推走

    def fake_scan(r, ver, a):
        return [{"filename": src.name, "stamp": candidate_stamp(src.name, src),
                 "stamp_legacy": f"{src.name}:legacy", "stamp_hash": stamp,
                 "book_count": 5, "unreadable": False, "recommended": True}]

    monkeypatch.setattr(router, "scan_migration_candidates", fake_scan)
    cands = asyncio.run(router.candidates())["data"]["candidates"]
    mine = next(c for c in cands if c["filename"] == src.name)
    assert mine["carried"] is True  # 漂移后仍判已迁移——告知卡不再复弹
    assert mine["suppressed"] is True


def test_migrated_stamps_resolves_hash_form(tmp_path, monkeypatch):
    """清理白名单换算：哈希形态完成记录能换算成扫描项可对上的 stamp 集合。"""
    root = tmp_path / "data"
    root.mkdir()
    src = _make_lib(root / "novel-v0.38.db", books=3, schema_id="s-0.38")
    active = _make_lib(root / "novel-v0.39.db", books=0, schema_id="s-0.39")
    monkeypatch.setattr(router, "_active_db_path", lambda: active)
    monkeypatch.setattr(router, "DATA_ROOT", root)

    stamp = router.candidate_stamp_hash(src.name, src)
    con = sqlite3.connect(active)
    con.execute(
        "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('migration.last', ?)",
        (json.dumps({"source_filename": src.name, "source_stamp": stamp,
                     "source_version": "0.38",
                     "report": {"status": "ok", "tables_skipped": [], "fk_violations": [],
                                "book_count_source": 3, "book_count_present": 3}}),),
    )
    con.commit()
    con.close()

    stamps = router._migrated_stamps()
    scanned_stamp = candidate_stamp(src.name, src)
    assert scanned_stamp in stamps or stamp in stamps  # 两种形态至少其一命中扫描项
