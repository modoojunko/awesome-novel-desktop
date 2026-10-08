"""c-silent-data-guards — GET /prompt-summary 批量端点契约（提示词总览 N+1 收口）

矩阵：
- 一次返回全书各章 has_stored；无提示词时全 False，PUT write 后仅该章翻 True
- 不存在的项目 404

用法：
    cd client/backend
    python -m pytest tests/test_prompt_summary_batch.py -v
"""

import asyncio
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_psum.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_prompt_summary_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service  # noqa: E402
from auth_local.deps import (  # noqa: E402
    require_novel_model,
    require_project_limit,
    require_tier_access,
)
from auth_local.middleware import get_current_user  # noqa: E402
from db import Base, async_session, engine, get_db  # noqa: E402
from main import app  # noqa: E402
from models.user import User  # noqa: E402

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")

USER_ID = "psum_user"


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


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    _run_async(_create_tables())

    async def _create_user():
        async with async_session() as session:
            session.add(
                User(
                    id=USER_ID,
                    email=f"{USER_ID}@test.com",
                    password_hash="*",
                    display_name=USER_ID,
                )
            )
            await session.commit()

    _run_async(_create_user())
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": USER_ID}


async def _override_true():
    return True


@pytest.fixture(autouse=True)
def _setup_overrides():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = _override_true
    # 批量端点与章级 /prompts 同挂登录＋档位门（看/改不依赖写作大模型 Key，2026-10-08）
    app.dependency_overrides[require_tier_access] = _override_true
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_config_after():
    yield
    _service.CONFIG_FILE = _CFG_PATH
    if os.path.exists(_CFG_PATH):
        os.remove(_CFG_PATH)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _create_project_with_two_chapters(client) -> tuple[str, str, str]:
    name = f"psum-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    r = client.post(f"/api/novels/{pid}/volumes", json={"vol_num": 1, "title": "第一卷"})
    assert r.status_code in (200, 201), r.text
    r1 = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第1章"})
    r2 = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第2章"})
    assert r1.status_code in (200, 201) and r2.status_code in (200, 201)
    return pid, r1.json()["chapter_ref"], r2.json()["chapter_ref"]


def test_summary_all_false_then_true_after_write(client):
    pid, ref1, ref2 = _create_project_with_two_chapters(client)

    r = client.get(f"/api/novels/{pid}/prompt-summary")
    assert r.status_code == 200, r.text
    data = {c["ref"]: c["has_stored"] for c in r.json()["chapters"]}
    assert data[ref1] is False and data[ref2] is False

    r = client.put(
        f"/api/novels/{pid}/chapters/{ref1}/prompts/write",
        json={"content": "## 任务指示\n测试提示词"},
    )
    assert r.status_code in (200, 201, 204), r.text

    data = {
        c["ref"]: c["has_stored"]
        for c in client.get(f"/api/novels/{pid}/prompt-summary").json()["chapters"]
    }
    assert data[ref1] is True and data[ref2] is False


def test_summary_project_404(client):
    assert client.get("/api/novels/nope/prompt-summary").status_code == 404
