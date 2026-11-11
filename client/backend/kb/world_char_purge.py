"""清掉已撤回书籍的拆书派生内容：KB「世界设定/角色设定」＋任务产物 world/characters 段。

背景（boss 2026-11-11 拍板）：v0.47.4 只清官方基线层，用户自己的拆书产物
（`src_kind='deconstruct'` / `origin='material'`）按约定保留。但本机实测发现，
用户拆书库里仍存有五本撤回书（13路末班车/斩神/749收容怪物/十宗罪/顶级灵异小说家）
的世界设定/角色设定/角色库迁移卡，与已撤回基线同源。本模块清这些书的**世界/角色**：

- 删 KB：五本书的 deconstruct 世界/角色条目、character_library_migration 角色卡、
  以及全部实例都来自这五本书的 `origin='summary'` 世界/角色总结节点；
  连带书级副本、实例、版本、标签、关系、库成员、匹配项、绑定快照、旧角色库卡与头像。
- 剥产物（v0.47.7 拔根）：五本书拆书任务 `products_json` 里的 `world`/`characters`
  两段——version_reconcile 每个大版本会从产物全量重收（app_meta 不随 carry，
  reconcile 标记重置），不剥则世界/角色每次升级都复活一次再被清一遍；剥掉种子
  即终结循环。其余 dim（genre/style/techniques/relations…）原样保留——genre
  必须在，否则空产物会让重收恒 collect_fail。
- 不删：手法/文风/文笔（含这五本书的）、其他书的拆书、用户手录、以及
  手法/文风/文笔的总结节点。

已记录残留（不进知识库、不复活，本模块不动）：任务 `dims_json.state.graph` 里的
世界/角色图谱节点；`relations`（人物关系与势力）dim。

书名匹配统一走 `_norm_book` 归一（剥 `-前N章` 试拆后缀）——部分拆书任务
（如 `斩神-前30章`）与全本同书命中。

幂等：`kb_world_char_purge_v1` 标记；carry/备份恢复后必须 `force=True` 重扫。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import delete, or_, select

from kb.revocation import (
    _chunks,
    _clean_bindings,
    _clean_findings,
    _delete_by_ids,
    hooks_enabled,
)
from models.app_meta import AppMeta
from models.character_library import CharacterLibrary, CharacterLibraryBlob
from models.deconstruct import DeconstructJob
from models.kb import (
    KbBookEntry,
    KbBookEntryTag,
    KbEntry,
    KbEntryBlob,
    KbEntryMerge,
    KbEntryTag,
    KbKnowledgeAlias,
    KbKnowledgeInstance,
    KbKnowledgeRevision,
    KbLibraryItem,
    KbMatchItem,
    KbOrganizeFeedback,
    KbPref,
    KbRelation,
)

logger = logging.getLogger(__name__)

MARKER_KEY = "kb_world_char_purge_v1"
# 规范化书名（_norm_book 剥 -前N章 试拆后缀后的名字）。
WITHDRAWN_BOOKS = (
    "13路末班车", "斩神", "749收容怪物", "十宗罪", "顶级灵异小说家",
)
WORLD_CHAR_CONCEPTS = ("世界设定", "角色设定")
# 拆书任务产物里剥掉的维度（与 KB 清理同边界）。
STRIP_PRODUCT_DIMS = ("world", "characters")


def _is_withdrawn_book(name: str) -> bool:
    """书名归一后命中撤回书单（斩神-前30章 → 斩神 → 命中）。

    每次从 WITHDRAWN_BOOKS 活值构建集合：测试 monkeypatch 书单即时生效。
    """
    from kb.version_reconcile import _norm_book

    return _norm_book(name) in {_norm_book(b) for b in WITHDRAWN_BOOKS}

_applied_in_process = False
_last_probe = 0.0
_lock = asyncio.Lock()


async def plan_world_char_purge(db, *, user_id: str | None = None) -> dict[str, Any]:
    """只读计划：返回待删条目/书副本/旧角色库卡 id 与计数。

    `user_id` 仅用于测试/单账号清理；生产钩子不传＝全账号。
    """
    filters = [KbEntry.concept.in_(WORLD_CHAR_CONCEPTS)]
    if user_id:
        filters.append(KbEntry.user_id == user_id)
    rows = (
        await db.execute(
            select(
                KbEntry.id,
                KbEntry.origin,
                KbEntry.src_kind,
                KbEntry.src_novel_name,
            ).where(*filters)
        )
    ).all()

    entry_ids: set[str] = set()
    for row in rows:
        if row.origin == "summary":
            books = (
                await db.execute(
                    select(KbKnowledgeInstance.source_novel).where(
                        KbKnowledgeInstance.knowledge_id == row.id
                    )
                )
            ).scalars().all()
            # 空节点（无实例）＝纯分类壳，直接删；有实例的只在全部来自撤回书单时删，
            # 混合来源的保留，避免误伤其他书。
            if not books or all(_is_withdrawn_book(b or "") for b in books):
                entry_ids.add(row.id)
            continue
        if (
            row.src_kind in ("deconstruct", "character_library_migration")
            and _is_withdrawn_book(row.src_novel_name or "")
        ):
            entry_ids.add(row.id)

    book_copy_ids: set[str] = set()
    if entry_ids:
        book_filters = [KbBookEntry.src_key.in_(entry_ids)]
        if user_id:
            book_filters.append(KbBookEntry.user_id == user_id)
        book_copy_ids = set(
            (
                await db.execute(select(KbBookEntry.id).where(*book_filters))
            ).scalars().all()
        )

    lib_filters = [CharacterLibrary.src_novel_name.in_(WITHDRAWN_BOOKS)]
    if user_id:
        lib_filters.append(CharacterLibrary.user_id == user_id)
    library_ids = set(
        (
            await db.execute(select(CharacterLibrary.id).where(*lib_filters))
        ).scalars().all()
    )

    # 拆书任务产物：书名 LIKE 前缀粗筛（SQL 面）＋归一精判（Python 面），只装
    # 命中任务的轻量列，避免全表 products_json 进内存。
    job_filters = [
        or_(*[DeconstructJob.book_name.like(f"{b}%") for b in WITHDRAWN_BOOKS])
    ]
    if user_id:
        job_filters.append(DeconstructJob.user_id == user_id)
    job_rows = (
        await db.execute(
            select(DeconstructJob.id, DeconstructJob.book_name).where(*job_filters)
        )
    ).all()
    product_job_ids = [
        row.id for row in job_rows if _is_withdrawn_book(row.book_name)
    ]

    counts = {
        "entries": len(entry_ids),
        "book_copies": len(book_copy_ids),
        "library_cards": len(library_ids),
        "products": len(product_job_ids),
    }
    return {
        "entry_ids": entry_ids,
        "book_copy_ids": book_copy_ids,
        "library_ids": library_ids,
        "product_job_ids": product_job_ids,
        "counts": counts,
    }


async def _apply(db, *, force: bool, user_id: str | None = None) -> dict[str, Any]:
    marker = await db.get(AppMeta, MARKER_KEY)
    plan = await plan_world_char_purge(db, user_id=user_id)
    entry_ids: set[str] = plan["entry_ids"]
    book_copy_ids: set[str] = plan["book_copy_ids"]
    library_ids: set[str] = plan["library_ids"]
    product_job_ids: list[str] = plan["product_job_ids"]
    if (
        marker is not None and not force
        and not entry_ids and not book_copy_ids and not library_ids
        and not product_job_ids
    ):
        return {"status": "already", "marker": marker.value}

    counts: dict[str, int] = dict(plan["counts"])
    all_ids = entry_ids | book_copy_ids

    # 1) 书级副本先删。
    await _delete_by_ids(db, KbBookEntry, KbBookEntry.id, book_copy_ids, "book_copies_deleted", counts)
    await _delete_by_ids(
        db, KbBookEntryTag, KbBookEntryTag.entry_id, book_copy_ids, "book_entry_tags", counts
    )

    # 2) 条目依赖行（与 v0.47.4 撤回同一套；无 FK 的手动清）。
    await _delete_by_ids(db, KbEntryTag, KbEntryTag.entry_id, entry_ids, "entry_tags", counts)
    await _delete_by_ids(db, KbEntryBlob, KbEntryBlob.entry_id, entry_ids, "entry_blobs", counts)
    await _delete_by_ids(
        db, KbKnowledgeInstance, KbKnowledgeInstance.knowledge_id, entry_ids, "instances", counts
    )
    await _delete_by_ids(
        db, KbKnowledgeAlias, KbKnowledgeAlias.knowledge_id, entry_ids, "aliases", counts
    )
    await _delete_by_ids(
        db, KbKnowledgeRevision, KbKnowledgeRevision.knowledge_id, entry_ids, "revisions", counts
    )
    await _delete_by_ids(db, KbLibraryItem, KbLibraryItem.entry_id, entry_ids, "library_items", counts)
    await _delete_by_ids(
        db, KbOrganizeFeedback, KbOrganizeFeedback.entry_id, entry_ids, "organize_feedback", counts
    )
    await _delete_by_ids(db, KbPref, KbPref.entry_id, all_ids, "prefs", counts)
    await _delete_by_ids(db, KbMatchItem, KbMatchItem.entry_id, all_ids, "match_items", counts)
    for chunk in _chunks(all_ids):
        result = await db.execute(
            delete(KbRelation).where(
                or_(KbRelation.from_id.in_(chunk), KbRelation.to_id.in_(chunk))
            )
        )
        counts["relations"] = counts.get("relations", 0) + int(result.rowcount or 0)
        result = await db.execute(
            delete(KbEntryMerge).where(
                or_(KbEntryMerge.surviving_id.in_(chunk), KbEntryMerge.merged_id.in_(chunk))
            )
        )
        counts["entry_merges"] = counts.get("entry_merges", 0) + int(result.rowcount or 0)
    await _clean_findings(db, all_ids, counts)
    await _clean_bindings(db, all_ids, counts)

    # 3) 条目本身；4) 旧角色库卡与头像（防 ensure_legacy_migrated 再迁回来）。
    await _delete_by_ids(db, KbEntry, KbEntry.id, entry_ids, "entries_deleted", counts)
    await _delete_by_ids(
        db, CharacterLibraryBlob, CharacterLibraryBlob.library_id, library_ids,
        "library_blobs", counts,
    )
    await _delete_by_ids(
        db, CharacterLibrary, CharacterLibrary.id, library_ids, "library_cards_deleted", counts
    )

    # 5) 产物剥除（v0.47.7 拔根）：world/characters 键从 products_json 删除。
    #    genre 等其余 dim 原样保留（空产物会让 version_reconcile 恒 collect_fail）。
    stripped_tasks = 0
    stripped_dims = 0
    for chunk in _chunks(product_job_ids):
        rows = (
            await db.execute(
                select(DeconstructJob).where(DeconstructJob.id.in_(chunk))
            )
        ).scalars().all()
        for job in rows:
            try:
                products = json.loads(job.products_json or "{}")
            except (TypeError, ValueError):
                continue
            if not isinstance(products, dict):
                continue
            removed = [dim for dim in STRIP_PRODUCT_DIMS if dim in products]
            if not removed:
                continue
            for dim in removed:
                products.pop(dim, None)
            job.products_json = json.dumps(products, ensure_ascii=False)
            stripped_tasks += 1
            stripped_dims += len(removed)
    counts["products_stripped"] = counts.get("products_stripped", 0) + stripped_tasks
    counts["product_dims_removed"] = (
        counts.get("product_dims_removed", 0) + stripped_dims
    )

    deleted_total = sum(
        v for k, v in counts.items() if k.endswith("_deleted")
    )
    if deleted_total == 0 and not counts.get("products_stripped") and marker is None:
        # 新装/空库：不写 marker，等 carry/恢复后 force 重扫（同 v0.47.4 口径）。
        await db.commit()
        return {"status": "clean", **counts}

    payload = json.dumps(
        {"at": "v0.47.7", "books": list(WITHDRAWN_BOOKS), "counts": counts},
        ensure_ascii=False,
    )
    if marker is None:
        db.add(AppMeta(key=MARKER_KEY, value=payload))
    else:
        marker.value = payload
    await db.commit()

    global _applied_in_process
    _applied_in_process = True
    return {"status": "purged", **counts}


async def apply_world_char_purge(
    db=None, *, force: bool = False, user_id: str | None = None
) -> dict[str, Any]:
    """执行清理（幂等）。carry/备份恢复后必须 `force=True`。

    `user_id` 只给测试/单账号清理用；生产钩子不传＝全账号。
    """
    async with _lock:
        if db is not None:
            return await _apply(db, force=force, user_id=user_id)
        from db import async_session

        async with async_session() as session:
            return await _apply(session, force=force, user_id=user_id)


async def purge_withdrawn_world_char(*, force: bool = False) -> dict[str, Any]:
    """启动/读面钩子：测试态 `KB_REVOCATION=0` 关闭；失败只留痕。"""
    global _last_probe
    if not hooks_enabled():
        return {"status": "skipped", "reason": "disabled"}
    if _applied_in_process and not force:
        return {"status": "already", "reason": "process"}
    now = asyncio.get_running_loop().time()
    if not force and now - _last_probe < 60:
        return {"status": "already", "reason": "throttle"}
    _last_probe = now
    try:
        return await apply_world_char_purge(force=force)
    except Exception:  # noqa: BLE001 — 清理失败不挡启动
        logger.warning("event=kb_world_char_purge_failed", exc_info=True)
        return {"status": "failed"}
