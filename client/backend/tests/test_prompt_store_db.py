"""chapter_prompts 表持久化回环测试（PR④ 数据全量入库；ai-prompt-crafting 整章化）。

覆盖：save_prompt/load_prompt 读写回环 + upsert 覆写；
HTTP 列表（只回 write-prompt 一条）/{seg} 收敛（仅 write，其余 404）/
存量 seg 行不迁移不返回。

用法：
    cd client/backend
    python -m pytest tests/test_prompt_store_db.py -v
"""

import asyncio
import os
import tempfile
import uuid

_tmp_db = tempfile.NamedTemporaryFile(suffix="_prompt_db.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_prompt_store_db_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from conftest import seed_chapter_db  # noqa: E402
from sqlalchemy import select  # noqa: E402

from db import Base, async_session, engine  # noqa: E402
from filesystem.storage import get_storage  # noqa: E402
from models.archive import ChapterPrompt  # noqa: E402
from models.chapter import Chapter  # noqa: E402
from models.project import Novel  # noqa: E402
from prompt.store import load_prompt, save_prompt  # noqa: E402


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


_CHAPTER = {
    "volume": 1,
    "chapter": 1,
    "title": "第一章",
    "outline": {"summary": "主角来到边境城邦。", "characters": ["张三"]},
    "memo": {},
}


def _seed(root: str) -> None:
    _run_async(
        get_storage().write_yaml(
            root,
            "settings/writing-style.yaml",
            {"role": "一位小说家", "core_principles": "", "possible_mistakes": ""},
        )
    )
    _run_async(seed_chapter_db(root, _CHAPTER))


async def _prompt_rows(root: str) -> list[ChapterPrompt]:
    async with async_session() as session:
        stmt = (
            select(ChapterPrompt)
            .join(Chapter, Chapter.id == ChapterPrompt.chapter_id)
            .join(Novel, Novel.id == Chapter.project_id)
            .where(Novel.root_path == root)
            .order_by(ChapterPrompt.name)
        )
        return (await session.scalars(stmt)).all()


def test_save_and_load_prompt_upsert():
    root = tempfile.mkdtemp(prefix="psdb2_")
    _seed(root)

    assert _run_async(load_prompt(root, "vol-1-ch-1", "write-prompt")) == ""
    _run_async(save_prompt(root, "vol-1-ch-1", "write-prompt", "写作提示词 V1"))
    assert _run_async(load_prompt(root, "vol-1-ch-1", "write-prompt")) == "写作提示词 V1"
    # 同名覆写（upsert 不重复建行）
    _run_async(save_prompt(root, "vol-1-ch-1", "write-prompt", "写作提示词 V2"))
    rows = _run_async(_prompt_rows(root))
    assert len(rows) == 1
    assert rows[0].content == "写作提示词 V2"


def test_save_prompt_missing_chapter_silent():
    root = tempfile.mkdtemp(prefix="psdb3_")
    # 不种章行：对齐文件时代不抛错
    _run_async(save_prompt(root, "vol-9-ch-9", "write-prompt", "孤儿"))
    assert _run_async(_prompt_rows(root)) == []


# ── HTTP 层：list / get / put 三端点（整章单卡契约）────────────────────────


import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from auth_local.deps import (  # noqa: E402
    require_ai_access,
    require_novel_model,
    require_project_limit,
)
from auth_local.middleware import get_current_user  # noqa: E402
from db import get_db  # noqa: E402
from main import app  # noqa: E402
from models.user import User  # noqa: E402


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
    _run_async(_create_user("psdb_user"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "psdb_user"}


async def _override_true():
    return True


@pytest.fixture(autouse=True)
def _setup_overrides():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_project_limit] = _override_true
    app.dependency_overrides[require_ai_access] = _override_true
    app.dependency_overrides[require_novel_model] = lambda: True
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestPromptHTTPEndpoints:
    def test_write_only_roundtrip_and_seg_404(self, client):
        # 建项目 + 卷 + 章（HTTP 正规链路）
        name = f"psdb-{uuid.uuid4().hex[:6]}"
        r = client.post("/api/novels", json={"name": name})
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]
        r2 = client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷"})
        assert r2.status_code in (200, 201), r2.text
        r3 = client.post(
            f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第一章"}
        )
        assert r3.status_code in (200, 201), r3.text
        ref = r3.json()["ref"]

        # 无 write-prompt 行 → 列表空；GET write → 空文本（对齐缺文件语义）
        r6 = client.get(f"/api/novels/{pid}/chapters/{ref}/prompts")
        assert r6.status_code == 200, r6.text
        assert r6.json() == []
        r7 = client.get(f"/api/novels/{pid}/chapters/{ref}/prompts/write")
        assert r7.status_code == 200, r7.text
        assert r7.text == ""

        # 编辑 upsert → 读回
        r8 = client.put(
            f"/api/novels/{pid}/chapters/{ref}/prompts/write",
            json={"content": "手改后的整章提示词"},
        )
        assert r8.status_code == 200, r8.text
        r9 = client.get(f"/api/novels/{pid}/chapters/{ref}/prompts/write")
        assert r9.text == "手改后的整章提示词"

        # 列表只回整章一条（文件名形态保持）
        r10 = client.get(f"/api/novels/{pid}/chapters/{ref}/prompts")
        assert r10.json() == [f"{ref}-write-prompt.md"]

        # 分段已退役：seg 路径 404（读/写皆拒）
        assert (
            client.get(f"/api/novels/{pid}/chapters/{ref}/prompts/seg-1").status_code
            == 404
        )
        assert (
            client.put(
                f"/api/novels/{pid}/chapters/{ref}/prompts/seg-1",
                json={"content": "x"},
            ).status_code
            == 404
        )

    def test_legacy_seg_rows_not_listed(self, client):
        """存量 seg-N-prompt 行不迁移不删除，但读端点不再返回它们。"""
        name = f"psdb-{uuid.uuid4().hex[:6]}"
        r = client.post("/api/novels", json={"name": name})
        pid = r.json()["id"]
        client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷"})
        r3 = client.post(
            f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第一章"}
        )
        ref = r3.json()["ref"]

        # 直接落一条旧形态 seg 行（模拟存量库）
        from models import Novel

        async def _seed_legacy():
            async with async_session() as session:
                proj = await session.get(Novel, pid)
                await save_prompt(proj.root_path, ref, "seg-1-prompt", "旧分段提示词")

        _run_async(_seed_legacy())

        r6 = client.get(f"/api/novels/{pid}/chapters/{ref}/prompts")
        assert r6.json() == []
        assert (
            client.get(f"/api/novels/{pid}/chapters/{ref}/prompts/seg-1").status_code
            == 404
        )
        # 存量行仍在库里（不迁移不删除）
        from models import Novel as _N

        async def _count():
            async with async_session() as session:
                proj = await session.get(_N, pid)
                return await load_prompt(proj.root_path, ref, "seg-1-prompt")

        assert _run_async(_count()) == "旧分段提示词"
