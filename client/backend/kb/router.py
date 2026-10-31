"""写作知识库 API 端点——挂 /api/kb 前缀。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import get_current_user
from db import get_db
from kb.concepts import CONCEPTS, THEMES
from kb.service import (
    create_entry,
    genre_counts,
    get_entry,
    list_entries,
    list_libraries,
)
from models.kb import KbBookBinding, KbEntry
from novels.service import get_novel

router = APIRouter(prefix="/api/kb", tags=["kb"])


def _user(dep: dict) -> str:
    return dep["id"]


def _entry_dict(e: KbEntry) -> dict[str, Any]:
    return {
        "id": e.id,
        "genre": e.genre,
        "concept": e.concept,
        "concept_id": e.concept_id,
        "title": e.title,
        "instruction": e.instruction,
        "payload": json.loads(e.payload_json),
        "example": e.example,
        "negative_example": e.negative_example,
        "when": json.loads(e.when_json),
        "evidence": e.evidence,
        "src_kind": e.src_kind,
        "src_novel_name": e.src_novel_name,
        "created_at": e.created_at.isoformat(),
        "updated_at": e.updated_at.isoformat(),
    }


# ─── 题材栏 ──────────────────────────────────────────────

@router.get("/genres")
async def get_genres(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    counts = await genre_counts(db, user_id=uid)
    items = []
    for t in THEMES:
        items.append({"name": t, "count": counts.get(t, 0)})
    if "" in counts:
        items.append({"name": "跨题材通用", "count": counts[""], "key": ""})
    return {"ok": True, "data": items}


# ─── 条目列表 ─────────────────────────────────────────────

@router.get("/entries")
async def list_entries_api(
    genre: str = "",
    concept: str = "",
    src: str = "",
    q: str = "",
    cursor: str = "",
    limit: int = 30,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    entries, next_cursor = await list_entries(
        db, user_id=uid, genre=genre, concept=concept,
        src=src, q=q, cursor=cursor, limit=limit,
    )
    return {"ok": True, "data": {"entries": [_entry_dict(e) for e in entries], "next_cursor": next_cursor}}


# ─── 条目详情 ─────────────────────────────────────────────

@router.get("/entries/{entry_id}")
async def get_entry_api(
    entry_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    e = await get_entry(db, user_id=uid, entry_id=entry_id)
    if not e:
        raise HTTPException(404, "Entry not found")
    return {"ok": True, "data": _entry_dict(e)}


# ─── 手录 ─────────────────────────────────────────────────

class CreateEntryRequest(BaseModel):
    genre: str = ""
    concept: str = ""
    concept_id: str = ""
    title: str = ""
    payload: dict[str, Any] = {}
    instruction: str = ""
    example: str = ""
    negative_example: str = ""
    when_json: dict[str, Any] = {}


@router.post("/entries")
async def create_entry_api(
    body: CreateEntryRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    entry, gate, error = await create_entry(
        db,
        user_id=uid,
        genre=body.genre,
        concept=body.concept,
        concept_id=body.concept_id,
        title=body.title,
        payload=body.payload,
        instruction=body.instruction,
        example=body.example,
        negative_example=body.negative_example,
        when_json=body.when_json,
        src_kind="manual",
    )
    if error:
        first = next(iter(error.errors.values()), "入库校验未通过")
        raise HTTPException(422, detail={"message": first, "errors": error.errors, "warnings": gate.warnings})
    return {"ok": True, "data": _entry_dict(entry)}


# ─── 概念元数据 ────────────────────────────────────────────

@router.get("/concepts")
async def get_concepts(
    genre: str = "",
    user: dict = Depends(get_current_user),
):
    """概念元数据——前端按此生成手录动态字段。"""
    from kb.payloads import _PAYLOAD_MODELS
    result = []
    for name in CONCEPTS:
        model_cls = _PAYLOAD_MODELS.get(name)
        fields = []
        if model_cls:
            for fname, fprop in model_cls.model_fields.items():
                fields.append({
                    "key": fname,
                    "required": fprop.is_required(),
                    "max_length": fprop.metadata[0].max_length if fprop.metadata and hasattr(fprop.metadata[0], 'max_length') else None,
                })
        result.append({
            "name": name,
            "fields": fields,
            "readonly": name == "情节",
        })
    return {"ok": True, "data": {"concepts": result, "themes": THEMES}}


# ─── 库列表 ──────────────────────────────────────────────

@router.get("/libraries")
async def list_libraries_api(
    genre: str = "",
    novel_id: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    libs = await list_libraries(db, user_id=uid, genre=genre)
    # 几本书启用（库卡亮相批3）：绑定行按库分组计数（跨书）
    bound_counts: dict[str, int] = {
        row[0]: row[1]
        for row in (
            await db.execute(
                select(KbBookBinding.library_id, func.count(KbBookBinding.id))
                .where(KbBookBinding.enabled.is_(True))
                .group_by(KbBookBinding.library_id)
            )
        ).all()
    }
    # 成员数（含场景条目）：auto 库按 (user,genre,concept) 计数；手动圈选库走 items
    from models.kb import KbLibraryItem

    entry_counts: dict[str, int] = {}
    for l in libs:
        if l.rule_kind == "auto":
            n = (
                await db.execute(
                    select(func.count(KbEntry.id)).where(
                        KbEntry.user_id == uid,
                        KbEntry.genre == l.genre,
                        KbEntry.concept == l.concept,
                        KbEntry.status == "active",
                    )
                )
            ).scalar_one()
        else:
            n = (
                await db.execute(
                    select(func.count(KbLibraryItem.id)).where(KbLibraryItem.library_id == l.id)
                )
            ).scalar_one()
        entry_counts[l.id] = int(n or 0)
    items = []
    for l in libs:
        # 本书是否已启用（库卡「本书已启用」徽章；novel_id 缺省＝账号级浏览）
        bound = 0
        if novel_id:
            bound = 1 if (
                await db.execute(
                    select(KbBookBinding.id).where(
                        KbBookBinding.novel_id == novel_id,
                        KbBookBinding.library_id == l.id,
                        KbBookBinding.enabled.is_(True),
                    )
                )
            ).scalar_one_or_none() else 0
        items.append(
            {
                "id": l.id,
                "genre": l.genre,
                "concept": l.concept,
                "name": l.name,
                "purpose": l.purpose,
                "contract": l.contract,
                "enabled": l.enabled,
                "entry_count": entry_counts.get(l.id, 0),
                "bound_novels": bound_counts.get(l.id, 0),
                "bound_in_book": bound,
            }
        )
    return {"ok": True, "data": items}


# ─── 书内绑定（c-kb-snapshot 批3：启用落设定）──────────────


class BindRequest(BaseModel):
    novel_id: str = ""
    library_id: str = ""


@router.post("/bindings")
async def bind_library_api(
    body: BindRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    project = await get_novel(db, body.novel_id, uid)
    if not project:
        raise HTTPException(404, "Project not found")
    from kb.snapshot import bind_library

    binding, info, error = await bind_library(
        db,
        user_id=uid,
        novel_id=body.novel_id,
        root_path=project.root_path,
        library_id=body.library_id,
    )
    if error:
        raise HTTPException(404, error)
    return {"ok": True, "data": {"binding_id": binding.id, **info}}


@router.get("/bindings")
async def list_bindings_api(
    novel_id: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    project = await get_novel(db, novel_id, uid)
    if not project:
        raise HTTPException(404, "Project not found")
    from kb.snapshot import list_bindings

    return {"ok": True, "data": await list_bindings(db, novel_id=novel_id)}


@router.post("/bindings/{binding_id}/sync")
async def sync_binding_api(
    binding_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    binding = (
        await db.execute(
            select(KbBookBinding).where(KbBookBinding.id == binding_id)
        )
    ).scalar_one_or_none()
    if not binding:
        raise HTTPException(404, "Binding not found")
    project = await get_novel(db, binding.novel_id, uid)
    if not project:
        raise HTTPException(404, "Project not found")
    from kb.snapshot import sync_binding

    result = await sync_binding(db, binding, project.root_path)
    if result.get("error"):
        raise HTTPException(409, result["error"])
    return {"ok": True, "data": result}


@router.delete("/bindings/{binding_id}")
async def unbind_api(
    binding_id: str,
    novel_id: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    project = await get_novel(db, novel_id, uid)
    if not project:
        raise HTTPException(404, "Project not found")
    from kb.snapshot import unbind

    removed = await unbind(db, novel_id=novel_id, binding_id=binding_id)
    if not removed:
        raise HTTPException(404, "Binding not found")
    return {"ok": True, "data": {"unbound": binding_id}}
