from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_state import effective_model
from auth_local.deps import require_ai_access, require_novel_model
from auth_local.middleware import get_current_user
from db import get_db
from models.archive import ChapterPrompt
from novels.service import get_novel
from repositories import chapter_repo
from workflow.engine import _validate_ref, load_chapter


class UpdatePromptRequest(BaseModel):
    content: str


router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}",
    tags=["prompts"],
)


@router.post("/perspective")
async def run_perspective_conversion(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    chapter = await load_chapter(project.root_path, chapter_ref)
    summary = chapter.get("outline", {}).get("summary", "")
    pov = chapter.get("pov_character", "主角")

    from ai_client import get_ai_client_for_novel

    # C/S: Token tracking removed — user brings own API key
    client = await get_ai_client_for_novel(project.id)
    usage: dict = {}
    guidance = await client.chat(
        model=effective_model(project),
        max_tokens=500,
        system="将以下上帝视角章纲转换为沉浸式写作指引。用第二人称'你'。保留所有关键事件，但用感官细节替换概括性描述。200-300字。",
        messages=[{"role": "user", "content": f"视角：{pov}\n章纲：{summary}"}],
        usage=usage,
    )

    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=user["id"],
        project_id=project.id,
        chapter_id=chapter_ref,
        operation="perspective",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )

    # C/S: Token tracking removed — user brings own API key
    chapter["outline"]["perspective_guidance"] = guidance
    from workflow.engine import save_chapter

    await save_chapter(project.root_path, chapter_ref, chapter)

    return {
        "guidance": guidance,
    }


@router.get("/prompts")
async def list_prompts(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
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
async def get_prompt_content(
    project_id: str,
    chapter_ref: str,
    seg: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
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
async def update_prompt_content(
    project_id: str,
    chapter_ref: str,
    seg: str,
    body: UpdatePromptRequest,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
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
