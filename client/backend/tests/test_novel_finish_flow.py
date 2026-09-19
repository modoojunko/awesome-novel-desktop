"""
Tests for POST /api/novels/{id}/finish · /reopen（works-finish-flow 完本链路）：
  finish  — 守卫（未完结 + 主线章数>0 + 主线归档数==主线章数），写入 finished_at
  reopen  — 守卫（已完结），清空 finished_at
  list    — finished_at 下发

Isolated TestClient with dependency overrides — no running server needed.
Usage:
    cd client/backend
    python -m pytest tests/test_novel_finish_flow.py -v
"""

import asyncio
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_finish.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_finish_")

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
    _run_async(_create_user("finuser"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "finuser"}


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
    name = f"fin-test-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name, "source": "manual", **extra})
    assert r.status_code in (200, 201), f"Create project failed: {r.text}"
    return r.json()


def _archived_mainline_chapter(client, pid: str, title: str, text: str) -> str:
    """建一章＋写正文＋归档，返回章 ref（≥100 字过归档门禁）。"""
    base = f"/api/novels/{pid}"
    if not getattr(_archived_mainline_chapter, "_vol", {}).get(pid):
        rv = client.post(f"{base}/volumes", json={"title": "第一卷"})
        assert rv.status_code in (200, 201), rv.text
        _archived_mainline_chapter._vol[pid] = rv.json()["ref"]
    vol_ref = _archived_mainline_chapter._vol[pid]
    rc = client.post(f"{base}/volumes/{vol_ref}/chapters", json={"title": title})
    assert rc.status_code in (200, 201), rc.text
    ref = rc.json()["chapter_ref"]
    rp = client.put(f"{base}/chapters/{ref}/prose", json={"prose": text})
    assert rp.status_code == 200, rp.text
    ra = client.post(f"{base}/chapters/{ref}/archive", json={"full_text": text})
    assert ra.status_code in (200, 201), ra.text
    return ref


_archived_mainline_chapter._vol = {}  # type: ignore[attr-defined]


def _row(client, pid: str) -> dict:
    return next(r for r in client.get("/api/novels").json() if r["id"] == pid)


class TestFinishFlow:
    def test_finish_blocked_when_mainline_not_all_archived(self, client):
        created = _create_project(client)
        pid = created["id"]
        _archived_mainline_chapter(client, pid, "第1章", "明月出天山，苍茫云海间。" * 20)
        # 第 2 章有正文但未归档（排队门禁：第 1 章归档后才可写）
        base = f"/api/novels/{pid}"
        vol_ref = _archived_mainline_chapter._vol[pid]
        rc = client.post(f"{base}/volumes/{vol_ref}/chapters", json={"title": "第2章"})
        ref2 = rc.json()["chapter_ref"]
        client.put(
            f"{base}/chapters/{ref2}/prose", json={"prose": "苍茫云海间。" * 10}
        )

        r = client.post(f"/api/novels/{pid}/finish")
        assert r.status_code == 409, r.text
        assert _row(client, pid)["finished_at"] is None

    def test_finish_blocked_on_empty_book(self, client):
        created = _create_project(client)
        r = client.post(f"/api/novels/{created['id']}/finish")
        assert r.status_code == 409, r.text

    def test_finish_success_then_repeat_409(self, client):
        created = _create_project(client)
        pid = created["id"]
        _archived_mainline_chapter(client, pid, "第1章", "明月出天山，苍茫云海间。" * 20)

        r = client.post(f"/api/novels/{pid}/finish")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["finished_at"], "响应应带完结时间戳"

        row = _row(client, pid)
        assert row["finished_at"] == body["finished_at"]
        # detail 端点同字段
        detail = client.get(f"/api/novels/{pid}").json()
        assert detail["finished_at"] == body["finished_at"]

        r2 = client.post(f"/api/novels/{pid}/finish")
        assert r2.status_code == 409, r2.text

    def test_reopen_clears_finished_at_then_409(self, client):
        created = _create_project(client)
        pid = created["id"]
        _archived_mainline_chapter(client, pid, "第1章", "明月出天山，苍茫云海间。" * 20)
        assert client.post(f"/api/novels/{pid}/finish").status_code == 200

        r = client.post(f"/api/novels/{pid}/reopen")
        assert r.status_code == 200, r.text
        assert r.json()["finished_at"] is None
        assert _row(client, pid)["finished_at"] is None

        # 未完结再撤 → 409
        r2 = client.post(f"/api/novels/{pid}/reopen")
        assert r2.status_code == 409, r2.text

    def test_ghost_chapter_does_not_block_finish(self, client):
        """主线口径：回退转入旧稿支线的章不计入主线——只剩一条已归档主线章
        时应可完本（与书架「待完本」判据同源，不得劈叉）。"""
        created = _create_project(client)
        pid = created["id"]
        base = f"/api/novels/{pid}"
        ref1 = _archived_mainline_chapter(
            client, pid, "第1章", "明月出天山，苍茫云海间，长风几万里。" * 8
        )
        vol_ref = _archived_mainline_chapter._vol[pid]
        rc = client.post(f"{base}/volumes/{vol_ref}/chapters", json={"title": "第2章"})
        ref2 = rc.json()["chapter_ref"]
        client.put(f"{base}/chapters/{ref2}/prose", json={"prose": "苍茫云海间。" * 10})
        # 回退：第 2 章转入旧稿支线（ghost）
        rr = client.post(f"{base}/chapters/{ref1}/revert")
        assert rr.status_code in (200, 201), rr.text

        r = client.post(f"/api/novels/{pid}/finish")
        assert r.status_code == 200, f"ghost 章不应挡完本: {r.text}"
        assert _row(client, pid)["finished_at"]
