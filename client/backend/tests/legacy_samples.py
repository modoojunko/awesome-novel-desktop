"""历史世代样本登记表（c-legacy-drill-gate）——每个曾发布的库形态一份合成样本。

**只增不减**：样本键是身份键，删除既有样本会被
tests/test_legacy_replay_gate.py 的只增不减断言拦下；迁移事故判例 MUST 以样本
形式入册（origin 写明出处）。样本 MUST 是可审阅的合成构造（代码建库），MUST NOT
塞真实用户数据入库。

每个样本 = 一个「曾经真实存在于用户盘上」的形态。门禁逐样本跑 run_migration 进
当前 schema——任何 schema 变更打破其中一种形态的可迁性，CI 即红。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LegacySample:
    """一个历史世代库形态。build 在 root 下建源库（可含边车），返回主文件路径。"""

    key: str
    filename: str
    origin: str
    build: Callable[[Path], Path]


def _base_tables(conn: sqlite3.Connection, *, with_plan_line: bool) -> None:
    """第 0 代核心业务表；with_plan_line=False 即「源缺 plan_line 列」的历史缺列形态。"""
    vol_cols = ("id TEXT PRIMARY KEY, novel_id TEXT, volume_no INTEGER, title TEXT, "
                "summary TEXT, chapter_count INTEGER, created_at TIMESTAMP, updated_at TIMESTAMP"
                + (", plan_line VARCHAR(150)" if with_plan_line else ""))
    conn.execute("CREATE TABLE novels (id TEXT PRIMARY KEY, user_id TEXT, name TEXT, "
                 "slug TEXT, root_path TEXT, current_phase TEXT, status TEXT, "
                 "total_volumes INTEGER, total_chapters INTEGER, created_at TIMESTAMP, "
                 "updated_at TIMESTAMP)")
    conn.execute(f"CREATE TABLE volumes ({vol_cols})")
    conn.execute("CREATE TABLE chapters (id TEXT PRIMARY KEY, novel_id TEXT, volume_id TEXT, "
                 "chapter_no INTEGER, ref TEXT, title TEXT, status TEXT)")
    conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO app_meta (key, value) VALUES ('schema_id', 'legacy-sample')")


def _seed_book(conn: sqlite3.Connection, idx: int, name: str, with_plan_line: bool = False) -> None:
    """一本多卷多章的书（真实形态：中文书名、显式列名直插）。"""
    nid, vid = f"s{idx}", f"s{idx}v1"
    conn.execute(
        "INSERT INTO novels (id, user_id, name, slug, root_path, current_phase, status,"
        " total_volumes, total_chapters, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (nid, "u1", name, f"slug-{nid}", f"./data/{nid}", "write", "active", 1, 2,
         "2026-01-01 00:00:00", "2026-01-02 00:00:00"))
    vcols = ("id, novel_id, volume_no, title, summary, chapter_count, created_at, updated_at"
             + (", plan_line" if with_plan_line else ""))
    conn.execute(f"INSERT INTO volumes ({vcols}) VALUES ({','.join('?' * (9 if with_plan_line else 8))})",
                 (vid, nid, 1, "第一卷", "概要", 2, "2026-01-01 00:00:00", "2026-01-02 00:00:00")
                 + (("本卷对抗物",) if with_plan_line else ()))
    for c in (1, 2):
        conn.execute(
            "INSERT INTO chapters (id, novel_id, volume_id, chapter_no, ref, title, status)"
            " VALUES (?,?,?,?,?,?,?)",
            (f"s{idx}c{c}", nid, vid, c, f"第 {c} 章", f"第{c}章 试炼", "draft"))


def _build_gen0(root: Path) -> Path:
    """第 0 代 novel.db（已发布客户端写出的最老形态）。"""
    p = root / "novel.db"
    conn = sqlite3.connect(p)
    _base_tables(conn, with_plan_line=False)
    _seed_book(conn, 1, "我重生在魔兽世界种田发家")
    conn.commit()
    conn.close()
    return p


def _build_legacy_numbered(root: Path) -> Path:
    """遗留代数名 novel-v3.db（v0.2x 之前的代数库命名，parse.kind=legacy）。"""
    p = root / "novel-v3.db"
    conn = sqlite3.connect(p)
    _base_tables(conn, with_plan_line=False)
    _seed_book(conn, 2, "旧代数名库的书")
    conn.commit()
    conn.close()
    return p


def _build_semver_missing_column(root: Path) -> Path:
    """novel-v0.24.db：上一代 semver 库，缺本代新增列（plan_line）——缺列回填面。"""
    p = root / "novel-v0.24.db"
    conn = sqlite3.connect(p)
    _base_tables(conn, with_plan_line=False)
    _seed_book(conn, 3, "缺列形态库的书")
    conn.commit()
    conn.close()
    return p


def _build_semver_wal_sidecars(root: Path) -> Path:
    """novel-v0.30.2.db 带 -wal/-shm 边车（旧版应用被强杀遗留的形态）。

    实勘：空闲连接不持边车——w1 关闭即 checkpoint 删边车，要等 w2 首次读才就地
    重建。所以建完立刻用第二连接读一次，把边车留在盘上。"""
    p = root / "novel-v0.30.2.db"
    conn = sqlite3.connect(p)
    conn.execute("PRAGMA journal_mode=WAL")
    _base_tables(conn, with_plan_line=True)
    _seed_book(conn, 4, "带边车库的书", with_plan_line=True)
    conn.commit()
    w2 = sqlite3.connect(p)
    conn.close()
    w2.execute("SELECT COUNT(*) FROM novels").fetchone()
    w2.close()
    return p


LEGACY_SAMPLES: list[LegacySample] = [
    LegacySample(
        key="gen0-novel-db",
        filename="novel.db",
        origin="第 0 代：最早发布客户端写出的库（无版本号命名）",
        build=_build_gen0,
    ),
    LegacySample(
        key="legacy-numbered-gen",
        filename="novel-v3.db",
        origin="遗留代数名：semver 命名之前的代数库（v0.2x 期）",
        build=_build_legacy_numbered,
    ),
    LegacySample(
        key="semver-missing-column",
        filename="novel-v0.24.db",
        origin="缺列形态：源库落后于当前 schema（中性字面量回填面；total_archives 同族）",
        build=_build_semver_missing_column,
    ),
    LegacySample(
        key="semver-wal-sidecars",
        filename="novel-v0.30.2.db",
        origin="强杀形态：-wal/-shm 边车遗留（c-carry-modal-reshow 同族现场）",
        build=_build_semver_wal_sidecars,
    ),
]

# 只增不减的基线键集（2026-10-10 首批四份）。删样本/改键 = 红灯执法；
# 新事故判例往 LEGACY_SAMPLES 追加后，把新键补进这里并写明判例出处。
BASELINE_SAMPLE_KEYS: frozenset[str] = frozenset({
    "gen0-novel-db",
    "legacy-numbered-gen",
    "semver-missing-column",
    "semver-wal-sidecars",
})
