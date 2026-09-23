"""版本升级验收用例（c-db-per-version）——评审矩阵 UP-01…UP-15 落地。

每个用例对应矩阵一行，判据是**可断言的结果**（源三件套 sha256/mtime_ns 不变、
候选排序与推荐位、计数对拍、app_meta 版本戳、路径安全），不是「看起来正常」。
证据物（哈希对照表 / 候选 JSON / report JSON）随 `-s` 打印，由 tasks 12.6 汇总到
`openspec/changes/c-db-per-version/evidence/`。

层级：UP-01…UP-10/12/13/15 在本文件（pytest）；UP-11 在 playwright（前端双出口）；
UP-14 在 tests/test_release_components.py；端到端首启（真进程 + 真 env）在
`scripts/upgrade_drill.py` 的 version-chain 阶段。真数据演练（UP-16）见 tasks 12.5。
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import create_engine

import models  # noqa: F401 —— 注册全表
from db import Base
from db_lifecycle import (
    boot_lifecycle,
    compute_schema_fingerprint,
    list_quarantined,
    scan_migration_candidates,
)
from migration.engine import run_migration
from schema_version import db_filename_for

CUR = "0.25"
PREV = "0.24"


# ── 造库与取证工具 ────────────────────────────────────────────────────────


def _sig(path: Path) -> dict:
    """证据物：三件套 (sha256, mtime_ns, size)——源只读断言的唯一判据。"""
    out = {}
    for p in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if p.exists():
            st = p.stat()
            out[p.name] = (sha256(p.read_bytes()).hexdigest()[:16], st.st_mtime_ns, st.st_size)
    return out


def _make_lib(path: Path, books: int = 3, *, plan_line: bool = False,
              schema_id: str | None = None, names: list[str] | None = None,
              id_prefix: str = "n") -> Path:
    """一套最小但真实形态的库（novels/volumes/chapters/app_meta）。"""
    cols = ("id TEXT PRIMARY KEY, novel_id TEXT, volume_no INTEGER, title TEXT, "
            "summary TEXT, chapter_count INTEGER, created_at TIMESTAMP, updated_at TIMESTAMP")
    if plan_line:
        cols += ", plan_line VARCHAR(150)"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE novels (id TEXT PRIMARY KEY, user_id TEXT, name TEXT, "
                 "slug TEXT, root_path TEXT, current_phase TEXT, status TEXT, "
                 "total_volumes INTEGER, total_chapters INTEGER, created_at TIMESTAMP, "
                 "updated_at TIMESTAMP)")
    conn.execute(f"CREATE TABLE volumes ({cols})")
    conn.execute("CREATE TABLE chapters (id TEXT PRIMARY KEY, novel_id TEXT, volume_id TEXT, "
                 "chapter_no INTEGER, ref TEXT, title TEXT, status TEXT)")
    conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT)")
    if schema_id is not None:
        conn.execute("INSERT INTO app_meta (key, value) VALUES ('schema_id', ?)", (schema_id,))
    for i in range(books):
        nm = (names or [f"书{i}"])[i] if i < len(names or []) else f"书{i}"
        nid, vid, cid = f"{id_prefix}{i}", f"{id_prefix}v{i}", f"{id_prefix}c{i}"
        conn.execute("INSERT INTO novels (id, user_id, name, slug, root_path, current_phase,"
                     " status, total_volumes, total_chapters, created_at, updated_at)"
                     " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (nid, "u1", nm, f"s{nid}", f"./data/s{nid}", "write", "active", 1, 1,
                      "2026-01-01 00:00:00", "2026-01-02 00:00:00"))
        vcols = ("id, novel_id, volume_no, title, summary, chapter_count, created_at,"
                 " updated_at" + (", plan_line" if plan_line else ""))
        conn.execute(f"INSERT INTO volumes ({vcols})"
                     f" VALUES ({','.join('?' * (9 if plan_line else 8))})",
                     (vid, nid, 1, "第一卷", "概要", 1,
                      "2026-01-01 00:00:00", "2026-01-02 00:00:00")
                     + (("本卷对抗物",) if plan_line else ()))
        conn.execute("INSERT INTO chapters (id, novel_id, volume_id, chapter_no, ref, title,"
                     " status) VALUES (?,?,?,?,?,?,?)",
                     (cid, nid, vid, 1, f"第 {i+1} 章", f"章{i}", "draft"))
    conn.commit()
    conn.close()
    return path


def _make_target(root: Path, version: str = CUR) -> Path:
    target = root / db_filename_for(version)
    se = create_engine(f"sqlite:///{target}")
    Base.metadata.create_all(se)
    se.dispose()
    return target


def _insert_novel(con, novel_id: str, name: str) -> None:
    """向目标库直插一行书——按目标 schema 自适配（NOT NULL 列补中性值）。

    目标库是全量 schema（19 列），测试不该抄列清单：NOT NULL 且无默认的列自动
    补 0/''，其余留空。"""
    cols, vals = [], []
    for _cid, cname, ctype, notnull, dflt, _pk in con.execute("PRAGMA table_info(novels)"):
        if cname == "id":
            cols.append(cname); vals.append(novel_id)
        elif cname == "name":
            cols.append(cname); vals.append(name)
        elif notnull and dflt is None:
            cols.append(cname)
            vals.append(0 if any(k in (ctype or "").upper()
                                 for k in ("INT", "REAL", "NUM", "BOOL")) else "")
    con.execute(f"INSERT INTO novels ({','.join(cols)})"
                f" VALUES ({','.join('?' * len(cols))})", vals)


def _count(con, table: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _app_meta(path: Path) -> dict:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = dict(con.execute("SELECT key, value FROM app_meta").fetchall())
    except sqlite3.Error:
        rows = {}
    finally:
        con.close()
    return rows


# ── UP-01 全新安装首启 ────────────────────────────────────────────────────


def test_up01_fresh_boot_empty(tmp_path):
    """UP-01：空 DATA_ROOT 首启 → 建自己版本的库、书架为空、无候选。"""
    target = tmp_path / db_filename_for(CUR)
    res = boot_lifecycle(target, Base.metadata, compute_schema_fingerprint(Base.metadata))
    assert res["boot"] == "fresh_boot"
    _make_target(tmp_path)  # create_all 兜底
    con = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        assert _count(con, "novels") == 0
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert {"novels", "volumes", "chapters", "characters", "novel_hooks", "app_meta"} <= tables
    cands = scan_migration_candidates(tmp_path, CUR, target)
    assert [c["filename"] for c in cands] == []
    print(f"[UP-01] db={target.name} books=0 candidates=[] quarantined={list_quarantined(tmp_path)}")


# ── UP-02 同路径升级（主场景） ────────────────────────────────────────────


def test_up02_in_place_upgrade(tmp_path):
    """UP-02：v0.24 库 → v0.25 首启：新库空启动 + 源三件套不变 + 候选 + 搬运对拍。"""
    src = _make_lib(tmp_path / db_filename_for(PREV), books=3, plan_line=True,
                    schema_id="old-fp")
    before = _sig(src)
    target = tmp_path / db_filename_for(CUR)

    assert boot_lifecycle(target, Base.metadata, "fp-new")["boot"] == "fresh_boot"
    _make_target(tmp_path)
    assert target.read_bytes() != src.read_bytes()

    cands = scan_migration_candidates(tmp_path, CUR, target)
    assert [c["filename"] for c in cands] == [src.name]
    assert cands[0]["version"] == PREV and cands[0]["book_count"] == 3
    assert cands[0]["recommended"] is True

    rep = run_migration(tmp_path, src.name, target)
    assert rep["status"] == "ok", rep
    assert rep["source_version"] == PREV
    assert rep["book_count_source"] == 3 and rep["book_count_migrated"] == 3
    assert _sig(src) == before, "源三件套 sha256/mtime_ns 必须逐字节不变"
    con = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        assert (_count(con, "novels"), _count(con, "volumes"), _count(con, "chapters")) == (3, 3, 3)
        pl = con.execute("SELECT plan_line FROM volumes LIMIT 1").fetchone()[0]
    finally:
        con.close()
    assert pl == "本卷对抗物", "列交集搬运保留旧库已有列（plan_line 不丢）"
    meta = _app_meta(target)
    assert meta["app_version"] == CUR
    assert json.loads(meta["app_components"])["db_filename"] == db_filename_for(CUR)
    print(f"[UP-02] src={before}\n[UP-02] report_tables={len(rep['tables'])} "
          f"fk_violations={len(rep['fk_violations'])} app_meta={meta}")


# ── UP-03 遗留代数名（本 change 之前的落地形态） ──────────────────────────


def test_up03_legacy_generation_bringable(tmp_path):
    """UP-03：盘上只有 `novel-v1.db`（纯数字遗留名）→ 进候选、垫底、可带回。

    回归点：`1 > 0.25` 若按语义化比较会被「版本 ≥ 当前不收」静默排除——本机
    1213 本的真实形态正落在这里。
    """
    legacy = _make_lib(tmp_path / "novel-v1.db", books=3)
    before = _sig(legacy)
    target = tmp_path / db_filename_for(CUR)
    _make_target(tmp_path)

    cands = scan_migration_candidates(tmp_path, CUR, target)
    assert [c["filename"] for c in cands] == ["novel-v1.db"], cands
    assert cands[0]["kind"] == "legacy" and cands[0]["legacy_generation"] == 1
    assert cands[0]["recommended"] is True, "唯一遗留候选＝『紧邻上一版』，可单次确认带回"

    rep = run_migration(tmp_path, "novel-v1.db", target)
    assert rep["status"] == "ok" and rep["legacy_generation"] == 1
    assert rep["book_count_migrated"] == 3
    assert _sig(legacy) == before
    print(f"[UP-03] candidates={json.dumps(cands, ensure_ascii=False)}")


# ── UP-04 第 0 代 + WAL 边车（未 checkpoint 的提交必须一起带过来）──────────


_WAL_BOOK = ("INSERT INTO novels (id, user_id, name, slug, root_path, current_phase, status,"
             " total_volumes, total_chapters, created_at, updated_at)"
             " VALUES ('n9','u1','WAL 里的书','s9','./data/s9','write','active',1,1,"
             "'2026-01-01 00:00:00','2026-01-02 00:00:00')")

# 硬退出（不做干净关闭）→ WAL 不被 checkpoint，提交只存在于 -wal 里
_WAL_WRITER = f"""
import os, sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute("PRAGMA journal_mode=WAL")
con.execute({_WAL_BOOK!r})
con.commit()
os._exit(0)
"""


def _write_uncheckpointed(path: Path) -> None:
    """在子进程里以 WAL 模式写一行并硬退出（保留未落主文件的提交）。"""
    proc = subprocess.run([sys.executable, "-c", _WAL_WRITER, str(path)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_up04_gen0_with_wal_sidecar(tmp_path):
    """UP-04：`novel.db` 带活跃 `-wal`（未 checkpoint 的提交）→ 计数含 WAL、源不变。"""
    src = _make_lib(tmp_path / "novel.db", books=2)
    _write_uncheckpointed(src)
    wal = Path(f"{src}-wal")
    assert wal.exists() and wal.stat().st_size > 0, "前置：提交只存在于 WAL"
    before = _sig(src)
    assert set(before) == {"novel.db", "novel.db-wal", "novel.db-shm"}, before

    target = tmp_path / db_filename_for(CUR)
    _make_target(tmp_path)
    cands = scan_migration_candidates(tmp_path, CUR, target)
    assert cands[0]["book_count"] == 3, "体检必须读得到 WAL 里的提交"
    assert _sig(src) == before, "体检不得改动源（含边车 mtime）"

    rep = run_migration(tmp_path, "novel.db", target)
    assert rep["status"] == "ok" and rep["book_count_source"] == 3
    con = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute("SELECT name FROM novels ORDER BY id")]
    finally:
        con.close()
    assert "WAL 里的书" in names, "WAL 中未 checkpoint 的提交不得丢"
    assert _sig(src) == before, "源三件套（含 WAL）不得被 checkpoint/改动"
    print(f"[UP-04] src_sig={before}\n[UP-04] target_books={names}")


def test_up04b_wal_without_sidecars_no_trace(tmp_path):
    """UP-04b：`WAL 模式头 + 缺 -shm`（只拷了 `.db` 的库）→ 体检可读且**源目录零痕迹**。

    只读连接会在源目录就地创建 `-shm`/`-wal`（旧实现的实际副作用）——复检一律走
    暂存口径，源目录不得多出任何文件、源文件 mtime 不得变。
    """
    src = _make_lib(tmp_path / "novel.db", books=3)
    Path(f"{src}-wal").unlink(missing_ok=True)
    Path(f"{src}-shm").unlink(missing_ok=True)
    # 只拷 .db 的形态：把库拷到别处，再删掉边车（保留 WAL 模式头）
    lone = tmp_path / "lone"
    lone.mkdir()
    copy = lone / "novel.db"
    copy.write_bytes(src.read_bytes())
    assert not list(lone.glob("novel.db-*")), "前置：无任何边车"
    before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in lone.iterdir()}

    info = __import__("db_lifecycle").probe_library(copy)
    assert info["unreadable"] is False and info["book_count"] == 3, info
    assert not list(lone.glob("novel.db-*")), "复检不得在源目录留下 -shm/-wal"
    assert {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in lone.iterdir()} == before
    print(f"[UP-04b] lone_probe={info}")


# ── UP-05 回滚：装回旧版本直接可用 ────────────────────────────────────────


def test_up05_rollback_old_version_keeps_own_db(tmp_path):
    """UP-05：v0.25 写过书后装回 v0.24 → 打开自己的库（3 本），新库只列出不推荐。"""
    # v0.24 的库由 v0.24 自己写过 → 带该版本的指纹戳（回滚时才算「自己的库」）
    old = _make_lib(tmp_path / db_filename_for(PREV), books=3,
                    schema_id=compute_schema_fingerprint(Base.metadata))
    target = tmp_path / db_filename_for(CUR)
    _make_target(tmp_path)
    run_migration(tmp_path, old.name, target)
    # v0.25 里再写一本
    con = sqlite3.connect(target)
    _insert_novel(con, "nx", "v0.25 新写的")
    con.commit()
    con.close()
    new_sig = _sig(target)

    # 装回 v0.24：它按路径找自己的库
    res = boot_lifecycle(old, Base.metadata, compute_schema_fingerprint(Base.metadata))
    assert res["boot"] == "current", res
    con = sqlite3.connect(f"file:{old}?mode=ro", uri=True)
    try:
        assert _count(con, "novels") == 3, "回滚后自己的库直接可用（不出现空书架）"
    finally:
        con.close()
    assert _sig(target) == new_sig, "回滚不得触碰新版本库"
    assert list_quarantined(tmp_path) == []
    cands = scan_migration_candidates(tmp_path, PREV, old)
    newer = [c for c in cands if c["version"] == CUR]
    assert newer and newer[0]["recommended"] is False, "更新的版本列出但不推荐"
    print(f"[UP-05] rollback_candidates={json.dumps(cands, ensure_ascii=False)}")


# ── UP-06 跨两版链式搬运 + 幂等 ──────────────────────────────────────────


def test_up06_two_hop_chain(tmp_path):
    """UP-06：v0.23 + v0.24 → v0.25：候选按版本降序、两跳都成功、无重复。"""
    a = _make_lib(tmp_path / db_filename_for("0.23"), books=2, schema_id="fp-023",
                  id_prefix="a")
    b = _make_lib(tmp_path / db_filename_for(PREV), books=3, schema_id="fp-024",
                  id_prefix="b")
    sig = {p.name: _sig(p) for p in (a, b)}
    target = tmp_path / db_filename_for(CUR)
    _make_target(tmp_path)

    cands = scan_migration_candidates(tmp_path, CUR, target)
    assert [c["filename"] for c in cands] == [b.name, a.name], "逐段数值比较降序"
    assert [c["recommended"] for c in cands] == [True, False]

    for src in (b, a):
        rep = run_migration(tmp_path, src.name, target)
        assert rep["status"] == "ok", rep
    con = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        assert _count(con, "novels") == 5
        dup = con.execute("SELECT id, COUNT(*) c FROM novels GROUP BY id HAVING c > 1").fetchall()
    finally:
        con.close()
    assert dup == [], "链式搬运零重复行"
    for p in (a, b):
        assert _sig(p) == sig[p.name]
    print(f"[UP-06] chain=0.23→0.25 books=5 dups=0")


def test_up06b_rerun_is_idempotent(tmp_path):
    """UP-06b：同一源再搬一次（用户重复点）→ 零重复、report 计数一致。"""
    src = _make_lib(tmp_path / db_filename_for(PREV), books=3)
    before = _sig(src)
    target = tmp_path / db_filename_for(CUR)
    _make_target(tmp_path)
    assert run_migration(tmp_path, src.name, target)["status"] == "ok"
    rep2 = run_migration(tmp_path, src.name, target)
    # 新语义：migrated＝**本次真正带回**的书数 → 重复点一次带回 0 本（幂等的正面证据），
    # 目标库总数不变
    assert rep2["status"] == "ok" and rep2["book_count_migrated"] == 0, rep2
    assert rep2["book_count_target_after"] == 3
    con = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        assert _count(con, "novels") == 3
    finally:
        con.close()
    assert _sig(src) == before


# ── UP-07 搬运中断（硬杀）后重跑 ─────────────────────────────────────────


_KILL_CHILD = r"""
import os, sys
sys.path.insert(0, os.getcwd())
from pathlib import Path
from migration.engine import run_migration

