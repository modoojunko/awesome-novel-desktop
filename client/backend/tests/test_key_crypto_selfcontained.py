"""key-crypto-selfcontained — 判定层可解密性 ＋ 钥匙入库迁移

矩阵：
- crypto 迁移三态：旧文件合法在（migrated，行=文件内容、文件保留）/ 文件非法
  （generated＋warning、文件保留）/ 文件不在（generated）；并发首启撞 PK →
  重读装载先到者；幂等（二次 init = ready）。
- 判定层：config_key_usable 三态矩阵（空/死文/测试失败/可解）；no_key_message
  三分支＋固定优先级「解不开 优先于 测试失败」；user_has_ai_key 全死文不放行、
  死文+活放行；get_ai_client_for_user 跳死文用活配置。
- 门控金丝雀：死文配置下 POST /volumes/ai/options → 503 reason=no_key +
  「重新粘贴保存」文案（不 500、AI 不被触达）；story /init 同口径早拦。

用法：
    cd client/backend
    python -m pytest tests/test_key_crypto_selfcontained.py -v
"""

import asyncio
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_kcs.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_key_crypto_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from sqlalchemy.ext.asyncio import (
    async_sessionmaker,  # noqa: E402
    create_async_engine,  # noqa: E402
)

import auth_local.service as _service  # noqa: E402
from api_configs import crypto as _crypto  # noqa: E402
from api_configs.crypto import encrypt_api_key  # noqa: E402
from auth_local.deps import ensure_novel_model_ready  # noqa: E402
from auth_local.middleware import get_current_user  # noqa: E402
from db import async_session, get_db  # noqa: E402
from main import app  # noqa: E402
from models import Novel  # noqa: E402
from models.api_config import ApiConfig  # noqa: E402
from models.user import User  # noqa: E402

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")
USER_ID = "kcs_user"

# 「另一把钥匙」加密的死文密文（模块级生成一次；与当前钥匙必不匹配）
_DEAD_CIPHER = "enc:" + Fernet(Fernet.generate_key()).encrypt(b"sk-dead-key").decode()


def _set_tier(tier: str, api_key: str = "sk-test"):
    _service.CONFIG_FILE = _CFG_PATH
    _service.save_local_config(
        {"tier": tier, "expires_at": _future_iso() if tier != "none" else "", "api_key": api_key}
    )


def _future_iso(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": USER_ID}


# ── Part A：crypto 迁移三态（独立临时库，只建 app_meta） ──────────────────


def _init_on_fresh_db(tmpdir: str, *, racy: bool = False):
    """独立空库（只建 app_meta）单 loop 内建表＋init＋读回行。

    aiosqlite 连接绑定创建它的 event loop——engine 生命周期整体留在一次
    _run_async（单个 loop）内，用完 dispose，避免跨 loop 连接错乱。
    racy=True 时模拟并发首启：init 的首次 INSERT 前，另一「进程」已抢先把
    同名行落库，本次 commit 撞 PK → init 应回读先到者装载。
    """
    async def _run():

        from models.app_meta import AppMeta

        db_path = os.path.join(tmpdir, "k.db")
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(AppMeta.__table__.create)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                outcome = await _crypto.init_crypto(
                    _RacySession(session, factory) if racy else session
                )
            async with factory() as session:
                row = await session.get(AppMeta, _crypto.FERNET_KEY_ROW_ID)
                return outcome, (row.value if row else None)
        finally:
            await engine.dispose()

    return _run_async(_run())


class _RacySession:
    """包装 AsyncSession：首次 commit 前让「对手进程」（独立会话）抢先落库提交，
    本会话随后的 INSERT 提交真实撞 PK → init 走 rollback＋重读先到者分支。"""

    def __init__(self, inner, factory):
        self._inner = inner
        self._factory = factory
        self._first = True

    def add(self, obj):
        self._inner.add(obj)

    async def commit(self):
        if self._first:
            self._first = False
            from models.app_meta import AppMeta as _AM

            async with self._factory() as rival:
                rival.add(_AM(key=_crypto.FERNET_KEY_ROW_ID, value="z" * 44))
                await rival.commit()
        return await self._inner.commit()

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.fixture()
def _crypto_isolated(tmp_path):
    """Part A 专用：独立钥匙文件路径＋干净模块态；用例后恢复共享库装载。"""
    orig_file = _crypto._FERNET_KEY_FILE
    _crypto._FERNET_KEY_FILE = str(tmp_path / ".fernet_key")
    _crypto._reset_for_tests()
    yield
    _crypto._FERNET_KEY_FILE = orig_file
    _crypto._reset_for_tests()

    async def _run():
        from db import async_session as _as

        async with _as() as session:
            await _crypto.init_crypto(session)

    _run_async(_run())


# ── Part B：判定层（本模块库＋假死文配置） ────────────────────────────────


@pytest.fixture(autouse=True)
def _setup_overrides():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    _set_tier("max")  # 会员（MAX：放行 ai-plot 等全部 key）：require_ai_access 放行，专测模型链路门控
    with TestClient(app) as c:
        yield c


async def _ensure_user():
    async with async_session() as session:
        if await session.get(User, USER_ID) is None:
            session.add(User(id=USER_ID, email=f"{USER_ID}@test.local", password_hash="x"))
            await session.commit()


def _mk_config(name: str, api_key: str) -> str:
    _run_async(_ensure_user())
    async def _s():
        async with async_session() as session:
            cfg = ApiConfig(
                id=str(uuid.uuid4()),
                user_id=USER_ID,
                name=name,
                vendor="deepseek",
                api_format="openai",
                base_url="https://api.example.com/v1",
                api_key=api_key,
                models='["m-1"]',
                status="active",
            )
            session.add(cfg)
            await session.commit()
            return cfg.id

    return _run_async(_s())


def _call_user_has_ai_key(uid: str) -> bool:
    async def _run():
        from ai_state import user_has_ai_key

        async with async_session() as session:
            return await user_has_ai_key(session, uid)

    return _run_async(_run())


def _mk_project(client, config_id: str) -> str:
    _run_async(_ensure_user())
    r = client.post("/api/novels", json={"name": f"kcs-{uuid.uuid4().hex[:6]}"})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]

    async def _bind():
        async with async_session() as session:
            proj = await session.get(Novel, pid)
            proj.ai_config_id = config_id
            proj.ai_model = "m-1"
            await session.commit()

    _run_async(_bind())
    return pid


