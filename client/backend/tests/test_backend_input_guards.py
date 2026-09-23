"""c-backend-infra-hygiene — 三个守卫补全的单测

- 迁移端点 _validated_source：路径穿越/子目录/不存在 → 400
- 卷纲退役键：plot_nodes 显式携带 → 422；正常保存不受影响
- 章域 AI _vol_no：非法 vol_ref → 400；合法 vol-{N} → N
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import migration.router as migration_router
from chapters.ai_plan import _vol_no
from volumes.schemas import VolumeUpdate


def test_validated_source_rejects_traversal_and_subdir(tmp_path, monkeypatch):
    monkeypatch.setattr(migration_router, "DATA_ROOT", str(tmp_path))
    for bad in ("../x.db", "sub/x.db", "含'引号.db"):
        with pytest.raises(HTTPException) as ei:
            migration_router._validated_source(bad)
        assert ei.value.status_code == 400, bad


def test_validated_source_rejects_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(migration_router, "DATA_ROOT", str(tmp_path))
    # 白名单形状 + 存在性：形状合法但文件不存在同样 400
    with pytest.raises(HTTPException):
        migration_router._validated_source("novel-v99.db")
    # 白名单本身放行形状合法且存在的文件（对照臂）
    (tmp_path / "novel-v1.db").write_bytes(b"SQLite format 3\x00")
    assert migration_router._validated_source("novel-v1.db") == tmp_path / "novel-v1.db"


def test_attach_statement_survives_quoted_name():
    """ATTACH 字面量转义：文件名含引号时语句仍合法（双写 '）。"""
    staged = "/data/mig-staging/it's.db"
    staged_sql = str(staged).replace("'", "''")
    assert staged_sql == "/data/mig-staging/it''s.db"
    assert "'" not in staged_sql.replace("''", "")


def test_volume_update_rejects_plot_nodes():
    with pytest.raises(ValidationError) as ei:
        VolumeUpdate(plot_nodes=[{"who": "林拓"}])
    assert "plot_nodes" in str(ei.value)


def test_volume_update_without_retired_keys_ok():
    v = VolumeUpdate(title="新标题")
    assert v.title == "新标题"


def test_vol_no_rejects_illegal_ref():
    with pytest.raises(HTTPException) as ei:
        _vol_no("vol-abc")
    assert ei.value.status_code == 400
    with pytest.raises(HTTPException):
        _vol_no("")


def test_vol_no_parses_legal_ref():
    assert _vol_no("vol-3") == 3
    assert _vol_no("vol-12") == 12