def cb(ev):
    if ev.get("stage") == "transfer" and ev.get("tables_done", 0) >= 1:
        os._exit(9)          # 硬杀：跳过 finally 清理，留下 staging 残留

root = Path(sys.argv[1]); src = sys.argv[2]; tgt = Path(sys.argv[3])
run_migration(root, src, tgt, report_progress=cb)
print("should-not-reach")
"""


def test_up07_hard_kill_then_rerun(tmp_path):
    """UP-07：搬运中硬杀 → 源无损、staging 残留；重跑零重复。"""
    src = _make_lib(tmp_path / db_filename_for(PREV), books=3, schema_id="fp-old")
    before = _sig(src)
    target = tmp_path / db_filename_for(CUR)
    _make_target(tmp_path)

    env = dict(os.environ, CLIENT_VERSION=CUR, DATA_ROOT=str(tmp_path),
               DATABASE_URL=f"sqlite+aiosqlite:///{target}")
    proc = subprocess.run([sys.executable, "-c", _KILL_CHILD, str(tmp_path), src.name, str(target)],
                          cwd=Path(__file__).resolve().parent.parent, env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 9, (proc.returncode, proc.stdout, proc.stderr)
    assert proc.stdout.strip() == "", "必须在 transfer 阶段前被硬杀"
    staging = tmp_path / "migration-staging"
    residue = sorted(p.name for p in staging.iterdir()) if staging.is_dir() else []
    assert _sig(src) == before, "硬杀不得动源"

    from db_lifecycle import clean_stale_staging

    cleaned = clean_stale_staging(tmp_path)
    rep = run_migration(tmp_path, src.name, target)
    assert rep["status"] == "ok", rep
    con = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        counts = tuple(_count(con, t) for t in ("novels", "volumes", "chapters"))
        dup = con.execute("SELECT id, COUNT(*) c FROM novels GROUP BY id HAVING c > 1").fetchall()
    finally:
        con.close()
    assert counts == (3, 3, 3) and dup == [], "重跑必须零重复"
    assert _sig(src) == before
    print(f"[UP-07] kill_rc=9 residue={residue} cleaned={cleaned} rerun_counts={counts}")


# ── UP-08 用户先在新库写作，之后再搬运 ───────────────────────────────────


def test_up08_local_wins_on_same_pk(tmp_path):
    """UP-08：同 PK 行当前库获胜（新写内容不被旧库覆盖），旧库其余行带回。"""
    src = _make_lib(tmp_path / db_filename_for(PREV), books=2, names=["旧名", "乙"])
    target = tmp_path / db_filename_for(CUR)
    _make_target(tmp_path)
    con = sqlite3.connect(target)
    _insert_novel(con, "n0", "新名")
    con.commit()
    con.close()

    rep = run_migration(tmp_path, src.name, target)
    assert rep["status"] == "ok"
    con = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        rows = dict(con.execute("SELECT id, name FROM novels"))
    finally:
        con.close()
    assert rows == {"n0": "新名", "n1": "乙"}, rows
    assert "旧名" not in rows.values(), "同 PK 不覆盖当前库"
    src_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        assert dict(src_con.execute("SELECT id, name FROM novels"))["n0"] == "旧名"
    finally:
        src_con.close()
    print(f"[UP-08] target={rows} (同 PK 当前库获胜)")


# ── UP-09 同名库损坏：隔离 + 只读可见 ───────────────────────────────────


def test_up09_corrupt_same_version(tmp_path):
    """UP-09：当前版本库损坏 → `.corrupt-*` 隔离、空库启动、隔离件只读可见。"""
    db = tmp_path / db_filename_for(CUR)
    db.write_bytes(b"not a database" * 200)
    res = boot_lifecycle(db, Base.metadata, "fp")
    assert res["boot"] == "quarantined_new" and ".corrupt-" in res["quarantined_to"]
    _make_target(tmp_path)  # 空库顶上
    quarantined = list_quarantined(tmp_path)
    assert [q["filename"] for q in quarantined] == [Path(res["quarantined_to"]).name]
    cands = scan_migration_candidates(tmp_path, CUR, db)
    assert cands == [], "隔离件不进候选（但进只读面）"
    print(f"[UP-09] quarantined={json.dumps(quarantined, ensure_ascii=False)} candidates=[]")


# ── UP-10 dev 哨兵 ───────────────────────────────────────────────────────


def test_up10_dev_sentinel(tmp_path, monkeypatch):
    """UP-10：dev 构建＝哨兵名、自身不入候选、不做版本过滤；正式版过滤。"""
    monkeypatch.delenv("CLIENT_VERSION", raising=False)
    from schema_version import active_db_filename, app_version

    assert app_version() == "dev" and active_db_filename() == "novel-dev.db"
    dev_db = _make_lib(tmp_path / "novel-dev.db", books=1)
    _make_lib(tmp_path / "novel-v0.99.db", books=1)
    _make_lib(tmp_path / db_filename_for(PREV), books=1)

    dev_cands = scan_migration_candidates(tmp_path, "dev", dev_db)
    names = [c["filename"] for c in dev_cands]
    assert "novel-dev.db" not in names, "哨兵自身是活跃库"
    assert "novel-v0.99.db" in names, "dev 无版本语义 → 不过滤更新版本"

    monkeypatch.setenv("CLIENT_VERSION", CUR)
    prod_cands = scan_migration_candidates(tmp_path, CUR, tmp_path / db_filename_for(CUR))
    prod_names = [c["filename"] for c in prod_cands]
    assert prod_names[-1] == "novel-dev.db", "哨兵垫底列出（别的构建写过的数据仍可达）"
    assert "novel-v0.99.db" in prod_names, "列出（可达）"
    assert [c["recommended"] for c in prod_cands if c["filename"] == "novel-v0.99.db"] == [False]
    assert [c["recommended"] for c in prod_cands if c["filename"] == db_filename_for(PREV)] == [True]
    print(f"[UP-10] dev={json.dumps(names, ensure_ascii=False)} prod={json.dumps(prod_names, ensure_ascii=False)}")


# ── UP-12 旧库留存与清理（只认已带回；路径收口） ─────────────────────────


def test_up12_retention_and_cleanup(tmp_path):
    """UP-12：默认保留最近 2 份；未带回的件不可删；路径穿越被拒。"""
    from db_lifecycle import deletable_candidates, delete_candidate, validate_candidate_filename
    from schema_version import candidate_stamp

    migrated: set[str] = set()
    libs = []
    for ver in ("0.21", "0.22", "0.23", "0.24"):
        p = _make_lib(tmp_path / db_filename_for(ver), books=1)
        libs.append(p)
        migrated.add(candidate_stamp(p.name, p))
        time.sleep(0.01)
        os.utime(p, None)
    never_migrated = _make_lib(tmp_path / "novel-v0.20.db", books=1)

    items = deletable_candidates(tmp_path, migrated, keep=2)
    assert [it["filename"] for it in items] == [db_filename_for("0.22"), db_filename_for("0.21")], items
    assert never_migrated.name not in [it["filename"] for it in items], "未带回的件不可删"

    # 路径安全：穿越 / 子目录 / 活跃库 / 哨兵名 一律拒
    assert validate_candidate_filename(tmp_path, "../novel-v0.21.db") is None
    assert validate_candidate_filename(tmp_path, "sub/novel-v0.21.db") is None
    assert validate_candidate_filename(tmp_path, "novel-dev.db") is None
    assert validate_candidate_filename(tmp_path, db_filename_for("0.21"),
                                       tmp_path / db_filename_for("0.21")) is None
    assert delete_candidate(tmp_path, "../novel-v0.21.db") is False
    assert never_migrated.exists()

    assert delete_candidate(tmp_path, db_filename_for("0.21")) is True
    assert not (tmp_path / db_filename_for("0.21")).exists()
    assert (tmp_path / db_filename_for("0.23")).exists()
    assert (tmp_path / db_filename_for(PREV)).exists()
    print(f"[UP-12] deletable={[it['filename'] for it in items]} deleted=1 kept=2 "
          f"never_migrated_kept={never_migrated.name}")


def test_up12b_retention_endpoints(tmp_path, monkeypatch):
    """UP-12b：端点面（待删清单/执行）+ 部分失败语义（未带回件永不出现）。"""
    from fastapi.testclient import TestClient

    from schema_version import candidate_stamp

    root = tmp_path / "data"
    root.mkdir()
    for ver in ("0.21", "0.22", "0.23"):
        _make_lib(root / db_filename_for(ver), books=1)
    stamps = {v: candidate_stamp(db_filename_for(v), root / db_filename_for(v))
              for v in ("0.21", "0.22", "0.23")}
    # history：0.21＝本次成功带回（完整）；0.22＝半途（整表跳过）；0.23＝老格式（缺完整性字段）
    history = [
        {"source_filename": db_filename_for("0.21"), "source_stamp": stamps["0.21"],
         "book_count_migrated": 1, "book_count_source": 1,
         "tables_skipped": 0, "fk_violations": 0},
        {"source_filename": db_filename_for("0.22"), "source_stamp": stamps["0.22"],
         "book_count_migrated": 1, "book_count_source": 1,
         "tables_skipped": 1, "fk_violations": 0},
        {"source_filename": db_filename_for("0.23"), "source_stamp": stamps["0.23"],
         "book_count_migrated": 1},
    ]
    target = root / db_filename_for(CUR)
    _make_target(root)
    con = sqlite3.connect(target)
    con.execute("INSERT INTO app_meta (key, value) VALUES ('migration.history', ?)",
                (json.dumps(history),))
    con.execute("INSERT INTO app_meta (key, value) VALUES ('migration.last', ?)",
                (json.dumps({"source_filename": db_filename_for("0.21"),
                             "source_stamp": stamps["0.21"]}),))
    con.commit()
    con.close()

    from main import app
    import migration.router as mr

    monkeypatch.setattr(mr, "DATA_ROOT", root)
    monkeypatch.setattr(mr, "HISTORY_KEY", "migration.history")
    monkeypatch.setattr(mr, "_active_db_path", lambda: target)
    with TestClient(app) as client:
        d = client.get("/api/backup/db-migration/retention").json()["data"]
        # 新契约（c-db-version-hardening）：只认 migration.last 且搬运完整——
        # 半途的 0.22 与老格式的 0.23 即使在 history 里也 SHALL NOT 进待删清单
        assert [it["filename"] for it in d["items"]] == [db_filename_for("0.21")], d
        assert d["keep"] == 0  # 白名单收窄后保留窗口由白名单承载（keep 置 0）
        r = client.post("/api/backup/db-migration/cleanup",
                        json={"filenames": [db_filename_for("0.21"), db_filename_for("0.22"),
                                            db_filename_for("0.23"), "../../etc/passwd"]}).json()["data"]
        assert r["deleted"] == [db_filename_for("0.21")]
        assert set(r["refused"]) == {db_filename_for("0.22"), db_filename_for("0.23"),
                                     "../../etc/passwd"}
    assert not (root / db_filename_for("0.21")).exists()
    assert (root / db_filename_for("0.22")).exists()
    assert (root / db_filename_for("0.23")).exists()
    print(f"[UP-12b] retention={d} cleanup={r}")


# ── UP-13 版本戳与库自证 ─────────────────────────────────────────────────


def test_up13_version_stamp_and_self_proof(tmp_path):
    """UP-13：新库有 app_version＋组件快照；源 app_meta 前后不变；库被拷走仍自证。"""
    src = _make_lib(tmp_path / db_filename_for(PREV), books=2, schema_id="fp-old")
    src_before = _app_meta(src)
    target = tmp_path / db_filename_for(CUR)
    _make_target(tmp_path)

    assert run_migration(tmp_path, src.name, target)["status"] == "ok"
    meta = _app_meta(target)
    assert meta["app_version"] == CUR
    comp = json.loads(meta["app_components"])
    assert comp["db_filename"] == db_filename_for(CUR) and comp["backup_format_version"] >= 1
    assert _app_meta(src) == src_before, "源库 app_meta 不得被写（源只读）"

    copied = tmp_path / "elsewhere"
    copied.mkdir()
    shutil_copy = copied / target.name
    shutil_copy.write_bytes(target.read_bytes())
    assert _app_meta(shutil_copy)["app_version"] == CUR, "库文件脱离数据目录仍自证来源"
    print(f"[UP-13] target_meta={meta} src_diff={_app_meta(src) == src_before}")


# ── UP-15 噪声排除（端到端形态） ─────────────────────────────────────────


def test_up15_noise_never_candidate(tmp_path):
    """UP-15：边车/`.bak`/`.corrupt`/磁盘残件/空库/空壳/staging 全不进候选。"""
    good = _make_lib(tmp_path / db_filename_for(PREV), books=1)
    (tmp_path / f"{good.name}-wal").write_bytes(b"\x00" * 32)
    (tmp_path / f"{good.name}-shm").write_bytes(b"\x00" * 16)
    (tmp_path / f"{good.name}.bak-20260910").write_bytes(b"\x00" * 8)
    (tmp_path / f"{good.name}.corrupt-20260910-120000").write_bytes(b"\x00" * 8)
    (tmp_path / "novel.db.recovered-20260917-052608").write_bytes(b"\x00" * 64)
    (tmp_path / "novels.db").write_bytes(b"")
    sqlite3.connect(tmp_path / db_filename_for("0.20")).close()          # 空壳
    _make_lib(tmp_path / db_filename_for("0.19"), books=0)              # 空库（0 本）
    staging = tmp_path / "migration-staging" / "x"
    staging.mkdir(parents=True)
    _make_lib(staging / db_filename_for("0.18"), books=5)

    cands = scan_migration_candidates(tmp_path, CUR, tmp_path / db_filename_for(CUR))
    assert [c["filename"] for c in cands] == [good.name]
    assert all(".corrupt" not in c["filename"] and ".bak" not in c["filename"] for c in cands)
    print(f"[UP-15] candidates={[c['filename'] for c in cands]}")


# ── 回归：release 组件清单单源（UP-14 的单源部分） ────────────────────────


def test_up14_components_single_source(tmp_path):
    """UP-14（单源部分）：CI 用的取数脚本与后端单源逐字一致。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    subprocess.run([sys.executable, "scripts/release_components.py", CUR],
                   cwd=Path(__file__).resolve().parent.parent, check=True,
                   capture_output=True, text=True)
    from scripts.release_components import build_components

    comp = build_components(CUR)
    assert comp["db_filename"] == db_filename_for(CUR)
    from backup.format import FORMAT_VERSION

    assert comp["backup_format_version"] == FORMAT_VERSION


