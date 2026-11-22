"""db_lifecycle — 库文件版本治理（c-db-per-version）。

首启状态机（`novel-v{本机版本}.db`）：
- 不存在，或存在但无表且无 `schema_id`（中断首启残壳）→ `fresh_boot`（空库，
  `create_all` 兜底）。
- 指纹匹配 → `current`。
- 指纹不符且**可读** → 分流改名 `novel-v{X}.db.mismatch-<stamp>`（**可作候选
  带回**：同 tag 重打包、删 tag 重打、dev 连续开发三种事故的唯一出口）。
- **不可读** → 三件套移入 `novel-v{X}.db.corrupt-<stamp>/` 隔离（只读可见，
  不进候选）。改名失败不抛异常（Windows 文件锁不得把应用打崩）。

候选扫描：白名单**形状枚举**（`schema_version.parse_db_filename`）＋活跃库
**按路径排除**（不靠版本比较）＋三件套 `max(mtime)` 排序＋`recommended` 后端
单源＋只读打不开时走暂存复检（修「WAL 模式头缺 `-shm` 被误判不可读」）。

代内就地补列路径已随 `SCHEMA_VERSION` 一并退役——本模块不再有任何对既有库执行
DDL 的能力（每版只写自己的库文件）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import sqlite3
import tempfile
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path

from schema_version import (
    app_version,
    candidate_rank,
    candidate_stamp,
    candidate_stamp_hash,
    candidate_stamp_legacy,
    data_file_mtime,
    data_file_size,
    data_identity_key,
    is_newer,
    is_release_version,
    parse_db_filename,
    sidecar_paths,
)

# c-upgrade-log：库生命周期属无损升级链——migration 具名 logger（upgrade.log 专项档
# ＋propagate 双写 app.log）。
logger = logging.getLogger("migration")

SCHEMA_ID_KEY = "schema_id"
APP_VERSION_KEY = "app_version"
APP_COMPONENTS_KEY = "app_components"
STAGING_DIRNAME = "migration-staging"
MISMATCH_MARKER = "mismatch"
CORRUPT_MARKER = "corrupt"


# ── 指纹与体检 ────────────────────────────────────────────────────────────


def compute_schema_fingerprint(metadata) -> str:
    lines = []
    for table in sorted(metadata.tables.values(), key=lambda t: t.name):
        cols = "|".join(
            f"{c.name}:{c.type!s}"
            for c in sorted(table.columns, key=lambda c: c.name)
        )
        lines.append(f"{table.name}::{cols}")
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()[:32]


def inspect_library(db_path: Path) -> dict:
    """只读体检：exists/unreadable/schema_id/book_count/has_app_meta/has_tables。"""
    out = {"exists": db_path.exists(), "unreadable": False, "schema_id": None,
           "book_count": None, "has_app_meta": False, "has_tables": False,
           "has_projects": False}
    if not out["exists"]:
        return out
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
        try:
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            out["has_tables"] = bool(tables)
            if "app_meta" in tables:
                out["has_app_meta"] = True
                row = con.execute(
                    "SELECT value FROM app_meta WHERE key=?", (SCHEMA_ID_KEY,)
                ).fetchone()
                if row:
                    out["schema_id"] = row[0]
            # 书数只认 novels：`projects` 是「novel 正名」之前的世代，行级搬运搬不到
            # 它的数据（表名/外键列都不同）——计它会把「搬不到书的库」标成有书
            out["has_projects"] = "projects" in tables
            if "novels" in tables:
                out["book_count"] = con.execute("SELECT COUNT(*) FROM novels").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        out["unreadable"] = True
    return out


def inspect_schema(db_path: Path) -> dict[str, list[str]] | None:
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
        try:
            schema = {}
            for (name,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ):
                schema[name] = [r[1] for r in con.execute(f"PRAGMA table_info('{name}')")]
            return schema
        finally:
            con.close()
    except sqlite3.Error:
        return None


# ── 副本整备与只读探针（引擎与候选体检同口径） ────────────────────────────


def copy_sidecars(src: Path, dst: Path) -> None:
    """拷贝库本体与 `-wal`（**SHALL NOT 拷 `-shm`**：易失共享内存索引）。

    只读连接在 WAL 模式库上需要 `-shm` 且要可写，这正是「只拷 .db 的库」打不开
    的成因；把整备交给 `prepare_staged`（可写打开自动重建 `-shm`）才是正确口径。
    """
    shutil.copy2(src, dst)
    wal = Path(f"{src}-wal")
    if wal.exists():
        shutil.copy2(wal, f"{dst}-wal")


def prepare_staged(staged: Path) -> bool:
    """整备副本：可写打开（按需重建 `-shm`）→ `wal_checkpoint(TRUNCATE)` 收编 WAL
    → `integrity_check`。返回是否可读且完整。"""
    try:
        con = sqlite3.connect(str(staged), timeout=10)
        try:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            row = con.execute("PRAGMA integrity_check").fetchone()
            return bool(row) and row[0] == "ok"
        finally:
            con.close()
    except sqlite3.Error:
        return False


def snapshot_signature(db_path: Path) -> tuple:
    """拷贝一致性守卫签名：三件套 `(name, size, mtime_ns)`（缺件记 -1）。"""
    sig = []
    for p in (db_path, *sidecar_paths(db_path)):
        if p.exists():
            st = p.stat()
            sig.append((p.name, st.st_size, st.st_mtime_ns))
        else:
            sig.append((p.name, -1, -1))
    return tuple(sig)


def migration_probe(db_path: Path) -> dict:
    """迁移用体检（**一次**暂存口径，源目录零痕迹）。

    返回 `{unreadable, book_count, has_tables, tables, novels_roots}`——
    precheck 的可读性判定与「ADR 前世代」门禁同源于这一次读取（各自开连接会在
    WAL 库上改写 `-shm`，实测 sha 变化，违源只读）。
    """
    tables: set[str] = set()
    roots: list[str] = []
    book_count = None

    def _read(con: sqlite3.Connection) -> None:
        """读结构/计数/root_path。**可读性只由「打开＋读表清单」决定**——某条具体查询
        失败（如老库 `novels` 没有 `root_path` 列）不得被误判成整库不可读（会连带把
        precheck 打成 source_unreadable）。"""
        nonlocal tables, roots, book_count
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "novels" in tables:
            try:
                book_count = con.execute("SELECT COUNT(*) FROM novels").fetchone()[0]
            except sqlite3.Error:
                book_count = None
            try:
                roots = [r[0] for r in con.execute("SELECT root_path FROM novels LIMIT 200")]
            except sqlite3.Error:
                roots = []

    def _open(target: Path) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{target}?mode=ro", uri=True, timeout=3)

    try:
        if _is_wal_mode(db_path):
            with tempfile.TemporaryDirectory(prefix="mprobe-") as tmp:
                staged = Path(tmp) / db_path.name
                copy_sidecars(db_path, staged)
                prepare_staged(staged)
                con = _open(staged)
                try:
                    _read(con)
                finally:
                    con.close()
        else:
            con = _open(db_path)
            try:
                _read(con)
            finally:
                con.close()
        return {"unreadable": False, "book_count": book_count, "tables": sorted(tables),
                "novels_roots": roots}
    except sqlite3.Error:
        return {"unreadable": True, "book_count": None, "tables": [], "novels_roots": []}


def _is_wal_mode(db_path: Path) -> bool:
    """读文件头第 18/19 字节判定 WAL 模式（2＝WAL；只读，不改文件）。"""
    try:
        with open(db_path, "rb") as f:
            head = f.read(20)
    except OSError:
        return False
    return len(head) == 20 and head[18] == 2 and head[19] == 2


def probe_library(db_path: Path) -> dict:
    """只读体检＋暂存复检：**绝不在源目录留下任何痕迹**。

    **WAL 模式库一律走暂存复检**：SQLite 的只读连接会就地创建 `-shm`（缺件时）或
    改写 `-shm` 字节（存在时，实测 sha 变化）——源目录/源三件套会变，违「源只读」。
    非 WAL（回滚日志模式）库直接只读体检（零拷贝、零痕迹）。代价：WAL 候选多一次
    同体积拷贝（本地几十 MB 级，可接受；体检与选中后的 precheck 同口径）。
    """
    if not db_path.exists():
        return {"exists": False, "unreadable": False, "schema_id": None, "book_count": None,
                "has_app_meta": False, "has_tables": False}
    # 先判 WAL：**任何**就地只读打开都会改写 `-shm`（实测 sha 变化）——WAL 库直接
    # 走暂存，绝不先做一次「无害体检」
    needs_staging = _is_wal_mode(db_path)
    if not needs_staging:
        info = inspect_library(db_path)
        if info["unreadable"]:
            needs_staging = True
        else:
            return info
    info = inspect_library(db_path) if not needs_staging else {"exists": True, "unreadable": True,
                                                               "schema_id": None, "book_count": None,
                                                               "has_app_meta": False,
                                                               "has_tables": False}
    try:
        with tempfile.TemporaryDirectory(prefix="probe-") as tmp:
            staged = Path(tmp) / db_path.name
            copy_sidecars(db_path, staged)
            if prepare_staged(staged):
                recovered = inspect_library(staged)
                if not recovered["unreadable"]:
                    recovered["probe_via_staging"] = True
                    return recovered
    except OSError as exc:
        logger.warning("db_lifecycle: staged probe failed for %s: %s", db_path.name, exc)
    return info


# ── 盘点缓存（c-carry-candidates-perf）：候选盘点在 Worker 线程执行，多槽 LRU ──

_SCAN_CACHE_CAP = 64
_probe_cache: OrderedDict[tuple, dict] = OrderedDict()
_probe_cache_lock = threading.Lock()
_migration_last_cache: OrderedDict[tuple, dict | None] = OrderedDict()
_migration_last_cache_lock = threading.Lock()


def _cache_get(cache: OrderedDict, lock: threading.Lock, key: tuple) -> object | None:
    with lock:
        hit = cache.get(key)
        if hit is not None:
            cache.move_to_end(key)
        return hit


def _cache_put(cache: OrderedDict, lock: threading.Lock, key: tuple, value: object) -> None:
    with lock:
        cache[key] = value
        while len(cache) > _SCAN_CACHE_CAP:
            cache.popitem(last=False)


def probe_library_cached(db_path: Path) -> dict:
    """probe_library 的多槽缓存皮（c-carry-candidates-perf）。

    键＝`data_identity_key`（主文件＋`-wal` 的 mtime_ns/size）——字节未变即复用。
    probe 对 WAL 库要整库拷贝暂存复检（源目录零痕迹纪律），真机 43 槽一次盘点
    就是数 GB 的拷贝＋哈希；缓存后重复盘点降到 stat 级。结果按键原样缓存
    （键未变＝探活结论不变，与 stamp_hash 同一假设）。"""
    key = data_identity_key(db_path)
    if key is None:
        return probe_library(db_path)
    hit = _cache_get(_probe_cache, _probe_cache_lock, key)
    if hit is not None:
        return dict(hit)
    info = probe_library(db_path)
    if info.get("exists", True):
        _cache_put(_probe_cache, _probe_cache_lock, key, dict(info))
    return info


def migration_last_cached(db_path: Path, wal_aware: bool = False) -> dict | None:
    """读槽自身 `app_meta['migration.last']`（链上溯源证据，c-carry-candidates-perf）。

    两种只读口（按槽角色分）：候选槽默认 **immutable**——只读主文件、不建 `-shm`、
    不读 `-wal`，绝不碰源目录（与 probe 的暂存纪律同向）；代价是 `-wal` 里未
    checkpoint 的记录读不到 → None＝证据缺失，回溯保守断链（少归档优于误归档）。
    活跃槽走 `wal_aware=True`（mode=ro 可见 WAL）——它是应用自己的库、`-shm` 本就
    在，而迁移完成记录是直连写入、引擎连接池长持不关，**可能长期躺在 WAL 里没
    checkpoint**（真机 0.49.2 实锤：immutable 读不到当日迁移记录）；链回溯第一跳
    MUST 走此口，否则整链断、归档白名单恒空。
    缓存键带模式维度（同一文件两种口读到的可见集不同，MUST NOT 互串）。"""
    key = data_identity_key(db_path)
    if key is None:
        return None
    cache_key = (*key, "w" if wal_aware else "i")
    hit = _cache_get(_migration_last_cache, _migration_last_cache_lock, cache_key)
    if hit is not None:
        return dict(hit) if isinstance(hit, dict) else None
    last: dict | None = None
    # 路径百分号编码（router._ro_uri 同判例）：数据目录含空格（Application Support）
    # 等字符时裸 f-string 拼 URI 会被截断/误读。
    from urllib.parse import quote

    enc = quote(str(db_path))
    uri = f"file:{enc}?mode=ro" if wal_aware else f"file:{enc}?mode=ro&immutable=1"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=3)
        try:
            row = con.execute(
                "SELECT value FROM app_meta WHERE key='migration.last'").fetchone()
            if row and row[0]:
                loaded = json.loads(row[0])
                last = loaded if isinstance(loaded, dict) else None
        finally:
            con.close()
    except (sqlite3.Error, json.JSONDecodeError, ValueError):
        last = None
    _cache_put(_migration_last_cache, _migration_last_cache_lock, cache_key, last)
    return dict(last) if isinstance(last, dict) else None


def trace_carry_chain(data_root: Path, active_db_path: Path | None) -> dict[str, bool]:
    """迁移链回溯（c-carry-candidates-perf）：活跃槽沿 `migration.last.source_filename`
    逐跳回溯，返回 `{源文件名: 链上完整}`——True＝从活跃槽到该源的**每一跳**都
    「完整达成」（单源判定，惰性导入防 engine→db_lifecycle 循环）；任一跳缺证/
    断链即止（更早的槽不再标 True，少归档优于误归档）。visited 防环，深度封顶。"""
    if active_db_path is None:
        return {}
    try:
        from migration.engine import is_complete_report
    except Exception:  # noqa: BLE001 — 判定函数不可得＝无法证明完整，全链保守不标
        return {}
    chain: dict[str, bool] = {}
    visited: set[str] = set()
    cur = Path(active_db_path)
    ok_so_far = True
    for _hop in range(64):  # 深度封顶：库文件名一代一槽，链长不可能到 64
        if cur.name in visited:
            break  # 环＝数据异常，保守停走
        visited.add(cur.name)
        # 第一跳＝活跃槽（应用自己的库）：走 WAL 可见口——迁移完成记录可能未
        # checkpoint（真机实锤）；后续跳＝候选槽（源只读纪律）：immutable 零痕迹。
        last = migration_last_cached(cur, wal_aware=(cur == Path(active_db_path)))
        if not last:
            break  # 缺证据（未迁移/老库/记录读不到）——链到此为止
        src_name = str(last.get("source_filename") or "")
        if not src_name:
            break
        # 数据件复写守卫：跳记录的 stamp 必须仍与源文件现行指纹对拍命中（三形态），
        # 不命中＝迁移后源又被写过（或记录失效）——该源断链，不再标 True。
        src = Path(data_root) / src_name
        if not src.exists():
            break
        stamp = str(last.get("source_stamp") or "")
        current = {candidate_stamp(src_name, src), candidate_stamp_hash(src_name, src),
                   candidate_stamp_legacy(src_name, src)}
        if not stamp or stamp not in current:
            ok_so_far = False
        if ok_so_far and not is_complete_report(last.get("report")
                                                if isinstance(last.get("report"), dict)
                                                else None):
            ok_so_far = False  # 本跳缺证/不完整：该源不标，更早的也断
        chain[src_name] = ok_so_far
        if not ok_so_far:
            break  # 断链：更早的槽一律不再标（少归档优于误归档）
        cur = src
    return chain


# ── 首启状态机 ────────────────────────────────────────────────────────────


def _best_effort_checkpoint(db_path: Path) -> None:
    """分流/隔离前尽力把 WAL 落盘（主文件自带全部已提交内容；失败不阻断）。"""
    try:
        con = sqlite3.connect(str(db_path), timeout=5)
        try:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            con.close()
    except sqlite3.Error as exc:  # 损坏库 checkpoint 失败是预期
        logger.warning("db_lifecycle: checkpoint before relocate failed: %s", exc)


def relocate(db_path: Path, marker: str) -> str | None:
    """分流/隔离改名：主文件一次 rename 为 `<db>.{marker}-<stamp>`，边车随后同前缀。

    内容先经 `_best_effort_checkpoint` 落进主文件（边车搬运失败也不丢已提交数据）；
    失败重试一次后返回 None（不抛异常）：文件被另一个实例/杀软占用时，应用必须
    照常起得来，由调用方给出可展示状态。形态与 `parse_db_filename` 的
    `.mismatch-*` / `.corrupt-*` 白名单一致（旧版留下的单文件隔离件同样可识别）。
    """
    stamp = datetime.now(UTC).replace(tzinfo=None).strftime("%Y%m%d-%H%M%S")
    target = Path(f"{db_path}.{marker}-{stamp}")
    _best_effort_checkpoint(db_path)
    for attempt in (1, 2):
        try:
            if db_path.exists():
                db_path.replace(target)
            for suffix in ("-wal", "-shm"):
                src = Path(f"{db_path}{suffix}")
                if src.exists():
                    src.replace(Path(f"{target}{suffix}"))
            return str(target)
        except OSError as exc:
            logger.warning(
                "db_lifecycle: relocate %s attempt %d failed: %s", db_path.name, attempt, exc
            )
            if attempt == 1:
                time.sleep(0.2)
    return None


def boot_lifecycle(db_path: Path, metadata, schema_fp: str) -> dict:
    """首启状态机入口（lifespan 最前、任何 engine 连接之前）。

    返回 `{"boot": fresh_boot|current|mismatch_renamed|quarantined_new|
    mismatch_rename_failed|quarantine_failed, ...}`。
    """
    del metadata  # 只读元数据由调用方算指纹；此处不再做形状比对（无就地补列）
    if not db_path.exists():
        return {"boot": "fresh_boot"}

    info = probe_library(db_path)
    if info["unreadable"]:
        renamed = relocate(db_path, CORRUPT_MARKER)
        if renamed:
            logger.warning("db_lifecycle: corrupt library quarantined to %s", renamed)
            return {"boot": "quarantined_new", "quarantined_to": renamed}
        logger.error(
            "db_lifecycle: quarantine incomplete for %s (main file moved=%s；未移动的边车原位保留)",
            db_path.name, not db_path.exists())
        return {"boot": "quarantine_failed"}

    if not info.get("has_tables") and not info.get("schema_id"):
        return {"boot": "fresh_boot", "empty_shell": True}

    if info.get("schema_id") == schema_fp:
        return {"boot": "current", "probe_via_staging": bool(info.get("probe_via_staging"))}

    renamed = relocate(db_path, MISMATCH_MARKER)
    if renamed:
        logger.warning(
            "db_lifecycle: schema mismatch renamed to %s (可作候选带回)", renamed
        )
        return {"boot": "mismatch_renamed", "renamed_to": renamed}
    logger.error(
        "db_lifecycle: mismatch rename incomplete for %s (main file moved=%s；未移动的边车原位保留)",
        db_path.name, not db_path.exists())
    return {"boot": "mismatch_rename_failed"}


# ── 版本戳（库自证来源） ──────────────────────────────────────────────────


def version_stamp_payload() -> dict[str, str]:
    """写进当前库 `app_meta` 的版本戳：本机版本＋组件快照（键名钉死在规格里）。"""
    from backup.format import FORMAT_VERSION

    return {
        APP_VERSION_KEY: app_version(),
        APP_COMPONENTS_KEY: json.dumps(
            {"db_filename": _active_filename(), "backup_format_version": FORMAT_VERSION},
            ensure_ascii=False,
        ),
    }


def _active_filename() -> str:
    from schema_version import active_db_filename

    return active_db_filename()


# ── 候选只读清单（c-lossless-upgrade：告知卡「作品＋模型配置」两块清单）──
# 只对 recommended 候选计算（免登端点每次全量重扫大候选既慢又放大返回面）；
# 逐本封顶，超出以 total 计数表达（前端显示「等 N 项」）。
# **密钥永不返回**：本函数不得查询 api_key 列（test_db_lifecycle 断言响应全文无 enc:）。

MANIFEST_BOOK_CAP = 50


def candidate_manifest(db_path: Path, book_cap: int = MANIFEST_BOOK_CAP) -> dict | None:
    """recommended 候选的只读内容清单。

    返回 `{"books": [{"name","words"}…], "books_total": N, "configs": [{"name"}…],
    "configs_total": N}`。库打不开或缺 novels 表返回 None（调用方降级为只报数量，
    不阻塞搬运）；缺 api_configs 表按 0 条处理（更老的库没有该表属正常形态）。
    **WAL 库一律暂存复检**（probe_library 同口径）：只读连接也会就地创建/改写
    `-shm`，违「源三件套字节与 mtime 均不变」——本函数曾在每次候选扫描就地主开
    只读连接，边车 mtime 被顶新 → 完成记录指纹永不对上 → 告知卡复弹
    （c-carry-modal-reshow 真机判例）。非 WAL（回滚日志模式）库直接只读体检。
    """
    def _open_ro(target: Path) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{target}?mode=ro", uri=True, timeout=5)

    try:
        if _is_wal_mode(db_path):
            with tempfile.TemporaryDirectory(prefix="manifest-") as tmp:
                staged = Path(tmp) / db_path.name
                copy_sidecars(db_path, staged)
                if not prepare_staged(staged):
                    return None
                con = _open_ro(staged)
                try:
                    return _manifest_rows(con, book_cap)
                finally:
                    con.close()
        con = _open_ro(db_path)
        try:
            return _manifest_rows(con, book_cap)
        finally:
            con.close()
    except sqlite3.Error:
        return None


def _manifest_rows(con: sqlite3.Connection, book_cap: int) -> dict | None:
    """清单查询体（candidate_manifest 共用）：书名＋字数与配置名两块。"""
    try:
        book_rows = con.execute(
            "SELECT n.name, COALESCE((SELECT SUM(c.word_count) FROM chapters c"
            " WHERE c.novel_id = n.id), 0) FROM novels n ORDER BY n.created_at, n.name"
        ).fetchall()
    except sqlite3.Error:
        # 老库 chapters 无 word_count 列：降级为书名清单（words=0），书名仍可列
        try:
            book_rows = con.execute(
                "SELECT n.name, 0 FROM novels n ORDER BY n.created_at, n.name"
            ).fetchall()
        except sqlite3.Error:
            return None  # 缺 novels 表——清单取不到，整体降级
    try:
        cfg_rows = con.execute(
            "SELECT name FROM api_configs ORDER BY created_at, name"
        ).fetchall()
    except sqlite3.Error:
        cfg_rows = []  # 老库无 api_configs 表：配置清单为空而非整体失败
    try:
        library_total = int(
            con.execute("SELECT COUNT(*) FROM character_library").fetchone()[0] or 0
        )
    except sqlite3.Error:
        library_total = 0  # 老库无角色库表：计数为 0（告知卡第三块不渲染）
    return {
        "books": [{"name": str(b), "words": int(w or 0)}
                  for b, w in book_rows[:book_cap]],
        "books_total": len(book_rows),
        "configs": [{"name": str(c)} for (c,) in cfg_rows],
        "configs_total": len(cfg_rows),
        "library_total": library_total,
    }


# ── 候选扫描 ──────────────────────────────────────────────────────────────

def scan_migration_candidates(data_root: Path, current_version: str | None = None,
                              active_db_path: Path | None = None,
                              chain_map: dict[str, bool] | None = None) -> list[dict]:
    """迁入候选：白名单形状枚举＋活跃库按路径排除＋数据件 max(mtime) 排序。

    c-carry-candidates-perf：探活走多槽缓存（`probe_library_cached`）；`chain_map`
    （`trace_carry_chain` 产物）在场时逐项标注 `chain_carried`（链上且完整带回，
    归档白名单的呈现源——判定单源在后端，前端只展示）。归档子目录（`archive/`）
    不参与盘点：`iterdir` 只取文件已天然排除，此处显式拒一点名防将来改成递归。"""
    root = Path(data_root)
    items: list[dict] = []
    if not root.is_dir():
        return items
    active = None
    if active_db_path is not None:
        try:
            active = Path(active_db_path).resolve()
        except OSError:
            active = None
    for f in sorted(root.iterdir()):
        if not f.is_file():
            continue
        if f.name == ARCHIVE_DIRNAME:
            continue  # 归档件退出盘点（防御式点名；子目录本就进不了 is_file）
        parsed = parse_db_filename(f.name)
        if not parsed.is_candidate:
            continue
        try:
            if active is not None and f.resolve() == active:
                continue  # 活跃库按路径排除（不靠版本比较）
        except OSError:
            continue
        mtime = data_file_mtime(f)
        size = data_file_size(f)
        info = probe_library_cached(f)
        book_count = info.get("book_count")
        if book_count in (None, 0) and not (info.get("unreadable") and size > 0):
            continue  # 空库/空壳不进候选
        items.append({
            "filename": f.name,
            "version": parsed.version,
            "kind": parsed.kind,
            "legacy_generation": parsed.generation,
            "size_bytes": size,
            "mtime": mtime,
            "book_count": book_count,
            "unreadable": bool(info.get("unreadable")),
            "recommended": False,
            # 链上完整带回态（c-carry-candidates-perf）：归档白名单的呈现源；判定
            # 单源在 trace_carry_chain（每跳完整性单源判定＋指纹对拍），前端只展示
            "chain_carried": bool(chain_map) and bool(chain_map.get(f.name)),
            # stamp＝现行指纹（数据件）；stamp_legacy＝旧三件套形态，供完成/抑制
            # 存量记录兼容对拍（c-carry-modal-reshow——升级前写入的记录可能是旧形）；
            # stamp_hash＝内容指纹（c-carry-completion-robust）：mtime 分量在不可靠
            # 文件系统（Docker Desktop virtiofs）上随触碰漂移，完成/抑制对拍需
            # 内容哈希形态兜底，否则「已迁移」状态失效、告知卡每次首页复弹。
            "stamp": candidate_stamp(f.name, f),
            "stamp_legacy": candidate_stamp_legacy(f.name, f),
            "stamp_hash": candidate_stamp_hash(f.name, f),
        })
    items.sort(
        key=lambda it: (candidate_rank(parse_db_filename(it["filename"])), it["mtime"],
                        it["filename"]),
        reverse=True,  # 同族同时间时按名字降序（确定性；遗留名内嵌时间戳，名字序＝时间序）
    )
    _mark_recommended(items, current_version)
    return items


def _mark_recommended(items: list[dict], current_version: str | None) -> None:
    """推荐位＝第一个「不新于当前版本」的可读候选（dev 构建不设版本门槛）。

    **新于当前版本的候选列出但不推荐**：用版本比较把它们排除会让这些库彻底不可
    达（`0.24` 与 `0.24.0` 相等、遗留全数字名与 tag `v1` 同形）。
    """
    dev = (not current_version) or (not is_release_version(current_version))
    for it in items:
        if it["unreadable"]:
            continue
        if not dev and it["version"] and is_newer(it["version"], current_version):
            continue
        it["recommended"] = True
        return


def list_quarantined(data_root: Path) -> list[dict]:
    """只读可见的隔离件（`.corrupt-*`，新旧两种形态：单目录或单文件）。"""
    root = Path(data_root)
    out = []
    if not root.is_dir():
        return out
    for f in sorted(root.iterdir()):
        parsed = parse_db_filename(f.name)
        if parsed.kind != "corrupt":
            continue
        try:
            if f.is_dir():
                size = sum(c.stat().st_size for c in f.iterdir() if c.is_file())
                mtime = int(f.stat().st_mtime)
            else:
                size = f.stat().st_size
                mtime = int(f.stat().st_mtime)
        except OSError:
            continue
        out.append({"filename": f.name, "size_bytes": size, "mtime": mtime})
    return out


def clean_stale_staging(data_root: Path) -> int:
    """清掉 `migration-staging/*` 残留（硬杀/断电遗留的整份副本；候选扫描不看它）。"""
    staging_root = Path(data_root) / STAGING_DIRNAME
    if not staging_root.is_dir():
        return 0
    removed = 0
    for child in staging_root.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            removed += 1
        except OSError as exc:
            logger.warning("db_lifecycle: stale staging cleanup failed for %s: %s", child.name, exc)
    return removed


# ── 清理（旧库留存：只允许删本次成功带回的件） ─────────────────────────────


def deletable_candidates(data_root: Path, migrated_stamps: str | set[str] | None,
                         keep: int = 2, active_db_path: Path | None = None) -> list[dict]:
    """待删清单：仅「已成功带回」的候选，且默认保留最近 `keep` 份。

    `migrated_stamps` 来自运行库 `app_meta['migration.history']` 的 source_stamp 集合
    （本次与历次成功带回的源；router 侧已把旧三件套形态换算成现行指纹）。**未成功
    带回过的件一律不可删**——它们是用户还没带过来的数据；「最近」按数据件
    `max(mtime)` 计（只看主文件会被 WAL 骗到；`-shm` 非数据不算，c-carry-modal-reshow）。
    """
    if not migrated_stamps:
        return []
    stamps = {migrated_stamps} if isinstance(migrated_stamps, str) else set(migrated_stamps)
    # 对拍含内容哈希形态（c-carry-completion-robust）：完成记录自 2026-10-24 起记
    # 内容指纹——mtime 指纹在不可靠 FS（virtiofs）上随触碰漂移，仅对 mtime 会让
    # 已带回的源永远进不了待删清单。
    items = [it for it in scan_migration_candidates(data_root, None, active_db_path)
             if it["stamp"] in stamps or it.get("stamp_hash") in stamps]
    items.sort(key=lambda it: it["mtime"], reverse=True)
    return items[keep:] if len(items) > keep else []


def validate_candidate_filename(data_root: Path, filename: str,
                                active_db_path: Path | None = None,
                                allow_sentinel: bool = False) -> Path | None:
    """路径安全校验：白名单形状＋`resolve()` 收敛在数据目录内＋非活跃库＋非哨兵。

    `allow_sentinel=True` 供**迁入链**（start/preview/dismiss）放行 dev 哨兵候选——
    哨兵本就在候选白名单（c-dev-sentinel-migration-candidate：扫得到就必须搬得动）；
    cleanup 仍恒拒（待删清单 MUST NOT 是哨兵名）。判例 c-sentinel-carry-gate
    （v0.30.1 真机实锤）：本函数曾把 cleanup 的非哨兵规则上扩到全家——哨兵候选
    扫得到、点「带过来」即 400「文件名不合法或不在数据目录内」。
    返回可安全操作的文件路径；不合法返回 None（供 dismiss/cleanup 复用）。
    """
    if not filename or "/" in filename or "\\" in filename:
        return None
    parsed = parse_db_filename(filename)
    if not parsed.is_candidate:
        return None
    if parsed.kind == "sentinel" and not allow_sentinel:
        return None
    root = Path(data_root)
    candidate = root / filename
    try:
        resolved = candidate.resolve()
        if resolved.parent != root.resolve():
            return None
        if active_db_path is not None and resolved == Path(active_db_path).resolve():
            return None
    except OSError:
        return None
    return candidate


def delete_candidate(data_root: Path, filename: str,
                     active_db_path: Path | None = None) -> bool:
    """删除单个候选三件套（路径校验在此收口；不存在视为已删成功）。"""
    target = validate_candidate_filename(data_root, filename, active_db_path)
    if target is None:
        return False
    for p in (target, *sidecar_paths(target)):
        try:
            p.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("db_lifecycle: cleanup failed for %s: %s", p.name, exc)
            return False
    return True


# 归档子目录（c-carry-candidates-perf）：数据目录下的固定名，链上旧槽移入此处
# 退出盘点。移动不删除——回滚/找回承诺不破（旧版 App 扫描同样跳过子目录）。
ARCHIVE_DIRNAME = "archive"


def archive_candidate(data_root: Path, filename: str,
                      active_db_path: Path | None = None) -> bool:
    """把单个候选三件套移入归档子目录（移动可逆，绝不删除）。

    路径校验与删除同源收口（`validate_candidate_filename`：白名单形状＋resolve
    收敛在数据目录根＋非活跃库）——归档目录里的件本身因带路径分隔天然过不了
    校验，MUST NOT 二次归档。三件（主文件＋`-wal`/`-shm`）整体搬运，字节不动。
    """
    target = validate_candidate_filename(data_root, filename, active_db_path)
    if target is None:
        return False
    dest_dir = Path(data_root) / ARCHIVE_DIRNAME
    try:
        dest_dir.mkdir(exist_ok=True)
        for p in (target, *sidecar_paths(target)):
            if not p.exists():
                continue
            p.replace(dest_dir / p.name)
        return True
    except OSError as exc:
        logger.warning("db_lifecycle: archive failed for %s: %s", filename, exc)
        return False
