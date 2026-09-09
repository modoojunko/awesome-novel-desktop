"""API routes for API Key Config management.

IMPORTANT: Static paths (status, usage-summary, apply-model-to-all) MUST
be declared BEFORE parameterized paths ({config_id}, {project_id}) so
FastAPI doesn't match them as path parameters.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.middleware import get_current_user
from db import get_db
from models.api_config import ApiConfig
from models.user import User
from novels.service import (
    get_novel as _get_novel,
)
from novels.service import (
    list_projects as _list_projects,
)
from novels.service import (
    novel_to_dict,
)

from .connection import test_connection as _test_raw_connection
from .schemas import (
    ApplyModelToAllBody,
    CreateApiConfigBody,
    SetAiModelBody,
    TestRawBody,
    UpdateApiConfigBody,
)
from .service import (
    apply_model_to_all_projects,
    create_api_config,
    delete_api_config,
    get_api_config,
    get_batch_status,
    get_config_usage,
    get_model_history,
    get_project_ai_model,
    get_project_usage,
    get_usage_summary,
    get_user_api_configs,
    restore_api_config,
    restore_model_history,
    set_project_model,
    update_api_config,
)
from .service import (
    test_api_config as _test_api_config,
)

router = APIRouter(prefix="/api/v1", tags=["api-configs"])


# ── Helper ─────────────────────────────────────────────────────────────────


def _user_id(user: dict) -> str:
    return user["id"]


# ═══════════════════════════════════════════════════════════════════════════
#  User profile (v1, with migration status)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/user/profile")
async def user_profile(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user profile with migration status."""
    result = await db.execute(select(User).where(User.id == _user_id(user)))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(404, "User not found")

    resp: dict[str, Any] = {
        "id": u.id,
        "email": u.email,
        "display_name": u.display_name,
    }

    has_old_fields = bool(u.api_key)
    if has_old_fields:
        cfg_result = await db.execute(
            select(ApiConfig).where(ApiConfig.user_id == u.id).limit(1)
        )
        api_config = cfg_result.scalar_one_or_none()
        if api_config:
            resp["migration_completed"] = True
            resp["migration_config_name"] = api_config.name
        else:
            resp["migration_completed"] = False
            resp["migration_config_name"] = None

    return resp


