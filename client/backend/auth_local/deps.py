"""FastAPI Dependencies — 权限门控

require_ai_access(): AI 功能门控（tier-plan-four-tiers 起按 feature key）——
    非会员 403 member_required；会员但档位不够 403 feature_required（带
    feature/tier_required）；过档位门后还需配置 API Key，未配置 503 引导设置。
ai_feature(key): 路由装饰器——setattr 标注端点所需 key（不做 wraps，保证
    route.endpoint 即标注对象）；require_ai_access 读 route.endpoint.__ai_feature__。
require_project_limit(): 按快照 limits.max_projects 拦截；会员不限。
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models.api_config import ApiConfig
from models.project import Novel
from models.user import User

from .middleware import get_current_user
from .service import check_permission, ensure_entitlement_snapshot, get_local_config


def ai_feature(key: str):
    """路由装饰器：标注端点所需 feature key（tier-plan-four-tiers）。

    setattr 后返回原函数——**不做 functools.wraps**（wrap 会换掉函数对象，
    route.endpoint 就不是标注对象，require_ai_access 读不到 key）；
    加在 `@router.post` 之下（先路由注册后标注，route.endpoint 即它）。
    """
    def _decorate(fn):
        setattr(fn, "__ai_feature__", key)
        return fn
    return _decorate


def _route_feature(request) -> str | None:
    """从请求路由读端点标注的 feature key；防御式——request/route/endpoint 任一
    缺失（直调、测试桩、非路由上下文）一律返回 None＝退回二元会员语义。"""
    if request is None:
        return None
    try:
        route = request.scope.get("route")
        return getattr(getattr(route, "endpoint", None), "__ai_feature__", None)
    except AttributeError:
        return None


def _tier_required_for(feature: str) -> str | None:
    """key → 最低档：按档位序扫 STANDARD_FALLBACK，首个含该 key 的档。
    （B3 的 tier_catalog 目录下发后改走目录 rank 序；目录缺失退本镜像，
    镜像与 entitlement-defaults.json 对拍锁定。）"""
    from .service import STANDARD_FALLBACK
    for tier in ("standard", "pro", "max"):
        if feature in STANDARD_FALLBACK.get(tier, {}).get("features", []):
            return tier
    return None


_TIER_RANK = {"none": 0, "free": 1, "standard": 2, "pro": 3, "trial": 3, "max": 4}  # trial=pro 同权（含朱雀）


async def require_ai_access(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request=None,
):
    """AI 功能门控：非会员 403 member_required → 档位不够 403 feature_required
    → 未配 Key 503。

    403 detail 为结构化 {reason, message, feature?, tier_required?}，
    前端 request() 据此弹分档升级引导，而非裸错误。request 为 FastAPI 注入；
    直调（测试/非路由路径）不传 request＝无 feature 标注，保持二元会员语义。
    """
    # 0) 快照三段式：不完整时先重同步一次（async 边界），失败走档位标准兜底
    await ensure_entitlement_snapshot()

    # 1) 会员校验：免费/过期用户即使配置了 Key 也拦截（AI 是会员权益）
    perm = check_permission()
    if not perm.get("is_member", False):
        message = (
            "AI 是会员功能 — 套餐已过期，续费后继续使用"
            if perm.get("expired")
            else "AI 是会员功能 — 开通套餐或 7 天免费试用后即可使用"
        )
        raise HTTPException(
            status_code=403,
            detail={"reason": "member_required", "message": message},
        )

    # 1.5) 档位校验：端点标注 key → feature_required（快照单源）
    # 完整快照在场（branch 3 才透传 entitlement）→ 按 features 判（快照可能比
    # tier 标签新/旧，以快照为准）；快照缺失/降级 → 退档位序比较。
    feature = _route_feature(request)
    if feature:
        ent = perm.get("entitlement")
        if isinstance(ent, dict):
            allowed = feature in ent.get("features", [])
        else:
            tier_required = _tier_required_for(feature)
            allowed = tier_required is not None and (
                _TIER_RANK.get(perm.get("tier", "none"), 0)
                >= _TIER_RANK.get(tier_required, 99)
            )
        if not allowed:
            tier_required = _tier_required_for(feature) or "pro"
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": "feature_required",
                    "feature": feature,
                    "tier_required": tier_required,
                    "message": f"当前套餐不含该能力 — 升级到 {tier_required.upper()} 后可用",
                },
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


def ai_access_granted(feature: str | None = None) -> bool:
    """门控层非抛出版本：供「可选 AI」路径（如归档摘要）决定是否调用 AI。

    业务层不得自判会员（D11 边界禁令③）——需要「有则用、无则降级」的语义时，
    调本函数而不是在业务层内联 `check_permission()`。
    feature 传 key 时按档位判定（标准/PRO/MAX 各取所需）；None 保持二元语义
    （既有消费点零改动）。
    """
    try:
        perm = check_permission()
        if not perm.get("is_member", False):
            return False
        if feature is None:
            return True
        tier_required = _tier_required_for(feature)
        if not tier_required:
            return True
        return _TIER_RANK.get(perm.get("tier", "none"), 0) >= _TIER_RANK.get(tier_required, 99)
    except Exception:  # noqa: BLE001
        return False


async def ensure_novel_model_ready(
    db: AsyncSession,
    user_id: str,
    project_id: str,
) -> bool:
    """本书模型就绪判定核心（key-crypto-selfcontained 抽取）。

    `require_novel_model` 复用本函数；路由路径无 `project_id` 的场景
    （story 推演：`project_id` 在会话引擎内）在端点内取值后直调本函数。
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
        select(Novel).where(Novel.id == project_id, Novel.user_id == user_id)
    )
    novel = result.scalar_one_or_none()
    if novel is None:
        raise HTTPException(404, "Project not found")

    config = None
    if novel.ai_config_id:
        config = await db.get(ApiConfig, novel.ai_config_id)

    state = compute_ai_state(novel, config, await user_has_ai_key(db, user_id))
    if state == "ready":
        return True

    message = no_key_message(config) if state == "no_key" else state_message(state)
    raise HTTPException(503, detail={"reason": state, "message": message})


async def require_novel_model(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """门控层（D11 ⑤）：本书模型就绪——与 `require_ai_access` 并列挂载，会员在前。

    判定核心见 `ensure_novel_model_ready`（判据复用判定层，本函数只做 DI 绑定）。
    """
    await ensure_novel_model_ready(db, user["id"], project_id)
    return True


def _book_limit_message(tier: str, limit: int) -> str:
    """建书满额 403 文案按档双口径（3.4）：有档显档名，免费走免费口径。"""
    display = {"standard": "标准", "pro": "PRO", "max": "MAX"}.get(tier)
    if display:
        return f"当前套餐最多创建 {limit} 个项目 — 升级套餐后可创建更多"
    return f"免费用户最多创建 {limit} 个项目 — 开通套餐后可创建更多"


async def require_project_limit(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目上限门控：免费/过期用户最多 1 个项目，会员不限"""
    # 快照三段式：不完整时先重同步一次（async 边界），失败走档位标准兜底
    await ensure_entitlement_snapshot()

    perm = check_permission()
    limit = perm.get("project_limit")
    tier = perm.get("tier", "none")
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
            403, _book_limit_message(tier, limit)
        )

    return True
