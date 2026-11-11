"""官方基线撤回清理：官方派生全删、用户拆书/原创全留（v0.47.4 合规）。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid

import pytest
from sqlalchemy import delete, func, or_, select

from db import async_session
from kb.revoked_baseline import REVOKED_ENTRY_IDS
from models.app_meta import AppMeta
from models.kb import (
    KbBaselineEntry,
    KbBaselineOverlay,
    KbBaselineTag,
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


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _count(model, *where) -> int:
    async with async_session() as db:
        stmt = select(func.count()).select_from(model)
        for clause in where:
            stmt = stmt.where(clause)
        return int((await db.execute(stmt)).scalar() or 0)


async def _clear_markers():
    async with async_session() as db:
        for key in (
            "kb_baseline_retired",
            "kb_revocation_v1",
            "kb_baseline_version",
            "kb_baseline_last_sync",
        ):
            row = await db.get(AppMeta, key)
            if row is not None:
                await db.delete(row)
        await db.commit()


_CURRENT: dict = {}


async def _purge(ids: dict) -> None:
    """清掉本测试造的全部行，避免污染共享 session DB 的后续 KB 测试。"""
    uid = ids["uid"]
    novels = {ids["novel_official"], ids["novel_base"], ids["novel_user"]}
    async with async_session() as db:
        entry_ids = set(
            (await db.execute(select(KbEntry.id).where(KbEntry.user_id == uid))).scalars().all()
        )
        book_ids = set(
            (
                await db.execute(
                    select(KbBookEntry.id).where(KbBookEntry.user_id == uid)
                )
            ).scalars().all()
        )
        if entry_ids:
            await db.execute(
                delete(KbKnowledgeInstance).where(
                    KbKnowledgeInstance.knowledge_id.in_(entry_ids)
                )
            )
            await db.execute(
                delete(KbKnowledgeRevision).where(
                    KbKnowledgeRevision.knowledge_id.in_(entry_ids)
                )
            )
            await db.execute(
                delete(KbEntryBlob).where(KbEntryBlob.entry_id.in_(entry_ids))
            )
            await db.execute(delete(KbEntryTag).where(KbEntryTag.entry_id.in_(entry_ids)))
            await db.execute(
                delete(KbLibraryItem).where(KbLibraryItem.entry_id.in_(entry_ids))
            )
            await db.execute(
                delete(KbOrganizeFeedback).where(
                    KbOrganizeFeedback.entry_id.in_(entry_ids)
                )
            )
            await db.execute(delete(KbPref).where(KbPref.entry_id.in_(entry_ids)))
            await db.execute(
                delete(KbMatchItem).where(KbMatchItem.entry_id.in_(entry_ids))
            )
            await db.execute(
                delete(KbRelation).where(
                    or_(KbRelation.from_id.in_(entry_ids), KbRelation.to_id.in_(entry_ids))
                )
            )
            await db.execute(
                delete(KbEntryMerge).where(
                    or_(
                        KbEntryMerge.surviving_id.in_(entry_ids),
                        KbEntryMerge.merged_id.in_(entry_ids),
                    )
                )
            )
        if book_ids:
            await db.execute(
                delete(KbBookEntryTag).where(KbBookEntryTag.entry_id.in_(book_ids))
            )
            await db.execute(
                delete(KbMatchItem).where(KbMatchItem.entry_id.in_(book_ids))
            )
            await db.execute(delete(KbPref).where(KbPref.entry_id.in_(book_ids)))
        await db.execute(delete(KbBookBinding).where(KbBookBinding.novel_id.in_(novels)))
        await db.execute(delete(KbBookEntry).where(KbBookEntry.user_id == uid))
        await db.execute(delete(KbEntry).where(KbEntry.user_id == uid))
        await db.execute(
            delete(KbBaselineOverlay).where(KbBaselineOverlay.user_id == uid)
        )
        await db.execute(
            delete(KbOrganizeFinding).where(KbOrganizeFinding.user_id == uid)
        )
        await db.execute(
            delete(KbOrganizeFeedback).where(KbOrganizeFeedback.user_id == uid)
        )
        await db.execute(
            delete(KbBookEntryTag).where(KbBookEntryTag.user_id == uid)
        )
        await db.execute(delete(KbEntryTag).where(KbEntryTag.user_id == uid))
        await db.execute(delete(KbPref).where(KbPref.user_id == uid))
        await db.execute(delete(KbRelation).where(KbRelation.user_id == uid))
        await db.execute(
            delete(KbBaselineTag).where(KbBaselineTag.entry_id == ids["base_id"])
        )
        await db.execute(
            delete(KbBaselineEntry).where(
                KbBaselineEntry.entry_id == ids["base_id"]
            )
        )
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


@pytest.fixture(autouse=True)
def _restore_meta():
    yield
    ids = _CURRENT.pop("ids", None)
    if ids:
        _run(_purge(ids))
    _run(_clear_markers())


def _seed() -> dict:
    """官方侧与用户侧各造一套完整依赖，返回 id 表。"""
    suffix = uuid.uuid4().hex[:8]
    uid = f"rev-{suffix}"
    base_id = next(iter(REVOKED_ENTRY_IDS))
    base_src = "baseline:都市:test-" + suffix
    promoted_id = _uid("promoted")
    official_book_id = _uid("bkoff")
    baseline_book_id = _uid("bkbase")
    material_id = _uid("mat")
    card_id = _uid("card")
    summary_id = _uid("sum")
    manual_id = _uid("manual")
    user_book_id = _uid("bkuser")
    official_text = "官方基线正文-" + suffix
    user_text = "用户自己拆出来的正文-" + suffix
    novel_official = "n-off-" + suffix
    novel_base = "n-base-" + suffix
    novel_user = "n-user-" + suffix

    async def _go():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            # ── 官方层 ──
            db.add(KbBaselineEntry(
                entry_id=base_id,
                src_key=base_src,
                pack_version=3,
                genre="都市",
                concept="手法",
                title="官方手法",
                instruction=official_text,
                content_sha256=_sha(official_text),
            ))
            db.add(KbBaselineTag(entry_id=base_id, dim="concept", value="手法"))
            db.add(KbBaselineOverlay(
                user_id=uid, src_key=base_src, action="edit",
                content=official_text + "（用户改）", base_content_sha256=_sha(official_text),
            ))
            # 提升副本（官方精选已下架）＋书级副本
            db.add(KbEntry(
                id=promoted_id, user_id=uid, genre="都市", concept="手法",
                title="官方旧条目", instruction=official_text + "（提升）",
                status="active", rev=1, src_kind="manual",
                src_novel_name="官方精选（已下架）",
                evidence_json=json.dumps({"promoted_from": base_src}, ensure_ascii=False),
            ))
            db.add(KbBookEntry(
                id=official_book_id, novel_id=novel_official, user_id=uid,
                genre="都市", concept="手法", title="官方旧条目",
                instruction=official_text, src_kind="book_copy",
                src_ref=novel_official, src_key=promoted_id,
                evidence_json=json.dumps({"promoted_from": base_src}, ensure_ascii=False),
            ))
            db.add(KbBookEntry(
                id=baseline_book_id, novel_id=novel_base, user_id=uid,
                genre="都市", concept="手法", title="官方手法",
                instruction=official_text, src_kind="book_copy",
                src_ref=novel_base, src_key=base_id, evidence_json="{}",
            ))
            # ── 用户拆书 / 原创 ──
            db.add(KbEntry(
                id=material_id, user_id=uid, genre="悬疑", concept="手法",
                title="我的拆书手法", instruction=user_text,
                status="active", rev=1, src_kind="deconstruct",
                src_ref="task-" + suffix, src_key="technique:1",
                src_novel_name="我的书", origin="material",
            ))
            db.add(KbEntry(
                id=card_id, user_id=uid, genre="悬疑", concept="角色设定",
                title="张三", instruction="我的角色卡",
                status="active", rev=1, src_kind="deconstruct",
                src_ref="task-" + suffix, src_key="张三",
                src_novel_name="我的书", origin="deconstruct",
            ))
            db.add(KbEntry(
                id=summary_id, user_id=uid, genre="悬疑", concept="手法",
                title="我的总结", instruction="我的总结正文",
                status="active", rev=1, src_kind="manual", origin="summary",
            ))
            db.add(KbEntry(
                id=manual_id, user_id=uid, genre="都市", concept="文风",
                title="我的手录", instruction="我的手录正文",
                status="active", rev=1, src_kind="manual", origin="manual",
            ))
            db.add(KbBookEntry(
                id=user_book_id, novel_id=novel_user, user_id=uid,
                genre="悬疑", concept="手法", title="我的拆书手法",
                instruction=user_text, src_kind="book_copy",
                src_ref=novel_user, src_key=material_id, evidence_json="{}",
            ))
            # ── 依赖行：官方侧 ──
            for entry_id in (promoted_id, material_id, card_id):
                db.add(KbEntryTag(
                    entry_id=entry_id, user_id=uid, dim="concept", value="手法",
                ))
                db.add(KbKnowledgeInstance(
                    knowledge_id=entry_id, text="实例-" + entry_id,
                    source_kind="拆书", quote="引文",
                ))
            db.add(KbKnowledgeRevision(
                knowledge_id=promoted_id, version=1, snapshot_json="{}",
            ))
            db.add(KbEntryBlob(entry_id=promoted_id, variant="full", data=b"x"))
            db.add(KbPref(user_id=uid, entry_id=base_id))
            db.add(KbPref(user_id=uid, entry_id=material_id))
            db.add(KbMatchItem(
                run_id="run-1", entry_id=base_id, text_snapshot=official_text,
            ))
            db.add(KbMatchItem(
                run_id="run-1", entry_id=material_id, text_snapshot=user_text,
            ))
            db.add(KbRelation(
                user_id=uid, from_id=promoted_id, to_id=manual_id,
                rel_type="related",
            ))
            db.add(KbRelation(
                user_id=uid, from_id=material_id, to_id=card_id,
                rel_type="related",
            ))
            db.add(KbLibraryItem(library_id="lib-1", entry_id=promoted_id))
            db.add(KbLibraryItem(library_id="lib-1", entry_id=material_id))
            db.add(KbOrganizeFinding(
                user_id=uid, kind="merge", subject_id=promoted_id,
                subject2_id=manual_id, signature="sig-" + suffix,
                payload_json=json.dumps({"surviving": manual_id, "merged": promoted_id}),
            ))
            db.add(KbOrganizeFeedback(
                user_id=uid, kind="merge", signature="fb-" + suffix, entry_id=promoted_id,
            ))
            db.add(KbEntryMerge(
                surviving_id=manual_id, merged_id=promoted_id, run_id="run-1",
            ))
            db.add(KbBookEntryTag(
                entry_id=official_book_id, novel_id=novel_official,
                user_id=uid, dim="concept", value="手法",
            ))
            db.add(KbBookEntryTag(
                entry_id=user_book_id, novel_id=novel_user,
                user_id=uid, dim="concept", value="手法",
            ))
            db.add(KbBookBinding(
                novel_id=novel_base, library_id="lib-1", enabled=True,
                snapshot_json=json.dumps({
                    "members": [
                        {"entry_id": official_book_id, "text": official_text},
                        {"entry_id": user_book_id, "text": user_text},
                    ]
                }, ensure_ascii=False),
            ))
            await db.commit()

    _run(_go())
    ids = {
        "uid": uid,
        "base_id": base_id,
        "promoted_id": promoted_id,
        "official_book_id": official_book_id,
        "baseline_book_id": baseline_book_id,
        "material_id": material_id,
        "card_id": card_id,
        "summary_id": summary_id,
        "manual_id": manual_id,
        "user_book_id": user_book_id,
        "official_text": official_text,
        "user_text": user_text,
        "novel_official": novel_official,
        "novel_base": novel_base,
        "novel_user": novel_user,
    }
    _CURRENT["ids"] = ids
    return ids


def test_撤回官方派生_保留用户拆书且幂等():
    from kb.revocation import apply_revocations, is_retired, plan_revocations

    _create_tables()
    ids = _seed()

    async def _plan():
        async with async_session() as db:
            return await plan_revocations(db)

    plan = _run(_plan())
    assert ids["base_id"] in plan["baseline_ids"]
    assert ids["promoted_id"] in plan["promoted_ids"]
    assert ids["official_book_id"] in plan["book_copy_ids"]
    assert ids["baseline_book_id"] in plan["book_copy_ids"]
    assert ids["user_book_id"] not in plan["book_copy_ids"]
    assert ids["material_id"] not in plan["promoted_ids"]
    assert ids["card_id"] not in plan["promoted_ids"]

    r1 = _run(apply_revocations(force=True))
    assert r1["status"] == "revoked"
    assert _run(is_retired()) is True

    async def _state():
        async with async_session() as db:
            return {
                "baseline": int((await db.execute(
                    select(func.count()).select_from(KbBaselineEntry))).scalar() or 0),
                "tags": int((await db.execute(
                    select(func.count()).select_from(KbBaselineTag))).scalar() or 0),
                "overlays": int((await db.execute(
                    select(func.count()).select_from(KbBaselineOverlay))).scalar() or 0),
                "promoted": int((await db.execute(
                    select(func.count()).select_from(KbEntry).where(
                        KbEntry.src_novel_name == "官方精选（已下架）"))).scalar() or 0),
                "official_books": int((await db.execute(
                    select(func.count()).select_from(KbBookEntry).where(
                        KbBookEntry.id.in_([ids["official_book_id"], ids["baseline_book_id"]])))).scalar() or 0),
                "user_rows": [
                    (
                        row.id, row.instruction, row.origin, row.src_kind,
                        row.src_ref, row.src_key,
                    )
                    for row in (await db.execute(
                        select(KbEntry).where(KbEntry.id.in_([
                            ids["material_id"], ids["card_id"],
                            ids["summary_id"], ids["manual_id"],
                        ])).order_by(KbEntry.id)
                    )).scalars().all()
                ],
                "user_book": int((await db.execute(
                    select(func.count()).select_from(KbBookEntry).where(
                        KbBookEntry.id == ids["user_book_id"]))).scalar() or 0),
                "user_instances": int((await db.execute(
                    select(func.count()).select_from(KbKnowledgeInstance).where(
                        KbKnowledgeInstance.knowledge_id.in_([
                            ids["material_id"], ids["card_id"],
                        ])))).scalar() or 0),
                "user_pref": int((await db.execute(
                    select(func.count()).select_from(KbPref).where(
                        KbPref.entry_id == ids["material_id"]))).scalar() or 0),
                "user_match": int((await db.execute(
                    select(func.count()).select_from(KbMatchItem).where(
                        KbMatchItem.entry_id == ids["material_id"]))).scalar() or 0),
                "user_relation": int((await db.execute(
                    select(func.count()).select_from(KbRelation).where(
                        KbRelation.from_id == ids["material_id"]))).scalar() or 0),
                "user_lib": int((await db.execute(
                    select(func.count()).select_from(KbLibraryItem).where(
                        KbLibraryItem.entry_id == ids["material_id"]))).scalar() or 0),
                "official_pref": int((await db.execute(
                    select(func.count()).select_from(KbPref).where(
                        KbPref.entry_id == ids["base_id"]))).scalar() or 0),
                "official_match": int((await db.execute(
                    select(func.count()).select_from(KbMatchItem).where(
                        KbMatchItem.entry_id == ids["base_id"]))).scalar() or 0),
                "official_relation": int((await db.execute(
                    select(func.count()).select_from(KbRelation).where(
                        KbRelation.from_id == ids["promoted_id"]))).scalar() or 0),
                "official_lib": int((await db.execute(
                    select(func.count()).select_from(KbLibraryItem).where(
                        KbLibraryItem.entry_id == ids["promoted_id"]))).scalar() or 0),
                "bindings": (await db.execute(
                    select(KbBookBinding).where(
                        KbBookBinding.novel_id == ids["novel_base"]
                    )
                )).scalars().all(),
            }

    state = _run(_state())
    assert state["baseline"] == 0
    assert state["tags"] == 0
    assert state["overlays"] == 0
    assert state["promoted"] == 0
    assert state["official_books"] == 0
    assert state["official_pref"] == 0
    assert state["official_match"] == 0
    assert state["official_relation"] == 0
    assert state["official_lib"] == 0
    # 用户侧四类条目一字未动
    assert {row[0] for row in state["user_rows"]} == {
        ids["material_id"], ids["card_id"], ids["summary_id"], ids["manual_id"],
    }
    assert all(row[1] != "" for row in state["user_rows"])
    assert state["user_book"] == 1
    assert state["user_instances"] == 2
    assert state["user_pref"] == 1
    assert state["user_match"] == 1
    assert state["user_relation"] == 1
    assert state["user_lib"] == 1
    # 绑定快照只删官方成员，用户成员保留
    assert len(state["bindings"]) == 1
    members = json.loads(state["bindings"][0].snapshot_json)["members"]
    assert [m["entry_id"] for m in members] == [ids["user_book_id"]]

    # 幂等：第二次零删除，用户侧仍不变
    r2 = _run(apply_revocations(force=True))
    assert r2["status"] == "revoked"
    assert r2["baseline_entries_deleted"] == 0
    assert r2["promoted_deleted"] == 0
    assert _run(_count(KbEntry, KbEntry.id == ids["material_id"])) == 1


def test_停用基线同步():
    from kb.baseline import sync_baseline
    from kb.revocation import apply_revocations

    _create_tables()
    _seed()
    _run(apply_revocations(force=True))
    result = _run(sync_baseline())
    assert result["status"] == "skipped"
    assert result["reason"] == "retired"


def test_uuid5兜底_未知版本书级副本删除_用户副本保留():
    """账本外的 uuid5 书级副本也删（旧版本/未登记包）；uuid4 用户副本保留。"""
    from kb.revocation import apply_revocations

    _create_tables()
    ids = _seed()
    unknown_entry_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, "https://ai-novel/kb-baseline/unknown")
    )
    unknown_book_id = _uid("bkunknown")

    async def _go():
        async with async_session() as db:
            db.add(KbBookEntry(
                id=unknown_book_id, novel_id="n-unknown-" + ids["uid"],
                user_id=ids["uid"], genre="都市", concept="手法",
                title="未知版本官方复制", instruction="未知版本官方正文",
                src_kind="book_copy", src_ref="n-unknown", src_key=unknown_entry_id,
                evidence_json="{}",
            ))
            await db.commit()

    _run(_go())
    _run(apply_revocations(force=True))
    assert _run(_count(KbBookEntry, KbBookEntry.id == unknown_book_id)) == 0
    assert _run(_count(KbBookEntry, KbBookEntry.id == ids["user_book_id"])) == 1


def test_伪装成官方的拆书_保留不删_其余照清():
    from kb.revocation import apply_revocations

    _create_tables()
    ids = _seed()
    bad_id = _uid("bad")

    async def _go():
        async with async_session() as db:
            db.add(KbEntry(
                id=bad_id, user_id=ids["uid"], genre="悬疑", concept="手法",
                title="伪装成官方的拆书", instruction="用户拆书正文",
                status="active", rev=1, src_kind="deconstruct",
                src_ref="task-x", src_key="technique:9",
                src_novel_name="官方精选（已下架）", origin="material",
            ))
            await db.commit()

    _run(_go())
    rv = _run(apply_revocations(force=True))
    assert rv["status"] == "revoked"
    assert rv["protected_user_rows"] >= 1
    # 用户拆书被保护；同批官方提升副本照删
    assert _run(_count(KbEntry, KbEntry.id == bad_id)) == 1
    assert _run(_count(KbEntry, KbEntry.id == ids["promoted_id"])) == 0
