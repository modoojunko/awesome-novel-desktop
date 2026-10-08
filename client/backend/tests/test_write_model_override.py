"""c-prose-model-select — 生成按次模型对（POST /write 可选 `api_config_id` + `model`）。

契约（specs/prose-writing「生成按次选择模型」）：
  * 覆盖对按与绑定同源谓词校验：配置存在且未删除 / 归属本书用户 / 非朱雀检测配置 /
    Key 可解密 / `model ∈ config.models`——任一不满足在**开流前** 400（可读错因、
    无 SSE、不发起模型调用、不改本书绑定）；
  * 合法覆盖对生效：上游调用使用所选模型，本书绑定与规划类 AI 不受影响；
  * 未给覆盖对＝今日路径（本书模型，请求与行为逐字不变）；
  * 记账记**实际生效模型 id ＋ 配置 id**（成功/失败两路，收敛原「别名 haiku＋空配置」）。

用法：
    cd client/backend
    python -m pytest tests/test_write_model_override.py -v
"""

import asyncio
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_wmo.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_write_model_override_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import ai_client as ai_client_mod  # noqa: E402
import auth_local.service as _service  # noqa: E402
from auth_local.deps import require_novel_model, require_project_limit  # noqa: E402
from auth_local.middleware import get_current_user  # noqa: E402
from db import Base, async_session, engine, get_db  # noqa: E402
from main import app  # noqa: E402
from models.api_config import ApiConfig  # noqa: E402
from models.project import Novel  # noqa: E402
from models.token_log import TokenLog  # noqa: E402
from models.user import User  # noqa: E402

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")
USER_ID = "wmo_user"

# 真解析函数（patch 前捕获）：端点测试用它做真校验，仅把流式调用换假
_REAL_GET_AI_CLIENT = ai_client_mod.get_ai_client_for_novel


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _set_member():
    _service.CONFIG_FILE = _CFG_PATH
    _service.save_local_config(
        {
            "tier": "max",
            "expires_at": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
            "api_key": "sk-test",
        }
    )


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session() as session:
            session.add(
                User(
                    id=USER_ID,
                    email=f"{USER_ID}@test.com",
                    password_hash="*",
                    display_name=USER_ID,
                )
            )
            session.add(
                User(
                    id="wmo_other",
                    email="wmo_other@test.com",
                    password_hash="*",
                    display_name="wmo_other",
                )
            )
            await session.commit()

    _run_async(_create())
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": USER_ID}


@pytest.fixture(autouse=True)
def _setup_overrides():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    # 本书模型门控在本模块另测（就绪判据不属本 change）；这里测按次覆盖与记账
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = lambda: True
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


# ── 造数助手 ─────────────────────────────────────────────────────────────


def _mk_config(name: str, models: list[str] | None, **kw) -> str:
    """直插一条可用配置（Key 加密入库），返回 config_id。"""
    from api_configs.crypto import encrypt_api_key

    async def _seed() -> str:
        async with async_session() as session:
            cfg = ApiConfig(
                user_id=kw.get("user_id", USER_ID),
                name=name,
                vendor=kw.get("vendor", "deepseek"),
                api_format=kw.get("api_format", "openai"),
                api_key=encrypt_api_key(kw.get("api_key", "sk-test")),
                base_url=kw.get("base_url", f"https://{name}.example.com/v1"),
                models=json.dumps(models) if models is not None else None,
                status=kw.get("status", "active"),
                last_test_status=kw.get("last_test_status"),
            )
            session.add(cfg)
            await session.commit()
            await session.refresh(cfg)
            return cfg.id

    return _run_async(_seed())


def _bind(novel_id: str, config_id: str, model: str) -> None:
    async def _seed():
        async with async_session() as session:
            novel = await session.get(Novel, novel_id)
            novel.ai_config_id = config_id
            novel.ai_model = model
            await session.commit()

    _run_async(_seed())


def _get_binding(novel_id: str) -> tuple[str | None, str | None]:
    async def _read():
        async with async_session() as session:
            novel = await session.get(Novel, novel_id)
            return novel.ai_config_id, novel.ai_model

    return _run_async(_read())


