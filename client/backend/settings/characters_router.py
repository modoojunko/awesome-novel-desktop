"""角色端点（character-settings-v2 tasks 2.3-2.5）。

注册顺序必须先于 settings/router.py 的 GET /settings/{type} 兜底——
照 settings_status_router 的先例（main.py:484）。
"""

import json

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import get_current_user
from db import get_db
from settings import character_service as svc

router = APIRouter(prefix="/api/novels/{project_id}/characters", tags=["characters"])


def _svc_error(e: svc.Unprocessable | svc.Conflict):
    from fastapi import HTTPException

    status = 409 if isinstance(e, svc.Conflict) else 400
    return HTTPException(status_code=status, detail=e.detail)


@router.get("")
async def list_characters(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    data = await svc.list_characters(db, project_id)
    return {"ok": True, "data": data}


@router.post("")
async def create_character(
    project_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    try:
        ch = await svc.create_character(
            db, project_id, str(body.get("name") or ""), str(body.get("role") or "配角")
        )
    except (svc.Unprocessable, svc.Conflict) as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": svc.card_to_dict(ch)}


@router.get("/{character_id}")
async def get_character(
    project_id: str,
    character_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    try:
        ch = await svc._load_card(db, project_id, character_id)
    except svc.Unprocessable as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": await svc._card_view(db, ch)}


@router.patch("/{character_id}")
async def patch_character(
    project_id: str,
    character_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    try:
        result = await svc.patch_character(
            db, project_id, character_id,
            str(body.get("path") or ""), body.get("value"),
            int(body.get("base_rev") or 0),
        )
    except (svc.Unprocessable, svc.Conflict) as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": result}


@router.delete("/{character_id}")
async def delete_character(
    project_id: str,
    character_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    try:
        result = await svc.delete_character(db, project_id, character_id)
    except (svc.Unprocessable, svc.Conflict) as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": result}


@router.post("/{character_id}/merge")
async def merge_character(
    project_id: str,
    character_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    try:
        result = await svc.merge_character(
            db, project_id, character_id, str(body.get("target_id") or "")
        )
    except (svc.Unprocessable, svc.Conflict) as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": result}


@router.post("/ops/{token}/undo")
async def undo_op(
    project_id: str,
    token: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    try:
        result = await svc.undo_op(db, project_id, token)
    except (svc.Unprocessable, svc.Conflict) as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": result}


@router.get("/{character_id}/relations")
async def list_relations(
    project_id: str,
    character_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    try:
        ch = await svc._load_card(db, project_id, character_id)
    except svc.Unprocessable as e:
        raise _svc_error(e) from e
    view = await svc._card_view(db, ch)
    return {"ok": True, "data": view["relations"]}


@router.put("/{character_id}/relations/{other_id}")
async def upsert_relation(
    project_id: str,
    character_id: str,
    other_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    try:
        rel = await svc.upsert_relation(
            db, project_id, character_id, other_id,
            str(body.get("rel_type") or ""),
            str(body.get("stance") or ""),
            str(body.get("note") or ""),
            str(body.get("ch_ref") or ""),
        )
    except (svc.Unprocessable, svc.Conflict) as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": svc.rel_to_dict(rel)}


@router.delete("/{character_id}/relations/{other_id}")
async def delete_relation(
    project_id: str,
    character_id: str,
    other_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    try:
        result = await svc.delete_relation(db, project_id, character_id, other_id)
    except (svc.Unprocessable, svc.Conflict) as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": result}


@router.post("/confirm")
async def confirm_characters(
    project_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """确认门禁两档：请求带 first=true 走首次档（只查主角卡完整）。"""
    try:
        result = await svc.confirm_characters(db, project_id, bool(body.get("first")))
    except (svc.Unprocessable, svc.Conflict) as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": result}


@router.get("/gate/status")
async def gate_status(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    row = await svc.gate_status(db, project_id)
    return {"ok": True, "data": row}


_ = json  # json 保留给后续 audit 扩展