# ═══════════════════════════════════════════════════════════════════════════
#  ApiConfig CRUD — static paths before parameterized paths
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/api-configs", status_code=201)
async def create_config(
    body: CreateApiConfigBody,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API Key config."""
    try:
        result = await create_api_config(
            db,
            _user_id(user),
            body.name,
            body.vendor_id,
            body.base_url,
            api_key=body.api_key,
            vendor_override=body.vendor_override,
            api_format=body.api_format,
        )
        return result
    except ValueError as e:
        if "名称已被使用" in str(e):
            raise HTTPException(409, "名称已被使用")
        raise HTTPException(422, str(e))


@router.get("/api-configs")
async def list_configs(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all API Key configs."""
    return await get_user_api_configs(db, _user_id(user))


# STATIC paths BEFORE parameterized paths
@router.get("/api-configs/status")
async def batch_status(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get batch status for all configs."""
    return await get_batch_status(db, _user_id(user))


@router.post("/api-configs/test-connection")
async def test_raw_connection(
    body: TestRawBody,
    user: dict = Depends(get_current_user),
):
    """Test a connection with raw config data (no saved config needed)."""
    return await _test_raw_connection(
        vendor_id=body.vendor_id,
        api_key=body.api_key,
        base_url=body.base_url,
        api_format=body.api_format,
    )


@router.get("/api-configs/usage-summary")
async def usage_summary(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get global usage summary."""
    return await get_usage_summary(db, _user_id(user))


# PARAMETERIZED paths
@router.get("/api-configs/{config_id}")
async def get_config(
    config_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single API Key config."""
    result = await get_api_config(db, _user_id(user), config_id)
    if not result:
        raise HTTPException(404, "配置不存在")
    return result


@router.put("/api-configs/{config_id}")
async def update_config(
    config_id: str,
    body: UpdateApiConfigBody,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an API Key config."""
    updates: dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.base_url is not None:
        updates["base_url"] = body.base_url
    if body.api_key is not None:
        updates["api_key"] = body.api_key
    if body.vendor_override is not None:
        updates["vendor_override"] = body.vendor_override
    if body.api_format is not None:
        updates["api_format"] = body.api_format

    try:
        result = await update_api_config(db, _user_id(user), config_id, updates)
        if not result:
            raise HTTPException(404, "配置不存在")
        return result
    except ValueError as e:
        if "名称已被使用" in str(e):
            raise HTTPException(409, "名称已被使用")
        raise HTTPException(422, str(e))


@router.delete("/api-configs/{config_id}")
async def delete_config(
    config_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an API Key config（软删，status=deleted，行保留供撤销恢复）。"""
    result = await delete_api_config(db, _user_id(user), config_id)
    if not result:
        raise HTTPException(404, "配置不存在")
    return result


@router.post("/api-configs/{config_id}/restore")
async def restore_config(
    config_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤销删除：把软删的配置恢复为 active（同一 id，前端「撤销」调用）。"""
    try:
        result = await restore_api_config(db, _user_id(user), config_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not result:
        raise HTTPException(404, "配置不存在")
    return result


@router.post("/api-configs/{config_id}/test")
async def test_config(
    config_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test a single config's connection and save results."""
    result = await _test_api_config(db, _user_id(user), config_id)
    if result.get("status") == "not_found":
        raise HTTPException(404, "配置不存在")
    return result


@router.post("/api-configs/{config_id}/refresh-models")
async def refresh_models(
    config_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Refresh models for a config."""
    config = await get_api_config(db, _user_id(user), config_id)
    if not config:
        raise HTTPException(404, "配置不存在")
    if config.get("status") == "disabled":
        raise HTTPException(400, "已禁用的配置无法刷新模型")
    return {"ok": False, "status": "untested", "models": []}


@router.get("/api-configs/{config_id}/usage")
async def config_usage(
    config_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get usage for a specific config."""
    return await get_config_usage(db, _user_id(user), config_id)


# ═══════════════════════════════════════════════════════════════════════════
#  Projects — static paths before parameterized paths
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/novels")
async def list_projects_v1(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all projects for the current user."""
    projects = await _list_projects(db, _user_id(user))
    return [novel_to_dict(p) for p in projects]


# STATIC before parameterized
@router.post("/novels/apply-model-to-all")
async def apply_model_to_all(
    body: ApplyModelToAllBody,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply a model to all projects."""
    result = await apply_model_to_all_projects(
        db,
        _user_id(user),
        body.api_config_id,
        body.model,
    )
    return result


@router.get("/novels/{project_id}")
async def get_project_v1(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single project."""
    project = await _get_novel(db, project_id, _user_id(user))
    if not project:
        raise HTTPException(404, "Project not found")
    return novel_to_dict(project)


@router.get("/novels/{project_id}/ai-model")
async def get_project_model(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a project's current AI model."""
    result = await get_project_ai_model(db, _user_id(user), project_id)
    if result is None:
        raise HTTPException(404, "Project not found")
    return result


@router.put("/novels/{project_id}/ai-model")
async def set_project_model_route(
    project_id: str,
    body: SetAiModelBody,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set a project's AI model."""
    result = await set_project_model(
        db,
        _user_id(user),
        project_id,
        body.api_config_id,
        body.model,
    )
    if result is None:
        raise HTTPException(404, "Project or config not found")
    return result


@router.get("/novels/{project_id}/model-history")
async def get_model_history_route(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """Get model change history for a project."""
    entries = await get_model_history(db, _user_id(user), project_id, limit, offset)
    return {"history": entries}


@router.post("/novels/{project_id}/model-history/{entry_id}/restore")
async def restore_model_history_route(
    project_id: str,
    entry_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Restore a project's model from a history entry."""
    result = await restore_model_history(db, _user_id(user), project_id, entry_id)
    if result is None:
        raise HTTPException(404, "Project or history entry not found")
    if "error" in result:
        raise HTTPException(400, result["message"])
    return result


@router.get("/novels/{project_id}/usage")
async def project_usage(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get usage for a specific project."""
    result = await get_project_usage(db, _user_id(user), project_id)
    if result is None:
        raise HTTPException(404, "Project not found")
    return result
