"""
Tests for novel rename (PATCH /api/novels/{id}) and story synopsis endpoints
(GET/PUT /api/novels/{id}/story).

Isolated TestClient with dependency overrides — no running server needed.
Usage:
    cd client/backend
    python -m pytest tests/test_novel_rename_story.py -v
"""

import asyncio
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_rename.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_rename_story_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
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
    _run_async(_create_user("rnuser"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "rnuser"}


@pytest.fixture(autouse=True)
def _setup_overrides():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_ai_access] = lambda: True
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = lambda: True
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _create_project(client) -> str:
    name = f"rn-test-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), f"Create project failed: {r.text}"
    return r.json()["id"]


# ── PATCH /api/novels/{id} — rename ────────────────────────────────────────


class TestRename:
    def test_rename_ok_name_changes_slug_stays(self, client):
        pid = _create_project(client)
        before = client.get(f"/api/novels/{pid}").json()
        r = client.patch(f"/api/novels/{pid}", json={"name": "新书名"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "新书名"
        assert data["id"] == before["id"]
        assert data["slug"] == before["slug"]  # slug 不变（root_path 跟随 slug）

        # GET 返回新名
        after = client.get(f"/api/novels/{pid}").json()
        assert after["name"] == "新书名"

    def test_rename_empty_name_422(self, client):
        pid = _create_project(client)
        r = client.patch(f"/api/novels/{pid}", json={"name": "   "})
        assert r.status_code == 422

    def test_rename_same_name_idempotent(self, client):
        pid = _create_project(client)
        name = client.get(f"/api/novels/{pid}").json()["name"]
        r = client.patch(f"/api/novels/{pid}", json={"name": name})
        assert r.status_code == 200

    def test_rename_not_found_404(self, client):
        r = client.patch("/api/novels/no-such-id", json={"name": "X"})
        assert r.status_code == 404


# ── GET/PUT /api/novels/{id}/story — synopsis backfill ────────────────────


class TestStory:
    def test_story_empty_by_default(self, client):
        pid = _create_project(client)
        r = client.get(f"/api/novels/{pid}/story")
        assert r.status_code == 200
        assert r.json()["synopsis"] == ""

    def test_story_write_and_read_back(self, client):
        pid = _create_project(client)
        synopsis = "一个农村少年意外获得操控植物的能力，守护家乡稻田的故事"
        r = client.put(
            f"/api/novels/{pid}/story", json={"synopsis": synopsis}
        )
        assert r.status_code == 200, r.text
        assert r.json()["synopsis"] == synopsis

        read = client.get(f"/api/novels/{pid}/story").json()
        assert read["synopsis"] == synopsis

    def test_story_write_empty_string(self, client):
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "  清空  "})
        r = client.put(f"/api/novels/{pid}/story", json={"synopsis": ""})
        assert r.status_code == 200
        assert client.get(f"/api/novels/{pid}/story").json()["synopsis"] == ""

    def test_story_not_found_404(self, client):
        assert client.get("/api/novels/no-such-id/story").status_code == 404
        assert (
            client.put("/api/novels/no-such-id/story", json={"synopsis": "x"}).status_code
            == 404
        )
