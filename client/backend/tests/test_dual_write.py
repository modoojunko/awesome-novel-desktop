"""Change 006 — 写路径一致性测试（TE-10；PR② 章族入库后 DB 唯一属主）

验证：save_chapter/save_prose 后 DB 元数据与正文一致（chapter_contents.prose）；
章 YAML 不再落盘；save_prose 缺章 404；versions 列表/回滚走 chapter_versions 表；
confirm 写 DB confirmed 态；delete_chapter 删 DB 行 + 计数维护（HTTP 层）。

用法：
    cd client/backend
    python -m pytest tests/test_dual_write.py -v
"""

import asyncio
import os
import tempfile
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_dual.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_dual_write_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from auth_local.deps import require_project_limit
from auth_local.middleware import get_current_user
from db import Base, async_session, engine, get_db
from filesystem.storage import LocalFileBackend
from main import app
from models import Novel
from models.user import User
from novels.service import count_chars
from repositories import chapter_repo, volume_repo

USER_ID = "dw_user"
storage = LocalFileBackend()

import auth_local.service as _auth_service

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")


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
    _run_async(_create_user(USER_ID))
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
    app.dependency_overrides[require_project_limit] = _override_true
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _free_tier():
    """免费套餐：gate 旁路，confirm 稀疏章可过（本模块聚焦双写而非 gate）。"""
    _auth_service.CONFIG_FILE = _CFG_PATH
    _auth_service.save_local_config(
        {"tier": "none", "expires_at": "", "api_key": ""}
    )
    yield
    if os.path.exists(_CFG_PATH):
        os.remove(_CFG_PATH)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


async def _new_project(name: str) -> Novel:
    root = os.path.join(_tmp_data_root, name)
    os.makedirs(os.path.join(root, "volumes"), exist_ok=True)
    os.makedirs(os.path.join(root, "chapters"), exist_ok=True)
    project = Novel(
        user_id=USER_ID, name=name, slug=name, root_path=root,
        source="manual", current_phase="settings",
    )
    async with async_session() as session:
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project


# ── TE-10 双写一致性 ─────────────────────────────────────────────────────


