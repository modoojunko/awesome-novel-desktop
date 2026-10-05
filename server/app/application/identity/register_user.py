"""注册新用户 + 赠送 7 天试用码。"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

from app.domain.identity import User
from app.domain.licensing import ActivationCode
from app.infrastructure.repositories.base import CodeRepo, UserRepo
from app.infrastructure.security.password import (
    hash_password,
    normalize_security_answer,
    password_too_long,
)

# 新注册用户名白名单（s-security-hardening）：只约束新账号；存量用户名零约束，
# 登录/改密/注销等既有路径不设形态门槛（拦截会把人锁在门外）。
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-]{3,32}$")
_USERNAME_HINT = "用户名需为 3–32 位字母、数字、下划线或连字符"


def register_user(
    user_repo: UserRepo,
    code_repo: CodeRepo,
    username: str,
    password: str,
    security_question: str = "",
    security_answer: str = "",
    db=None,
) -> dict:
    """注册用户 + 送 7 天 trial 码。返回 {token, tier, expires_at}。"""
    if not _USERNAME_RE.fullmatch(username or ""):
        return {"code": 1, "msg": _USERNAME_HINT}
    if user_repo.exists(username):
        return {"code": 1, "msg": "用户名已存在"}
    if password_too_long(password):
        return {"code": 1, "msg": "密码过长（最多 72 字节）"}

    answer_hash = hash_password(normalize_security_answer(security_answer)) if security_answer else ""
    user = User(
        username=username,
        password_hash=hash_password(password),
        status="active",
        security_question=security_question,
        security_answer_hash=answer_hash,
    )
    user_repo.create(user)
    user_repo.flush()  # SQLite 下确保用户已持久化，后续试用码 FK 不失败

    # 解析代理键 user_id（一次性迁移后 FK 引用 id 而非 username）
    user_id = user_repo.get_id(username)

    # 送 7 天试用 —— 与创建用户在同一事务中
    trial_code_id = f"TRIAL-{uuid.uuid4().hex[:8].upper()}"
    today = datetime.now(UTC).date()  # UTC 日期（存储 naive UTC 口径，不依赖容器 TZ）
    # 试用时长：trial 行 duration_days 单源（tier-catalog 改库即生效）；行缺/DB
    # 不可用退 7（历史口径）。
    trial_days = 7
    try:
        from app.infrastructure.repositories.payments_repo import TierRepo
        for row in TierRepo(db).find_all_cached():
            if row.get("key") == "trial":
                raw = row.get("duration_days")
                if raw is not None:  # 0 天是合法配置（禁试用），缺失才落兜底 7
                    trial_days = int(raw)
                break
    except Exception:  # noqa: BLE001 —— 兜底路径
        pass
    expires = today + timedelta(days=trial_days)
    trial = ActivationCode(
        code_id=trial_code_id,
        tier="trial",
        duration_days=trial_days,
        status="unused",
        user_id=user_id,  # 代理键 int
        expires_at=None,
        activated_at=None,
        created_at=datetime.now(UTC).replace(tzinfo=None),
        created_by="system",
    )
    code_repo.create(trial)
    code_repo.activate(trial_code_id, username, expires)

    from app.infrastructure.security.jwt import sign_jwt
    token = sign_jwt(username, user_id, ver=0)  # 新账号版本 0

    return {
        "code": 0,
        "data": {
            "token": token,
            "tier": "trial",
            "expires_at": expires.isoformat(),
        },
    }
