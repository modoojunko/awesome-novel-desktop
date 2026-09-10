"""legacy_archive — 旧库留档机制（c-novel-export-roundtrip PR0）。

schema 每版自由、新库生来正名（单轨升级）：启动期对存量库做指纹检查，
不匹配即「三件套改名留档」（db/-wal/-shm 零接触），create_all 出全新库。
兼容责任在资产包 format_version（backup-restore），库层零迁移零召回。

本模块必须发生在任何 engine 连接之前（engine 惰性连接，lifespan 最前安全）。
留档只增不删；唯一消费面是 /api/backup/legacy-db/status（只读检测）。
"""

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA_ID_KEY = "schema_id"


def compute_schema_fingerprint(metadata) -> str:
    """由 SQLAlchemy metadata 计算 schema 指纹（表+列名+类型，排序稳定）。"""
    lines = []
    for table in sorted(metadata.tables.values(), key=lambda t: t.name):
        cols = "|".join(
            f"{c.name}:{c.type!s}"
            for c in sorted(table.columns, key=lambda c: c.name)
        )
        lines.append(f"{table.name}::{cols}")
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return digest[:16]


def inspect_library(db_path: Path) -> dict:
    """裸 sqlite 只读体检（绝不经 ORM——schema 每版自由，跨代健壮读法）。"""
    info = {
        "exists": db_path.exists(),
        "has_app_meta": False,
        "schema_id": None,
        "book_count": None,
        "unreadable": False,
    }
    if not info["exists"]:
        return info
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            info["has_app_meta"] = "app_meta" in tables
            if info["has_app_meta"]:
                row = conn.execute(
                    "SELECT value FROM app_meta WHERE key = :key",
                    {"key": SCHEMA_ID_KEY},
                ).fetchone()
                info["schema_id"] = row[0] if row else None
            # 兼容旧库(projects)与新库(novels)：D20 改名后旧库走留档重建
            for _tname in ("novels", "projects"):
                if _tname in tables:
                    info["book_count"] = conn.execute(
                        f"SELECT COUNT(*) FROM {_tname}"
                    ).fetchone()[0]
                    break
        finally:
            conn.close()
    except sqlite3.Error:
        info["unreadable"] = True
    return info


def archive_if_legacy(db_path: Path, target_fingerprint: str) -> dict:
    """启动期（任何 engine 连接前）调用：指纹不匹配 → 三件套改名留档。

    返回 {archived, reason, archived_path}；archived_path 为主库留档新名。
    """
    db_path = Path(db_path)
    info = inspect_library(db_path)
    if not info["exists"]:
        return {"archived": False, "reason": "fresh"}
    if (
        not info["unreadable"]
        and info["has_app_meta"]
        and info["schema_id"] == target_fingerprint
    ):
        return {"archived": False, "reason": "current"}

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archived_path = None
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(db_path) + suffix)
        if not src.exists():
            continue
        dst = Path(f"{db_path}.legacy-{stamp}{suffix}")
        src.replace(dst)
        if suffix == "":
            archived_path = str(dst)
    return {
        "archived": True,
        "reason": "fingerprint_mismatch" if not info["unreadable"] else "unreadable",
        "archived_path": archived_path,
    }
