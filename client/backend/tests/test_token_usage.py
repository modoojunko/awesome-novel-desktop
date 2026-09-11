"""TokenLog 用量记录接线测试 — AI 端点调用后用量统计非零。

断言走公开 API（usage-summary / projects usage），即真实验收口径：
跑一次 AI 后用量统计返回非零 token。
"""

import asyncio
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB) ───────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_token_usage.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_token_usage_")

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + _tmp_db.name
os.environ["DATA_ROOT"] = _tmp_data_root

from auth_local.deps import (
    require_ai_access,
    require_novel_model,
    require_project_limit,
)
from auth_local.middleware import get_current_user
from db import Base, async_session, engine, get_db
from main import app
from models.user import User


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
                email=user_id + "@test.com",
                password_hash="*",
                display_name=user_id,
            )
        )
        await session.commit()
    return user_id


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    _run_async(_create_tables())
    _run_async(_create_user("usage-user"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "usage-user"}


async def _override_true():
    return True


@pytest.fixture(autouse=True)
def _setup_overrides():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_ai_access] = _override_true
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = _override_true
    yield
    app.dependency_overrides.clear()


class _FakeAIClient:
    """chat 填充 usage dict 并返回合法 JSON，模拟真实 provider usage 回传。"""

    model = "fake-model"

    def __init__(self, tokens_in: int = 10, tokens_out: int = 20):
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out

    async def chat(self, model, system, messages, max_tokens=1024, usage=None, **kwargs):
        if usage is not None:
            usage["tokens_in"] = self.tokens_in
            usage["tokens_out"] = self.tokens_out
        return '{"title": "测试书名", "synopsis": "一段简介", "genre": "都市言情", "value": "一段话世界设定"}'

    async def chat_stream(self, model, system, messages, max_tokens=4096, **kwargs):
        yield type("E", (), {"text": "", "is_done": True, "tokens": 0, "error": ""})()


@pytest.fixture
def client(monkeypatch):
    async def _fake_get_client(novel_id=None):
        return _FakeAIClient()

    # 建书期 suggest-meta 走豁免路径（仍用 get_ai_client）；题材字段走本书模型
    monkeypatch.setattr("novels.router.get_ai_client", _fake_get_client)
    monkeypatch.setattr("settings.ai_router.get_ai_client_for_novel", _fake_get_client)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project_id(client) -> str:
    name = "用量测试" + uuid.uuid4().hex[:6]
    resp = client.post("/api/novels", json={"name": name, "source": "manual"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _global_usage(client) -> int:
    resp = client.get("/api/v1/api-configs/usage-summary")
    assert resp.status_code == 200, resp.text
    return resp.json().get("total_all_time", 0)


def test_suggest_meta_records_token_usage(client, project_id):
    """suggest-meta 调用后全局用量统计非零。"""
    assert _global_usage(client) == 0
    resp = client.post("/api/ai/suggest-meta", json={"premise": "一个少年穿越到修仙世界"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "测试书名"
    assert _global_usage(client) > 0


def test_settings_field_generation_records_usage(client, project_id):
    """设定单字段生成后项目级用量统计非零。"""
    client.put("/api/novels/" + project_id + "/story", json={"synopsis": "测试前提"})
    resp = client.post(
        "/api/novels/" + project_id + "/settings/ai/world/draft",
        json={"topic": "力量体系"},
    )
    assert resp.status_code == 200, resp.text
    usage_resp = client.get("/api/v1/novels/" + project_id + "/usage")
    assert usage_resp.status_code == 200, usage_resp.text
    assert usage_resp.json().get("total_tokens", 0) > 0


def test_record_usage_skips_zero_tokens(client, project_id):
    """零 token 调用不落库（用量统计不变化，避免噪音）。"""
    from api_configs.usage import record_usage

    async def _call():
        async with async_session() as session:
            await record_usage(
                session,
                user_id="usage-user",
                project_id=project_id,
                operation="noop",
                tokens_in=0,
                tokens_out=0,
            )

    before = _global_usage(client)
    _run_async(_call())
    assert _global_usage(client) == before
