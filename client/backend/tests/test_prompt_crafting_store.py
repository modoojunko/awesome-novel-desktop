"""ai-prompt-crafting — 章纲新格子（提示词格子）拆装与迁移测试

验证：ladder_exit 标量、micro_payoffs 子表的 JSON→表→JSON 往返（c-og-slim-v2：
scene_cards 与读者获得位置档已退役——写入被忽略、装配不输出）；旧 JSON 无新键保存
不报错；应用 lifespan 二次启动幂等。

用法：
    cd client/backend
    python -m pytest tests/test_prompt_crafting_store.py -v
"""

import asyncio
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_pcs.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_prompt_crafting_store_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from chapters.service import create_chapter  # noqa: E402
from chapters.store import load_chapter, save_chapter  # noqa: E402
from db import Base, async_session, engine  # noqa: E402
from main import app  # noqa: E402
from models import Novel  # noqa: E402

USER_ID = "pcs_user"


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
    yield


async def _new_project(name: str) -> Novel:
    root = os.path.join(_tmp_data_root, name)
    os.makedirs(os.path.join(root, "volumes"), exist_ok=True)
    os.makedirs(os.path.join(root, "chapters"), exist_ok=True)
    project = Novel(
        user_id=USER_ID,
        name=name,
        slug=name,
        root_path=root,
        source="manual",
        current_phase="outline",
    )
    async with async_session() as session:
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project


async def _prepare_chapter(project: Novel) -> str:
    from repositories import volume_repo

    async with async_session() as session:
        proj = await session.get(Novel, project.id)
        await volume_repo.upsert(session, proj.id, 1, title="第一卷")
        await session.refresh(proj)
        ch = await create_chapter(session, proj, "vol-1", title="第一章")
        return ch["ref"]


def test_prompt_crafting_fields_round_trip():
    async def _run():
        project = await _new_project("pcs1")
        ref = await _prepare_chapter(project)
        data = {
            "title": "第一章",
            "prose": "",
            "ladder_exit": "拿到半张地图，连夜出门，更不安",
            # 已退役键：写入被忽略（不落库、不报错）
            "scene_cards": [
                {"scene_name": "酒馆对峙", "weight": "high", "focus": "核心冲突"},
            ],
            "segments": [{"summary": "酒馆", "target_words": 800}],
            "micro_payoffs": [
                {"kind": "clue", "description": "主角拿到半块玉佩", "location": "中段"},
                {"kind": "emotion", "description": "与师父决裂的痛感"},
            ],
        }
        await save_chapter(project.root_path, ref, data)
        loaded = await load_chapter(project.root_path, ref)
        assert loaded["ladder_exit"] == "拿到半张地图，连夜出门，更不安"
        assert "scene_cards" not in loaded and "segments" not in loaded
        # 读者获得：类型 + 描述往返，位置档不再输出
        assert loaded["micro_payoffs"] == [
            {"kind": "clue", "description": "主角拿到半块玉佩"},
            {"kind": "emotion", "description": "与师父决裂的痛感"},
        ]

    _run_async(_run())


def test_old_chapter_json_without_new_keys_still_saves():
    async def _run():
        project = await _new_project("pcs2")
        ref = await _prepare_chapter(project)
        # 旧形态：无 ladder_exit / weight / micro_payoffs
        data = {"title": "旧章", "prose": "旧正文若干字。", "outline": {"summary": "旧摘要"}}
        await save_chapter(project.root_path, ref, data)
        loaded = await load_chapter(project.root_path, ref)
        assert "ladder_exit" not in loaded
        assert "micro_payoffs" not in loaded
        assert loaded["prose"] == "旧正文若干字。"

    _run_async(_run())


def test_lifespan_migration_idempotent():
    # 首次启动：create_all + 幂等补列（新库列已存在，_add_missing 全跳过）
    with TestClient(app) as _client:
        pass
    # 二次启动：全部 no-op，不抛错
    with TestClient(app) as _client:
        pass
