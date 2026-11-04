"""知识 v2 迁移测试（c-kb-knowledge-v2）：知识+实例 / 关系不断 / 重跑幂等 / 归档映射 / 白名单约束。"""

import asyncio
import uuid

from sqlalchemy import select

from db import async_session
from models.kb import KbEntry, KbRelation
from models.kb_knowledge import (
    KbKnowledge,
    KbKnowledgeInstance,
    KbKnowledgeRelation,
)
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _create_tables():
    async def _go():
        from db import Base, engine

        # 空库跑两遍也不报错（任务 2.2 验证口径）
        for _ in range(2):
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
    return _run(_go())


def test_知识_实例_关系_迁移与幂等():
    from kb.knowledge_migration import migrate_kb_knowledge_v1

    suffix = uuid.uuid4().hex[:8]
    uid = f"kbv2-{suffix}"
    e1, e2, e3 = f"kbent1-{suffix}", f"kbent2-{suffix}", f"kbent3-{suffix}"
    rel_id = f"rel-{suffix}"
    ghost_from = f"ghost-{suffix}"  # 两端对不上旧条目 id → 跳过不迁

    async def _seed():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            db.add(KbEntry(
                id=e1, user_id=uid, title="叙事身份", genre="科幻", concept="文风",
                instruction="冷峻克制，句子短，少形容词。",
                evidence="那不是雨声，是整座城在往后退。",
                status="active", rev=1,
                src_kind="deconstruct", src_ref="deconstruct",
                src_key=e1, src_novel_name="星海拾遗",
            ))
            db.add(KbEntry(
                id=e2, user_id=uid, title="先果后因", genre="科幻", concept="手法",
                instruction="先写结果，再倒回去拆折。",
                status="active", rev=2, src_kind="manual",
            ))
            db.add(KbEntry(
                id=e3, user_id=uid, title="旧归档条目", genre="科幻", concept="文笔",
                instruction="旧归档条目的实例文本。",
                status="archived", rev=1, src_kind="manual",
            ))
            db.add(KbRelation(
                id=rel_id, user_id=uid, from_id=e1, to_id=e2,
                rel_type="refines", note="收窄", confidence=0.8,
                status="active", source="ai",
            ))
            db.add(KbRelation(
                id=rel_id + "-ghost", user_id=uid, from_id=ghost_from, to_id=e2,
                rel_type="applies_to", status="active", source="ai",
            ))
            await db.commit()

    _create_tables()
    _run(_seed())

    r1 = _run(migrate_kb_knowledge_v1(user_ids={uid}))
    assert r1["knowledge"] >= 2, f"知识应迁 2 条：{r1}"
    assert r1["instances"] >= 2, f"实例应 ≥2（每条知识 1 条）：{r1}"
    assert r1["relations"] >= 1, f"关系应 ≥1：{r1}"

    async def _check():
        async with async_session() as db:
            ks = (await db.execute(
                select(KbKnowledge).where(KbKnowledge.user_id == uid)
            )).scalars().all()
            ins = (await db.execute(
                select(KbKnowledgeInstance).join(
                    KbKnowledge,
                    KbKnowledgeInstance.knowledge_id == KbKnowledge.id,
                ).where(KbKnowledge.user_id == uid)
            )).scalars().all()
            rels = (await db.execute(
                select(KbKnowledgeRelation).where(KbKnowledgeRelation.user_id == uid)
            )).scalars().all()
            return ks, ins, rels

    ks, ins, rels = _run(_check())
    by_id = {k.id: k for k in ks}
    k1 = by_id[e1]
    # 知识 id 原样；定义置空（一般性定义是新字段，首轮「待补」）；状态/版本/来源映射
    assert k1.category == "文风"
    assert k1.definition == ""
    assert k1.status == "formed"
    assert k1.version == 1
    assert k1.origin == "deconstruct"
    assert k1.archived_at is None
    # 实例：id 独立、挂在知识下、instruction→text、evidence→quote、来源映射
    mine = [i for i in ins if i.knowledge_id == e1]
    assert len(mine) == 1
    assert mine[0].text == "冷峻克制，句子短，少形容词。"
    assert mine[0].quote == "那不是雨声，是整座城在往后退。"
    assert mine[0].source_kind == "拆书"
    assert mine[0].source_novel == "星海拾遗"
    # 关系：两端知识 id 原样
    assert any(r.from_id == e1 and r.to_id == e2 and r.rel_type == "refines" for r in rels)
    # 两端对不上旧条目 id 的关系不迁
    assert not any(r.from_id == ghost_from for r in rels)

    # 重跑幂等：不新增重复知识/实例/关系
    r2 = _run(migrate_kb_knowledge_v1(user_ids={uid}))
    assert r2["knowledge"] == 0 and r2["relations"] == 0
    ks2, ins2, rels2 = _run(_check())
    assert len(ks2) == len(ks) and len(ins2) == len(ins) and len(rels2) == len(rels)

    # 归档映射：旧 archived 条目 → formed + archived_at（生命周期态，不硬删）
    k_arch = next(k for k in ks if k.id == e3)
    assert k_arch.status == "formed"
    assert k_arch.archived_at is not None


def test_白名单约束_类别_状态_自环():
    import sqlalchemy.exc

    suffix = uuid.uuid4().hex[:8]
    uid = f"kbv2wl-{suffix}"
    kid = f"kbw-{suffix}"

    async def _seed():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            db.add(KbKnowledge(
                id=kid, user_id=uid, title="正常知识", genre="科幻",
                category="文风", definition="x", status="formed",
            ))
            await db.commit()
    _create_tables()
    _run(_seed())

    async def _bad_category():
        async with async_session() as db:
            db.add(KbKnowledge(
                id=kid + "-bad1", user_id=uid, title="x", genre="科幻",
                category="心得", definition="", status="formed",
            ))
            await db.commit()
    try:
        _run(_bad_category())
        raise AssertionError("非法类别应被 CHECK 拦截")
    except sqlalchemy.exc.IntegrityError:
        pass

    async def _bad_status():
        async with async_session() as db:
            db.add(KbKnowledge(
                id=kid + "-bad2", user_id=uid, title="x", genre="科幻",
                category="文风", definition="", status="published",
            ))
            await db.commit()
    try:
        _run(_bad_status())
        raise AssertionError("非法状态应被 CHECK 拦截")
    except sqlalchemy.exc.IntegrityError:
        pass

    async def _self_loop():
        async with async_session() as db:
            db.add(KbKnowledgeRelation(
                id=kid + "-loop", user_id=uid, from_id=kid, to_id=kid,
                rel_type="refines", status="active",
            ))
            await db.commit()
    try:
        _run(_self_loop())
        raise AssertionError("自环关系应被 CHECK 拦截")
    except sqlalchemy.exc.IntegrityError:
        pass
