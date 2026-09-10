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


def ai_access_granted() -> bool:
    """门控层非抛出版本：供「可选 AI」路径（如归档摘要）决定是否调用 AI。

    业务层不得自判会员（D11 边界禁令③）——需要「有则用、无则降级」的语义时，
    调本函数而不是在业务层内联 `check_permission()`。
    """
    try:
        return bool(check_permission().get("is_member", False))
    except Exception:  # noqa: BLE001
        return False


async def require_novel_model(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """门控层（D11 ⑤）：本书模型就绪——与 `require_ai_access` 并列挂载，会员在前。

    判据**复用判定层** `compute_ai_state`（不得内联重写）。未就绪一律 503 +
    `detail={reason, message}`，reason 与前端 `ai_state` 共用同一枚举；
    `reason=missing_model` 是前置未满足，**不可当瞬时故障重试**。
    """
    from ai_state import (
        compute_ai_state,
        no_key_message,
        state_message,
        user_has_ai_key,
    )

    result = await db.execute(
        select(Novel).where(Novel.id == project_id, Novel.user_id == user["id"])
    )
    novel = result.scalar_one_or_none()
    if novel is None:
        raise HTTPException(404, "Project not found")

    config = None
    if novel.ai_config_id:
        config = await db.get(ApiConfig, novel.ai_config_id)

    state = compute_ai_state(novel, config, await user_has_ai_key(db, user["id"]))
    if state == "ready":
        return True

    message = no_key_message(config) if state == "no_key" else state_message(state)
    raise HTTPException(503, detail={"reason": state, "message": message})


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
