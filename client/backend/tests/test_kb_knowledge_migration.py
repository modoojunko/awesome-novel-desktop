"""知识 v2 迁移测试（c-kb-knowledge-v2）：DDL 幂等 / 实例生成 / 重跑幂等 / 归档映射。"""

import asyncio
import uuid

from sqlalchemy import text

from db import async_session
from models.kb import KbEntry
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _create_tables():
    async def _go():
        from db import Base, engine
        for _ in range(2):  # 幂等验证：跑两遍不报错
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
    return _run(_go())


def test_迁移_DDL幂等_实例生成():
    from kb.knowledge_migration import migrate_kb_knowledge_v2

    suffix = uuid.uuid4().hex[:8]
    uid = f"kbv2-{suffix}"
    e1 = f"kbent1-{suffix}"
    e2 = f"kbent2-{suffix}"

    async def _seed():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            db.add(KbEntry(
                id=e1, user_id=uid, title="叙事身份", genre="科幻", concept="文风",
                instruction="冷峻克制，句子短，少形容词。",
                evidence="那不是雨声，是整座城在往后退。",
                status="active", rev=1,
                src_kind="deconstruct", src_ref="dec", src_key=e1,
                src_novel_name="星海拾遗",
            ))
            db.add(KbEntry(
                id=e2, user_id=uid, title="先果后因", genre="科幻", concept="手法",
                instruction="先写结果，再倒回去拆折。",
                status="active", rev=2, src_kind="manual",
            ))
            await db.commit()

    _create_tables()
    _run(_seed())

    r1 = _run(migrate_kb_knowledge_v2())
    assert r1["instances"] >= 2, f"实例应 ≥2：{r1}"
    r2 = _run(migrate_kb_knowledge_v2())
    assert r2["instances"] == 0, f"重跑应零新增：{r2}"

    async def _check():
        async with async_session() as db:
            cols = [r[1] for r in (await db.execute(
                text("PRAGMA table_info(kb_entries)")
            )).fetchall()]
            _r = await db.execute(text("SELECT COUNT(*) FROM kb_knowledge_instances"))
            n = _r.scalar()
            _rd = await db.execute(
                text("SELECT definition FROM kb_entries WHERE id = :id"), {"id": e1}
            )
            has_def = _rd.scalar()
            _rv = await db.execute(
                text("SELECT version FROM kb_entries WHERE id = :id"), {"id": e1}
            )
            has_ver = _rv.scalar()
            return cols, n, has_def, has_ver

    cols, n, has_def, has_ver = _run(_check())
    assert "definition" in cols and "version" in cols
    assert "origin" in cols and "archived_at" in cols
    assert n >= 2
    assert has_def == ""  # 新字段首轮待补
    assert has_ver == 1  # version 首轮即 1（迁移默认值落位）


def test_归档映射_约束():
    import sqlalchemy.exc

    from kb.knowledge_migration import migrate_kb_knowledge_v2

    suffix = uuid.uuid4().hex[:8]
    uid = f"kbv2wl-{suffix}"
    kid = f"kbwl-{suffix}"

    _create_tables()

    async def _seed():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            db.add(KbEntry(
                id=kid, user_id=uid, title="正常知识", genre="科幻", concept="文风",
                instruction="x", status="active",
            ))
            await db.commit()
    _run(_seed())
    _run(migrate_kb_knowledge_v2())

    async def _archive():
        async with async_session() as db:
            await db.execute(text(
                "UPDATE kb_entries SET archived_at = CURRENT_TIMESTAMP WHERE id = :id"
            ), {"id": kid})
            await db.commit()

    async def _count_active():
        async with async_session() as db:
            _r = await db.execute(text(
                "SELECT COUNT(*) FROM kb_entries WHERE user_id = :uid AND archived_at IS NULL"
            ), {"uid": uid})
            return _r.scalar()

    before = _run(_count_active())
    _run(_archive())
    after = _run(_count_active())
    assert after == before - 1, f"归档后列表应少 1 条：before={before} after={after}"

    async def _bad_cat():
        async with async_session() as db:
            await db.execute(text(
                "INSERT INTO kb_entries (id, user_id, title, genre, concept, instruction, status) "
                "VALUES (:id, :uid, 'x', '科幻', '心得', 'x', 'active')"
            ), {"id": f"bad-{suffix}", "uid": uid})
            await db.commit()
    try:
        _run(_bad_cat())
        raise AssertionError("非法类别应被 CHECK 拦截")
    except sqlalchemy.exc.IntegrityError:
        pass
