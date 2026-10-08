from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import ai_feature, require_tier_access
from auth_local.middleware import get_current_user
from db import get_db
from models.archive import ChapterPrompt
from models.chapter import Chapter
from novels.service import get_novel
from repositories import chapter_repo
from workflow.engine import _validate_ref


class UpdatePromptRequest(BaseModel):
    content: str


router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}",
    tags=["prompts"],
)

# 书级路由（c-silent-data-guards）：提示词总览批量取数用——
# 逐章串行 300 请求的 N+1 在此收口。只读聚合，不返回提示词内容。
book_router = APIRouter(prefix="/api/novels/{project_id}", tags=["prompts"])


@book_router.get("/prompt-summary")
@ai_feature("prompt-panel")
async def prompt_summary(
    project_id: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_tier_access),
    db: AsyncSession = Depends(get_db),
):
    """全书各章是否已有整章提示词（一次聚合；与章级 /prompts 同口径只认 write-prompt）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    stored = set(
        await db.scalars(
            select(Chapter.ref)
            .join(ChapterPrompt, ChapterPrompt.chapter_id == Chapter.id)
            .where(
                Chapter.project_id == project.id,
                ChapterPrompt.name == "write-prompt",
            )
        )
    )
    refs = await db.scalars(
        select(Chapter.ref).where(Chapter.project_id == project.id)
    )
    return {"chapters": [{"ref": r, "has_stored": r in stored} for r in refs]}


@router.get("/prompts")
@ai_feature("prompt-panel")
async def list_prompts(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_tier_access),
    db: AsyncSession = Depends(get_db),
):
    """整章单卡（ai-prompt-crafting）：只回 write-prompt 一条；存量 seg 行不迁移不返回。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    ch_row = await chapter_repo.get_by_ref(db, project.id, chapter_ref)
    if ch_row is None:
        return []
    has_write = await db.scalar(
        select(ChapterPrompt.id).where(
            ChapterPrompt.chapter_id == ch_row.id,
            ChapterPrompt.name == "write-prompt",
        )
    )
    if has_write is None:
        return []
    # 对外保持文件名形态 {ref}-{name}.md（前端零改动）
    return [f"{chapter_ref}-write-prompt.md"]


@router.get("/prompts/{seg}")
@ai_feature("prompt-panel")
async def get_prompt_content(
    project_id: str,
    chapter_ref: str,
    seg: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_tier_access),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    if seg != "write":
        # 分段链路退役：仅整章 write（读写 write-prompt 行），其余 404
        raise HTTPException(404, "Prompt not found")
    ch_row = await chapter_repo.get_by_ref(db, project.id, chapter_ref)
    content = ""
    if ch_row is not None:
        content = (
            await db.scalar(
                select(ChapterPrompt.content).where(
                    ChapterPrompt.chapter_id == ch_row.id,
                    ChapterPrompt.name == "write-prompt",
                )
            )
            or ""
        )
    return PlainTextResponse(content)


@router.put("/prompts/{seg}")
@ai_feature("prompt-panel")
async def update_prompt_content(
    project_id: str,
    chapter_ref: str,
    seg: str,
    body: UpdatePromptRequest,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_tier_access),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    if seg != "write":
        raise HTTPException(404, "Prompt not found")
    ch_row = await chapter_repo.get_by_ref(db, project.id, chapter_ref)
    if ch_row is None:
        raise HTTPException(404, "Chapter not found")
    row = await db.scalar(
        select(ChapterPrompt).where(
            ChapterPrompt.chapter_id == ch_row.id,
            ChapterPrompt.name == "write-prompt",
        )
    )
    if row is None:
        db.add(
            ChapterPrompt(chapter_id=ch_row.id, name="write-prompt", content=body.content)
        )
    else:
        row.content = body.content
    await db.commit()
    return {"status": "ok"}
