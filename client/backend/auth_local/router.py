# backend/auth_local/router.py
"""浏览器 OAuth 登录 API"""

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from http_client import build_async_client
from models.api_config import ApiConfig
from models.user import User

from .middleware import get_current_user
from .service import (
    _get_server_api,
    browser_auth,
    get_local_config,
    verify_session,
)

router = APIRouter(tags=["auth"])


@router.get("/check-auth")
async def api_check_auth():
    """检查当前浏览器在 S端 是否已登录（静默）"""
    return await browser_auth(silent=True)


@router.post("/browser-auth")
async def api_browser_auth():
    """打开浏览器 OAuth 登录"""
    return await browser_auth()


@router.post("/verify")
async def api_verify():
    """验证 30 天会话"""
    return await verify_session()


@router.get("/devices/current")
async def get_current_device(
    user: dict = Depends(get_current_user),
):
    """获取当前设备激活状态（代理到 S端）"""
    cfg = get_local_config()
    token = cfg.get("token", "")
    pc_hash = cfg.get("pc_hash", "")

    if not token:
        return {
            "enrolled": False,
            "activated": False,
            "device_count": 0,
            "active_limit": 0,
        }

    try:
        async with build_async_client(timeout=5) as client:
            resp = await client.get(
                f"{_get_server_api()}/api/devices/current",
                params={"pc_hash": pc_hash},
                headers={"Authorization": f"Bearer {token}"},
            )
            result = resp.json()

        # 消费 enrolled
        if result.get("enrolled"):
            async with build_async_client(timeout=3) as client:
                await client.post(
                    f"{_get_server_api()}/api/devices/consume-enrolled",
                    params={"pc_hash": pc_hash},
                    headers={"Authorization": f"Bearer {token}"},
                )

        return result
    except httpx.TimeoutException:
        return {
            "enrolled": False,
            "activated": False,
            "device_count": 0,
            "active_limit": 0,
            "error": "S端 超时",
        }
    except httpx.RequestError:
        return {
            "enrolled": False,
            "activated": False,
            "device_count": 0,
            "active_limit": 0,
            "error": "S端 不可达",
        }


@router.get("/config")
async def api_get_config(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取本地配置（从数据库，兼容旧 config.json）"""
    result = await db.execute(select(User).where(User.id == user["id"]))
    u = result.scalar_one_or_none()

    # 检查 ApiConfig 表中是否有任何配置（多 Key 时代）
    config_result = await db.execute(
        select(ApiConfig).where(ApiConfig.user_id == user["id"]).limit(1)
    )
    has_api_config = config_result.scalar_one_or_none() is not None

    if u:
        return {
            "has_token": bool(u.token),
            "tier": u.plan or "none",
            "expires_at": str(u.subscription_expires_at)
            if u.subscription_expires_at
            else "",
            "has_api_key": bool(u.api_key) or has_api_config,
            "api_base_url": u.api_base_url or "",
            "api_model": u.api_model or "",
            "portal_url": get_local_config().get("portal_url", ""),
        }
    # Fallback to config.json for migration period
    cfg = get_local_config()
    return {
        "has_token": bool(cfg.get("token", "")),
        "tier": cfg.get("tier", "none"),
        "expires_at": cfg.get("expires_at", ""),
        "has_api_key": has_api_config or bool(cfg.get("api_key")),
        "api_base_url": cfg.get("api_base_url", ""),
        "api_model": cfg.get("api_model", ""),
        "portal_url": cfg.get("portal_url", ""),
    }


@router.get("/user/profile")
async def api_user_profile(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user profile with migration status."""
    result = await db.execute(select(User).where(User.id == user["id"]))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(404, "User not found")

    resp: dict[str, Any] = {
        "id": u.id,
        "email": u.email,
        "display_name": u.display_name,
    }

    # Check if user has old api_key fields without ApiConfig
    has_old_fields = bool(u.api_key)
    if has_old_fields:
        # Check if at least one ApiConfig exists
        cfg_result = await db.execute(
            select(ApiConfig).where(ApiConfig.user_id == u.id).limit(1)
        )
        has_api_config = cfg_result.scalar_one_or_none() is not None

        if has_api_config:
            # Post-migration
            cfg = cfg_result.scalar_one()
            resp["migration_completed"] = True
            resp["migration_config_name"] = cfg.name
        else:
            # Pre-migration (has old fields but not migrated yet)
            resp["migration_completed"] = False
            resp["migration_config_name"] = None

    return resp

