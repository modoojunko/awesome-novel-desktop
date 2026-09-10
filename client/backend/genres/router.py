"""Global genre library CRUD routes.

题材库全局共享（单用户桌面应用，不做按 user 隔离，但走 get_current_user 鉴权）。
预置题材只读（PUT/DELETE → 403）；被项目引用的自定义题材不可删（DELETE → 409，
带引用项目名列表）。
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.middleware import get_current_user
from db import get_db

from .service import (
    _find_referencing_projects,
    create_genre,
    delete_genre,
    get_genre,
    list_genres,
    update_genre,
)

router = APIRouter(prefix="/api/genres", tags=["genres"])

GENRE_CATEGORIES = ("urban", "historical", "xianhuan", "suspense", "scifi", "independent")


class GenreDefinitionIn(BaseModel):
    """camelCase 镜像前端 GenreDefinition（不含 isPreset——后端强制）。"""

    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$", description="题材 slug")
    name: str
    description: str = ""
    category: Literal[
        "urban", "historical", "xianhuan", "suspense", "scifi", "independent"
    ]
    narratorRole: str = ""
    typicalArc: str = ""
    toneBlueprint: dict = {}
    taboos: list[str] = []
    promptInjection: str = ""
    genreConfig: dict = {}
    storyArcTemplates: list[dict] = []


def _user_id(user: dict) -> str:
    return user["id"]


@router.get("")
async def list_genres_route(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_genres(db)


@router.post("", status_code=201)
async def create_genre_route(
    body: GenreDefinitionIn,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await create_genre(db, body.model_dump())
    except ValueError as e:
        if "已存在" in str(e):
            raise HTTPException(409, str(e))
        raise HTTPException(422, str(e))


@router.get("/candidates")
async def list_candidates_route(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """题材候选源（D19）：promise / forbidden / battlefield 三组词汇。

    必须声明在 `/{genre_id}` 之前，否则会被路径参数吞掉。
    """
    from .novel_genre_service import list_candidates

    return await list_candidates(db)


@router.get("/{genre_id}")
async def get_genre_route(
    genre_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await get_genre(db, genre_id)
    if not result:
        raise HTTPException(404, "题材不存在")
    return result


@router.put("/{genre_id}")
async def update_genre_route(
    genre_id: str,
    body: GenreDefinitionIn,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await update_genre(db, genre_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(403, str(e))
    if not result:
        raise HTTPException(404, "题材不存在")
    return result


@router.delete("/{genre_id}")
async def delete_genre_route(
    genre_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await get_genre(db, genre_id)
    if not existing:
        raise HTTPException(404, "题材不存在")
    if existing.get("isPreset"):
        raise HTTPException(403, "预置题材不可删除，可新建自定义题材替代")

    projects = await _find_referencing_projects(db, _user_id(user), genre_id)
    if projects:
        raise HTTPException(
            409,
            detail={
                "message": f"该题材正在被 {len(projects)} 个作品使用，无法删除",
                "novels": projects,
            },
        )

    await delete_genre(db, genre_id)
    return {"ok": True}
