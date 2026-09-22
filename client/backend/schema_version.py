"""库文件命名与版本比较单源（c-db-per-version）。

库文件名 = `novel-v{C端版本}.db`：**版本号本身即库文件身份**（每版首启新建
自己的库，旧库只读留存、靠副本搬运带回）。dev/PR 构建无版本语义 → 固定哨兵名。

零依赖叶子模块：`config.py`（拼 DATABASE_URL）与 `update_check.py`（版本比较）
都反向引用本模块，避免出现第二份版本口径。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import NamedTuple

DEV_VERSION = "dev"
SENTINEL_FILENAME = "novel-dev.db"
GEN0_FILENAME = "novel.db"
GEN0_LEGACY_RE = re.compile(r"^novel\.db\.legacy-[0-9A-Za-z:_-]+$")
# 版本串：数值段（至少一段）＋可选后缀段（-rc1 / .beta 等）
_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)*(?:[-._][A-Za-z0-9._-]+)?$")
_PURE_DIGITS_RE = re.compile(r"^[0-9]+$")
_NOVEL_V_RE = re.compile(r"^novel-v([A-Za-z0-9._-]+)\.db$")
# 分流件：novel-v{X}.db.mismatch-<stamp> / novel-v{X}.db.corrupt-<stamp>（三件套同前缀）
_DISPOSED_RE = re.compile(r"^novel-v([A-Za-z0-9._-]+)\.db\.(mismatch|corrupt)-[0-9TZ:._-]+$")
_NUM_HEAD_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)*)(?:[-._](.+))?$")
_SEG_SPLIT_RE = re.compile(r"[-._]")

# 排序序位（大者靠前）：semver > 遗留代数名 > 第 0 代 > dev 哨兵
_RANK_SEMVER = 4
_RANK_LEGACY = 3
_RANK_GEN0 = 2
_RANK_SENTINEL = 1

_PAD_SEGMENTS = 8


class DBName(NamedTuple):
    """库文件名判别结果。

    kind 取值：
      - semver   语义化版本名（`novel-v0.24.db`）
      - legacy   遗留代数名（纯数字 `novel-v1.db`——本 change 之前的落地形态）
      - gen0     第 0 代（`novel.db` / `novel.db.legacy-*`）
      - sentinel dev 哨兵（`novel-dev.db`）
      - mismatch 形状不符分流件（可作候选带回）
      - corrupt  不可读隔离件（只读可见，不作候选）
      - sidecar  -wal/-shm 边车、`.bak` 等非库文件
      - None     非白名单形状（磁盘残件）
    version / generation 二者之一给出。
    """

    kind: str | None
    version: str | None = None
    generation: int | None = None

    @property
    def is_candidate(self) -> bool:
        return self.kind in ("semver", "legacy", "gen0", "sentinel", "mismatch")


def app_version() -> str:
    """本机版本：env CLIENT_VERSION（冻结包由 release.json 注入）> dev。"""
    return (os.environ.get("CLIENT_VERSION") or "").strip() or DEV_VERSION


def is_release_version(version: str) -> bool:
    return bool(version) and version != DEV_VERSION


def is_valid_version(version: str | None) -> bool:
    """是否形如版本串（数值段＋可选后缀）。**比较排序不依赖它**——
    `version_sort_key` 对非法串给确定序且永不抛；本函数只用于载荷/URL 校验边界。"""
    return bool(version) and bool(_VERSION_RE.match(str(version).strip()))


def db_filename_for(version: str) -> str:
    """版本 → 库文件名（dev/非法串 → 固定哨兵名，不随构建乱窜）。"""
    if not is_release_version(version) or not _VERSION_RE.match(version):
        return SENTINEL_FILENAME
    return f"novel-v{version}.db"


def active_db_filename() -> str:
    return db_filename_for(app_version())


def parse_db_filename(name: str) -> DBName:
    """库文件名 → 判别结果（白名单**形状枚举**，不得用 `novel*` 前缀通配）。

    非白名单形状（`novels.db`、`novel.db.e2e-*`、`novel.db.recovered-*` 等磁盘
    残件）一律 kind=None，不进候选。
    """
    if name.endswith(("-wal", "-shm")) or ".bak" in name:
        return DBName("sidecar")
    if name == SENTINEL_FILENAME:
        return DBName("sentinel")
    if name == GEN0_FILENAME or GEN0_LEGACY_RE.match(name):
        return DBName("gen0")
    m = _DISPOSED_RE.match(name)
    if m:
        inner, marker = m.group(1), m.group(2)
        if marker == "corrupt":
            return DBName("corrupt")
        return _versioned(inner, kind_if_version="mismatch")
    m = _NOVEL_V_RE.match(name)
    if m:
        return _versioned(m.group(1), kind_if_version="semver")
    return DBName(None)


def _versioned(inner: str, kind_if_version: str) -> DBName:
    if not _VERSION_RE.match(inner):
        return DBName(None)
    if _PURE_DIGITS_RE.match(inner):
        return DBName("legacy", generation=int(inner))
    return DBName(kind_if_version, version=inner)


def version_sort_key(version: str | None) -> tuple:
    """版本比较键：**全域全序、永不抛异常**（非法串降最低）。

    数值段逐段比较并右侧补零（`0.9 < 0.10`、`0.24 == 0.24.0`）；同数值前缀时
    「有后缀 < 无后缀」（`0.24-rc1 < 0.24`，预发布早于正式版）；后缀按 `-._`
    分段、数字段 < 字母段。
    """
    if not version:
        return ((-1,), 0, ())
    m = _NUM_HEAD_RE.match(version)
    if not m:
        return ((-1,), 0, ())
    nums = tuple(int(x) for x in m.group(1).split("."))
    padded = nums + (0,) * max(0, _PAD_SEGMENTS - len(nums))
    suffix = m.group(2)
    if not suffix:
        return (padded, 1, ())  # 无后缀＝正式版，序位高于同前缀的预发布
    segs = tuple(
        (0, int(s), "") if s.isdigit() else (1, 0, s)
        for s in _SEG_SPLIT_RE.split(suffix)
        if s
    )
    return (padded, 0, segs)


def is_newer(candidate: str | None, current: str | None) -> bool:
    """candidate 严格新于 current（数值段补零比较；非法串永不抛）。"""
    return version_sort_key(candidate) > version_sort_key(current)


def candidate_rank(parsed: DBName) -> tuple:
    """候选排序序位（大者靠前）：semver → legacy → gen0 → sentinel。"""
    if parsed.kind in ("semver", "mismatch"):
        return (_RANK_SEMVER, version_sort_key(parsed.version))
    if parsed.kind == "legacy":
        return (_RANK_LEGACY, (parsed.generation or 0,))
    if parsed.kind == "gen0":
        return (_RANK_GEN0, ())
    return (_RANK_SENTINEL, ())


def sidecar_paths(db_path: Path) -> list[Path]:
    return [Path(f"{db_path}{suf}") for suf in ("-wal", "-shm")]


def three_file_mtime(db_path: Path) -> int:
    """三件套 `max(mtime)`：只看主文件会漏掉 WAL 里刚写的提交（mtime 滞后）。"""
    stamps = [db_path.stat().st_mtime]
    for side in sidecar_paths(db_path):
        if side.exists():
            stamps.append(side.stat().st_mtime)
    return int(max(stamps))


def three_file_size(db_path: Path) -> int:
    total = db_path.stat().st_size
    for side in sidecar_paths(db_path):
        if side.exists():
            total += side.stat().st_size
    return total


def candidate_stamp(filename: str, db_path: Path) -> str:
    """候选身份指纹（dismiss 记忆键与完成记录同源）：名字＋三件套 max(mtime)＋体积。"""
    return f"{filename}:{three_file_mtime(db_path)}:{three_file_size(db_path)}"
