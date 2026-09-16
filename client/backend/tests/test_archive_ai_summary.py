"""批次四 — 归档 AI 摘要的开关与会员门控（体验三件之一）

矩阵（ai_summary 参数 × 会员态）：
- 会员 + 默认（不传 ai_summary）→ 调用 AI 生成摘要
- 会员 + ai_summary=False（设置里关掉）→ 不调用 AI，降级为正文前 200 字
- 免费用户 + 默认 → 不调用 AI（AI 是会员权益，后端直接降级）

用法：
    cd client/backend
    python -m pytest tests/test_archive_ai_summary.py -v
"""

import asyncio
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB) ───────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_archive_ai_summary.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_archive_ai_summary_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")


def _set_tier(tier: str, expires_at: str = ""):
    _service.CONFIG_FILE = _CFG_PATH
    _service.save_local_config({"tier": tier, "expires_at": expires_at, "api_key": ""})


def _future_iso(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


import archive.service as archive_service
from auth_local.deps import require_novel_model, require_project_limit
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
    _run_async(_create_user("archai"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "archai"}


async def _override_true():
    return True


@pytest.fixture(autouse=True)
def _setup_overrides():
    # 不覆盖 require_ai_access（归档端点本就免费可用）；配额与会员态走真实 check_permission
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    # 本书模型门控：本模块测的是内容/其他门控，模型就绪另测（9.2）
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = _override_true
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


def _create_sparse_project(client) -> str:
    name = f"archai-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), f"Create failed: {r.text}"
    return r.json()["id"]


def _create_volume_and_chapter(client, pid: str) -> str:
    r = client.post(
        f"/api/novels/{pid}/volumes", json={"vol_num": 1, "title": "Volume 1"}
    )
    assert r.status_code in (200, 201)
    r2 = client.post(
        f"/api/novels/{pid}/volumes/{r.json()['ref']}/chapters",
        json={"title": "第1章"},
    )
    assert r2.status_code in (200, 201)
    return r2.json()["chapter_ref"]


LONG_TEXT = "（归档正文）灯火在雨里摇晃，她合上日志，决定明日启程。行囊里只有半册旧书，与一枚磨亮的铜哨。" * 20

AI_SUMMARY = "（AI 摘要）她合上日志决定明日启程。"


class _FakeAIClient:
    def __init__(self, calls: list):
        self._calls = calls

    async def chat(self, **kwargs):
        self._calls.append("chat")
        usage = kwargs.get("usage")
        if usage is not None:
            # 贴真客户端契约：成功调用回填 provider usage（记账数据源）
            usage["tokens_in"] = 30
            usage["tokens_out"] = 12
        return AI_SUMMARY


class TestArchiveAiSummary:
    def test_member_default_calls_ai(self, client, monkeypatch):
        # 会员 + 不传 ai_summary（默认 True）→ AI 被调用，摘要取 AI 结果
        _set_tier("monthly", _future_iso())
        calls: list = []

        async def _fake_get_ai_client(novel_id=None):
            return _FakeAIClient(calls)

        monkeypatch.setattr(archive_service, "get_ai_client_for_novel", _fake_get_ai_client)

        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive", json={"full_text": LONG_TEXT}
        )
        assert r.status_code == 200, r.text
        assert calls == ["chat", "chat"], (
            "member + default calls AI twice：归档摘要 + 世界 lore 建议（world-setting-v2 D11 解耦）"
        )
        assert r.json()["summary"] == AI_SUMMARY

    def test_member_opt_out_skips_ai(self, client, monkeypatch):
        # 会员 + ai_summary=False（设置里关掉）→ 不调 AI，降级为正文前 200 字
        _set_tier("monthly", _future_iso())
        calls: list = []

        async def _fake_get_ai_client(novel_id=None):
            return _FakeAIClient(calls)

        monkeypatch.setattr(archive_service, "get_ai_client_for_novel", _fake_get_ai_client)

        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive",
            json={"full_text": LONG_TEXT, "ai_summary": False},
        )
        assert r.status_code == 200, r.text
        assert calls == ["chat"], (
            "member + ai_summary=False 仍跑 lore 建议（D11：两开关解耦），仅跳过摘要"
        )
        assert r.json()["summary"] == LONG_TEXT[:200]

    def test_ai_calls_record_usage(self, client, monkeypatch):
        # ai-client capability 需求 2：归档链两处 AI 调用成功后各落一行账
        _set_tier("monthly", _future_iso())
        calls: list = []

        async def _fake_get_ai_client(novel_id=None):
            return _FakeAIClient(calls)

        monkeypatch.setattr(archive_service, "get_ai_client_for_novel", _fake_get_ai_client)

        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive", json={"full_text": LONG_TEXT}
        )
        assert r.status_code == 200, r.text

        from sqlalchemy import select

        from models.token_log import TokenLog

        async def _ops():
            async with async_session() as session:
                rows = await session.execute(
                    select(TokenLog).where(TokenLog.project_id == pid)
                )
                return [(row.operation, row.tokens_in, row.tokens_out) for row in rows.scalars()]

        assert _run_async(_ops()) == [
            ("archive_summary", 30, 12),
            ("archive_lore", 30, 12),
        ]

    def test_ai_failure_records_fail_rows(self, client, monkeypatch):
        # 调用失败走静默降级（归档不拦）但必须落 _fail 行（force 零 token）
        _set_tier("monthly", _future_iso())

        class _BoomClient:
            async def chat(self, **_kwargs):
                raise RuntimeError("供应商 5xx")

        async def _fake_get_ai_client(novel_id=None):
            return _BoomClient()

        monkeypatch.setattr(archive_service, "get_ai_client_for_novel", _fake_get_ai_client)

        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive", json={"full_text": LONG_TEXT}
        )
        assert r.status_code == 200, r.text  # 静默降级：归档照常成功
        assert r.json()["summary"] == LONG_TEXT[:200]

        from sqlalchemy import select

        from models.token_log import TokenLog

        async def _ops():
            async with async_session() as session:
                rows = await session.execute(
                    select(TokenLog).where(TokenLog.project_id == pid)
                )
                return [(row.operation, row.tokens_in, row.tokens_out) for row in rows.scalars()]

        assert _run_async(_ops()) == [
            ("archive_summary_fail", 0, 0),
            ("archive_lore_fail", 0, 0),
        ]

    def test_free_default_skips_ai(self, client, monkeypatch):
        # 免费用户 + 默认 → AI 是会员权益，后端直接降级（get_ai_client 不该被触达）
        _set_tier("none")
        calls: list = []

        async def _fake_get_ai_client(novel_id=None):
            return _FakeAIClient(calls)

        monkeypatch.setattr(archive_service, "get_ai_client_for_novel", _fake_get_ai_client)

        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive", json={"full_text": LONG_TEXT}
        )
        assert r.status_code == 200, r.text
        assert calls == [], "free tier must not call AI even with ai_summary default"
        assert r.json()["summary"] == LONG_TEXT[:200]
