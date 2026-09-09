"""Change 002 — tier-free-bypass 测试（TE-01 单元 + TE-02 HTTP + TE-05 settings_ai 补测）

免费（tier=none）与过期套餐绕过阶段门控与阶段机校验；付费未过期用户
仍被 gate 拦截。settings AI 生成字段（generate_field）无 AI 权限时 403（D5 回归）。

用法：
    cd client/backend
    python -m pytest tests/test_free_bypass.py -v
"""

import asyncio
import os
import tempfile
import types
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB) ───────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_free_bypass.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_free_bypass_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

# 每个测试模块独立 config.json；set_tier 在调用时重定向 CONFIG_FILE 到本模块路径，
# 避免跨模块收集顺序导致读到别的模块写入的套餐状态。
import auth_local.service as _service

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")


def _set_tier(tier: str, expires_at: str = "", api_key: str = ""):
    _service.CONFIG_FILE = _CFG_PATH
    _service.save_local_config(
        {
            "tier": tier,
            "expires_at": expires_at,
            "api_key": api_key,
        }
    )


def _future_iso(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


def _past_iso(days: int = 1) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).date().isoformat()


from auth_local.deps import require_novel_model, require_project_limit
from auth_local.middleware import get_current_user
from db import Base, async_session, engine, get_db
from main import app
from models.user import User
from workflow.gates import GateResult
from workflow.tier import tier_bypass, tier_or_gate, tier_phase_transition