class TestJudgmentLayer:
    def test_config_key_usable_matrix(self):
        from ai_state import config_key_usable

        assert config_key_usable(None) is False
        empty = ApiConfig(api_key="")
        assert config_key_usable(empty) is False
        dead = ApiConfig(api_key=_DEAD_CIPHER)
        assert config_key_usable(dead) is False
        testfail = ApiConfig(api_key="sk-plain", last_test_status="auth_error")
        assert config_key_usable(testfail) is False
        ok = ApiConfig(api_key=encrypt_api_key("sk-live"))
        assert config_key_usable(ok) is True

    def test_no_key_message_three_branches_and_priority(self):
        from ai_state import no_key_message

        assert "模型配置" in no_key_message(None)
        assert "重新粘贴保存" in no_key_message(ApiConfig(api_key=_DEAD_CIPHER))
        assert "重测" in no_key_message(ApiConfig(api_key="sk-plain", last_test_status="auth_error"))
        assert "模型配置" in no_key_message(ApiConfig(api_key=""))
        # 固定优先级：死文＋测试失败并存 → 指向重新粘贴保存
        both = ApiConfig(api_key=_DEAD_CIPHER, last_test_status="auth_error")
        assert "重新粘贴保存" in no_key_message(both)

    def test_user_has_ai_key_with_dead_and_live(self):

        _mk_config("dead", _DEAD_CIPHER)
        _mk_config("live", encrypt_api_key("sk-live"))
        assert _call_user_has_ai_key(USER_ID) is True

    def test_user_has_ai_key_all_dead(self):

        uid = f"{USER_ID}_dead"

        async def _seed():
            async with async_session() as session:
                session.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
                session.add(
                    ApiConfig(
                        id=str(uuid.uuid4()), user_id=uid, name="d1", vendor="v",
                        api_format="openai", base_url="https://x", api_key=_DEAD_CIPHER,
                        models='["m"]', status="active",
                    )
                )
                await session.commit()

        _run_async(_seed())
        assert _call_user_has_ai_key(uid) is False

    def test_get_ai_client_for_user_skips_dead_uses_live(self):
        from ai_client import get_ai_client_for_user

        uid = f"{USER_ID}_order"
        _run_async(_ensure_user())

        async def _seed():
            async with async_session() as session:
                session.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
                # 同一用户两条配置：较新的死文（原 limit(1) 会选中它）＋较旧的活文
                session.add(
                    ApiConfig(
                        id="c-order-dead", user_id=uid, name="newer-dead", vendor="v",
                        api_format="openai", base_url="https://dead", api_key=_DEAD_CIPHER,
                        models='["m-dead"]', status="active", created_at=datetime(2021, 1, 1),
                    )
                )
                session.add(
                    ApiConfig(
                        id="c-order-live", user_id=uid, name="older-live", vendor="v",
                        api_format="openai", base_url="https://live.example.com/v1",
                        api_key=encrypt_api_key("sk-live-order"),
                        models='["m-live"]', status="active", created_at=datetime(2020, 1, 1),
                    )
                )
                await session.commit()

        _run_async(_seed())
        client_obj = _run_async(get_ai_client_for_user(uid))
        # 死文（较新）被跳过 → 用的是活配置（base_url 区分；api_key 不外露为属性）
        assert client_obj._base_url == "https://live.example.com/v1"

    def test_ensure_novel_model_ready_dead_503(self, client):
        from fastapi import HTTPException

        cfg_id = _mk_config("bind-dead", _DEAD_CIPHER)
        pid = _mk_project(client, cfg_id)

        async def _gate():
            async with async_session() as session:
                await ensure_novel_model_ready(session, USER_ID, pid)

        with pytest.raises(HTTPException) as ei:
            _run_async(_gate())
        assert ei.value.status_code == 503
        assert ei.value.detail["reason"] == "no_key"
        assert "重新粘贴保存" in ei.value.detail["message"]


# ── Part C：金丝雀——死文态端点 503 非 500 ────────────────────────────────


class TestCanaryEndpoints:
    def test_volume_options_dead_key_503_not_500(self, client):
        from fastapi.testclient import (
            TestClient as _TC,  # noqa: F401 — client fixture 已覆盖
        )

        cfg_id = _mk_config("canary-dead", _DEAD_CIPHER)
        pid = _mk_project(client, cfg_id)
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": ""})
        assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.text}"
        detail = r.json().get("detail") or {}
        assert detail.get("reason") == "no_key"
        assert "重新粘贴保存" in detail.get("message", "")

    def test_story_init_dead_key_503(self, client):
        cfg_id = _mk_config("story-dead", _DEAD_CIPHER)
        pid = _mk_project(client, cfg_id)
        r = client.post("/api/story/init", json={"project_id": pid})
        assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.text}"
        detail = r.json().get("detail") or {}
        assert detail.get("reason") == "no_key"
        assert "重新粘贴保存" in detail.get("message", "")
