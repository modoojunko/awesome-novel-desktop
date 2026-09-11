from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.middleware import get_current_user
from db import get_db
from filesystem.paths import KEY_TO_PATH, MULTI_FILE_SETTING_KEYS
from filesystem.storage import get_storage
from novels.service import get_novel

router = APIRouter(prefix="/api/novels/{project_id}/settings", tags=["settings"])

# 单文件设定 CRUD 类型：从 PATH_TO_KEY 推导（story 走 /story、status 走 /settings/status，
# 均非通用 CRUD；characters 是目录型，天然不在 KEY_TO_PATH）。KEY_TO_PATH 是唯一来源，
# 不重复维护 FILE_MAP。
SINGLE_FILE_TYPES = set(KEY_TO_PATH) - {"story", "status"}


@router.get("/character/{name}")
async def get_character(
    project_id: str,
    name: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    return (
        await get_storage().read_yaml(
            project.root_path, f"settings/character-setting/{name}.yaml"
        )
        or {}
    )


@router.put("/character/{name}")
async def update_character(
    project_id: str,
    name: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    await get_storage().write_yaml(
        project.root_path, f"settings/character-setting/{name}.yaml", body
    )
    return {"ok": True}


@router.get("/{type}")
async def get_settings(
    project_id: str,
    type: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    if type in MULTI_FILE_SETTING_KEYS:
        raise HTTPException(
            400,
            f"「{type}」是目录型设定，无 /settings/{type} 单文件端点；"
            f"角色设定请用 GET/PUT/DELETE /character/{{name}} 与 GET /characters/list",
        )
    if type not in SINGLE_FILE_TYPES:
        raise HTTPException(400, f"Invalid settings type: {type}")
    # world 契约 v2（world-setting-v2）：GET 永远返回归一化 v2 并剥离 `_legacy`
    if type == "world":
        from settings.world_model import read_world

        return read_world(await get_storage().read_yaml(project.root_path, KEY_TO_PATH[type]) or {})
    # genre 已关系化（D19）：对外仍是五字段 JSON，存储层走 novel_genre_service
    if type == "genre":
        from genres.novel_genre_service import get_novel_genre

        data = await get_novel_genre(db, project.id)
        # 题材目录（01 大类/子类）落 story.yaml（与简介同族，复用既有 genre 键）：
        # 契约上仍是同一个「题材」，故在这里合成一个响应，前端一次取全
        story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
        data["theme"] = story.get("genre") or ""
        data["sub_genre"] = story.get("sub_genre") or ""
        return data
    return await get_storage().read_yaml(project.root_path, KEY_TO_PATH[type])


@router.put("/{type}")
async def update_settings(
    project_id: str,
    type: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    if type in MULTI_FILE_SETTING_KEYS:
        raise HTTPException(
            400,
            f"「{type}」是目录型设定，无 /settings/{type} 单文件端点；"
            f"角色设定请用 GET/PUT/DELETE /character/{{name}} 与 GET /characters/list",
        )
    if type not in SINGLE_FILE_TYPES:
        raise HTTPException(400, f"Invalid settings type: {type}")
    # world 契约 v2（world-setting-v2）：WorldIn 校验 + 写边界落 `_legacy`（v1 原文留一个版本周期回滚）
    if type == "world":
        from pydantic import ValidationError

        from settings.world_model import (
            WorldIn,
            _is_v1,
            normalize_world,
            put_world_merged,
        )

        raw = await get_storage().read_yaml(project.root_path, KEY_TO_PATH[type]) or {}
        # 兼容旧前端/旧客户端直接 PUT 旧十字段形状：归一化成 v2，原文落 _legacy
        if _is_v1(body):
            merged = put_world_merged(raw, normalize_world(body))
            # `_legacy` 只记首次迁移原文（回滚基准），后续旧客户端重放不覆盖
            merged.setdefault("_legacy", body)
        else:
            try:
                payload = WorldIn.model_validate(body).model_dump(exclude_none=True)
            except ValidationError as e:
                raise HTTPException(400, f"世界设定校验失败：{e.errors()[0]['msg']}") from e
            merged = put_world_merged(raw, payload)
        await get_storage().write_yaml(project.root_path, KEY_TO_PATH[type], merged)
    elif type == "genre":
        from pydantic import ValidationError

        from genres.novel_genre_service import NovelGenreIn, put_novel_genre
        from genres.theme_catalog import sub_type_or_none, theme_or_none

        try:
            payload = NovelGenreIn.model_validate(body)
        except ValidationError as e:
            raise HTTPException(400, f"题材字段校验失败：{e.errors()[0]['msg']}") from e

        # 题材目录按「键存在才写」处理：老调用方只 PUT 五字段，不该把已选题材清空
        theme_touched = "theme" in body or "sub_genre" in body
        theme = ""
        sub = ""
        if theme_touched:
            try:
                theme = theme_or_none(body.get("theme")) or ""
                sub = sub_type_or_none(theme, body.get("sub_genre")) or ""
            except ValueError as e:
                raise HTTPException(400, str(e)) from e

        try:
            await put_novel_genre(db, project.id, payload.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

        if theme_touched:
            storage = get_storage()
            story = await storage.read_yaml(project.root_path, "story.yaml") or {}
            # 复用既有 genre 键（书卡胶囊/书内标签的展示链一直读它）
            if theme:
                story["genre"] = theme
            else:
                story.pop("genre", None)
            if sub:
                story["sub_genre"] = sub
            else:
                story.pop("sub_genre", None)
            await storage.write_yaml(project.root_path, "story.yaml", story)
    else:
        await get_storage().write_yaml(project.root_path, KEY_TO_PATH[type], body)

    if project.current_phase == "init":
        project.current_phase = "settings"
        await db.commit()

    return {"ok": True}


@router.delete("/character/{name}")
async def delete_character(
    project_id: str,
    name: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    await get_storage().delete_file(
        project.root_path, f"settings/character-setting/{name}.yaml"
    )
    return {"ok": True}


@router.post("/world/lore-apply")
async def lore_apply(
    project_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI lore 建议的人工确认入账：按 (key, origin) 幂等合并进世界设定。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    from settings.world_model import (
        lore_apply_entries,
        normalize_world,
        put_world_merged,
        read_world,
    )

    entries = body.get("entries")
    if not isinstance(entries, list) or not entries:
        raise HTTPException(400, "缺少要入账的条目（entries）")
    if len(entries) > 20:
        raise HTTPException(400, "单次最多入账 20 条")

    raw = await get_storage().read_yaml(project.root_path, KEY_TO_PATH["world"]) or {}
    v2 = normalize_world(raw)
    try:
        v2 = lore_apply_entries(v2, entries)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    merged = put_world_merged(raw, v2)
    await get_storage().write_yaml(project.root_path, KEY_TO_PATH["world"], merged)
    return read_world(merged)


@router.get("/characters/list")
async def list_characters(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    names = await get_storage().list_dir(
        project.root_path, "settings/character-setting"
    )
    return [n.replace(".yaml", "") for n in names if n.endswith(".yaml")]