# ── UP-16b 改名前世代门禁（真数据演练现场发现）────────────────────────────


def test_up16b_pre_rename_generation_gated(tmp_path):
    """`projects` 世代（novel 正名之前）→ 不进候选 + precheck 引走备份包通道。

    现场发现（UP-16 真数据演练）：本机 `client/backend/data/novel.db` 无 `novels` 表、
    业务数据挂在 `projects` 下——行级搬运行列交集与表名都对不上，**搬过去会是「成功但
    0 本书」**。故书数只认 `novels`（不进候选），直接点名则响亮拒绝。
    """
    from migration.engine import precheck

    src = tmp_path / "novel.db"
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO projects (id, name) VALUES ('p1', '改名前的书')")
    conn.execute("CREATE TABLE volumes (id TEXT PRIMARY KEY, project_id TEXT, volume_no INTEGER)")
    conn.commit()
    conn.close()
    target = tmp_path / db_filename_for(CUR)
    _make_target(tmp_path)

    cands = scan_migration_candidates(tmp_path, CUR, target)
    assert cands == [], f"projects 世代不计书数、不进候选：{cands}"
    pc = precheck(tmp_path, "novel.db", target)
    assert pc["ok"] is False and pc["reason"] == "pre_rename_generation", pc
    print(f"[UP-16b] gated: book_count 不计 projects → 候选为空；precheck={pc['reason']}")


