"""章档端点族（c-chapter-dossier）。

章级（/api/novels/{pid}/chapters/{ref}/dossier）：
- GET            单章四域行＋进度＋提取任务态＋stale/未归档标注（页签一次往返）
- POST /rows/{id}    逐条动作（accept/reject/restore）
- DELETE /rows/{id}  删除已采纳行（退出后续提示词组装）
- POST /rows         批量动作（按域或全章 accept/reject）
- POST /extract      重试/补提取（未归档章＝完整归档提取；已归档章＝只重写章档行）
- POST /skip         逃生阀：跳过提取仍归档（首次失败后出现，前端控制）

书级（/api/novels/{pid}/dossier）：
- GET /preview?up_to_ref=   「截至本章」累计预览——消费装配同一折叠单源，前端不重算

读取/操作须登录；提取全档可用（不挂会员门）——门控＝本书模型就绪。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from archive.dossier import accept_extraction, get_job_state, prose_sha256
from auth_local.deps import get_current_user
from db import get_db
from models.project import Novel

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/dossier",
    tags=["dossier"],
)

book_router = APIRouter(
    prefix="/api/novels/{project_id}/dossier",
    tags=["dossier"],
)

# 域键（章 JSON dossier 四键，与前端/页签一致）
DOMAINS = ("settings", "relations", "items", "knowledge")


async def _chapter_by_ref(db: AsyncSession, project_id: str, chapter_ref: str, user: dict):
    from models.chapter import Chapter

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
    return ch, novel


def _row_out(row, domain: str) -> dict:
    base = {
        "id": row.id,
        "domain": domain,
        "status": row.status,
        "flags": row.flags,
        "evidence": row.evidence,
        "decided_at": row.decided_at.isoformat() if row.decided_at else "",
    }
    if domain == "settings":
        base.update({"area": row.area, "content": row.content})
    elif domain == "relations":
        base.update({
            "owner": row.owner_name, "other": row.other_name,
            "rel_type": row.rel_type, "change_note": row.change_note,
        })
    elif domain == "items":
        base.update({
            "name": row.item_name, "change_type": row.change_type,
            "holder": row.holder_name, "detail": row.detail,
        })
    else:
        base.update({"character": row.character_name, "fact": row.fact, "learned": row.learned})
    return base


@router.get("")
async def get_dossier(
    chapter_ref: str,
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ch, _novel = await _chapter_by_ref(db, project_id, chapter_ref, user)
    groups = {
        "settings": ch.dossier_settings,
        "relations": ch.dossier_relations,
        "items": ch.dossier_items,
        "knowledge": ch.dossier_knowledge,
    }
    rows = [_row_out(r, d) for d in DOMAINS for r in groups[d]]
    progress = {
        "pending": sum(1 for r in rows if r["status"] == "pending"),
        "accepted": sum(1 for r in rows if r["status"] == "accepted"),
        "rejected": sum(1 for r in rows if r["status"] == "rejected"),
    }
    extraction = await get_job_state(ch.id)
    return {
        "rows": rows,
        "progress": progress,
        "extraction": extraction,
        # 未提取态：已归档但无 job 行且无章档行（模型未就绪放行/逃生阀跳过后的补提取入口）
        "not_extracted": ch.status == "archived"
        and extraction is None and not rows,
        "stale": ch.dossier_stale,
        "archived": ch.status == "archived",
        # 重归档覆盖警示素材：已采纳条数
        "accepted_count": progress["accepted"],
    }


async def _load_owned_dossier_row(db: AsyncSession, row_id: str, user: dict):
    from models.chapter import (
        Chapter,
        ChapterItemChange,
        ChapterKnowledgeChange,
        ChapterRelationChange,
        ChapterSettingChange,
    )

    for domain, model in (
        ("settings", ChapterSettingChange),
        ("relations", ChapterRelationChange),
        ("items", ChapterItemChange),
        ("knowledge", ChapterKnowledgeChange),
    ):
        row = await db.get(model, row_id)
        if row is not None:
            # 所有权：用已加载行的 chapter_id 值联查（勿把 model.chapter_id 列表达式
            # 写进 WHERE——该表不在 FROM 里会隐式交叉连接，随机命中另一本书）
            novel = (
                await db.scalars(
                    select(Novel)
                    .join(Chapter, Chapter.project_id == Novel.id)
                    .where(Chapter.id == row.chapter_id)
                )
            ).first()
            if novel is None or novel.user_id != user["id"]:
                raise HTTPException(404, "章档行不存在")
            return row, domain
    raise HTTPException(409, "章档已重新提取，请重新确认")


def _decide(row, action: str):
    if action == "accept":
        if row.status != "pending":
            raise HTTPException(409, "该条已处理")
        row.status = "accepted"
    elif action == "reject":
        if row.status != "pending":
            raise HTTPException(409, "该条已处理")
        row.status = "rejected"
    elif action == "restore":
        if row.status != "rejected":
            raise HTTPException(409, "仅驳回条可恢复为待确认")
        row.status = "pending"
    else:
        raise HTTPException(400, f"未知动作：{action}")
    row.decided_at = datetime.now(UTC).replace(tzinfo=None)


@router.post("/rows/{row_id}")
async def row_action(
    row_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row, domain = await _load_owned_dossier_row(db, row_id, user)
    _decide(row, str((body or {}).get("action", "")))
    await db.commit()
    return {"ok": True, "row": _row_out(row, domain)}


@router.delete("/rows/{row_id}")
async def row_delete(
    row_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除已采纳行（AI 提错了的兜底）：确认在调用方，删除即退出后续提示词组装。"""
    row, _domain = await _load_owned_dossier_row(db, row_id, user)
    if row.status != "accepted":
        raise HTTPException(409, "仅已采纳条可删除（待确认用驳回、驳回用恢复）")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.post("/rows")
