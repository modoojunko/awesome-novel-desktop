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
RECONNECT_DONE_KEY = "kb_baseline_reconnect_done"

# 接回版本界（c-kb-baseline-reconnect，2026-11-22）：官方基线 v5（8197 条蒸馏
# 写法，audit 全 clean、rights 全 distilled_ideas_only）已过 CI 签名上 CDN——
# 11-11 撤回时代的「见官方层即清」收窄为「只清低于本版本的行」：
#   - v1-v4 行＝撤回内容，任何自动路径仍清（合规）；
#   - v5+ 行＝合法内容，boot/迁移搬运后/备份恢复后 SHALL NOT 删除；
#   - `kb_baseline_retired` 戳退役自动打点（is_retired 保留为手动合规急刹：
#     手动置 1 全局停同步）。
# 未来再撤某版时的人工口径：改本常量→手动置 retired=1→（可选）force 清理。
RECONNECT_PACK_VERSION = 5
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


async def ensure_reconnected(db=None) -> bool:
    """一次性接回过渡（c-kb-baseline-reconnect）：存量客户端清 retired 戳＋落
    接回标记。幂等（标记在/本来没戳＝零动作）；v5 起同步由此恢复消费。

    合规急刹不受影响：手动重置 `kb_baseline_retired=1` 后，本函数因接回标记
    已在而不再清除——急刹需要解除时同样手动操作。
    `KB_REVOCATION=0` 同闸（测试/诊断用）：与撤回家族共享同一测试开关。"""
    if not hooks_enabled():
        return False
    from db import async_session

    async def _ensure(session) -> bool:
        row = await session.get(AppMeta, RETIRED_KEY)
        done = await session.get(AppMeta, RECONNECT_DONE_KEY)
        if done is not None or row is None or str(row.value) != "1":
            return False
        await session.delete(row)
        session.add(AppMeta(key=RECONNECT_DONE_KEY, value="1"))
        await session.commit()
        logger.info("event=kb_baseline_reconnect applied")
        return True

    if db is not None:
        return await _ensure(db)
    async with async_session() as session:
        return await _ensure(session)


async def plan_revocations(db) -> dict[str, Any]:
    """只读计划：算出官方派生 id 集与计数，不删任何行。

    测试与 dry-run 都走这里；`apply_revocations` 复用同一口径。

    c-kb-baseline-reconnect：计划只覆盖**低于接回版本**的官方基线行（v1-v4＝
    撤回内容）；v5+ 行是合法内容， SHALL NOT 进删除集——书级副本的 uuid5 兜底
    同步排除接回行的 src_key（否则改名兜底会误杀 v5 派生副本）。
    """
    local_baseline_ids = set(
        (
            await db.execute(
                select(KbBaselineEntry.entry_id).where(
                    KbBaselineEntry.pack_version < RECONNECT_PACK_VERSION
                )
            )
        ).scalars().all()
    )
    reconnected_ids = set(
        (
            await db.execute(
                select(KbBaselineEntry.entry_id).where(
                    KbBaselineEntry.pack_version >= RECONNECT_PACK_VERSION
                )
            )
        ).scalars().all()
    ) - set(REVOKED_ENTRY_IDS)  # 硬闸优先：撤回清单命中行即使版本达标也照清
    stale_src_keys = set(
        (
            await db.execute(
                select(KbBaselineEntry.src_key).where(
                    KbBaselineEntry.pack_version < RECONNECT_PACK_VERSION
                )
            )
        ).scalars().all()
    ) | set(REVOKED_SRC_KEYS)
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
        and row.src_key not in reconnected_ids
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
        "reconnected_ids": reconnected_ids,
        "stale_src_keys": stale_src_keys,
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


def _marker_reconnect_version(marker: AppMeta | None) -> int:
    """marker 记录的接回版本界：旧撤回态 marker（无该字段）按 0 读＝必然重入
    一次以落新语义（真清 0 行＋写新 marker）。"""
    if marker is None:
        return 0
    try:
        return int(json.loads(str(marker.value)).get("reconnect_version") or 0)
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0


async def _apply(db, *, force: bool) -> dict[str, Any]:
    marker = await db.get(AppMeta, MARKER_KEY)
    # 幂等跳过＝marker 已是本接回版本界＋低于界的行已清零＋无晋升残留。
    # v5+ 行在库（baseline_left>0）不再阻止跳过——它们不是撤回对象。
    stale = int(
        (
            await db.execute(
                select(func.count())
                .select_from(KbBaselineEntry)
                .where(KbBaselineEntry.pack_version < RECONNECT_PACK_VERSION)
            )
        ).scalar()
        or 0
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
    if (
        marker is not None
        and not force
        and _marker_reconnect_version(marker) >= RECONNECT_PACK_VERSION
        and not stale
        and not promoted_left
    ):
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

    # 4) 官方层三表撤低版本行（c-kb-baseline-reconnect）：v1-v4＝撤回内容照清
    #    （含撤回清单命中行）；v5+ 行（含其用户 overlay/标签——合法数据）SHALL
    #    NOT 被自动路径删除。overlay 按 src_key 关联（无 entry_id 列）。
    stale_baseline_ids = set(baseline_ids)
    for model, id_col, label in (
        (KbBaselineTag, KbBaselineTag.entry_id, "baseline_tags_deleted"),
        (KbBaselineOverlay, KbBaselineOverlay.src_key, "baseline_overlays_deleted"),
        (KbBaselineEntry, KbBaselineEntry.entry_id, "baseline_entries_deleted"),
    ):
        result = await db.execute(
            delete(model).where(id_col.in_(stale_baseline_ids | plan["stale_src_keys"]))
        )
        counts[label] = int(result.rowcount or 0)

    # 5) 标记：只有真清了低于接回版本的行才重置基线层版本记账（触发重同步拉
    #    新版）；`kb_baseline_retired` 退役自动打点（c-kb-baseline-reconnect）——
    #    合规急刹走手动置位，代码 SHALL NOT 自动盖戳。
    purged_any = any(
        counts.get(k, 0) > 0
        for k in ("baseline_entries_deleted", "promoted_deleted", "book_copies_deleted")
    )
    if purged_any:
        await _set_meta(db, VERSION_KEY, "0")
        await _set_meta(
            db,
            LAST_SYNC_KEY,
            json.dumps(
                {"status": "revoked", "version": 0, "counts": counts}, ensure_ascii=False
            ),
        )
    await _set_meta(
        db,
        MARKER_KEY,
        json.dumps(
            {
                "at": f"reconnect-{RECONNECT_PACK_VERSION}",
                "reconnect_version": RECONNECT_PACK_VERSION,
                "src_keys": len(REVOKED_SRC_KEYS),
                "purged_below": counts.get("baseline_entries_deleted", 0),
                "counts": counts,
            },
            ensure_ascii=False,
        ),
    )
    await db.commit()

    global _applied_in_process
    _applied_in_process = True
    status = "revoked" if purged_any else "already"
    return {"status": status, **counts}


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