# ── 检视整改回归（2026-09-22） ────────────────────────────────────────────


def test_up_review_books_skipped_reports_zero_migrated(tmp_path, monkeypatch):
    """检视 P2：`novels` 表被跳过时 `book_count_migrated` 必须是 0。

    旧实现回退成「目标库总数」——目标已有书时会把「本次什么都没带过来」报成
    「带回了一堆」，结果页数字虚高。
    """
    import migration.engine as eng

    src = _make_lib(tmp_path / "novel-v0.24.db", books=2)
    target = tmp_path / db_filename_for(CUR)
    _make_target(tmp_path)
    # 造一个「目标已有书」的现场
    con = sqlite3.connect(target)
    _insert_novel(con, "existing-1", "目标里已有的书")
    con.commit()
    con.close()

    # 让 novels 表进 tables_skipped（模拟 NOT NULL 阻塞）
    real_build_plan = eng.build_plan

    def _plan_without_novels(staged):
        plan = real_build_plan(staged)
        plan["tables"] = [e for e in plan["tables"] if e["table"] != "novels"]
        plan["tables_skipped"].append({"table": "novels", "reason": "notnull_nodefault",
                                       "columns": ["x"]})
        return plan

    monkeypatch.setattr(eng, "build_plan", _plan_without_novels)
    rep = eng.run_migration(tmp_path, "novel-v0.24.db", target)
    assert rep["status"] == "ok", rep
    assert rep["book_count_source"] == 2
    assert rep["book_count_migrated"] == 0, "跳过 novels 时本次写入必须是 0（不得回退成目标总数）"
    assert rep["book_count_target_after"] == 1


def test_up_review_retention_excludes_active_db(tmp_path):
    """检视 P3：待删清单按**路径**排除活跃库（stamp 恰好命中历史时也不得列出）。"""
    from db_lifecycle import deletable_candidates
    from schema_version import candidate_stamp

    active = _make_lib(tmp_path / db_filename_for(CUR), books=1)
    old = _make_lib(tmp_path / db_filename_for(PREV), books=1)
    stamps = {candidate_stamp(active.name, active), candidate_stamp(old.name, old)}

    without_exclusion = deletable_candidates(tmp_path, stamps, keep=0)
    assert {it["filename"] for it in without_exclusion} == {active.name, old.name}

    with_exclusion = deletable_candidates(tmp_path, stamps, keep=0, active_db_path=active)
    assert {it["filename"] for it in with_exclusion} == {old.name}