async def rows_batch(
    chapter_ref: str,
    project_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量动作：{action: accept|reject, domain?: settings|relations|items|knowledge}。

    缺省 domain＝全章。只作用于 pending 行；返回实际处理条数。"""
    ch, _novel = await _chapter_by_ref(db, project_id, chapter_ref, user)
    action = str((body or {}).get("action", ""))
    if action not in ("accept", "reject"):
        raise HTTPException(400, "批量动作只支持 accept/reject")
    domain = str((body or {}).get("domain", "") or "")
    if domain and domain not in DOMAINS:
        raise HTTPException(400, f"未知域：{domain}")
    targets = {
        "settings": ch.dossier_settings,
        "relations": ch.dossier_relations,
        "items": ch.dossier_items,
        "knowledge": ch.dossier_knowledge,
    }
    now = datetime.now(UTC).replace(tzinfo=None)
    n = 0
    for key, group in targets.items():
        if domain and key != domain:
            continue
        for row in group:
            if row.status == "pending":
                row.status = "accepted" if action == "accept" else "rejected"
                row.decided_at = now
                n += 1
    await db.commit()
    return {"ok": True, "updated": n}


@router.post("/extract")
async def extract(
    chapter_ref: str,
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重试/补提取：未归档章＝完整归档提取（成功即置 archived）；已归档章＝
    只重写章档行（rows_only，不动收口）。模型未就绪 → 409 model_not_ready。"""
    ch, novel = await _chapter_by_ref(db, project_id, chapter_ref, user)
    if ch.ghost_of:
        raise HTTPException(409, "旧稿支线章只读")
    try:
        # 门禁 grep ④ 豁免名单成员（archive/dossier.py，降级路径）；探测版调用
        from ai_client import get_ai_client_for_novel

        await get_ai_client_for_novel(novel.id)
    except Exception:  # noqa: BLE001
        raise HTTPException(409, "model_not_ready: 本书模型未配置，无法提取") from None
    prose = ch.content.prose if ch.content is not None else ""
    if len(prose) < 100:
        raise HTTPException(400, "正文不足 100 字，先完成本章再提取")
    job = await accept_extraction(
        novel.id, novel.root_path, chapter_ref, ch.id, prose_sha256(prose),
        rows_only=(ch.status == "archived"),
    )
    return {"ok": True, **job}


@router.post("/skip")
async def skip(
    chapter_ref: str,
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """逃生阀：跳过提取仍归档（确认与代价文案在前端）。"""
    ch, novel = await _chapter_by_ref(db, project_id, chapter_ref, user)
    if ch.status == "archived":
        raise HTTPException(409, "本章已归档")
    if ch.ghost_of:
        raise HTTPException(409, "旧稿支线章只读")
    prose = ch.content.prose if ch.content is not None else ""
    if len(prose) < 100:
        raise HTTPException(400, "正文不足 100 字")
    from archive.dossier import skip_extraction_and_archive

    result = await skip_extraction_and_archive(
        novel.id, novel.root_path, chapter_ref, ch.id, prose
    )
    return {"ok": True, **result}


@book_router.get("/preview")
async def preview(
    project_id: str,
    up_to_ref: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """「截至本章」累计预览：与写章消费同一折叠单源（story_state_upto）。"""
    novel = await db.get(Novel, project_id)
    if novel is None or novel.user_id != user["id"]:
        raise HTTPException(404, "Project not found")
    from write.story_state import story_state_upto

    state = await story_state_upto(project_id, up_to_ref or None)
    return {
        "up_to_ref": up_to_ref or None,
        "domains": {
            key: state.get(key) or [] for key in ("settings", "relations", "items", "knowledge")
        },
        "counts": {
            key: len(state.get(key) or [])
            for key in ("settings", "relations", "items", "knowledge")
        },
        "skipped_stale_refs": state.get("skipped_stale_refs") or [],
    }
