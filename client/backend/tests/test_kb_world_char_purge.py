"""v0.47.5：只清三本书的用户拆书「世界设定/角色设定」，手法/文风/文笔与其他书不动。"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from sqlalchemy import delete, func, or_, select

from db import async_session
from models.character_library import CharacterLibrary, CharacterLibraryBlob
from models.kb import (
    KbBookBinding,
    KbBookEntry,
    KbBookEntryTag,
    KbEntry,
    KbEntryBlob,
    KbEntryMerge,
    KbEntryTag,
    KbKnowledgeInstance,
    KbKnowledgeRevision,
    KbLibraryItem,
    KbMatchItem,
    KbOrganizeFeedback,
    KbOrganizeFinding,
    KbPref,
    KbRelation,
)
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _create_tables():
    async def _go():
        from db import Base, engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    _run(_go())


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


_CURRENT: dict = {}


async def _purge(ids: dict) -> None:
    uid = ids["uid"]
    novels = {ids["novel_target"], ids["novel_keep"]}
    async with async_session() as db:
        entry_ids = set(
            (await db.execute(select(KbEntry.id).where(KbEntry.user_id == uid))).scalars().all()
        )
        book_ids = set(
            (await db.execute(select(KbBookEntry.id).where(KbBookEntry.user_id == uid))).scalars().all()
        )
        lib_ids = set(
            (await db.execute(select(CharacterLibrary.id).where(CharacterLibrary.user_id == uid))).scalars().all()
        )
        if entry_ids:
            await db.execute(delete(KbKnowledgeInstance).where(KbKnowledgeInstance.knowledge_id.in_(entry_ids)))
            await db.execute(delete(KbKnowledgeRevision).where(KbKnowledgeRevision.knowledge_id.in_(entry_ids)))
            await db.execute(delete(KbEntryBlob).where(KbEntryBlob.entry_id.in_(entry_ids)))
            await db.execute(delete(KbEntryTag).where(KbEntryTag.entry_id.in_(entry_ids)))
            await db.execute(delete(KbLibraryItem).where(KbLibraryItem.entry_id.in_(entry_ids)))
            await db.execute(delete(KbOrganizeFeedback).where(KbOrganizeFeedback.entry_id.in_(entry_ids)))
            await db.execute(delete(KbPref).where(KbPref.entry_id.in_(entry_ids)))
            await db.execute(delete(KbMatchItem).where(KbMatchItem.entry_id.in_(entry_ids)))
            await db.execute(
                delete(KbRelation).where(
                    or_(KbRelation.from_id.in_(entry_ids), KbRelation.to_id.in_(entry_ids))
                )
            )
            await db.execute(
                delete(KbEntryMerge).where(
                    or_(KbEntryMerge.surviving_id.in_(entry_ids), KbEntryMerge.merged_id.in_(entry_ids))
                )
            )
        if book_ids:
            await db.execute(delete(KbBookEntryTag).where(KbBookEntryTag.entry_id.in_(book_ids)))
            await db.execute(delete(KbMatchItem).where(KbMatchItem.entry_id.in_(book_ids)))
            await db.execute(delete(KbPref).where(KbPref.entry_id.in_(book_ids)))
        if lib_ids:
            await db.execute(delete(CharacterLibraryBlob).where(CharacterLibraryBlob.library_id.in_(lib_ids)))
        await db.execute(delete(KbBookBinding).where(KbBookBinding.novel_id.in_(novels)))
        await db.execute(delete(KbBookEntry).where(KbBookEntry.user_id == uid))
        await db.execute(delete(KbEntry).where(KbEntry.user_id == uid))
        await db.execute(delete(KbOrganizeFinding).where(KbOrganizeFinding.user_id == uid))
        await db.execute(delete(KbOrganizeFeedback).where(KbOrganizeFeedback.user_id == uid))
        await db.execute(delete(KbBookEntryTag).where(KbBookEntryTag.user_id == uid))
        await db.execute(delete(KbEntryTag).where(KbEntryTag.user_id == uid))
        await db.execute(delete(KbPref).where(KbPref.user_id == uid))
        await db.execute(delete(KbRelation).where(KbRelation.user_id == uid))
        await db.execute(delete(CharacterLibrary).where(CharacterLibrary.user_id == uid))
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    ids = _CURRENT.pop("ids", None)
    if ids:
        _run(_purge(ids))
    async def _clear():
        from models.app_meta import AppMeta

        async with async_session() as db:
            row = await db.get(AppMeta, "kb_world_char_purge_v1")
            if row is not None:
                await db.delete(row)
                await db.commit()

    _run(_clear())


def _seed() -> dict:
    suffix = uuid.uuid4().hex[:8]
    uid = f"wc-{suffix}"
    novel_target = f"n-t-{suffix}"
    novel_keep = f"n-k-{suffix}"
    # 唯一书名单，避免全局清理误伤其它测试的同名书数据
    book_a = f"撤回书A-{suffix}"
    book_b = f"撤回书B-{suffix}"

    def entry(prefix, concept, **kw):
        return KbEntry(
            id=_uid(prefix), user_id=uid, genre="悬疑", concept=concept,
            title=prefix, instruction=f"{prefix}-正文", status="active", rev=1, **kw,
        )

    w13 = entry("w13", "世界设定", src_kind="deconstruct", origin="material",
                src_ref="task-1", src_key="world.stage:1", src_novel_name=book_a)
    c13 = entry("c13", "角色设定", src_kind="deconstruct", origin="material",
                src_ref="task-1", src_key="character:1", src_novel_name=book_a)
    mig13 = entry("mig13", "角色设定", src_kind="character_library_migration", origin="manual",
                  src_ref="character_library", src_key=_uid("card"), src_novel_name=book_a)
    sum_w = entry("sumw", "世界设定", src_kind="manual", origin="summary", src_novel_name="")
    sum_char = entry("sumc", "角色设定", src_kind="manual", origin="summary", src_novel_name="")
    tech13 = entry("tech13", "手法", src_kind="deconstruct", origin="material",
                   src_ref="task-1", src_key="technique:1", src_novel_name=book_a)
    w_other = entry("wother", "世界设定", src_kind="deconstruct", origin="material",
                    src_ref="task-2", src_key="world.stage:2", src_novel_name="我的原创书")
    manual_w = entry("mw", "世界设定", src_kind="manual", origin="manual", src_novel_name="")
    sum_empty = entry("sume", "世界设定", src_kind="manual", origin="summary", src_novel_name="")
    sum_tech = entry("sumt", "手法", src_kind="manual", origin="summary", src_novel_name="")
    lib13 = _uid("lib")

    async def _go():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            db.add_all([
                w13, c13, mig13, sum_w, sum_char, sum_empty,
                tech13, w_other, manual_w, sum_tech,
            ])
            db.add(CharacterLibrary(
                id=lib13, user_id=uid, name="13路角色", src_kind="deconstruct",
                src_ref="task-1", src_character_id="c-1", src_novel_name=book_a,
            ))
            db.add(CharacterLibraryBlob(library_id=lib13, variant="full", data=b"x"))
            # 实例：总结节点靠 source_novel 判来源；素材/手法各挂一条
            for kid, novel in (
                (w13.id, book_a), (c13.id, book_a),
                (sum_w.id, book_a), (sum_char.id, book_b),
                (tech13.id, book_a), (sum_tech.id, book_a),
            ):
                db.add(KbKnowledgeInstance(
                    knowledge_id=kid, text="实例", source_kind="拆书",
                    source_novel=novel, quote="引文",
                ))
            db.add(KbKnowledgeRevision(knowledge_id=w13.id, version=1, snapshot_json="{}"))
            db.add(KbEntryBlob(entry_id=w13.id, variant="full", data=b"x"))
            db.add(KbEntryTag(entry_id=w13.id, user_id=uid, dim="concept", value="世界设定"))
            db.add(KbEntryTag(entry_id=tech13.id, user_id=uid, dim="concept", value="手法"))
            db.add(KbPref(user_id=uid, entry_id=w13.id))
            db.add(KbPref(user_id=uid, entry_id=tech13.id))
            db.add(KbRelation(user_id=uid, from_id=w13.id, to_id=tech13.id, rel_type="related"))
            db.add(KbLibraryItem(library_id="lib-1", entry_id=w13.id))
            db.add(KbLibraryItem(library_id="lib-1", entry_id=tech13.id))
            db.add(KbOrganizeFinding(
                user_id=uid, kind="merge", subject_id=w13.id, subject2_id=tech13.id,
                signature="sig-" + suffix, payload_json=json.dumps({"merged": w13.id}),
            ))
            db.add(KbOrganizeFeedback(
                user_id=uid, kind="merge", signature="fb-" + suffix, entry_id=w13.id,
            ))
            db.add(KbEntryMerge(surviving_id=tech13.id, merged_id=w13.id, run_id="run-1"))
            # 书级副本：目标条目一条、手法一条
            book_target = _uid("bkt")
            book_keep = _uid("bkk")
            db.add(KbBookEntry(
                id=book_target, novel_id=novel_target, user_id=uid, genre="悬疑",
                concept="世界设定", title="w13", instruction="w13-正文",
                src_kind="book_copy", src_ref=novel_target, src_key=w13.id, evidence_json="{}",
            ))
            db.add(KbBookEntry(
                id=book_keep, novel_id=novel_keep, user_id=uid, genre="悬疑",
                concept="手法", title="tech13", instruction="tech13-正文",
                src_kind="book_copy", src_ref=novel_keep, src_key=tech13.id, evidence_json="{}",
            ))
            db.add(KbBookEntryTag(entry_id=book_target, novel_id=novel_target,
                                  user_id=uid, dim="concept", value="世界设定"))
            db.add(KbBookBinding(
                novel_id=novel_target, library_id="lib-1", enabled=True,
                snapshot_json=json.dumps({
                    "members": [
                        {"entry_id": book_target, "text": "w13-正文"},
                        {"entry_id": book_keep, "text": "tech13-正文"},
                    ]
                }, ensure_ascii=False),
            ))
            await db.commit()

    _run(_go())
    ids = {
        "uid": uid, "novel_target": novel_target, "novel_keep": novel_keep,
        "w13": w13.id, "c13": c13.id, "mig13": mig13.id,
        "sum_w": sum_w.id, "sum_char": sum_char.id, "sum_empty": sum_empty.id,
        "tech13": tech13.id, "w_other": w_other.id, "manual_w": manual_w.id,
        "sum_tech": sum_tech.id, "lib13": lib13,
        "book_a": book_a, "book_b": book_b,
    }
    _CURRENT["ids"] = ids
    return ids


def _count(model, *where):
    async def _go():
        async with async_session() as db:
            stmt = select(func.count()).select_from(model)
            for clause in where:
                stmt = stmt.where(clause)
            return int((await db.execute(stmt)).scalar() or 0)

    return _run(_go())


def test_只清三本书的世界角色_其他全留且幂等(monkeypatch):
    from kb.world_char_purge import apply_world_char_purge

    _create_tables()
    ids = _seed()
    monkeypatch.setattr(
        "kb.world_char_purge.WITHDRAWN_BOOKS", (ids["book_a"], ids["book_b"])
    )

    r1 = _run(apply_world_char_purge(force=True, user_id=ids["uid"]))
    assert r1["status"] == "purged"
    assert r1["entries_deleted"] == 6  # w13/c13/mig13/sum_w/sum_char/sum_empty
    assert r1["library_cards_deleted"] == 1

    # 目标侧全删
    for key in ("w13", "c13", "mig13", "sum_w", "sum_char", "sum_empty"):
        assert _count(KbEntry, KbEntry.id == ids[key]) == 0, key
    assert _count(CharacterLibrary, CharacterLibrary.id == ids["lib13"]) == 0
    assert _count(CharacterLibraryBlob, CharacterLibraryBlob.library_id == ids["lib13"]) == 0
    # 保留侧不动
    for key in ("tech13", "w_other", "manual_w", "sum_tech"):
        assert _count(KbEntry, KbEntry.id == ids[key]) == 1, key
    assert _count(KbEntryTag, KbEntryTag.entry_id == ids["tech13"]) == 1
    assert _count(KbKnowledgeInstance, KbKnowledgeInstance.knowledge_id == ids["tech13"]) == 1
    assert _count(KbPref, KbPref.entry_id == ids["tech13"]) == 1
    assert _count(KbLibraryItem, KbLibraryItem.entry_id == ids["tech13"]) == 1
    assert _count(
        KbBookEntry,
        KbBookEntry.novel_id == ids["novel_keep"],
        KbBookEntry.src_key == ids["tech13"],
    ) == 1
    # 目标书级副本已删
    assert _count(KbBookEntry, KbBookEntry.novel_id == ids["novel_target"]) == 0

    # 幂等
    r2 = _run(apply_world_char_purge(force=True, user_id=ids["uid"]))
    assert r2["entries_deleted"] == 0
    assert r2["library_cards_deleted"] == 0
    assert _count(KbEntry, KbEntry.id == ids["tech13"]) == 1


def test_读面reconcile重收后仍被清掉(monkeypatch):
    """v0.47.5 回归：reconcile 在读面把拆书条目重新收回，清理必须在它之后。"""
    from kb.migrate_library import ensure_legacy_migrated

    _create_tables()
    ids = _seed()
    monkeypatch.setattr(
        "kb.world_char_purge.WITHDRAWN_BOOKS", (ids["book_a"], ids["book_b"])
    )
    extra_id = _uid("recollected")

    async def fake_reconcile(*, user_id):  # noqa: ARG001
        # 模拟 version_reconcile 从 deconstruct 任务重新收条目（自开会话并提交）
        async with async_session() as db:
            db.add(KbEntry(
                id=extra_id, user_id=ids["uid"], genre="悬疑", concept="世界设定",
                title="reconcile 重新收回的", instruction="reconcile 重新收回的正文",
                status="active", rev=1, src_kind="deconstruct", origin="material",
                src_ref="task-x", src_key="world.stage:9", src_novel_name=ids["book_a"],
            ))
            await db.commit()

    monkeypatch.setattr(
        "kb.version_reconcile.reconcile_deconstruct_versions", fake_reconcile
    )

    async def _go():
        async with async_session() as db:
            await ensure_legacy_migrated(db, user_id=ids["uid"])

    _run(_go())

    assert _count(KbEntry, KbEntry.id == ids["w13"]) == 0
    assert _count(KbEntry, KbEntry.id == extra_id) == 0
    assert _count(KbEntry, KbEntry.id == ids["tech13"]) == 1
