"""软删作品不可再打开（2026-10-23 用户拍板）。

删除作品＝软删（`status="deleted"`，行与数据保留），但所有读取/编辑入口 SHALL 一律 404：
详情、树、设定、卷章、角色、伏笔、文风影子、改名/设定写入；列表与按 slug 查询不可见；
删除本身保持幂等（重复删除仍 200，供双击/多窗口兜底）。

Usage:
    cd client/backend
    python -m pytest tests/test_novel_soft_delete.py -v
"""

import asyncio
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_soft_delete.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_soft_delete_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from auth_local.deps import (  # noqa: E402
    require_ai_access,
    require_novel_model,
    require_project_limit,
)
from auth_local.middleware import get_current_user  # noqa: E402
from db import Base, async_session, engine, get_db  # noqa: E402
from main import app  # noqa: E402
from models.user import User  # noqa: E402

_UID = f"softdel-{uuid.uuid4().hex[:8]}"


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _bootstrap():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        session.add(
            User(
                id=_UID,
                email=f"{_UID}@test.local",
                password_hash="*",
                display_name="软删测试",
            )
        )
        await session.commit()


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    _run_async(_bootstrap())
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": _UID}


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_ai_access] = lambda: True
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = lambda: True
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _create_project(client, *, with_chapter: bool = False) -> tuple[dict, str]:
    name = f"软删书-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name, "source": "manual"})
    assert r.status_code in (200, 201), r.text
    project = r.json()
    pid = project["id"]
    if not with_chapter:
        return project, ""
    rv = client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷"})
    assert rv.status_code in (200, 201), rv.text
    vol_ref = rv.json()["ref"]
    rc = client.post(
        f"/api/novels/{pid}/volumes/{vol_ref}/chapters", json={"title": "第1章"}
    )
    assert rc.status_code in (200, 201), rc.text
    return project, rc.json()["chapter_ref"]


def test_soft_deleted_novel_rejects_every_read_and_write(client):
    project, ch_ref = _create_project(client, with_chapter=True)
    pid = project["id"]

    # 删前一切正常，并留一条伏笔供 hooks 可读
    assert client.get(f"/api/novels/{pid}").status_code == 200
    rh = client.post(f"/api/novels/{pid}/hooks", json={"description": "神秘罗盘"})
    assert rh.status_code == 200, rh.text
    assert client.get(f"/api/novels/{pid}/hooks").status_code == 200

    assert client.delete(f"/api/novels/{pid}").status_code == 200

    # 打开/读取入口：全部 404（不是返回已删数据）
    for path in (
        f"/api/novels/{pid}",
        f"/api/novels/{pid}/tree",
        f"/api/novels/{pid}/settings/world",
        f"/api/novels/{pid}/volumes",
        f"/api/novels/{pid}/chapters/{ch_ref}",
        f"/api/novels/{pid}/chapters/{ch_ref}/style-shadow/baseline",
        f"/api/novels/{pid}/chapters/{ch_ref}/dossier",
        f"/api/novels/{pid}/chapters/{ch_ref}/reconcile",
        f"/api/novels/{pid}/dossier/preview",
        f"/api/novels/{pid}/characters",
        f"/api/novels/{pid}/hooks",
    ):
        assert client.get(path).status_code == 404, path

    # 写入入口同样 404
    assert client.patch(f"/api/novels/{pid}", json={"name": "改名"}).status_code == 404
    assert client.put(f"/api/novels/{pid}/story", json={"synopsis": "x"}).status_code == 404
    assert client.post(
        f"/api/novels/{pid}/hooks", json={"description": "第二条"}
    ).status_code == 404

    # 列表与 slug 查询不可见
    assert all(p["id"] != pid for p in client.get("/api/novels").json())
    assert client.get(f"/api/novels/by-slug/{project['slug']}").status_code == 404

    # 删除幂等：重复删除仍 200（双击/多窗口不产生报错）
    assert client.delete(f"/api/novels/{pid}").status_code == 200


def test_soft_deleted_novel_still_holds_data_but_no_endpoint_touches_it(client):
    """软删只封入口不删数据：行仍在库（数据可回），但没有端点能读到。"""
    project, _ = _create_project(client)
    pid = project["id"]
    assert client.delete(f"/api/novels/{pid}").status_code == 200

    async def _row():
        async with async_session() as session:
            from models.project import Novel

            return await session.get(Novel, pid)

    row = _run_async(_row())
    assert row is not None and row.status == "deleted"
    assert client.get(f"/api/novels/{pid}").status_code == 404
