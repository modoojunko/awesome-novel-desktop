from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from archive.service import archive_chapter
from auth_local.middleware import get_current_user
from db import get_db
from models.archive import Archive
from models.chapter import Chapter
from models.project import Novel
from novels.service import get_novel
from workflow.engine import _validate_ref
from workflow.tier import tier_phase_transition

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/archive",
    tags=["archive"],
)

archives_router = APIRouter(
    prefix="/api/novels/{project_id}/archives",
    tags=["archives"],
)


def _slugify(title: str) -> str:
    return (title or "").replace(" ", "-").lower()[:50]


def _archive_filename(chapter_ref: str, title: str) -> str:
    """归档文件名（文件时代的寻址形态，前端零改动继续用它当地址）。"""
    return f"{chapter_ref}-{_slugify(title)}.md"


def _parse_archive_filename(filename: str) -> tuple[str, str] | None:
    """'vol-1-ch-2-标题.md' → ('vol-1-ch-2', 标题 slug)；形态不符返回 None。"""
    if "/" in filename or ".." in filename or not filename.endswith(".md"):
        return None
    body = filename[:-3]
    parts = body.split("-")
    if len(parts) < 4 or parts[0] != "vol" or parts[2] != "ch":
        return None
    if not (parts[1].isdigit() and parts[3].isdigit()):
        return None
    ref = f"vol-{parts[1]}-ch-{parts[3]}"
    slug = "-".join(parts[4:])
    return ref, slug


@router.post("")
async def archive(
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

    full_text = body.get("full_text", "")
    if len(full_text) < 100:
        raise HTTPException(400, "Text too short to archive")
    # ai_summary=False：用户在设置中关闭归档 AI 摘要（正文降级摘要，不烧 AI 额度）；
    # 会员判定走门控层非抛出版本（业务层不得自判会员，D11 禁令③）。
    from auth_local.deps import ai_access_granted

    ai_summary = body.get("ai_summary", True) and ai_access_granted()
    # lore-keeping 与摘要解耦（D11）：只看会员门控，不看 ai_summary 偏好
    lore = ai_access_granted()

    result = await archive_chapter(
        project.id, project.root_path, chapter_ref, full_text, ai_summary, lore
    )
    # force：归档是内容驱动操作（≥100 字已校验），phase 仅记账，不再要求 write→archive
    # 严格流转——直接写第一章的手工路径 phase 停在 outline，严格校验会 500。
    tier_phase_transition(project, "archive", force=True)

    # DB 章行 archived 态（status + archived_at）
    from repositories import chapter_repo

    row = await chapter_repo.get_by_ref(db, project.id, chapter_ref)
    # total_archives 语义＝**已归档章节数**（供书架卡片阶段判据）→ 必须幂等：
    # 重复归档同一章不再累加，取消归档要回减（见 chapters/router.py unarchive）。
    was_archived = row is not None and getattr(row, "status", "") == "archived"
    if row is not None:
        row.status = "archived"
        row.archived_at = datetime.now(UTC).replace(tzinfo=None)
    if not was_archived:
        project.total_archives = (project.total_archives or 0) + 1
    await db.commit()

    return result


@archives_router.get("")
async def list_archives(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    stmt = (
        select(Archive)
        .join(Chapter, Chapter.id == Archive.chapter_id)
        .where(Chapter.project_id == project.id)
        .order_by(Archive.archived_at.desc())
    )
    rows = (await db.scalars(stmt)).all()
    return [
        {
            "filename": _archive_filename(r.chapter.ref, r.title),
            "path": f"archives/{_archive_filename(r.chapter.ref, r.title)}",
        }
        for r in rows
    ]


@archives_router.get("/{filename}")
async def get_archive(
    project_id: str,
    filename: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    parsed = _parse_archive_filename(filename)
    if parsed is None:
        raise HTTPException(404, "Archive not found")
    ref, _slug = parsed
    stmt = (
        select(Archive)
        .join(Chapter, Chapter.id == Archive.chapter_id)
        .join(Novel, Novel.id == Chapter.project_id)
        .where(Novel.root_path == project.root_path, Chapter.ref == ref)
    )
    row = await db.scalar(stmt)
    if row is None or _archive_filename(ref, row.title) != filename:
        raise HTTPException(404, "Archive not found")
    return {"filename": filename, "content": row.content}
