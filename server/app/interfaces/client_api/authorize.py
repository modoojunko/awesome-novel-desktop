"""C端 设备授权流：authorize / check-auth。

授权页实体由 S端 前端 /auth（AuthPage.vue）唯一承载，C端 直接打开该页；
后端内联授权页（原 GET /api/auth-page）已删除（auth-page-direct-entry），
契约测试固化其 404。
"""
from __future__ import annotations

import logging

from fastapi import Depends

from app.application.devices.authorize_device import authorize_device
from app.infrastructure.repositories.factory import (
    code_repo,
    device_repo,
    grant_repo,
    user_repo,
)
from app.interfaces.deps import Db, get_db
from app.interfaces.dto import AuthorizeRequest

logger = logging.getLogger("api.client.auth")

from app.interfaces.client_api.router import router as r


@r.post("/api/authorize")
async def api_authorize(
    req: AuthorizeRequest,
    db: Db = Depends(get_db),
):
    logger.info("event=authorize.start user=%s", req.username)
    result = authorize_device(
        user_repo(db), code_repo(db), device_repo(db), grant_repo(db),
        username=req.username.strip(),
        password=req.password,
        pc_hash=req.pc_hash,
        pc_name=req.pc_name,
        device_profile_b64=req.device_profile,
    )
    logger.info("event=authorize.result user=%s code=%d", req.username, result["code"])
    if result["code"] == 0:
        db.commit()
    return result


@r.get("/api/check-auth")
async def api_check_auth(pc_hash: str = "", db: Db = Depends(get_db)):
    """C端 轮询：该 pc_hash 是否已授权。"""
    if not pc_hash:
        return {"code": 1, "msg": "缺少 pc_hash"}
    try:
        grant = grant_repo(db).get(pc_hash)
        if grant:
            from datetime import datetime, timedelta, timezone

            from app.domain.identity.deletion import is_due, remaining_days
            from app.domain.licensing import License
            from app.infrastructure.repositories.factory import user_repo
            from app.infrastructure.repositories.payments_repo import OrderRepo

            # 注销门禁（account-deletion）：撤销期付费功能暂停（code 2）；已注销拒绝
            # （执行时 device_grants 已清空，此分支为补偿扫描先行标记的兜底）
            user = user_repo(db).get(grant.username)
            if user and user.is_deleted():
                return {"code": 1, "msg": "该账号已注销", "data": {"deleted": True}}
            if user and user.is_deletion_pending():
                if user.deletion_deadline and is_due(user.deletion_deadline):
                    from app.application.identity.deletion_service import (
                        execute_due_deletions,
                    )
                    execute_due_deletions(
                        user_repo(db), code_repo(db), device_repo(db), grant_repo(db),
                        usernames=[grant.username],
                    )
                    return {"code": 1, "msg": "该账号已注销", "data": {"deleted": True}}
                return {
                    "code": 2,
                    "msg": "账号注销进行中",
                    "data": {
                        "deletion_pending": True,
                        "days_left": remaining_days(user.deletion_deadline) if user.deletion_deadline else 0,
                        "deadline": user.deletion_deadline.isoformat() if user.deletion_deadline else "",
                    },
                }

            codes = code_repo(db).find_active_by_username(grant.username)
            license_ = License(username=grant.username).merge(codes)

            data = {
                "token": grant.token,
                "username": grant.username,
                "tier": license_.effective_tier,
                "expires_at": license_.max_expires_at.isoformat() if license_.max_expires_at else "",
            }

            # ── 权益快照（c-s-entitlement-sync，契约 v1）：档位目录配置 →
            #    ENTITLEMENT_DEFAULTS 兜底（档位行缺配置/坏 JSON/未知档位）；
            #    免费基线 = 空 features + max_projects=1。排队/冻结/收回语义由
            #    License.merge 继承，快照随下次 check-auth 自动反映。──
            from app.config import settings as _settings
            from app.infrastructure.repositories.payments_repo import TierRepo

            tier_cfg = TierRepo(db).find_entitlement_by_key(license_.effective_tier)
            ent = tier_cfg or _settings.ENTITLEMENT_DEFAULTS.get(
                license_.effective_tier, _settings.ENTITLEMENT_DEFAULTS["none"])
            data["entitlement"] = {"v": 1, **ent}

            # ── A4 扩展（可选字段，无支付数据时省略）──
            # days_remaining：北京自然日口径（今日 0 点到 expires_at，floor）；无套餐/免费省略
            if license_.max_expires_at:
                tier = license_.effective_tier
                if tier not in ("none", "free"):
                    bj_tz = timezone(timedelta(hours=8))
                    expires_bj = license_.max_expires_at.astimezone(bj_tz)
                    today0_bj = datetime.now(bj_tz).replace(
                        hour=0, minute=0, second=0, microsecond=0)
                    days = (expires_bj - today0_bj).days
                    days = max(days, 0)
                    data["days_remaining"] = days

            # attention：账号动态（退款进行中含冷静期 / 冻结待核对）
            uid = user_repo(db).get_id(grant.username)
            if uid:
                flags = OrderRepo(db).attention_flags(uid)
                if flags["refund_processing"] or flags["verify_pending"]:
                    data["attention"] = flags

            return {"code": 0, "data": data}
        return {"code": 1, "msg": "等待授权"}
    except Exception:
        logger.exception("event=check_auth_error pc_hash=%s", pc_hash)
        return {"code": -1, "msg": "内部错误，请查看服务器日志"}
