"""迁移兼容重放门禁（c-legacy-drill-gate）——CI 每次全量重放历史世代样本登记表。

任何 schema 变更打破任一历史形态的可迁性（整表跳过/行损失/源书缺口/不可检出），
本文件即红：把「迁移部分成功」类事故从用户现场拦在合入前。样本只增不减另针执法。
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from sqlalchemy import create_engine

import models  # noqa: F401 —— 注册全表
from db import Base
from db_lifecycle import probe_library, scan_migration_candidates
from migration.engine import is_complete_report, run_migration
from schema_version import db_filename_for
from tests.legacy_samples import BASELINE_SAMPLE_KEYS, LEGACY_SAMPLES


def _sig(path: Path) -> dict:
    """源只读证据：三件套 (sha256, mtime_ns)——重放不得污染样本。"""
    out = {}
    for p in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if p.exists():
            st = p.stat()
            out[p.name] = (sha256(p.read_bytes()).hexdigest()[:16], st.st_mtime_ns)
    return out


def _make_target(root: Path) -> Path:
    target = root / db_filename_for("0.25")
    se = create_engine(f"sqlite:///{target}")
    Base.metadata.create_all(se)
    se.dispose()
    return target


def test_gate_registry_only_grows():
    """登记表只增不减：删样本/改键＝红；新判例入册后把键补进 BASELINE 并写明出处。"""
    keys = {s.key for s in LEGACY_SAMPLES}
    missing = BASELINE_SAMPLE_KEYS - keys
    assert not missing, f"登记表样本被删除/改名：{sorted(missing)}（只增不减，判例不可出册）"
    assert len(keys) == len({s.filename for s in LEGACY_SAMPLES}), "样本文件名不得重复"


def test_gate_replays_all_registered_samples(tmp_path):
    """重放门禁：每份样本可检出、可迁、迁即完整达成、源零接触。"""
    for sample in LEGACY_SAMPLES:
        root = tmp_path / sample.key
        root.mkdir()
        src = sample.build(root)
        assert src.exists(), f"[{sample.key}] 样本构造未产出 {sample.filename}"
        before = _sig(src)

        # 检出面：候选扫描认得该形态；期望书数经 probe_library（暂存安全，
        # 直开 ro 连接会在 WAL 库上就地创建 -shm——零接触断言会当场抓获）
        expected = probe_library(src)
        assert not expected["unreadable"], f"[{sample.key}] 体检判不可读"
        found = [c for c in scan_migration_candidates(root, "0.25")
                 if c["filename"] == sample.filename]
        assert found, f"[{sample.key}] 候选扫描检不出该历史形态"
        assert found[0]["book_count"] == expected["book_count"]

        # 迁移面：完整达成——零跳表、逐表零行损、源书全在场
        rep = run_migration(root, sample.filename, _make_target(root))
        ctx = f"[{sample.key}] report={rep}"
        assert rep["status"] == "ok", ctx
        assert is_complete_report(rep) and rep["complete"] is True, f"不完整：{ctx}"
        assert rep["tables_skipped"] == [], ctx
        assert all(e.get("rows_missing") == 0 for e in rep["tables"]), ctx
        assert rep["book_count_present"] == rep["book_count_source"], ctx

        # 源只读面：重放不得改样本任一字节（含边车）
        assert _sig(src) == before, f"[{sample.key}] 重放污染了源三件套"


def test_gate_v039_image_seed_columns_survive_carry(tmp_path):
    """v0.39 图像种子列退役（c-cover-scene-extract）：设置行零损失、值随列弃。

    源多列（cover_seed/seed）不拦路——交集搬行后 cover_prompt/avatar_prompt 原样
    保留，新 schema 里种子列不复存在（seed 一律按书/角色 id 派生）。
    """
    import sqlite3

    from sqlalchemy import text

    sample = next(s for s in LEGACY_SAMPLES if s.key == "v039-image-seed-columns")
    root = tmp_path / sample.key
    root.mkdir()
    src = sample.build(root)
    target = _make_target(root)
    rep = run_migration(root, sample.filename, target)
    assert rep["status"] == "ok", rep
    assert is_complete_report(rep) and rep["complete"] is True

    se = create_engine(f"sqlite:///{target}")
    with se.connect() as conn:
        book = conn.execute(text(
            "SELECT style_key, cover_prompt, image_model FROM book_image_settings"
        )).one()
        avatar = conn.execute(text(
            "SELECT avatar_prompt FROM character_image_settings"
        )).one()
        book_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(book_image_settings)"))}
        char_cols = {
            r[1] for r in conn.execute(text("PRAGMA table_info(character_image_settings)"))
        }
    se.dispose()
    assert book == ("ink", "一盏旧风灯", "doubao-seedream-4-0-250828")
    assert avatar == ("瘦高的守灯人",)
    assert "cover_seed" not in book_cols and "seed" not in char_cols
    with sqlite3.connect(src) as check:
        # 源零接触：种子值仍在源库原样（只是不再被带走）
        assert check.execute(
            "SELECT cover_seed FROM book_image_settings").fetchone()[0] == 321
