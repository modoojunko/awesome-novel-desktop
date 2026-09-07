"""FastAPI Dependencies — 权限门控

require_ai_access(): AI 是会员权益（2026-08-18 口径）——非会员（免费/过期）一律
    403（即使已配置 Key）；会员还需配置 API Key，未配置返回 503 引导设置。
require_project_limit(): 免费/过期用户最多 1 个项目；会员不限。
"""

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models.api_config import ApiConfig
from models.project import Novel
from models.user import User

from .middleware import get_current_user
from .service import check_permission, ensure_entitlement_snapshot, get_local_config


async def require_ai_access(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI 功能门控：先验会员身份，再验 API Key 配置

    403 detail 为结构化 {reason: "member_required", message}，
    前端 request() 据此弹统一升级引导，而非裸错误。
    """
    # 0) 快照三段式：不完整时先重同步一次（async 边界），失败走档位标准兜底
    await ensure_entitlement_snapshot()

    # 1) 会员校验：免费/过期用户即使配置了 Key 也拦截（AI 是会员权益）
    perm = check_permission()
    if not perm.get("is_member", False):
        message = (
            "AI 是会员功能 — 套餐已过期，续费后继续使用"
            if perm.get("expired")
            else "AI 是会员功能 — 开通 PRO 或 7 天免费试用后即可使用"
        )
        raise HTTPException(
            status_code=403,
            detail={"reason": "member_required", "message": message},
        )

    # 2) 会员需已配置 API Key（ApiConfig → 旧 User 字段 → config.json 迁移期兜底）
    # Check ApiConfig first (new system)
    try:
        result = await db.execute(
            select(ApiConfig)
            .where(
                ApiConfig.user_id == user["id"],
                ApiConfig.status == "active",
                ApiConfig.api_key != "",
            )
            .limit(1)
        )
        if result.scalar_one_or_none():
            return True
    except Exception:  # noqa: S110
        pass

    # Fallback: check old User.api_key for migration period
    try:
        result = await db.execute(select(User).where(User.id == user["id"]))
        u = result.scalar_one_or_none()
        if u and u.api_key:
            return True
    except Exception:  # noqa: S110
        pass

    # Fallback to config.json
    cfg = get_local_config()
    if cfg.get("api_key"):
        return True

    raise HTTPException(503, "AI 服务未配置 — 请先在设置中填写 API Key")


async def require_project_limit(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目上限门控：免费/过期用户最多 1 个项目，会员不限"""
    # 快照三段式：不完整时先重同步一次（async 边界），失败走档位标准兜底
    await ensure_entitlement_snapshot()

    perm = check_permission()
    limit = perm.get("project_limit")
    if limit is None:  # 会员无上限（免费/过期分支已带 project_limit=1）
        return True

    result = await db.execute(
        select(Novel).where(
            Novel.user_id == user["id"], Novel.status != "deleted"
        )
    )
    count = len(result.scalars().all())
    if count >= limit:
        if perm.get("expired"):
            raise HTTPException(
                403, "套餐已过期，已降为免费待遇（最多 1 个项目）— 续费后可创建更多"
            )
        raise HTTPException(
            403, f"免费用户最多创建 {limit} 个项目 — 购买套餐后可创建更多"
        )

    return True
