"""
Tests for GET /api/novels list enrichment (PR 1 设计 v2 书架卡片)：
  word_count — 章表 word_count 聚合
  synopsis / genre — story.yaml（创建时 genre 展示名写入；导入路径同字段）

Isolated TestClient with dependency overrides — no running server needed.
Usage:
    cd client/backend
    python -m pytest tests/test_novel_list_enrichment.py -v
"""

import asyncio
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_listrich.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_list_rich_")

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
    _run_async(_create_user("lruser"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "lruser"}


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


def _create_project(client, **extra) -> dict:
    name = f"lr-test-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name, "source": "manual", **extra})
    assert r.status_code in (200, 201), f"Create project failed: {r.text}"
    return r.json()


class TestListEnrichment:
    def test_create_with_genre_lands_in_story_yaml(self, client):
        created = _create_project(client, genre="科幻", synopsis="星港旧梦")
        assert created["id"]

        rows = client.get("/api/novels").json()
        row = next(r for r in rows if r["id"] == created["id"])
        assert row["genre"] == "科幻"
        assert row["synopsis"] == "星港旧梦"
        assert row["word_count"] == 0

    def test_create_without_genre_degrades_gracefully(self, client):
        created = _create_project(client)
        rows = client.get("/api/novels").json()
        row = next(r for r in rows if r["id"] == created["id"])
        assert row["genre"] is None
        assert row["synopsis"] == ""

    def test_word_count_sums_chapters(self, client):
        created = _create_project(client)
        pid = created["id"]
        base = f"/api/novels/{pid}"

        rv = client.post(f"{base}/volumes", json={"title": "第一卷"})
        assert rv.status_code in (200, 201), rv.text
        vol_ref = rv.json()["ref"]

        refs = []
        for i in (1, 2):
            rc = client.post(
                f"{base}/volumes/{vol_ref}/chapters", json={"title": f"第{i}章"}
            )
            assert rc.status_code in (200, 201), rc.text
            refs.append(rc.json()["chapter_ref"])

        # 两章各写一段正文（统一写入口派生 word_count）
        texts = ["明月出天山。", "苍茫云海间，长风几万里。"]
        for ref, text in zip(refs, texts):
            rp = client.put(f"{base}/chapters/{ref}/prose", json={"prose": text})
            assert rp.status_code == 200, rp.text

        rows = client.get("/api/novels").json()
        row = next(r for r in rows if r["id"] == pid)
        assert row["total_chapters"] == 2
        # 列表 word_count = 章表求和；正文非空后必须 > 0
        assert isinstance(row["word_count"], int) and row["word_count"] > 0
