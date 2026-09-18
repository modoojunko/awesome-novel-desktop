"""用户名密码登录（门户使用，非 OAuth 流程）。"""
from __future__ import annotations

from app.application.identity.deletion_service import (
    deletion_payload,
    execute_due_deletions,
)
from app.application.identity.update_user_theme import stored_to_wire
from app.domain.identity.deletion import is_due
from app.domain.licensing import License
from app.infrastructure.repositories.base import (
    CodeRepo,
    DeviceRepo,
    GrantRepo,
    UserRepo,
)
from app.infrastructure.security.jwt import sign_jwt
from app.infrastructure.security.password import (
    hash_password,
    needs_rehash,
    verify_password,
)


def login(
    user_repo: UserRepo,
    code_repo: CodeRepo,
    username: str,
    password: str,
    device_repo: DeviceRepo | None = None,
    grant_repo: GrantRepo | None = None,
) -> dict:
    """登录验证用户名密码，返回 JWT + 套餐信息（theme 供前端登录即应用，免闪默认）。

    注销链路（account-deletion）：已注销 → 明确拒绝（用户名存在性本可经注册接口枚举，
    明示无新增泄漏，满足 US-6.2「清晰的已注销结果」）；撤销期 → 结构化状态供撤销页消费；
    撤销期已到期 → 惰性触发到期执行后再判（design D2 惰性触发主路径）。
    """
    user = user_repo.get(username)
    if not user or not verify_password(password, user.password_hash):
        return {"code": 1, "msg": "用户名或密码错误"}
    # 惰性升级（s-security-hardening）：存量 PBKDF2 哈希在验证成功时改写为 bcrypt，
    # 用户零感知、无需停机迁移；非口令变更，不触发会话撤销。
    if needs_rehash(user.password_hash):
        user_repo.update_password(username, hash_password(password))
    if user.is_locked():
        return {"code": 1, "msg": "账户已被锁定，请联系客服"}
    if user.is_deleted():
        return {"code": 1, "msg": "该账号已注销", "data": {"deleted": True}}
    if user.is_deletion_pending():
        deadline = user.deletion_deadline
        if device_repo is not None and grant_repo is not None and deadline and is_due(deadline):
            execute_due_deletions(user_repo, code_repo, device_repo, grant_repo,
                                  usernames=[username])
            user = user_repo.get(username)
            if user and user.is_deleted():
                return {"code": 1, "msg": "该账号已注销", "data": {"deleted": True}}
        else:
            # code 4 = 注销进行中（避开 code 2 = 会话失效的全局前端拦截约定，见 design 补注）
            return {"code": 4, "msg": "账号注销进行中",
                    "data": {"deletion_pending": True, **deletion_payload(user)}}

    codes = code_repo.find_active_by_username(username)
    license_ = License(username=username).merge(codes)
    token = sign_jwt(username, user_repo.get_id(username), ver=user.token_version)

    return {
        "code": 0,
        "data": {
            "token": token,
            "tier": license_.effective_tier,
            "expires_at": license_.max_expires_at.isoformat() if license_.max_expires_at else "",
            "theme": stored_to_wire(user.theme),
        },
    }