def _last_usage(project_id: str, operation: str = "write_chapter") -> TokenLog | None:
    async def _read():
        async with async_session() as session:
            rows = (
                (
                    await session.execute(
                        select(TokenLog)
                        .where(
                            TokenLog.project_id == project_id,
                            TokenLog.operation == operation,
                        )
                        .order_by(TokenLog.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return rows[-1] if rows else None

    return _run_async(_read())


def _create_project_and_chapter(client, seed: int = 0) -> tuple[str, str]:
    name = f"wmo-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    client.post(f"/api/novels/{pid}/volumes", json={"vol_num": 1, "title": "第一卷"})
    r2 = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第1章"})
    assert r2.status_code in (200, 201), r2.text
    ref = r2.json()["chapter_ref"]

    async def _seed_chapter():
        async with async_session() as session:
            proj = await session.get(Novel, pid)
            root = proj.root_path
        from chapters.store import save_chapter

        await save_chapter(root, ref, {"title": "第1章", "prose": ""})

    _run_async(_seed_chapter())
    return pid, ref


class _FakeStreamClient:
    def __init__(self, text: str):
        self._text = text
        self.calls: list[dict] = []

    async def chat_stream(self, **kwargs):
        from ai_client import StreamEvent

        self.calls.append(kwargs)
        yield StreamEvent(text=self._text)
        yield StreamEvent(is_done=True, tokens=42, tokens_in=7)


PROSE = "雨下了一夜。\n他把伞收在门后。\n「走了。」他说。\n" * 3


def _patch_real_resolve_with_fake_stream(monkeypatch, fake: _FakeStreamClient) -> dict:
    """真解析 + 假流：覆盖对仍走真 `get_ai_client_for_novel`（校验与构造），
    只把流式调用换成假客户端；捕获真构造出的模型/供应商供断言。"""
    captured: dict = {}

    async def _fake(novel_id, *, api_config_id=None, model=None):
        real = await _REAL_GET_AI_CLIENT(
            novel_id, api_config_id=api_config_id, model=model
        )
        captured["model"] = real.model
        captured["vendor"] = getattr(real, "_vendor", "")
        return fake

    monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake)
    return captured


# ── 1. 解析层：覆盖对校验矩阵（直接测 get_ai_client_for_novel）──────────────


class TestOverrideResolution:
    def test_override_uses_selected_config_and_model(self, client):
        pid, _ = _create_project_and_chapter(client)
        c1 = _mk_config("deepseek-a", ["deepseek-v4-pro"], base_url="https://a.example.com/v1")
        c2 = _mk_config(
            "ollama-b", ["qwen2.5:14b"], vendor="ollama", base_url="http://127.0.0.1:11434/v1"
        )
        _bind(pid, c1, "deepseek-v4-pro")

        client = _run_async(
            ai_client_mod.get_ai_client_for_novel(
                pid, api_config_id=c2, model="qwen2.5:14b"
            )
        )
        assert client.model == "qwen2.5:14b"
        assert getattr(client, "_vendor", "") == "ollama"
        assert client._base_url == "http://127.0.0.1:11434/v1"  # noqa: SLF001 — 断言构造入参
        # 本书绑定不受影响
        assert _get_binding(pid) == (c1, "deepseek-v4-pro")

    def test_no_override_keeps_book_model(self, client):
        pid, _ = _create_project_and_chapter(client)
        c1 = _mk_config("deepseek-c", ["deepseek-v4-pro", "deepseek-v4-flash"])
        _bind(pid, c1, "deepseek-v4-flash")
        client = _run_async(ai_client_mod.get_ai_client_for_novel(pid))
        assert client.model == "deepseek-v4-flash"

    def test_model_not_in_config_list_rejected(self, client):
        pid, _ = _create_project_and_chapter(client)
        c1 = _mk_config("deepseek-d", ["deepseek-v4-pro"])
        c2 = _mk_config("deepseek-e", ["deepseek-v4-flash"])
        _bind(pid, c1, "deepseek-v4-pro")
        with pytest.raises(ValueError, match="模型清单"):
            _run_async(
                ai_client_mod.get_ai_client_for_novel(
                    pid, api_config_id=c2, model="deepseek-v4-pro"
                )
            )

    def test_zhuque_config_rejected(self, client):
        pid, _ = _create_project_and_chapter(client)
        c1 = _mk_config("deepseek-f", ["deepseek-v4-pro"])
        zq = _mk_config("朱雀检测", ["deepseek-v4-pro"], vendor="zhuque")
        _bind(pid, c1, "deepseek-v4-pro")
        with pytest.raises(ValueError, match="正文生成"):
            _run_async(
                ai_client_mod.get_ai_client_for_novel(
                    pid, api_config_id=zq, model="deepseek-v4-pro"
                )
            )

    def test_deleted_and_foreign_and_missing_config_rejected(self, client):
        pid, _ = _create_project_and_chapter(client)
        c1 = _mk_config("deepseek-g", ["deepseek-v4-pro"])
        dead = _mk_config("deepseek-dead", ["deepseek-v4-pro"], status="deleted")
        foreign = _mk_config("foreign", ["deepseek-v4-pro"], user_id="wmo_other")
        _bind(pid, c1, "deepseek-v4-pro")
        for cid in (dead, foreign, "no-such-config"):
            with pytest.raises(ValueError, match="不存在"):
                _run_async(
                    ai_client_mod.get_ai_client_for_novel(
                        pid, api_config_id=cid, model="deepseek-v4-pro"
                    )
                )

    def test_no_key_config_rejected(self, client):
        pid, _ = _create_project_and_chapter(client)
        c1 = _mk_config("deepseek-h", ["deepseek-v4-pro"])
        nokey = _mk_config("deepseek-nokey", ["deepseek-v4-pro"], api_key="")
        _bind(pid, c1, "deepseek-v4-pro")
        with pytest.raises(ValueError, match="可用 Key"):
            _run_async(
                ai_client_mod.get_ai_client_for_novel(
                    pid, api_config_id=nokey, model="deepseek-v4-pro"
                )
            )

    def test_failed_test_status_config_rejected(self, client):
        """评审 P3：与本书就绪同谓词——Key 已吊销（最近连接失败）的配置不得按次放行。"""
        pid, _ = _create_project_and_chapter(client)
        c1 = _mk_config("deepseek-rev", ["deepseek-v4-pro"])
        revoked = _mk_config(
            "deepseek-auth-error", ["deepseek-v4-pro"], last_test_status="auth_error"
        )
        _bind(pid, c1, "deepseek-v4-pro")
        with pytest.raises(ValueError, match="最近连接失败"):
            _run_async(
                ai_client_mod.get_ai_client_for_novel(
                    pid, api_config_id=revoked, model="deepseek-v4-pro"
                )
            )

    def test_untested_config_still_allowed(self, client):
        """只拦失败态：未测试（untested/None）与 ok 照旧放行（与本书就绪判据同口径）。"""
        pid, _ = _create_project_and_chapter(client)
        c1 = _mk_config("deepseek-un", ["deepseek-v4-pro"])
        fresh = _mk_config(
            "deepseek-untested", ["deepseek-v4-flash"], last_test_status="untested"
        )
        _bind(pid, c1, "deepseek-v4-pro")
        got = _run_async(
            ai_client_mod.get_ai_client_for_novel(
                pid, api_config_id=fresh, model="deepseek-v4-flash"
            )
        )
        assert got.model == "deepseek-v4-flash"

    def test_half_pair_rejected(self, client):
        pid, _ = _create_project_and_chapter(client)
        c1 = _mk_config("deepseek-i", ["deepseek-v4-pro"])
        _bind(pid, c1, "deepseek-v4-pro")
        with pytest.raises(ValueError, match="不完整"):
            _run_async(ai_client_mod.get_ai_client_for_novel(pid, api_config_id=c1))
        with pytest.raises(ValueError, match="不完整"):
            _run_async(
                ai_client_mod.get_ai_client_for_novel(pid, model="deepseek-v4-pro")
            )


# ── 2. 端点：开流前校验 + 记账 -------------------------------------------------


class TestWriteEndpointOverride:
    def test_override_streams_and_records_override_pair(self, client, monkeypatch):
        _set_member()
        pid, ref = _create_project_and_chapter(client)
        c1 = _mk_config("deepseek-j", ["deepseek-v4-pro"])
        c2 = _mk_config("ollama-k", ["qwen2.5:14b"], vendor="ollama")
        _bind(pid, c1, "deepseek-v4-pro")
        fake = _FakeStreamClient(PROSE)
        captured = _patch_real_resolve_with_fake_stream(monkeypatch, fake)

        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/write",
            json={"api_config_id": c2, "model": "qwen2.5:14b"},
        )
        assert r.status_code == 200, r.text
        assert captured["model"] == "qwen2.5:14b"
        assert fake.calls and fake.calls[0]["model"] == "haiku"  # 符号别名位不变
        # 记账＝实际生效模型 + 覆盖配置；本书绑定不变
        usage = _last_usage(pid)
        assert usage is not None
        assert usage.model == "qwen2.5:14b"
        assert usage.api_config_id == c2
        assert _get_binding(pid) == (c1, "deepseek-v4-pro")

    def test_default_path_records_book_pair(self, client, monkeypatch):
        _set_member()
        pid, ref = _create_project_and_chapter(client)
        c1 = _mk_config("deepseek-l", ["deepseek-v4-pro", "deepseek-v4-flash"])
        _bind(pid, c1, "deepseek-v4-flash")
        fake = _FakeStreamClient(PROSE)
        captured = _patch_real_resolve_with_fake_stream(monkeypatch, fake)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write", json={})
        assert r.status_code == 200, r.text
        assert captured["model"] == "deepseek-v4-flash"
        usage = _last_usage(pid)
        assert usage is not None
        assert usage.model == "deepseek-v4-flash"
        assert usage.api_config_id == c1

    def test_invalid_override_rejected_before_stream(self, client, monkeypatch):
        _set_member()
        pid, ref = _create_project_and_chapter(client)
        c1 = _mk_config("deepseek-m", ["deepseek-v4-pro"])
        c2 = _mk_config("deepseek-n", ["deepseek-v4-flash"])
        _bind(pid, c1, "deepseek-v4-pro")
        fake = _FakeStreamClient(PROSE)
        _patch_real_resolve_with_fake_stream(monkeypatch, fake)

        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/write",
            json={"api_config_id": c2, "model": "deepseek-v4-pro"},  # 不在 c2 清单
        )
        assert r.status_code == 400, r.text
        assert "模型清单" in r.text
        assert "data:" not in r.text  # 无 SSE
        assert fake.calls == []  # 未发起模型调用
        assert _last_usage(pid) is None  # 未记账（调用未发生）
        assert _get_binding(pid) == (c1, "deepseek-v4-pro")

        # 半对同样拦在开流前
        r2 = client.post(
            f"/api/novels/{pid}/chapters/{ref}/write", json={"api_config_id": c2}
        )
        assert r2.status_code == 400, r2.text
        assert fake.calls == []

        # 评审 P3：最近连接失败的配置（Key 已吊销）同样挡在开流前
        dead = _mk_config("deepseek-broken", ["deepseek-v4-pro"], last_test_status="auth_error")
        r3 = client.post(
            f"/api/novels/{pid}/chapters/{ref}/write",
            json={"api_config_id": dead, "model": "deepseek-v4-pro"},
        )
        assert r3.status_code == 400, r3.text
        assert "最近连接失败" in r3.text
        assert fake.calls == []

    def test_failure_path_records_real_override_model(self, client, monkeypatch):
        _set_member()
        pid, ref = _create_project_and_chapter(client)
        c1 = _mk_config("deepseek-o", ["deepseek-v4-pro"])
        c2 = _mk_config("deepseek-p", ["deepseek-v4-flash"])
        _bind(pid, c1, "deepseek-v4-pro")

        class _BoomClient:
            async def chat_stream(self, **kwargs):
                raise RuntimeError("上游挂了")
                yield  # pragma: no cover — 生成器形状

        _patch_real_resolve_with_fake_stream(monkeypatch, _BoomClient())  # type: ignore[arg-type]

        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/write",
            json={"api_config_id": c2, "model": "deepseek-v4-flash"},
        )
        assert r.status_code == 200, r.text  # 流内错误以 error 事件表达
        assert '"type": "error"' in r.text
        usage = _last_usage(pid, "write_chapter_fail")
        assert usage is not None
        assert usage.model == "deepseek-v4-flash"
        assert usage.api_config_id == c2
