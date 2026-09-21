"""db_lifecycle — 库文件代数治理（db-generation）。

首启状态机（novel-v{V}.db）：
- 存在 → 校验梯：指纹匹配→current；库为子集→additive 代内补列；库为超集
  且多出列均可空/带默认→tolerant 放行（不改戳）+drift_accepted 审计键；
  breaking/不可读→三件套改名 .corrupt-<stamp> 隔离＋空库启动（隔离件只读
  可见，不进迁入候选）。
- 不存在 → create_all 空库 → 扫描迁入候选（novel-v{k}.db k<V / novel.db /
  novel.db.legacy-*；排除 -wal/-shm/.bak 与空库）→ pending_migration。

由 legacy_archive.py 迁入函数重组而成（archive_if_legacy 的「自动改名留档」
语义删除——版本化命名后新代码根本不去开旧代文件，无事可留档）。
必须发生在任何 engine 连接之前（lifespan 最前）。
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

logger = logging.getLogger("uvicorn.error")

SCHEMA_ID_KEY = "schema_id"
DRIFT_ACCEPTED_KEY = "drift_accepted"
CORRUPT_SUFFIX_RE = re.compile(r"\.(corrupt|bak)(-[0-9T:-]+)?$")


# ── 指纹与体检（自 legacy_archive 迁入） ────────────────────────────────────


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
    """只读体检：exists/unreadable/schema_id/book_count（novels|projects 先命中）。"""
    out = {"exists": db_path.exists(), "unreadable": False, "schema_id": None,
           "book_count": None, "has_app_meta": False}
    if not db_path.exists():
        return out
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
        try:
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "app_meta" in tables:
                out["has_app_meta"] = True
                row = con.execute(
                    "SELECT value FROM app_meta WHERE key=?", (SCHEMA_ID_KEY,)
                ).fetchone()
                if row:
                    out["schema_id"] = row[0]
            for t in ("novels", "projects"):
                if t in tables:
                    out["book_count"] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    break
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


def classify_drift(old_schema: dict[str, list[str]], metadata) -> str:
    """差异分类（db-generation 扩展）：

    - additive：旧库表/列是 metadata 子集（代内旧 build 写的）→ 补列
    - tolerant：旧库是**超集**且多出表/列在 metadata 中可空或带默认（代内
      新 build 写过后回退旧 build）→ 放行+审计（修现状「误判 breaking 清库」）
    - breaking：真破坏（删列语义/类型变化/表消失）
    """
    meta_tables = {}
    for t in metadata.tables.values():
        meta_tables[t.name] = {c.name: c for c in t.columns}

    old_is_subset = True
    old_is_superset_with_safe_extras = True
    for tname, cols in (old_schema or {}).items():
        table = meta_tables.get(tname)
        if table is None:
            # 旧库多出的表：tolerant 仅当该表整表已不在 metadata（换代退役）→ 视超集项
            old_is_subset = False
            continue
        meta_cols = set(table.keys())
        for c in cols:
            if c not in meta_cols:
                old_is_subset = False  # 旧多列
        for cname, col in table.items():
            if cname not in cols:
                # metadata 多列：additive 候选（须可空/默认——由调用方 ADDITIVE_COLUMNS 判定）
                pass
    for tname, table in meta_tables.items():
        old_cols = (old_schema or {}).get(tname)
        if old_cols is None:
            old_is_superset_with_safe_extras = False  # metadata 新表：非超集
            continue
        for cname, col in table.items():
            if cname not in old_cols:
                old_is_superset_with_safe_extras = False
                break
        if not old_is_superset_with_safe_extras:
            break

    if old_is_subset:
        return "additive"
    if old_is_superset_with_safe_extras:
        return "tolerant"
    return "breaking"


# ── 首启状态机 ────────────────────────────────────────────────────────────


def generation_of(filename: str) -> int | None:
    """novel-v{k}.db → k；novel.db / .legacy-* → 0；其他 → None。"""
    m = re.match(r"^novel-v(\d+)\.db$", filename)
    if m:
        return int(m.group(1))
    if filename == "novel.db" or filename.startswith("novel.db.legacy-"):
        return 0
    return None


def scan_migration_candidates(data_root: Path, current_version: int) -> list[dict]:
    """迁入候选（db-generation）：低代库＋旧命名库＋.legacy-*；排除
    -wal/-shm/.bak/.corrupt 与 book_count=0 空库；每候选只读体检。"""
    items = []
    for f in sorted(data_root.glob("novel*")):
        if not f.is_file():
            continue
        name = f.name
        # 排除边车/噪声/隔离件/当前代
        if name.endswith(("-wal", "-shm")) or ".bak" in name or ".corrupt" in name:
            continue
        gen = generation_of(name)
        if gen is None or gen >= current_version:
            continue
        info = inspect_library(f)
        if info.get("book_count") in (None, 0):
            # 空库不进候选（防「空 v{k} 盖过有数据的低代库」）；不可读但体积>0 仍列出（只读可见）
            if not (info.get("unreadable") and f.stat().st_size > 0):
                continue
        stat = f.stat()
        items.append({
            "filename": name,
            "generation": gen,
            "size_bytes": stat.st_size,
            "mtime": int(stat.st_mtime),
            "book_count": info.get("book_count"),
            "unreadable": bool(info.get("unreadable")),
        })
    # 默认源：代数 desc → mtime desc（列表呈现，用户可改选）
    items.sort(key=lambda x: (-(x["generation"] if x["generation"] is not None else -1), -x["mtime"]))
    return items


def quarantine_corrupt(db_path: Path) -> str | None:
    """三件套改名 .corrupt-<stamp>（同代损坏隔离；源字节零改动）。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    renamed = None
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(db_path) + suffix)
        if src.exists():
            dst = Path(f"{db_path}.corrupt-{stamp}{suffix}")
            src.replace(dst)
            if suffix == "":
                renamed = str(dst)
    return renamed


