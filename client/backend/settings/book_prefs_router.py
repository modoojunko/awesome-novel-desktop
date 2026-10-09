"""作品偏好端点（c-chapter-default-words，内测反馈#10）。

- GET /settings/book-prefs   全文（未设置＝`{}`；前端按缺省 2500 回显）
- PUT /settings/book-prefs   只受理「章节默认字数」（body: {chapter_word_target}）

注册顺序必须先于 settings/router.py 的 GET /settings/{type} 兜底（main.py，
characters/hooks/style-quant 先例）。book-prefs 键仿 threads/style-quant：
route_relative_path 专用键，不进 PATH_TO_KEY——通用 /settings/{type} 天然拒绝该类型。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import get_current_user
from db import get_db
from filesystem.paths import BOOK_PREFS_PATH
from filesystem.storage import get_storage
from novels.service import get_novel
from settings import book_prefs_model as bm

router = APIRouter(prefix="/api/novels/{project_id}/settings", tags=["book-prefs"])


async def _load(root_path: str) -> dict[str, int]:
    return bm.read_book_prefs(await get_storage().read_yaml(root_path, BOOK_PREFS_PATH))


@router.get("/book-prefs")
async def get_book_prefs(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    return await _load(project.root_path)


@router.put("/book-prefs")
async def put_book_prefs(
    project_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """唯一前端写路径：章节默认字数。字段缺省＝无操作成功（沿用 style-quant 口径）；
    null/空＝清除设置（回落缺省），越界/非整数 400。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    if not isinstance(body, dict):
        raise HTTPException(400, "作品偏好需为对象")
    doc = await _load(project.root_path)
    if bm.CHAPTER_WORD_TARGET_FIELD in body:
        try:
            target = bm.normalize_chapter_word_target(
                body.get(bm.CHAPTER_WORD_TARGET_FIELD)
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        if target is None:
            doc.pop(bm.CHAPTER_WORD_TARGET_FIELD, None)
        else:
            doc[bm.CHAPTER_WORD_TARGET_FIELD] = target
        await get_storage().write_yaml(project.root_path, BOOK_PREFS_PATH, doc)
    return doc
