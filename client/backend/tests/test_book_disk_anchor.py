"""root_path 盘面锚点契约（c-retire-local-file-storage 评审修复）。

KV 键环境无关（book_root），盘面落点必须经 book_disk_dir 按 DATA_ROOT
锚定——打包桌面端 DATA_ROOT 是安装目录下绝对路径且不 chdir
（pywebview_app），CWD 相对解析会落错位置甚至无权限（macOS .app CWD=/）。
"""

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from auth_local.deps import (
    require_ai_access,
    require_novel_model,
    require_project_limit,
)
from auth_local.middleware import get_current_user
from config import book_disk_dir, book_root
from db import Base, async_session, engine, get_db
from main import app
from models.user import User

USER_ID = "anchoruser"


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _setup():
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
        await session.commit()


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    _run_async(_setup())
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
    app.dependency_overrides[require_ai_access] = lambda: True
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = lambda: True
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_book_disk_dir_anchors_relative_key_to_data_root(monkeypatch, tmp_path):
    monkeypatch.setattr("config.DATA_ROOT", str(tmp_path))
    assert book_disk_dir(book_root("我的书")) == os.path.join(str(tmp_path), "我的书")


def test_book_disk_dir_absolute_key_passthrough():
    """存量绝对键（历史 DATA_ROOT 绝对行）原样返回。"""
    assert book_disk_dir("/app/data/老书") == "/app/data/老书"


def test_create_project_seeds_samples_anchor_under_data_root(client):
    """建书后在 DATA_ROOT/<slug> 落 novel-samples 锚点：目录存在、内容为零
    （业务数据全量入库，盘上零骨架）。"""
    from config import DATA_ROOT

    r = client.post("/api/novels", json={"name": "锚点测试书"})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    slug = client.get(f"/api/novels/{pid}").json()["slug"]

    anchor = os.path.join(DATA_ROOT, slug)
    assert os.path.isdir(anchor), f"novel-samples 锚点未落 DATA_ROOT：{anchor}"
    assert os.listdir(anchor) == []