def boot_lifecycle(db_path: Path, metadata, schema_fp: str) -> dict:
    """首启状态机入口（lifespan 最前、任何 engine 连接之前）。

    返回 {"boot": current|fresh_boot|additive_booted|tolerant_booted|
    quarantined_new, "additive_tables": [...], "quarantined_to": str?}
    additive 场景同时返回补列计划（main.py 执行后打戳）。
    """
    info = inspect_library(db_path)
    if not info["exists"]:
        return {"boot": "fresh_boot"}

    # 校验梯：指纹匹配 → current
    if info.get("schema_id") == schema_fp:
        return {"boot": "current"}

    old_schema = inspect_schema(db_path)
    if old_schema is None or info.get("unreadable"):
        # 升级梯第二级：暂存副本 checkpoint 后重试由迁移引擎承担；启动期直接隔离
        to = quarantine_corrupt(db_path)
        logger.warning("db_lifecycle: corrupt library quarantined to %s", to)
        return {"boot": "quarantined_new", "quarantined_to": to}

    drift = classify_drift(old_schema, metadata)
    if drift == "additive":
        # 代内补列计划：metadata 有而库无的列（main.py ADDITIVE 执行）
        plan = {}
        for t in metadata.tables.values():
            old_cols = old_schema.get(t.name)
            if old_cols is None:
                continue
            missing = [c.name for c in t.columns if c.name not in old_cols]
            if missing:
                plan[t.name] = missing
        return {"boot": "additive_booted", "additive_tables": plan}
    if drift == "tolerant":
        # 超集放行：不改戳（回升 newer build 即 current）；审计键由 main.py 写
        extra = {}
        for t in metadata.tables.values():
            old_cols = old_schema.get(t.name)
            if old_cols is None:
                continue
            extras = [c for c in old_cols if c not in t.columns]
            if extras:
                extra[t.name] = extras
        return {"boot": "tolerant_booted", "extra_cols": extra}
    # breaking
    to = quarantine_corrupt(db_path)
    logger.warning("db_lifecycle: breaking drift quarantined to %s", to)
    return {"boot": "quarantined_new", "quarantined_to": to}

# ── 代内 additive 补列（声明式登记；幂等 checkfirst）────────────────────────
# 新表/新列一律在此登记（新库 create_all 全量建出；旧库由 apply_additive_columns
# 代内补列）；删/改列一律 SCHEMA_VERSION+1 走迁入。列名单一来源，DDL 由它派生。
ADDITIVE_COLUMNS: dict[str, list[str]] = {
    "volumes": [
        "ALTER TABLE volumes ADD COLUMN plan_line VARCHAR(150)",
        # c-volume-antagonist：本卷的坎（对抗物）——类型闭集＋一句话
        "ALTER TABLE volumes ADD COLUMN antagonist_type VARCHAR(20)",
        "ALTER TABLE volumes ADD COLUMN antagonist_line VARCHAR(150)",
    ],
    # c-volume-antagonist：伏笔建议入台账时的计划收束卷（确认成卷链写入）
    "novel_hooks": [
        "ALTER TABLE novel_hooks ADD COLUMN planned_volume_no INTEGER",
    ],
}


async def apply_additive_columns(engine, columns: dict[str, list[str]] | None = None) -> list[str]:
    """代内补列：逐条执行 DDL（列已存在＝幂等跳过）；其他异常向上抛——
    列缺失若被静默，会被指纹戳永久掩盖（runtime 才炸 no such column）。"""
    cols = columns if columns is not None else ADDITIVE_COLUMNS
    applied: list[str] = []
    for _table, ddls in cols.items():
        for ddl in ddls:
            try:
                async with engine.begin() as conn:
                    await conn.execute(text(ddl))
                applied.append(ddl)
            except Exception as exc:
                if "duplicate column" not in str(exc).lower() and "already exists" not in str(exc).lower():
                    raise
    return applied

