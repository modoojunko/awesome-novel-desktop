"""拆书/导入档位门禁矩阵（c-deconstruct-tier）。

口径：正文导入（direct import 链）与列表/详情/产物预览/取消**不设门**，不在本件；
这里钉 AI 拆书（`deconstruct`，PRO 起、trial 同权）与产物建书（`deconstruct-import`，
仅 MAX）。旧快照缺新 key 时按 key 最低档隐式放行（未过期）。
"""

import os

os.environ.setdefault("IMAGE_DISPATCHER_OFF", "1")

import pytest
from fastapi.testclient import TestClient

from auth_local import deps as auth_deps
from auth_local.middleware import get_current_user
from db import async_session, get_db
from main import app

USER_ID = "decon-tier-user"

# 旧权益快照：四档时代早期形态，不含任何新 key
LEGACY_FEATURES = ["ai-model", "ai-generate", "ai-plan"]


async def _override_db():
    async with async_session() as session:
        yield session


def _set_permission(monkeypatch, tier, features, *, is_member=True, expired=False):
    async def _ensure():
        return None

    async def _no_model(user, db):
        return None

    monkeypatch.setattr(auth_deps, "ensure_entitlement_snapshot", _ensure)
    monkeypatch.setattr(auth_deps, "_check_writing_model_configured", _no_model)
    monkeypatch.setattr(
        auth_deps, "check_permission",
        lambda: {
            "tier": tier, "is_member": is_member, "expired": expired,
            "entitlement": {"v": 1, "features": features},
        },
    )


@pytest.fixture()
def client():
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {"id": USER_ID}
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_create_task_gate_matrix(client, monkeypatch):
    """AI 拆书＝deconstruct（PRO 起、trial 同权）：免费会员拦截、标准 feature_required、
    旧快照 trial/pro 隐式放行（过门禁后因缺上传文件 422，不再 403）。"""
    _set_permission(monkeypatch, "free", [], is_member=False)
    r = client.post("/api/deconstruct/tasks")
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["reason"] == "member_required"

    _set_permission(monkeypatch, "standard", ["ai-plan", "ai-model"])
    r = client.post("/api/deconstruct/tasks")
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["reason"] == "feature_required"
    assert r.json()["detail"]["tier_required"] == "pro"

    for tier in ("trial", "pro", "monthly"):
        _set_permission(monkeypatch, tier, LEGACY_FEATURES)
        r = client.post("/api/deconstruct/tasks")
        assert r.status_code == 422, (tier, r.text)  # 门禁已过：缺文件是参数校验


def test_resume_and_export_gate(client, monkeypatch):
    """续拆/导出＝deconstruct：标准拒、旧快照 pro 过门禁后进业务层（无任务 404）。"""
    _set_permission(monkeypatch, "standard", ["ai-plan", "ai-model"])
    r = client.post("/api/deconstruct/tasks/t1/resume", json=None)
    assert r.status_code == 403 and r.json()["detail"]["reason"] == "feature_required"
    r = client.post(
        "/api/deconstruct/tasks/t1/export", json={"dest_dir": "/tmp/x", "files": ["a.md"]},
    )
    assert r.status_code == 403 and r.json()["detail"]["reason"] == "feature_required"

    _set_permission(monkeypatch, "pro", LEGACY_FEATURES)
    assert client.post("/api/deconstruct/tasks/t1/resume", json=None).status_code == 404
    assert client.post(
        "/api/deconstruct/tasks/t1/export", json={"dest_dir": "/tmp/x", "files": ["a.md"]},
    ).status_code == 404


def test_import_book_max_only(client, monkeypatch):
    """产物建书＝deconstruct-import（仅 MAX）：trial/pro/standard 拒、max 过门禁。"""
    _set_permission(monkeypatch, "trial", LEGACY_FEATURES)
    r = client.post("/api/deconstruct/tasks/t1/import-book", json=None)
    assert r.status_code == 403 and r.json()["detail"]["reason"] == "feature_required"
    assert r.json()["detail"]["tier_required"] == "max"

    _set_permission(monkeypatch, "pro", LEGACY_FEATURES + ["deconstruct"])
    r = client.post("/api/deconstruct/tasks/t1/import-book", json=None)
    assert r.status_code == 403 and r.json()["detail"]["tier_required"] == "max"

    _set_permission(monkeypatch, "max", LEGACY_FEATURES + ["deconstruct", "deconstruct-import"])
    assert client.post("/api/deconstruct/tasks/t1/import-book", json=None).status_code == 404


def test_import_book_legacy_max_snapshot_implicit_allow(client, monkeypatch):
    """旧 MAX 快照缺 deconstruct-import：终身/未过期 max 隐式放行（过门禁后 404）。"""
    _set_permission(monkeypatch, "max", LEGACY_FEATURES)
    assert client.post("/api/deconstruct/tasks/t1/import-book", json=None).status_code == 404
    _set_permission(monkeypatch, "lifetime", LEGACY_FEATURES)
    assert client.post("/api/deconstruct/tasks/t1/import-book", json=None).status_code == 404


def test_open_endpoints_not_gated(client, monkeypatch):
    """列表/详情/取消对免费用户开放（不设权益门）：只差登录。"""
    _set_permission(monkeypatch, "free", [], is_member=False)
    assert client.get("/api/deconstruct/tasks").status_code == 200
    assert client.get("/api/deconstruct/tasks/t1").status_code == 404  # 业务层 404，非 403
    assert client.post("/api/deconstruct/tasks/t1/cancel").status_code == 404


def test_expired_locked(client, monkeypatch):
    _set_permission(monkeypatch, "pro", LEGACY_FEATURES, is_member=False, expired=True)
    r = client.post("/api/deconstruct/tasks/t1/resume", json=None)
    assert r.status_code == 403
