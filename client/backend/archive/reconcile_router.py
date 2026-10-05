"""归档收尾提案端点（archive-reconcile）。

GET  /reconcile?chapter_id=      行列表＋聚合进度
POST /reconcile/{row_id}/accept  采纳：经目标对象自身服务写回（单次应用）
POST /reconcile/{row_id}/reject  驳回：仅标记
POST /reconcile/{row_id}/retry   对该章重跑该类收尾 AI（同键覆盖未决行）

读取/操作须登录；收尾 AI 的 PRO 门控在归档入口（lore=会员门控）已判定——
免费档不产生收尾行，此处行不存在即 404，无需重复判会员。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import ai_feature, get_current_user, require_ai_access, require_novel_model
from db import get_db
from models.project import Novel
from models.reconcile import ChapterReconcile

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/reconcile",
    tags=["reconcile"],
)


def _row_dict(row: ChapterReconcile) -> dict:
    import json as _json

    try:
        payload = _json.loads(row.payload or "{}")
    except Exception:  # noqa: BLE001
        payload = {}
    return {
        "id": row.id,
        "chapter_id": row.chapter_id,
        "kind": row.kind,
        "status": row.status,
        "payload": payload,
        "error": row.error,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "decided_at": row.decided_at.isoformat() if row.decided_at else "",
    }


async def _chapter_by_ref(
    db: AsyncSession, project_id: str, chapter_ref: str, user: dict
):
    from models.chapter import Chapter
    from models.project import Novel

    ch = (
        await db.scalars(
            select(Chapter).where(
                Chapter.project_id == project_id, Chapter.ref == chapter_ref
            )
        )
    ).first()
    if ch is None:
        raise HTTPException(404, "Chapter not found")
    novel = await db.get(Novel, project_id)
    if novel is None or novel.user_id != user["id"]:
        raise HTTPException(404, "Chapter not found")
    return ch


async def _load_owned_row(db: AsyncSession, row_id: str, user_id: str) -> ChapterReconcile:
    row = await db.get(ChapterReconcile, row_id)
    if row is None:
        raise HTTPException(404, "提案不存在")
    novel = await db.get(Novel, row.novel_id)
    if novel is None or novel.user_id != user_id:
        raise HTTPException(404, "提案不存在")
    return row


@router.get("")
async def list_reconcile(
    chapter_ref: str,
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ch = await _chapter_by_ref(db, project_id, chapter_ref, user)
    rows = (
        await db.scalars(
            select(ChapterReconcile)
            .where(ChapterReconcile.chapter_id == ch.id)
            .order_by(ChapterReconcile.created_at)
        )
    ).all()
    items = [_row_dict(r) for r in rows]
    progress = {
        "pending": sum(1 for i in items if i["status"] == "pending"),
        "failed": sum(1 for i in items if i["status"] == "failed"),
        "accepted": sum(1 for i in items if i["status"] == "accepted"),
        "rejected": sum(1 for i in items if i["status"] == "rejected"),
    }
    return {"rows": items, "progress": progress}


@router.post("/{row_id}/accept")
async def accept(
    row_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _load_owned_row(db, row_id, user["id"])
    if row.status != "pending":
        raise HTTPException(409, "该提案已处理")
    from archive.reconcile import apply_accept

    try:
        await apply_accept(db, row)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — 写回失败保留 payload 供重试
        row.status = "failed"
        row.error = str(e)[:500]
        row.decided_at = datetime.now(UTC).replace(tzinfo=None)
        await db.commit()
        raise HTTPException(502, f"写回失败：{e}") from e
    # 提交行状态迁移（accepted＋decided_at）——此前缺 commit，接口 200 但
    # 状态未落库（前端轮询永远看到待确认；e2e 全链撕出）
    await db.commit()
    return {"ok": True, "row": _row_dict(row)}


@router.post("/{row_id}/reject")
async def reject(
    row_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _load_owned_row(db, row_id, user["id"])
    if row.status != "pending":
        raise HTTPException(409, "该提案已处理")
    row.status = "rejected"
    row.decided_at = datetime.now(UTC).replace(tzinfo=None)
    await db.commit()
    return {"ok": True}


@router.post("/run")
async def run_now(
    chapter_ref: str,
    project_id: str,
    body: dict | None = None,
    user: dict = Depends(get_current_user),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """按需触发本章收尾（工作台右栏 AI 辅助入口）：body.kind 限一类，缺省全量。

    产出仍走提案制（chapter_reconcile 待确认行，在「操作」页签逐条确认）。"""
    ch = await _chapter_by_ref(db, project_id, chapter_ref, user)
    kind = str((body or {}).get("kind", "") or "").strip()
    from archive.reconcile import KINDS as _KINDS
    from archive.reconcile import start_reconcile_job

    if kind and kind not in _KINDS:
        raise HTTPException(400, f"未知的收尾类别：{kind}")
    novel = await db.get(Novel, ch.project_id)
    job = start_reconcile_job(
        novel.id, novel.root_path, ch.ref, ch.id, kinds=[kind] if kind else None
    )
    return {"ok": True, "started": bool(job), "kind": kind or None}


@router.post("/{row_id}/retry")
async def retry(
    row_id: str,
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """失败行重试：对该章重跑该类收尾 AI（同键覆盖未决行）。"""
    row = await _load_owned_row(db, row_id, user["id"])
    if row.status != "failed":
        raise HTTPException(409, "仅失败行可重试")
    ch, novel = await _chapter_and_novel(db, row.chapter_id)
    from archive.reconcile import start_reconcile_job

    job = start_reconcile_job(novel.id, novel.root_path, ch.ref, ch.id)
    return {"ok": True, "started": bool(job)}


async def _chapter_and_novel(db: AsyncSession, chapter_id: str):
    from models.chapter import Chapter

    ch = await db.get(Chapter, chapter_id)
    if ch is None:
        raise HTTPException(404, "Chapter not found")
    novel = await db.get(Novel, ch.project_id)
    if novel is None:
        raise HTTPException(404, "Novel not found")
    return ch, novel
