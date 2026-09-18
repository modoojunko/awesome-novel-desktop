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
from app.interfaces.guards import guard_identifiers

logger = logging.getLogger("api.client.auth")

from app.interfaces.client_api.router import router as r


@r.post("/api/authorize", dependencies=[guard_identifiers(body=("pc_hash",))])
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
        challenge=req.challenge,
    )
    logger.info("event=authorize.result user=%s code=%d", req.username, result["code"])
    if result["code"] == 0:
        db.commit()
    return result


@r.get("/api/check-auth", dependencies=[guard_identifiers(query=("pc_hash",))])
async def api_check_auth(pc_hash: str = "", db: Db = Depends(get_db)):
    """C端 轮询：该 pc_hash 是否已授权。"""
    if not pc_hash:
        return {"code": 1, "msg": "缺少 pc_hash"}
    try:
        grant = grant_repo(db).get(pc_hash)
        if grant:

            from app.domain.identity.deletion import is_due, remaining_days
            from app.infrastructure.repositories.factory import user_repo

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

            from app.interfaces.client_api.pairing import build_license_snapshot
            # ── s-security-hardening 硬切：本端点不再携带令牌——仅套餐刷新数据。
            #    令牌只经 POST /api/pair/exchange 发给持有本机配对密钥的请求
            #    （pc_hash 由硬件序列号派生、可推导，曾可未登录换取他人 30 天令牌）。──
            data = build_license_snapshot(db, grant.username)
            data["username"] = grant.username
            return {"code": 0, "data": data}
        return {"code": 1, "msg": "等待授权"}
    except Exception:
        logger.exception("event=check_auth_error pc_hash=%s", pc_hash)
        return {"code": -1, "msg": "内部错误，请查看服务器日志"}
