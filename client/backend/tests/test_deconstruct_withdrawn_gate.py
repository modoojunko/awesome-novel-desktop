"""撤回书出口闸：建书/收录角色卡/收录知识库 403，reconcile 跳过撤回书。"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from sqlalchemy import select

from db import async_session
from models.deconstruct import DeconstructJob
from models.kb import KbEntry
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _create_tables():
    async def _go():
        from db import Base, engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    _run(_go())


_PRODUCTS = {
    "genre": {"file": "题材.md", "data": {"genre": "悬疑"}},
    "world": {"file": "世界设定.md", "data": {"stage": {"content": "撤回书舞台"}}},
    "characters": {"file": "角色设定.md", "data": {"characters": [{"name": "张三"}]}},
    "style": {"file": "写作文风.md", "data": {"role": "第三人称限知"}},
}


def _seed_task(book: str, *, status: str = "completed") -> str:
    suffix = uuid.uuid4().hex[:8]
    uid = f"gate-{suffix}"
    jid = f"gatejob-{suffix}"

    async def _go():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            db.add(DeconstructJob(
                id=jid, user_id=uid, status=status, queue_seq=0,
                source_name=f"{book}.txt", source_size=1000, source_path="", encoding="",
                book_name=book, total_chars=1000, chapter_count=10, volume_count=1,
                parse_warnings_json="[]", api_config_id="cfg-1", ai_model="test",
                mode="smart", selected_chapters_json="[]", rhythm_json="{}",
                selected_dims_json="[]", dims_json="{}",
                products_json=json.dumps(_PRODUCTS, ensure_ascii=False), error_json="{}",
            ))
            await db.commit()

    _run(_go())
    return uid, jid


@pytest.fixture()
def client():
    _create_tables()
    from fastapi.testclient import TestClient

    from auth_local.middleware import get_current_user
    from main import app

    holders: dict = {}

    def _bind(uid: str):
        from auth_local.deps import require_ai_access

        app.dependency_overrides[get_current_user] = lambda: {"id": uid}
        app.dependency_overrides[require_ai_access] = lambda: True  # 权益闸放行，专测撤回闸
        return TestClient(app)

    holders["bind"] = _bind
    yield holders
    from auth_local.deps import require_ai_access

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_ai_access, None)


def test_三出口命中撤回书一律403(client):
    tc = client["bind"]
    uid, jid = _seed_task("斩神")

    app_tc = tc(uid)  # dependency_overrides 已绑 uid

    for path in (
        f"/api/deconstruct/tasks/{jid}/import-book",
        f"/api/deconstruct/tasks/{jid}/collect-to-kb",
    ):
        r = app_tc.post(path)
        assert r.status_code == 403, (path, r.status_code, r.text)
        assert "撤回" in r.json()["detail"]

    r = app_tc.post(
        f"/api/deconstruct/tasks/{jid}/to-library",
        json={"picks": ["张三"], "rename": False},
    )
    assert r.status_code == 403
    assert "撤回" in r.json()["detail"]


def test_试拆后缀书名同样命中(client):
    tc = client["bind"]
    uid, jid = _seed_task("斩神-前30章")
    app_tc = tc(uid)
    r = app_tc.post(f"/api/deconstruct/tasks/{jid}/collect-to-kb")
    assert r.status_code == 403


def test_非撤回书不受影响(client, monkeypatch):
    tc = client["bind"]
    uid, jid = _seed_task("我的原创书")
    app_tc = tc(uid)

    # collect-to-kb 走真实映射（产物含 world/characters）——非撤回书放行
    r = app_tc.post(f"/api/deconstruct/tasks/{jid}/collect-to-kb")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_reconcile跳过撤回书(monkeypatch):
    from kb.version_reconcile import reconcile_deconstruct_versions

    _create_tables()
    suffix = uuid.uuid4().hex[:8]
    uid = f"gaterec-{suffix}"
    jid = f"gaterecjob-{suffix}"

    async def _seed():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            db.add(DeconstructJob(
                id=jid, user_id=uid, status="completed", queue_seq=0,
                source_name="x.txt", source_size=1, source_path="", encoding="",
                book_name="斩神", total_chars=1, chapter_count=9, volume_count=1,
                parse_warnings_json="[]", api_config_id="", ai_model="test",
                mode="smart", selected_chapters_json="[]", rhythm_json="{}",
                selected_dims_json="[]", dims_json="{}",
                products_json=json.dumps(_PRODUCTS, ensure_ascii=False), error_json="{}",
            ))
            # 留一条撤回书的保留面素材（手法）——触发 reconcile 分组
            db.add(KbEntry(
                id=f"keep-{suffix}", user_id=uid, genre="都市", concept="手法",
                title="保留手法", instruction="保留手法正文", status="active", rev=1,
                src_kind="deconstruct", src_ref=jid, src_key="technique:1",
                src_novel_name="斩神", origin="material",
            ))
            await db.commit()

    _run(_seed())

    # 若 reconcile 没跳过，会走 teardown+重收——重收集函数被替换成会炸的桩，
    # 测试通过＝reconcile 根本没碰撤回书
    async def _boom(*a, **kw):
        raise AssertionError("reconcile 不应处理撤回书")

    async def _go():
        # collect_task_to_kb 换桩：撤回书若被处理必炸
        import kb.deconstruct_import as di

        monkeypatch.setattr(di, "collect_task_to_kb", _boom)
        await reconcile_deconstruct_versions(user_id=uid)

    _run(_go())

    async def _keep_alive():
        async with async_session() as db:
            row = await db.get(KbEntry, f"keep-{suffix}")
            return row is not None and row.status == "active"

    assert _run(_keep_alive()) is True
    # 清场
    async def _clean():
        async with async_session() as db:
            row = await db.get(User, uid)
            if row:
                await db.delete(row)
            jobs = (await db.execute(select(DeconstructJob).where(DeconstructJob.user_id == uid))).scalars().all()
            for j in jobs:
                await db.delete(j)
            entries = (await db.execute(select(KbEntry).where(KbEntry.user_id == uid))).scalars().all()
            for e in entries:
                await db.delete(e)
            await db.commit()

    _run(_clean())
