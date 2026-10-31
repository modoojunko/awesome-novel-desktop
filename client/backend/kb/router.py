"""写作知识库 API 端点——挂 /api/kb 前缀。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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
from models.kb import KbEntry

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
    return items


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
    return {
        "entries": [_entry_dict(e) for e in entries],
        "next_cursor": next_cursor,
    }


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
    return _entry_dict(e)


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
        raise HTTPException(422, detail={"errors": error.errors, "warnings": gate.warnings})
    return _entry_dict(entry)


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
    return {"concepts": result, "themes": THEMES}


# ─── 库列表 ──────────────────────────────────────────────

@router.get("/libraries")
async def list_libraries_api(
    genre: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    libs = await list_libraries(db, user_id=uid, genre=genre)
    return [
        {
            "id": l.id,
            "genre": l.genre,
            "concept": l.concept,
            "name": l.name,
            "purpose": l.purpose,
            "contract": l.contract,
            "enabled": l.enabled,
        }
        for l in libs
    ]
