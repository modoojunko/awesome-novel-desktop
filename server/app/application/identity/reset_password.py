"""密保重置密码。"""
from __future__ import annotations

from app.infrastructure.repositories.base import UserRepo
from app.infrastructure.security.password import (
    hash_password,
    normalize_security_answer,
    password_too_long,
    verify_password,
)


def reset_password(user_repo: UserRepo, username: str, security_answer: str, new_password: str) -> dict:
    user = user_repo.get(username)
    if not user:
        return {"code": 1, "msg": "用户不存在"}
    # 密保答案归一化（去首尾空白 + casefold）：与设置侧同一通道
    if not verify_password(normalize_security_answer(security_answer), user.security_answer_hash):
        return {"code": 1, "msg": "密保答案错误"}
    if password_too_long(new_password):
        return {"code": 1, "msg": "密码过长（最多 72 字节）"}

    user_repo.update_password(username, hash_password(new_password))
    return {"code": 0, "data": {"success": True}}
