"""知识库列表头像标志（角色设定条目与角色库同源）：has_avatar 只对角色设定条目出。"""

import asyncio
import uuid

from fastapi.testclient import TestClient

from auth_local.middleware import get_current_user
from db import async_session
from kb.service import create_entry
from main import app
from models.kb import KbEntryBlob
from models.user import User


def _run(coro):
    return asyncio.run(coro)


async def _seed() -> tuple[str, str, str]:
    uid = f"av{uuid.uuid4().hex[:8]}"
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="头像"))
        role, _g1, e1 = await create_entry(
            db, user_id=uid, genre="年代文", concept="角色设定",
            title="刘望津", payload={"archetype": "刘望津", "persona": "漂亮热情的农村姑娘。"},
            instruction="漂亮热情的农村出身姑娘。",
        )
        tech, _g2, e2 = await create_entry(
            db, user_id=uid, genre="", concept="手法", title="传功一句",
            payload={"instruction": "传功只给一句口诀。", "scene": "日常"},
            instruction="传功只给一句口诀。",
        )
        assert role is not None and tech is not None, (e1, e2)
        # 角色卡有头像字节；手法条目即使误挂字节也不得标 has_avatar
        db.add(KbEntryBlob(entry_id=role.id, variant="thumb", data=b"webp"))
        db.add(KbEntryBlob(entry_id=tech.id, variant="thumb", data=b"webp"))
        await db.commit()
        return uid, role.id, tech.id


def test_知识库列表与详情_角色条目has_avatar():
    uid, role_id, tech_id = _run(_seed())

    async def _override():
        return {"id": uid}

    app.dependency_overrides[get_current_user] = _override
    try:
        with TestClient(app) as c:
            d = c.get("/api/kb/entries?limit=50").json()["data"]["entries"]
            by_id = {e["id"]: e for e in d}
            assert by_id[role_id]["has_avatar"] is True
            assert by_id[tech_id]["has_avatar"] is False  # 只对角色设定概念出

            one = c.get(f"/api/kb/entries/{role_id}").json()["data"]
            assert one["has_avatar"] is True

            # 无字节的角色条目：has_avatar False（前端出姓氏占位）
            async def _strip():
                from sqlalchemy import delete as _del

                async with async_session() as db:
                    await db.execute(_del(KbEntryBlob).where(KbEntryBlob.entry_id == role_id))
                    await db.commit()
            _run(_strip())
            one2 = c.get(f"/api/kb/entries/{role_id}").json()["data"]
            assert one2["has_avatar"] is False
    finally:
        app.dependency_overrides.clear()
