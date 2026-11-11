"""官方基线撤回：清官方层与派生副本，保留用户自己的拆书/原创知识。

背景（2026-11-11 版权合规）：awesome-novel-knowledge 的基线包 v1/v2/v3
已从 CDN 全部撤下，但已装机用户的本地库仍有三类官方派生数据：

1. `kb_baseline_entries` / `kb_baseline_tags` / `kb_baseline_overlays`（官方层）
2. `kb_entries` 里 `src_novel_name='官方精选（已下架）'` 的提升副本
3. `kb_book_entries` 里从官方条目复制出去的书级副本

判定只认**溯源字段**，不按书名、不按正文相似度：
- 官方：`src_key` 在 `revoked_baseline.REVOKED_SRC_KEYS`，或书级副本的
  `src_key` 是官方 entry_id（uuid5），或带 `evidence_json.promoted_from`。
- 用户拆书：`src_kind='deconstruct'` / `origin in ('material','deconstruct',
  'book','summary')` —— 永不进删除集（函数内断言）。

幂等：`kb_revocation_v1` 标记 + 残留探针；carry/备份恢复后必须 `force=True`
重扫（新版本 DB 启动时是空的，旧数据由 carry 搬入）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import delete, func, or_, select

from kb.revoked_baseline import REVOKED_ENTRY_IDS, REVOKED_SRC_KEYS
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
    KbKnowledgeAlias,
    KbKnowledgeInstance,
    KbKnowledgeRevision,
    KbLibraryItem,
    KbMatchItem,
    KbOrganizeFeedback,
    KbOrganizeFinding,
    KbPref,
    KbRelation,
)

logger = logging.getLogger(__name__)

VERSION_KEY = "kb_baseline_version"
LAST_SYNC_KEY = "kb_baseline_last_sync"
RETIRED_KEY = "kb_baseline_retired"
MARKER_KEY = "kb_revocation_v1"
PROMOTED_SRC = "官方精选（已下架）"

# 用户自有知识的溯源白名单：这些 origin 永不删。
USER_ORIGINS = ("material", "deconstruct", "book", "summary")

_CHUNK = 400
_applied_in_process = False
_lock = asyncio.Lock()


def _chunks(ids: Sequence[str] | set[str], size: int = _CHUNK) -> Iterable[list[str]]:
    seq = list(ids)
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _is_uuid5(value: str) -> bool:
    """基线 entry_id 是 uuid5(NS, src_key)；用户条目 id 是 uuid4。"""
    try:
        return uuid.UUID(str(value)).version == 5
    except (ValueError, AttributeError, TypeError):
        return False


def _promoted_from(evidence_json: str | None) -> str:
    try:
        data = json.loads(evidence_json or "{}")
    except (TypeError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    value = data.get("promoted_from")
    return value if isinstance(value, str) else ""


def _json_references(blob: str | None, ids: set[str]) -> bool:
    """payload_json 里是否嵌了待删 id（组织建议的 revs/merge 载荷）。"""
    if not blob or not ids:
        return False
    try:
        data = json.loads(blob)
    except (TypeError, ValueError):
        return False

    def walk(node: Any) -> bool:
        if isinstance(node, str):
            return node in ids
        if isinstance(node, dict):
            return any(walk(k) or walk(v) for k, v in node.items())
        if isinstance(node, list):
            return any(walk(v) for v in node)
        return False

    return walk(data)


async def _set_meta(db, key: str, value: str) -> None:
    row = await db.get(AppMeta, key)
    if row is None:
        db.add(AppMeta(key=key, value=value))
    else:
        row.value = value


async def is_retired(db=None) -> bool:
    """官方基线是否已永久撤回（停用 CDN 同步）。"""
    if db is not None:
        row = await db.get(AppMeta, RETIRED_KEY)
        return bool(row and str(row.value) == "1")
    from db import async_session

    async with async_session() as session:
        row = await session.get(AppMeta, RETIRED_KEY)
        return bool(row and str(row.value) == "1")


def hooks_enabled() -> bool:
    """钩子总闸：测试/诊断用 `KB_REVOCATION=0` 关闭（直接调 apply 不受影响）。"""
    import os

    return (os.environ.get("KB_REVOCATION") or "").strip() != "0"


async def plan_revocations(db) -> dict[str, Any]:
    """只读计划：算出官方派生 id 集与计数，不删任何行。

    测试与 dry-run 都走这里；`apply_revocations` 复用同一口径。
    """
    local_baseline_ids = set(
        (await db.execute(select(KbBaselineEntry.entry_id))).scalars().all()
    )
    baseline_ids = set(REVOKED_ENTRY_IDS) | local_baseline_ids

    # 提升副本：哨兵名 + promoted_from 溯源（后者防哨兵被改名）。
    promoted_rows = (
        await db.execute(
            select(KbEntry.id, KbEntry.src_novel_name, KbEntry.evidence_json).where(
                or_(
                    KbEntry.src_novel_name == PROMOTED_SRC,
                    KbEntry.evidence_json.like("%promoted_from%"),
                )
            )
        )
    ).all()
    promoted_all = {
        row.id
        for row in promoted_rows
        if row.src_novel_name == PROMOTED_SRC
        or _promoted_from(row.evidence_json) in REVOKED_SRC_KEYS
    }
    # 硬保护：即使误挂哨兵，用户拆书/原创也不进删除集（宁可留一条官方残留，
    # 也不动用户自己的拆书知识）；命中只留 warning，不阻断其余清理。
    protected_ids: set[str] = set()
    for chunk in _chunks(promoted_all):
        protected_ids.update(
            (
                await db.execute(
                    select(KbEntry.id).where(
                        KbEntry.id.in_(chunk),
                        or_(
                            KbEntry.src_kind == "deconstruct",
                            KbEntry.origin.in_(USER_ORIGINS),
                        ),
                    )
                )
            ).scalars().all()
        )
    promoted_ids = promoted_all - protected_ids

    official_ids = baseline_ids | promoted_ids

    # 书级副本：官方层 id / 提升副本 id / promoted_from / uuid5 兜底。
    book_rows = (
        await db.execute(
            select(KbBookEntry.id, KbBookEntry.src_key, KbBookEntry.evidence_json)
        )
    ).all()
    book_copy_ids = {
        row.id
        for row in book_rows
        if row.src_key not in protected_ids
        and (
            row.src_key in official_ids
            or _promoted_from(row.evidence_json) in REVOKED_SRC_KEYS
            or _is_uuid5(row.src_key)
        )
    }

    counts = {
        "baseline_entries": len(local_baseline_ids),
        "baseline_tags": int(
            (await db.execute(select(func.count()).select_from(KbBaselineTag))).scalar() or 0
        ),
        "baseline_overlays": int(
            (await db.execute(select(func.count()).select_from(KbBaselineOverlay))).scalar() or 0
        ),
        "promoted_entries": len(promoted_ids),
        "book_copies": len(book_copy_ids),
        "protected_user_rows": len(protected_ids),
    }
    return {
        "baseline_ids": baseline_ids,
        "promoted_ids": promoted_ids,
        "protected_ids": protected_ids,
        "book_copy_ids": book_copy_ids,
        "counts": counts,
    }


async def _delete_by_ids(db, model, column, ids: set[str], label: str, counts: dict) -> int:
    total = 0
    for chunk in _chunks(ids):
        result = await db.execute(delete(model).where(column.in_(chunk)))
        total += int(result.rowcount or 0)
    counts[label] = counts.get(label, 0) + total
    return total


async def _clean_bindings(db, deleted_ids: set[str], counts: dict) -> None:
    """书级设定绑定快照里删掉官方成员；空快照则整条绑定删除。"""
    rows = (await db.execute(select(KbBookBinding))).scalars().all()
    touched = 0
    for binding in rows:
        try:
            snap = json.loads(binding.snapshot_json or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(snap, dict):
            continue
        members = snap.get("members")
        if not isinstance(members, list):
            continue
        kept = [
            m
            for m in members
            if not (isinstance(m, dict) and str(m.get("entry_id") or "") in deleted_ids)
        ]
        if len(kept) == len(members):
            continue
        touched += 1
        if kept:
            snap["members"] = kept
            binding.snapshot_json = json.dumps(snap, ensure_ascii=False)
        else:
            await db.delete(binding)
    counts["book_binding_snapshots"] = counts.get("book_binding_snapshots", 0) + touched


async def _clean_findings(db, deleted_ids: set[str], counts: dict) -> None:
    """组织建议：主体命中或 payload 引用命中即删（避免含官方正文的提案滞留）。"""
    rows = (await db.execute(select(KbOrganizeFinding))).scalars().all()
    total = 0
    for finding in rows:
        if (
            str(finding.subject_id or "") in deleted_ids
            or str(finding.subject2_id or "") in deleted_ids
            or _json_references(finding.payload_json, deleted_ids)
        ):
            await db.delete(finding)
            total += 1
    counts["organize_findings"] = counts.get("organize_findings", 0) + total


async def _apply(db, *, force: bool) -> dict[str, Any]:
    marker = await db.get(AppMeta, MARKER_KEY)
    baseline_left = int(
        (await db.execute(select(func.count()).select_from(KbBaselineEntry))).scalar() or 0
    )
    promoted_left = int(
        (
            await db.execute(
                select(func.count())
                .select_from(KbEntry)
                .where(KbEntry.src_novel_name == PROMOTED_SRC)
            )
        ).scalar()
        or 0
    )
    if marker is not None and not force and not baseline_left and not promoted_left:
        return {"status": "already", "marker": marker.value}

    plan = await plan_revocations(db)
    promoted_ids: set[str] = plan["promoted_ids"]
    book_copy_ids: set[str] = plan["book_copy_ids"]
    baseline_ids: set[str] = plan["baseline_ids"]
    protected_ids: set[str] = plan.get("protected_ids") or set()
    if protected_ids:
        logger.warning(
            "event=kb_revocation_protected_user_rows n=%d ids=%s",
            len(protected_ids), sorted(protected_ids)[:5],
        )

    account_ids = promoted_ids
    all_deleted = account_ids | book_copy_ids | baseline_ids
    counts: dict[str, int] = dict(plan["counts"])

    # 1) 书级副本先删（它们只是快照，不触发源条目级联）。
    await _delete_by_ids(db, KbBookEntry, KbBookEntry.id, book_copy_ids, "book_copies_deleted", counts)
    await _delete_by_ids(
        db, KbBookEntryTag, KbBookEntryTag.entry_id, book_copy_ids, "book_entry_tags", counts
    )

    # 2) 依赖行（无 FK 的手动清；有 FK 的也显式删，防 PRAGMA 关闭的边角）。
    await _delete_by_ids(db, KbEntryTag, KbEntryTag.entry_id, account_ids, "entry_tags", counts)
    await _delete_by_ids(db, KbEntryBlob, KbEntryBlob.entry_id, account_ids, "entry_blobs", counts)
    await _delete_by_ids(
        db, KbKnowledgeInstance, KbKnowledgeInstance.knowledge_id, account_ids, "instances", counts
    )
    await _delete_by_ids(
        db, KbKnowledgeAlias, KbKnowledgeAlias.knowledge_id, account_ids, "aliases", counts
    )
    await _delete_by_ids(
        db, KbKnowledgeRevision, KbKnowledgeRevision.knowledge_id, account_ids, "revisions", counts
    )
    await _delete_by_ids(db, KbLibraryItem, KbLibraryItem.entry_id, account_ids, "library_items", counts)
    await _delete_by_ids(
        db, KbOrganizeFeedback, KbOrganizeFeedback.entry_id, account_ids, "organize_feedback", counts
    )
    await _delete_by_ids(db, KbPref, KbPref.entry_id, all_deleted, "prefs", counts)
    await _delete_by_ids(db, KbMatchItem, KbMatchItem.entry_id, all_deleted, "match_items", counts)
    for chunk in _chunks(all_deleted):
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
    await _clean_findings(db, all_deleted, counts)
    await _clean_bindings(db, all_deleted, counts)

    # 3) 提升副本本身（级联实例/别名/版本；上面已显式删过）。
    await _delete_by_ids(db, KbEntry, KbEntry.id, account_ids, "promoted_deleted", counts)

    # 4) 官方层三表全撤。
    for model, label in (
        (KbBaselineTag, "baseline_tags_deleted"),
        (KbBaselineOverlay, "baseline_overlays_deleted"),
        (KbBaselineEntry, "baseline_entries_deleted"),
    ):
        result = await db.execute(delete(model))
        counts[label] = int(result.rowcount or 0)

    # 5) 标记：停用同步、版本归零、留审计计数。
    await _set_meta(db, VERSION_KEY, "0")
    await _set_meta(
        db,
        LAST_SYNC_KEY,
        json.dumps({"status": "revoked", "version": 0, "counts": counts}, ensure_ascii=False),
    )
    await _set_meta(db, RETIRED_KEY, "1")
    await _set_meta(
        db,
        MARKER_KEY,
        json.dumps(
            {"at": "v0.47.4", "src_keys": len(REVOKED_SRC_KEYS), "counts": counts},
            ensure_ascii=False,
        ),
    )
    await db.commit()

    global _applied_in_process
    _applied_in_process = True
    return {"status": "revoked", **counts}


async def apply_revocations(db=None, *, force: bool = False) -> dict[str, Any]:
    """执行撤回（幂等）。`force=True` 用于 carry / 备份恢复后重扫。"""
    async with _lock:
        if db is not None:
            return await _apply(db, force=force)
        from db import async_session

        async with async_session() as session:
            return await _apply(session, force=force)


async def revoke_official_baseline(*, force: bool = False) -> dict[str, Any]:
    """启动/读面钩子用：失败只留痕，不挡启动（下次重试）。

    `KB_REVOCATION=0` 关闭（测试/诊断用）：conftest 在导入 app 前设 0，
    避免 TestClient 的 lifespan 在共享测试库上真跑全局撤回、污染其它 KB 用例。
    直接调用 `apply_revocations` 不受此闸影响（撤回逻辑本身由专门用例覆盖）。
    """
    if not hooks_enabled():
        return {"status": "skipped", "reason": "disabled"}
    if _applied_in_process and not force:
        return {"status": "already", "reason": "process"}
    try:
        return await apply_revocations(force=force)
    except Exception:  # noqa: BLE001 — 合规清理失败不能挡启动
        logger.warning("event=kb_revocation_failed", exc_info=True)
        return {"status": "failed"}