def test_save_chapter_updates_db_metadata():
    async def _run():
        project = await _new_project("sc1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            await _create_volume(session, proj)
            await _create_chapter(session, proj)
            await _save_chapter(
                session, proj, "vol-1-ch-1",
                {"volume": 1, "chapter": 1, "title": "第一章",
                 "outline": {"summary": "本章概要"}, "prose": "你好 世界",
                 "status": "draft"},
            )
            row = await chapter_repo.get_by_ref(session, proj.id, "vol-1-ch-1")
            assert row.word_count == 4  # count_chars：你好世界
            assert row.has_prose is True
            assert row.outline_status == "in_progress"  # prose 非空 → in_progress
            assert row.title == "第一章"

    _run_async(_run())


def test_save_prose_db_authoritative():
    async def _run():
        project = await _new_project("sp1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            await _create_volume(session, proj)
            await _create_chapter(session, proj)
            await _save_prose(session, proj, "vol-1-ch-1", "灯火在雨里摇晃")
            # DB 为内容准：正文入 chapter_contents.prose
            row = await chapter_repo.get_by_ref(session, proj.id, "vol-1-ch-1")
            assert row.content is not None
            assert row.content.prose == "灯火在雨里摇晃"
            assert row.word_count == count_chars("灯火在雨里摇晃") == 7
            # 章 YAML 不再落盘（章族 DB 唯一属主）
            data = await storage.read_yaml(
                proj.root_path, "chapters/vol-1-ch-1.yaml"
            )
            assert data == {}

    _run_async(_run())


def test_save_prose_missing_chapter_404():
    async def _run():
        from fastapi import HTTPException

        project = await _new_project("df1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            await _create_volume(session, proj)
            # 章行不存在 → 统一写入口前置校验 404（不再有 YAML 自愈降级）
            from chapters.service import save_prose

            with pytest.raises(HTTPException) as exc_info:
                await save_prose(session, proj, "vol-1-ch-1", "孤身走暗巷")
            assert exc_info.value.status_code == 404

    _run_async(_run())


# ── HTTP 层：confirm / versions restore / delete ──────────────────────────


def _create_project_with_volume(client) -> str:
    name = f"dw-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    # 空设定即可（免费旁路 gate），先推进 phase：write world 使 settings→outline 合法
    client.put(
        f"/api/novels/{pid}/settings/world",
        json={"geography": {"scenes": "g"}, "politics": {}, "rules": {}},
    )
    r2 = client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷"})
    assert r2.status_code in (200, 201), r2.text
    assert r2.json()["ref"] == "vol-1"
    r3 = client.post(
        f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第一章"}
    )
    assert r3.status_code in (200, 201), r3.text
    return pid


def test_confirm_writes_db_status_and_meta(client):
    pid = _create_project_with_volume(client)
    r = client.post(f"/api/novels/{pid}/chapters/vol-1-ch-1/confirm")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed"
    # DB confirmed 态
    async def _check():
        async with async_session() as session:
            row = await chapter_repo.get_by_ref(session, pid, "vol-1-ch-1")
            assert row is not None
            assert row.status == "confirmed"
            assert row.outline_status == "confirmed"
            assert row.confirmed_at is not None
            assert row.confirmed_at <= datetime.now(UTC).replace(tzinfo=None)
            # 卷 YAML 不再落盘（卷族 DB 唯一属主）
            data = await storage.read_yaml(
                (await session.get(Novel, pid)).root_path, "volumes/vol-1.yaml"
            )
            assert data == {}

    _run_async(_check())


def test_restore_refreshes_db_meta(client):
    pid = _create_project_with_volume(client)
    # 先写长正文 → word_count=7
    r = client.put(
        f"/api/novels/{pid}/chapters/vol-1-ch-1/prose",
        json={"prose": "灯火在雨里摇晃"},
    )
    assert r.status_code == 200, r.text
    # 生成版本快照（engine.save_chapter 内容变化时快照）
    r2 = client.get(f"/api/novels/{pid}/chapters/vol-1-ch-1/versions")
    assert r2.status_code == 200, r2.text
    assert len(r2.json()) >= 1, "prose 变化应生成版本快照"

    # 覆写短正文 → word_count 变小，DB 同步
    client.put(
        f"/api/novels/{pid}/chapters/vol-1-ch-1/prose",
        json={"prose": "短"},
    )
    # 恢复第一版 → DB word_count 应回到恢复后的正文
    first = r2.json()[0]
    vid = first["version"]
    r3 = client.post(
        f"/api/novels/{pid}/chapters/vol-1-ch-1/versions/{vid}/restore"
    )
    assert r3.status_code == 200, r3.text

    async def _check():
        async with async_session() as session:
            row = await chapter_repo.get_by_ref(session, pid, "vol-1-ch-1")
            assert row is not None
            assert row.word_count == 7  # 「灯火在雨里摇晃」7 字（count_chars）
            assert row.has_prose is True

    _run_async(_check())


def test_delete_chapter_db_row_and_counts(client):
    pid = _create_project_with_volume(client)
    # 加第二章（MAX+1 → vol-1-ch-2）
    r = client.post(
        f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第二章"}
    )
    assert r.status_code in (200, 201), r.text
    assert r.json()["ref"] == "vol-1-ch-2"

    async def _before():
        async with async_session() as session:
            proj = await session.get(Novel, pid)
            return proj.total_chapters

    assert _run_async(_before()) == 2

    # c-chapter-plan-ai 守卫：非尾章单删 → 409（防章号空洞）
    r_non_tail = client.delete(f"/api/novels/{pid}/chapters/vol-1-ch-1")
    assert r_non_tail.status_code == 409, r_non_tail.text

    # 尾章（拟定无正文）可删
    r2 = client.delete(f"/api/novels/{pid}/chapters/vol-1-ch-2")
    assert r2.status_code == 200, r2.text

    async def _after():
        async with async_session() as session:
            row = await chapter_repo.get_by_ref(session, pid, "vol-1-ch-2")
            assert row is None
            vol = await volume_repo.get_by_volume_no(session, pid, 1)
            assert vol.chapter_count == 1
            proj = await session.get(Novel, pid)
            assert proj.total_chapters == 1

    _run_async(_after())

    # 删尾章后章号复用：再建仍是 ch-2（无跳号）
    r3 = client.post(
        f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第三章"}
    )
    assert r3.status_code in (200, 201), r3.text
    assert r3.json()["ref"] == "vol-1-ch-2", "删尾章后章号应复用"


# ── service 包装 ──────────────────────────────────────────────────────────


async def _create_volume(session, project):
    from volumes.service import create_volume

    return await create_volume(session, project, title="第一卷", summary="")


async def _create_chapter(session, project):
    from chapters.service import create_chapter

    return await create_chapter(session, project, "vol-1", title="第一章")


async def _save_chapter(session, project, ref, data):
    from chapters.service import save_chapter

    return await save_chapter(session, project, ref, data)


async def _save_prose(session, project, ref, prose):
    from chapters.service import save_prose

    return await save_prose(session, project, ref, prose)
