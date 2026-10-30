"""建书提示端点（c-deconstruct-import-async 5.x）。

- GET    /api/novels/{id}/settings/import-notice   建书时的降级提示（无则 `{}`）
- DELETE /api/novels/{id}/settings/import-notice   关闭提示条（幂等：键不存在也 200）

键仿 book-prefs：`route_relative_path` 专用键，不进 PATH_TO_KEY——通用
`/settings/{type}` 天然拒绝该类型。写入方是后台建书执行体（成功收尾时落），
前端只读与关。与任务侧 `import.warnings` 允许分叉（不同后端、无共同事务）：
任务详情以 `import.warnings` 为准，本键是给用户看的副本。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import get_current_user
from db import get_db
from filesystem.paths import IMPORT_NOTICE_PATH
from filesystem.storage import get_storage
from novels.service import get_novel

router = APIRouter(prefix="/api/novels/{project_id}/settings", tags=["import-notice"])


@router.get("/import-notice")
async def get_import_notice(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    return await get_storage().read_yaml(project.root_path, IMPORT_NOTICE_PATH) or {}


@router.delete("/import-notice")
async def dismiss_import_notice(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    await get_storage().write_yaml(project.root_path, IMPORT_NOTICE_PATH, {})
    return {"ok": True}
