"""伏笔端点（foreshadow-settings-v2 tasks 2.1）。

注册顺序必须先于 settings/router.py 的 GET /settings/{type} 兜底——
照 characters_router 的先例（main.py）。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import get_current_user
from db import get_db
from settings import hooks_service as svc

router = APIRouter(prefix="/api/novels/{project_id}/hooks", tags=["hooks"])


def _svc_error(e: svc.Unprocessable | svc.Conflict):
    from fastapi import HTTPException

    status = 409 if isinstance(e, svc.Conflict) else 400
    return HTTPException(status_code=status, detail=e.detail)


@router.get("")
async def list_hooks(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    data = await svc.list_hooks(db, project_id)
    return {"ok": True, "data": data}


@router.post("")
async def create_hook(
    project_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    try:
        h = await svc.create_hook(db, project_id, body or {})
    except (svc.Unprocessable, svc.Conflict) as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": svc.hook_to_dict(h)}


@router.patch("/{hook_id}")
async def patch_hook(
    project_id: str,
    hook_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    try:
        h = await svc.patch_hook(db, project_id, hook_id, body or {})
    except (svc.Unprocessable, svc.Conflict) as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": svc.hook_to_dict(h)}


@router.delete("/{hook_id}")
async def delete_hook(
    project_id: str,
    hook_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    try:
        result = await svc.delete_hook(db, project_id, hook_id)
    except (svc.Unprocessable, svc.Conflict) as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": result}


@router.post("/{hook_id}/restore")
async def restore_hook(
    project_id: str,
    hook_id: str,
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """按原 id 原样恢复；body 可带 {"token": ...}（DELETE 返回的撤销凭证）。"""
    token = (body or {}).get("token")
    try:
        h = await svc.restore_hook(
            db, project_id, hook_id, str(token) if token else None
        )
    except (svc.Unprocessable, svc.Conflict) as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": svc.hook_to_dict(h)}
