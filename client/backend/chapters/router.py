from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.middleware import get_current_user
from chapters.service import get_chapter_row, save_chapter, save_prose
from db import get_db
from novels.service import get_novel
from volumes.schemas import VolumeCreate, VolumeUpdate
from workflow.engine import _validate_ref, load_chapter
from workflow.gates import gate_chapter_ready
from workflow.tier import tier_or_gate

router = APIRouter(prefix="/api/novels/{project_id}", tags=["chapters"])


# ── Volumes ────────────────────────────────────────────────────────────────


@router.get("/volumes")
async def list_volumes(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    from volumes.service import list_volumes as list_volumes_db

    return await list_volumes_db(db, project)


@router.post("/volumes")
async def create_volume(
    project_id: str,
    body: VolumeCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    from volumes.service import create_volume as create_volume_db

    # body.vol_num 忽略（MAX+1，防撞 UNIQUE，B9/P2-N）
    return await create_volume_db(
        db, project, title=body.title, summary=body.summary
    )


@router.get("/volumes/{ref}")
async def get_volume(
    project_id: str,
    ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    from volumes.service import get_volume as get_volume_db

    data = await get_volume_db(db, project, ref)
    if not data:
        raise HTTPException(404, "Volume not found")
    return data


@router.put("/volumes/{ref}")
async def update_volume(
    project_id: str,
    ref: str,
    body: VolumeUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    from volumes.service import update_volume as update_volume_db

    return await update_volume_db(db, project, ref, body)


@router.delete("/volumes/{ref}")
async def delete_volume(
    project_id: str,
    ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    from volumes.service import delete_volume as delete_volume_db

    return await delete_volume_db(db, project, ref)


# ── Chapters ───────────────────────────────────────────────────────────────


@router.post("/volumes/{ref}/chapters")
async def create_chapter_in_volume(
    project_id: str,
    ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """卷内建章（替代旧 POST /chapters）：定位卷 → MAX+1 → 双写。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    from chapters.service import create_chapter

    return await create_chapter(
        db, project, ref, body.get("title", "新章节")
    )


@router.get("/chapters/{chapter_ref}")
async def get_chapter(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    data = await load_chapter(project.root_path, chapter_ref)
    if not data:
        raise HTTPException(404, "Chapter not found")
    # DB 组装章全量 JSON + 元数据合并（store 组 outline/memo/segments/prose）
    meta = await get_chapter_row(db, project, chapter_ref)
    if meta:
        data.update(meta)
    return data


@router.put("/chapters/{chapter_ref}")
async def update_chapter(
    project_id: str,
    chapter_ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    await save_chapter(db, project, chapter_ref, body)
    return {"ok": True}


@router.put("/chapters/{chapter_ref}/prose")
async def update_chapter_prose(
    project_id: str,
    chapter_ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑器自动保存专用：body {prose} → YAML + 版本快照 + refresh DB 元数据。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    await save_prose(db, project, chapter_ref, body.get("prose", ""))
    return {"ok": True}


@router.post("/chapters/{chapter_ref}/confirm")
async def confirm_chapter(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    chapter = await load_chapter(project.root_path, chapter_ref)
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    result = await tier_or_gate(db, project, gate_chapter_ready, chapter)
    if not result.valid:
        # warnings 为中文缺失项（gate_chapter_ready），前端直接透传展示
        missing = "、".join(result.warnings)
        raise HTTPException(400, f"章纲确认失败，请先填写：{missing}")
    chapter["status"] = "confirmed"
    # 统一写入口：DB 落库 + 元数据派生（status/outline_status）
    await save_chapter(db, project, chapter_ref, chapter)
    from datetime import UTC, datetime

    from repositories import chapter_repo

    row = await chapter_repo.get_by_ref(db, project.id, chapter_ref)
    if row is not None:
        row.status = "confirmed"
        row.outline_status = "confirmed"
        row.confirmed_at = datetime.now(UTC).replace(tzinfo=None)
        await db.commit()
    return {"ok": True, "status": "confirmed"}


@router.post("/chapters/{chapter_ref}/unarchive")
async def unarchive_chapter(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """P2 unarchive：把归档章恢复为可编辑态（DB draft + 清归档文件 + 清 archived_at）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    chapter = await load_chapter(project.root_path, chapter_ref)
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    from repositories import chapter_repo

    # 归档态须在 save_chapter 之前读：save_chapter 会把 chapter["status"]="draft"
    # 落到同一 session 的行对象上，之后再读就恒为 draft（回减会静默失效）。
    row = await chapter_repo.get_by_ref(db, project.id, chapter_ref)
    was_archived = row is not None and getattr(row, "status", "") == "archived"

    chapter["status"] = "draft"
    chapter.pop("archive_path", None)
    chapter.pop("archive_summary", None)
    await save_chapter(db, project, chapter_ref, chapter)

    if row is not None:
        # total_archives 语义＝已归档章节数 → 与归档端点对称回减（幂等：非归档态不减）
        if was_archived:
            project.total_archives = max(0, (project.total_archives or 0) - 1)
        row.status = "draft"
        row.archived_at = None
        # 对称清归档行（archives 表，PR④）：章恢复可编辑，归档全文撤下
        from models.archive import Archive

        arch = await db.scalar(
            select(Archive).where(Archive.chapter_id == row.id)
        )
        if arch is not None:
            await db.delete(arch)
    await db.commit()

    return {"ok": True, "ref": chapter_ref}


@router.delete("/chapters/{chapter_ref}")
async def delete_chapter(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    # DB 行（CASCADE 删章纲子表/正文/版本快照/归档/提示词）+ 计数维护
    from repositories import chapter_repo, volume_repo
    from workflow.engine import strip_suffix

    row = await chapter_repo.get_by_ref(db, project.id, chapter_ref)
    if row is not None:
        await chapter_repo.delete(db, row.id)
        parts = strip_suffix(chapter_ref).split("-")
        vol = await volume_repo.get_by_volume_no(db, project.id, int(parts[1]))
        if vol is not None:
            vol.chapter_count = max(0, vol.chapter_count - 1)
        project.total_chapters = max(0, (project.total_chapters or 0) - 1)
    await db.commit()
    return {"ok": True}
