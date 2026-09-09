"""AI 会员门控矩阵测试（2026-08-18 口径）

口径：AI 是会员权益 —— trial/月/季/年/终身（未过期）放行；免费/过期一律 403
member_required（即使已配置 Key）；会员未配置 Key → 503 引导设置。
过期降为免费待遇：project_limit=1（过期不再比免费用户更特权）。

用法：
    cd client/backend
    python -m pytest tests/test_ai_member_gate.py -v
"""

import asyncio
import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB) ───────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_ai_gate.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_ai_gate_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")

# 占位 Key（非真实凭据）：拼接构造，避免任何真实密钥形态的字面量
_FAKE_KEY = "".join(("sk-", "test-placeholder"))  # noqa: FLY002


def _set_tier(tier: str, expires_at: str = "", api_key: str = ""):
    _service.CONFIG_FILE = _CFG_PATH
    cfg = _service.get_local_config()
    cfg.update({"tier": tier, "expires_at": expires_at, "api_key": api_key})
    _service.save_local_config(cfg)


def _future_iso(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


def _past_iso(days: int = 1) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).date().isoformat()


from api_configs.crypto import encrypt_api_key
from auth_local.deps import require_ai_access, require_novel_model
from auth_local.middleware import get_current_user
from auth_local.service import verify_session
from db import Base, async_session, engine, get_db
from main import app
from models.api_config import ApiConfig
from models.user import User
from workflow.tier import tier_bypass

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
    _run_async(_create_user("gateuser"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "gateuser"}


@pytest.fixture(autouse=True)
def _setup_overrides():
    # 不覆盖 require_ai_access / require_project_limit：本模块就是测真实门控
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    # 本书模型门控：本模块测的是内容/其他门控，模型就绪另测（9.2）
    app.dependency_overrides[require_novel_model] = lambda: True
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_config_after():
    yield
    if os.path.exists(_CFG_PATH):
        os.remove(_CFG_PATH)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ── check_permission 矩阵 ─────────────────────────────────────────────────


class TestCheckPermissionMatrix:
    def test_free_none_no_expiry(self):
        _set_tier("none")
        perm = _service.check_permission()
        assert perm["allowed"] is True
        assert perm["is_member"] is False
        assert perm["expired"] is False
        assert perm["project_limit"] == 1
        assert perm["trial_remaining_days"] == 0  # 不再默认 7

    def test_free_none_with_future_expiry_counts_days(self):
        _set_tier("none", _future_iso(3))
        assert _service.check_permission()["trial_remaining_days"] == 3

    def test_unknown_tier_treated_as_free(self):
        for tier in ("free", "xyz", ""):
            _set_tier(tier)
            perm = _service.check_permission()
            assert perm["is_member"] is False
            assert perm["project_limit"] == 1

    def test_trial_future_is_member(self):
        _set_tier("trial", _future_iso(5))
        perm = _service.check_permission()
        assert perm["is_member"] is True
        assert perm["project_limit"] is None

    def test_trial_past_expired_to_free_treatment(self):
        _set_tier("trial", _past_iso())
        perm = _service.check_permission()
        assert perm["is_member"] is False
        assert perm["expired"] is True
        assert perm["allowed"] is False
        assert perm["reason"] == "expired"
        assert perm["project_limit"] == 1

    def test_monthly_future_is_member(self):
        _set_tier("monthly", _future_iso())
        perm = _service.check_permission()
        assert perm["is_member"] is True
        assert perm["project_limit"] is None

    def test_monthly_past_downgrades_to_limit_1(self):
        # 核心回归：过期用户不再比免费用户更特权（原实现无 project_limit → 不限）
        _set_tier("monthly", _past_iso())
        perm = _service.check_permission()
        assert perm["is_member"] is False
        assert perm["expired"] is True
        assert perm["project_limit"] == 1
        assert tier_bypass() is True  # 过期仍走免费旁路（workflow 门控语义不变）

    def test_lifetime_never_expires(self):
        _set_tier("lifetime", _past_iso(days=3650))
        perm = _service.check_permission()
        assert perm["is_member"] is True
        assert perm["project_limit"] is None

    def test_member_without_expiry_data_is_member(self):
        # S端 旧数据兼容：无到期数据视为有效
        _set_tier("monthly", "")
        assert _service.check_permission()["is_member"] is True

    def test_invalid_date_is_invalid_with_limit_1(self):
        _set_tier("monthly", "not-a-date")
        perm = _service.check_permission()
        assert perm["allowed"] is False
        assert perm["reason"] == "invalid"
        assert perm["project_limit"] == 1


# ── verify_session 形状（前端过期徽标数据源）──────────────────────────────


class TestVerifySessionShape:
    def _write_session_config(self, tier: str, expires_at: str):
        _service.CONFIG_FILE = _CFG_PATH
        _service.save_local_config(
            {
                "token": "t-123",
                "username": "gateuser",
                "last_login_at": datetime.now(UTC).isoformat(),
                "tier": tier,
                "expires_at": expires_at,
            }
        )

    def test_member_unexpired(self):
        self._write_session_config("monthly", _future_iso(10))
        r = _run_async(verify_session())
        assert r["valid"] is True
        assert r["is_member"] is True
        assert r["expired"] is False
        assert r["project_limit"] is None
        assert r["expires_at"] == _future_iso(10)

    def test_member_expired_flags_expired(self):
        self._write_session_config("monthly", _past_iso())
        r = _run_async(verify_session())
        assert r["valid"] is True
        assert r["is_member"] is False
        assert r["expired"] is True
        assert r["project_limit"] == 1


# ── require_ai_access 矩阵（直接调用真实门控）────────────────────────────


class TestRequireAiAccessMatrix:
    def _call(self):
        async def run():
            async with async_session() as session:
                return await require_ai_access({"id": "gateuser"}, session)

        return _run_async(run())

    def test_free_with_key_blocked(self):
        # 核心口径：免费用户即使配置了 Key 也拦截
        _set_tier("none", api_key=_FAKE_KEY)
        with pytest.raises(Exception) as e:
            self._call()
        assert e.value.status_code == 403
        assert e.value.detail["reason"] == "member_required"

    def test_free_without_key_blocked(self):
        _set_tier("none")
        with pytest.raises(Exception) as e:
            self._call()
        assert e.value.status_code == 403
        assert e.value.detail["reason"] == "member_required"
        assert "试用" in e.value.detail["message"]

    def test_expired_member_with_key_blocked(self):
        _set_tier("monthly", _past_iso(), api_key=_FAKE_KEY)
        with pytest.raises(Exception) as e:
            self._call()
        assert e.value.status_code == 403
        assert e.value.detail["reason"] == "member_required"
        assert "过期" in e.value.detail["message"]

    def test_member_without_key_503_configure(self):
        _set_tier("monthly", _future_iso(), api_key="")
        with pytest.raises(Exception) as e:
            self._call()
        assert e.value.status_code == 503

    def test_member_with_config_key_passes(self):
        _set_tier("monthly", _future_iso(), api_key=_FAKE_KEY)
        assert self._call() is True

    def test_trial_with_key_passes(self):
        _set_tier("trial", _future_iso(3), api_key=_FAKE_KEY)
        assert self._call() is True

    def test_lifetime_with_key_passes(self):
        _set_tier("lifetime", api_key=_FAKE_KEY)
        assert self._call() is True

    def test_member_with_db_apiconfig_passes(self):
        # ApiConfig 表路径：config.json 无 Key，但 DB 有 active 加密 Key
        _set_tier("monthly", _future_iso(), api_key="")

        async def seed():
            async with async_session() as session:
                session.add(
                    ApiConfig(
                        user_id="gateuser",
                        name="测试配置",
                        vendor="deepseek",
                        api_key=encrypt_api_key(_FAKE_KEY),
                        base_url="https://api.deepseek.com/anthropic",
                        status="active",
                    )
                )
                await session.commit()

        _run_async(seed())
        assert self._call() is True


# ── HTTP 集成：结构化 403 + 项目上限 ──────────────────────────────────────


class TestHttpIntegration:
    def test_settings_ai_free_returns_structured_403(self, client):
        _set_tier("none", api_key=_FAKE_KEY)
        r = client.post(
            "/api/novels/whatever/settings/ai/world/geography",
            json={"context": {}},
        )
        assert r.status_code == 403
        assert r.json()["detail"]["reason"] == "member_required"

    def test_project_limit_free_and_expired(self, client):
        # 免费第 1 本 OK
        _set_tier("none")
        r1 = client.post("/api/novels", json={"name": "gate-free-1"})
        assert r1.status_code in (200, 201), r1.text

        # 免费第 2 本 403
        r2 = client.post("/api/novels", json={"name": "gate-free-2"})
        assert r2.status_code == 403
        assert "免费" in r2.text

        # 过期套餐降到同样 1 本上限（核心回归：原实现过期不限量）
        _set_tier("yearly", _past_iso())
        r3 = client.post("/api/novels", json={"name": "gate-expired-2"})
        assert r3.status_code == 403
        assert "已过期" in r3.text

        # 会员恢复不限量
        _set_tier("yearly", _future_iso(365))
        r4 = client.post("/api/novels", json={"name": "gate-member-2"})
        assert r4.status_code in (200, 201), r4.text
        r5 = client.post("/api/novels", json={"name": "gate-member-3"})
        assert r5.status_code in (200, 201), r5.text
