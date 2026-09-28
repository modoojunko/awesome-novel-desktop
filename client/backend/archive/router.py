
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.middleware import get_current_user
from db import get_db
from models.archive import Archive
from models.chapter import Chapter
from models.project import Novel
from novels.service import get_novel
from workflow.engine import _validate_ref

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/archive",
    tags=["archive"],
)

archives_router = APIRouter(
    prefix="/api/novels/{project_id}/archives",
    tags=["archives"],
)


# 命名单源：archive/naming.py（c-archive-filename-safety——公式曾在本文件与
# service.py 各手抄一份，且漏安全规则）。本模块保留 `_` 前缀别名，外部既有 import
# 面（backup/export.py、novels/router.py）零改动。
from archive.naming import archive_filename as _archive_filename  # noqa: E402
from archive.naming import parse_archive_filename as _parse_archive_filename


@router.post("")
async def archive(
    project_id: str,
    chapter_ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """归档受理（c-chapter-dossier D1）：提取成功才归档。

    - 本书模型未就绪 → 同步收口（archived、无章档、摘要降级），受理即生效；
    - 模型就绪 → 受理返回 extracting，后台提取四域，成功原子收口置 archived；
      失败章不归档可重试（逃生阀「跳过提取仍归档」走同一收口函数）。
    - 提取不挂会员门（全档可用）；旧伏笔/lore 收尾仍 PRO，归档成功后由收口方触发。
    - 正文以 DB 现值为准（受理时记哈希，提取窗口内被改 → 本次失败提示重试）。
    """
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    from repositories import chapter_repo

    row = await chapter_repo.get_by_ref(db, project.id, chapter_ref)
    if row is None:
        raise HTTPException(404, "Chapter not found")
    if row.ghost_of:
        raise HTTPException(409, "旧稿支线章只读，不能归档")

    full_text = row.content.prose if row.content is not None else ""
    body_text = str(body.get("full_text") or "")
    if len(full_text) < 100 and len(body_text) >= 100:
        # 旧契约兼容：旁路调用只带 body 正文时以请求体为准先落库（编辑器常态
        # 已自动保存，此路径只是兜底），归档与提取仍以 DB 现值为单一事实源。
        from chapters.store import save_chapter

        await save_chapter(project.root_path, chapter_ref, {"prose": body_text})
        await db.refresh(row)
        full_text = row.content.prose if row.content is not None else ""
    if len(full_text) < 100:
        raise HTTPException(400, "Text too short to archive")

    from archive.dossier import accept_extraction, get_job_state, prose_sha256

    # 受理幂等：同章提取在跑 → 返回当前状态（不报错不排队）
    job_state = await get_job_state(row.id)
    if job_state is not None and job_state["state"] == "extracting":
        return {
            "accepted": True, "model_ready": True, "state": "extracting",
            "dedup": "in_flight", "archive_path": None, "summary": None,
        }

    # 模型就绪探测（非抛出版本）：未就绪 → 放行归档（无章档、可后补提取）
    model_ready = False
    try:
        from ai_client import get_ai_client_for_novel

        await get_ai_client_for_novel(project.id)
        model_ready = True
    except Exception:  # noqa: BLE001 — 未配置/无 Key：归档即刻生效，不烧调用
        model_ready = False

    ai_summary = body.get("ai_summary", True)

    if not model_ready:
        from archive.dossier import finalize_archive

        result = await finalize_archive(
            novel_id=project.id,
            root_path=project.root_path,
            chapter_id=row.id,
            chapter_ref=chapter_ref,
            title=row.title,
            full_text=full_text,
            summary=None,
            dossier_payload=None,
            job_state=None,
        )
        # 旧收尾（伏笔/lore 提案，PRO）随归档成功触发（模型未就绪时收尾内部自退）
        from archive.dossier import _maybe_start_reconcile

        _maybe_start_reconcile(project.id, project.root_path, chapter_ref, row.id)
        return {**result, "accepted": True, "model_ready": False, "state": "archived"}

    job = await accept_extraction(
        project.id, project.root_path, chapter_ref, row.id,
        prose_sha256(full_text), ai_summary=bool(ai_summary),
    )
    return {
        "accepted": True, "model_ready": True, "state": "extracting",
        "job_id": job.get("job_id"), "archive_path": None, "summary": None,
    }



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
