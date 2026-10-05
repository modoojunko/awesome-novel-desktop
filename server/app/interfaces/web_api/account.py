"""门户账户 API：web/login, web/register, user/me, user/password, user/security, user/deletion*。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.application.identity.deletion_service import (
    blocked_assets,
    request_asset_refund,
    request_deletion,
    revoke_deletion,
)
from app.application.identity.deletion_service import (
    deletion_status as deletion_status_uc,
)
from app.application.identity.login import login
from app.application.identity.register_user import register_user
from app.application.identity.update_user_theme import (
    InvalidThemeError,
    update_user_theme,
)
from app.infrastructure.repositories.factory import (
    code_repo,
    device_repo,
    grant_repo,
    user_repo,
)
from app.infrastructure.security.password import (
    hash_password,
    normalize_security_answer,
    password_too_long,
    verify_password,
)
from app.interfaces.deps import Db, get_current_user_or_none, get_db
from app.interfaces.dto import (
    AssetRefundRequest,
    ChangePasswordRequest,
    DeletionRequest,
    DeletionRevokeRequest,
    PreferencesRequest,
    SecurityRequest,
    WebLoginRequest,
    WebRegisterRequest,
    fail,
    ok,
)
from app.interfaces.guards import guard_identifiers

logger = logging.getLogger("api.web.account")

# 持有自己的 APIRouter，由 web_api/router.py 显式 include。
# 勿改回「from router import r 装饰器注册」的副作用写法：那依赖 import 副作用，
# ruff 会把"未使用"的模块 import 当死代码删掉，路由随之失挂（线上登录 404 事故）。
r = APIRouter(tags=["web"])


@r.post("/api/web/login")
async def api_web_login(req: WebLoginRequest, db: Db = Depends(get_db)):
    """登录返回 JWT token。撤销期/已注销账号返回结构化状态（account-deletion）。"""
    return login(user_repo(db), code_repo(db), req.username.strip(), req.password,
                 device_repo=device_repo(db), grant_repo=grant_repo(db))


@r.post("/api/web/register")
async def api_web_register(req: WebRegisterRequest, db: Db = Depends(get_db)):
    result = register_user(
        user_repo(db), code_repo(db),
        req.username.strip(), req.password,
        req.security_question, req.security_answer,
        db=db,
    )
    if result["code"] == 0:
        db.commit()
    return result


@r.get("/api/user/me")
async def api_user_me(db: Db = Depends(get_db), username: str = Depends(get_current_user_or_none)):
    if not username:
        return fail(code=1, msg="未登录")
    from app.application.licensing.get_license_info import get_license_info
    return get_license_info(user_repo(db), code_repo(db), username)


@r.put("/api/user/password")
async def api_user_password(req: ChangePasswordRequest, db: Db = Depends(get_db), username: str = Depends(get_current_user_or_none)):
    if not username:
        return fail(code=1, msg="未登录")
    user = user_repo(db).get(username)
    if not user or not verify_password(req.old_password, user.password_hash):
        return fail(code=1, msg="旧密码错误")
    if len(req.new_password) < 6:
        return fail(code=1, msg="密码至少6位")
    if password_too_long(req.new_password):
        return fail(code=1, msg="密码过长（最多 72 字节）")
    # 会话撤销（R5）：改密码即版本+1，全部存量令牌（含其他端）失效
    user_repo(db).update_password(
        username, hash_password(req.new_password),
        token_version=(user.token_version or 0) + 1)
    db.commit()
    return ok({"success": True})


@r.put("/api/user/security")
async def api_user_security(req: SecurityRequest, db: Db = Depends(get_db), username: str = Depends(get_current_user_or_none)):
    if not username:
        return fail(code=1, msg="未登录")
    # 会话撤销（R5）：改密保同改密口径——密保可重置密码，等价凭据变更
    user_row = user_repo(db).get(username)
    user_repo(db).update_security(
        username, req.security_question,
        hash_password(normalize_security_answer(req.security_answer)),
        token_version=((user_row.token_version or 0) + 1) if user_row else None)
    db.commit()
    return ok({"success": True})


@r.put("/api/user/preferences")
async def api_user_preferences(req: PreferencesRequest, db: Db = Depends(get_db), username: str = Depends(get_current_user_or_none)):
    """主题偏好写入（theme-preferences）。非法 key 422，不落库。"""
    if not username:
        return fail(code=1, msg="未登录")
    try:
        theme = update_user_theme(user_repo(db), username, req.theme)
    except InvalidThemeError:
        return JSONResponse(status_code=422, content=fail(code=422, msg=f"不支持的主题：{req.theme}"))
    db.commit()
    return ok({"theme": theme if theme else "teal"})


# ── 账号自助注销（account-deletion）：S 端向导端点 ──

@r.get("/api/user/deletion-status")
async def api_user_deletion_status(db: Db = Depends(get_db), username: str = Depends(get_current_user_or_none)):
    """注销状态查询（R7）：是否已申请 / 剩余撤销天数 / 到期执行时刻。"""
    if not username:
        return fail(code=1, msg="未登录")
    user = user_repo(db).get(username)
    if not user:
        return fail(code=1, msg="用户不存在")
    return deletion_status_uc(user)


@r.get("/api/user/deletion-assets")
async def api_user_deletion_assets(db: Db = Depends(get_db), username: str = Depends(get_current_user_or_none)):
    """未消耗权益清单（US-3.1：向导权益处置步展示用，登录态查询）。"""
    if not username:
        return fail(code=1, msg="未登录")
    return ok({"blocked_assets": blocked_assets(code_repo(db), username)})


@r.post("/api/user/deletion/refund-request", dependencies=[guard_identifiers(body=("code_id",))])
async def api_user_deletion_refund_request(req: AssetRefundRequest, db: Db = Depends(get_db), username: str = Depends(get_current_user_or_none)):
    """权益级退款申请（用户评审 2026-08-31：每个未消耗权益独立退款入口）。"""
    if not username:
        return fail(code=1, msg="未登录")
    return request_asset_refund(code_repo(db), user_repo(db), username, req.code_id)


@r.post("/api/user/deletion")
async def api_user_deletion(req: DeletionRequest, db: Db = Depends(get_db), username: str = Depends(get_current_user_or_none)):
    """受理注销申请（R2/R3/R4）：密码确认 + 未消耗权益校验 + CAS 进入 15 天撤销期。"""
    if not username:
        return fail(code=1, msg="未登录")
    return request_deletion(user_repo(db), code_repo(db), username, req.password, req.waive_assets)


@r.post("/api/user/deletion/revoke")
async def api_user_deletion_revoke(req: DeletionRevokeRequest, db: Db = Depends(get_db)):
    """撤销注销（R4）：撤销期账号登录被拒、无 JWT——用户名+密码本身即身份证明。"""
    return revoke_deletion(user_repo(db), req.username.strip(), req.password)