# ── Helpers ───────────────────────────────────────────────────────────────


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _create_user(user_id: str) -> str:
    async with async_session() as session:
        session.add(
            User(
                id=user_id,
                email=f"{user_id}@test.com",
                password_hash="*",
                display_name=user_id,
            )
        )
        await session.commit()
    return user_id


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    _run_async(_create_tables())
    _run_async(_create_user("freeuser"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "freeuser"}


async def _override_true():
    return True


@pytest.fixture(autouse=True)
def _setup_overrides():
    # 不覆盖 require_ai_access：真实门控跑，证明免费流程无 AI 权限可用。
    # 覆盖 require_project_limit：项目配额非本 change 范围，会话共享 DB 使项目跨测试残留。
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    # 本书模型门控：本模块测的是内容/其他门控，模型就绪另测（9.2）
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = _override_true
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_config_after():
    """每测试结束删除 config.json，恢复"无套餐"基线（tier=""），
    不污染后运行的 test_workflow_api（其依赖默认非旁路行为）。"""
    yield
    if os.path.exists(_CFG_PATH):
        os.remove(_CFG_PATH)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _create_sparse_project(client) -> str:
    name = f"fb-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), f"Create failed: {r.text}"
    return r.json()["id"]


def _create_volume_and_chapter(client, pid: str) -> str:
    """建卷 + 稀疏章节（不填充必填字段、不 prime settings）。"""
    r = client.post(
        f"/api/novels/{pid}/volumes", json={"vol_num": 1, "title": "Volume 1"}
    )
    assert r.status_code in (200, 201), f"Volume failed: {r.text}"
    r2 = client.post(
        f"/api/novels/{pid}/volumes/{r.json()['ref']}/chapters",
        json={"title": "第1章"},
    )
    assert r2.status_code in (200, 201), f"Chapter failed: {r2.text}"
    return r2.json()["chapter_ref"]


# ── TE-01 单元测试 ───────────────────────────────────────────────────────


class TestTierBypassUnit:
    def test_free_none_bypasses(self):
        _set_tier("none")
        assert _service.check_permission()["allowed"] is True
        assert tier_bypass() is True

    def test_paid_unexpired_not_bypass(self):
        _set_tier("monthly", _future_iso())
        assert tier_bypass() is False

    def test_paid_expired_bypasses(self):
        _set_tier("monthly", _past_iso())
        assert tier_bypass() is True

    def test_no_config_defaults_to_free_bypass(self):
        # 无 config.json → check_permission 默认 tier="none"（新装即免费）→ 旁路
        assert tier_bypass() is True

    def test_tier_or_gate_free_skips_gate_fn(self):
        _set_tier("none")
        calls: list = []

        async def gate_fn(*_a):
            calls.append(1)
            return GateResult(valid=False, warnings=["blocked"], hard_block=True)

        result = _run_async(tier_or_gate(None, None, gate_fn))
        assert calls == []
        assert result.valid is True
        assert result.hard_block is False

    def test_tier_or_gate_pro_runs_gate_fn(self):
        _set_tier("monthly", _future_iso())

        async def gate_fn(*_a):
            return GateResult(valid=False, warnings=["blocked"], hard_block=True)

        result = _run_async(tier_or_gate(None, None, gate_fn))
        assert result.valid is False
        assert result.warnings == ["blocked"]

    def test_tier_phase_transition_free_forces_illegal(self):
        _set_tier("none")
        project = types.SimpleNamespace(current_phase="settings")
        tier_phase_transition(project, "archive")  # settings→archive 非法，免费直接 force
        assert project.current_phase == "archive"

    def test_tier_phase_transition_pro_rejects_illegal(self):
        _set_tier("monthly", _future_iso())
        project = types.SimpleNamespace(current_phase="settings")
        with pytest.raises(ValueError):
            tier_phase_transition(project, "archive")
        assert project.current_phase == "settings"

    def test_tier_phase_transition_free_legal_still_forces(self):
        _set_tier("none")
        project = types.SimpleNamespace(current_phase="write")
        tier_phase_transition(project, "archive")  # write→archive 合法
        assert project.current_phase == "archive"


# ── TE-02 HTTP 集成 ──────────────────────────────────────────────────────


class TestFreeWorkflowHttp:
    def test_free_confirm_sparse_chapter_ok(self, client):
        _set_tier("none")
        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/confirm")
        assert r.status_code == 200, r.text

    def test_free_transition_to_write_no_prompts_ok(self, client):
        _set_tier("none")
        pid = _create_sparse_project(client)
        _create_volume_and_chapter(client, pid)
        r = client.post(f"/api/novels/{pid}/workflow/transition", json={"target": "write"})
        assert r.status_code == 200, r.text
        assert r.json()["phase"] == "write"

    def test_free_phase_status_all_complete(self, client):
        _set_tier("none")
        pid = _create_sparse_project(client)
        _create_volume_and_chapter(client, pid)
        r = client.get(f"/api/novels/{pid}/workflow/phase-status")
        assert r.status_code == 200
        data = r.json()
        assert data["tier_bypass"] is True
        assert set(data["phases"].values()) == {"complete"}
        assert data["warnings"] == []

    def test_pro_sparse_confirm_blocked(self, client):
        _set_tier("none")  # 免费态先建项目，避免 settings 未完成阻塞建卷
        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        _set_tier("monthly", _future_iso())
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/confirm")
        assert r.status_code == 400
        assert "章纲确认失败" in r.text

    def test_pro_phase_status_real_gates(self, client):
        _set_tier("none")
        pid = _create_sparse_project(client)
        _create_volume_and_chapter(client, pid)
        _set_tier("monthly", _future_iso())
        r = client.get(f"/api/novels/{pid}/workflow/phase-status")
        assert r.status_code == 200
        data = r.json()
        assert "tier_bypass" not in data
        # 建卷 update_phase("outline") 已推进 → outline 进行中，prompt 未达
        assert data["phases"]["outline"] == "in_progress"
        assert data["phases"]["prompt"] == "pending"

    def test_expired_paid_bypasses(self, client):
        _set_tier("none")
        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        _set_tier("monthly", _past_iso())  # 过期套餐按免费处理
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/confirm")
        assert r.status_code == 200, r.text


# ── TE-05 settings_ai 补测（D5 回归）──────────────────────────────────────


class TestSettingsAIGated:
    def test_generate_field_gated_without_ai_access(self, client):
        # 免费 + 试用到期 + 无 API Key → require_ai_access 抛 403（D5：generate_field 原未挂门控）
        _set_tier("none", _past_iso(), api_key="")
        pid = _create_sparse_project(client)
        r = client.post(
            f"/api/novels/{pid}/settings/ai/world/geography", json={"context": {}}
        )
        assert r.status_code == 403
        assert "到期" in r.text or "试用" in r.text
