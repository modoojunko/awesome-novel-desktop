"""OAuth 授权流核心用例。"""
from __future__ import annotations

import re

from app.domain.devices import DeviceProfile, DeviceRegistry
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

_CHALLENGE_RE = re.compile(r"^[0-9a-f]{64}$")


def authorize_device(
    user_repo: UserRepo,
    code_repo: CodeRepo,
    device_repo: DeviceRepo,
    grant_repo: GrantRepo,
    username: str,
    *,
    _mark_outdated=None,
    password: str,
    pc_hash: str,
    pc_name: str = "",
    device_profile_b64: str = "",
    challenge: str = "",
) -> dict:
    # 0) 配对挑战（s-security-hardening）：缺失/不合法即拒——令牌只发给持有本机
    #    配对密钥的客户端。
    #    s-auth-outdated-signal：分档为独立 code=3（client_outdated）——challenge
    #    缺失是模糊信号（≠版本旧），msg 用动作导向；**先验密码再落标记**（防匿名
    #    刷标记表）；密码错误不暴露 outdated 语义（防探测）。
    challenge_ok = bool(_CHALLENGE_RE.fullmatch(challenge or ""))

    # 1) 验证用户
    user = user_repo.get(username)
    if not user or not verify_password(password, user.password_hash):
        return {"code": 1, "msg": "用户名或密码错误"}
    if not challenge_ok:
        from app.config import settings as _settings
        # 标记写库走调用方同一 db 事务：接口层注入回调（测试亦可注入桩）
        if _mark_outdated is not None:
            _mark_outdated(pc_hash)
        data = {"client_outdated": True,
                "download_url": _settings.CLIENT_DOWNLOAD_URL}
        if _settings.CLIENT_MIN_VERSION:
            data["latest_version"] = _settings.CLIENT_MIN_VERSION
        return {"code": 3, "msg": "需要更新后重试", "reason": "client_outdated",
                "data": data}
    # 惰性升级（s-security-hardening）：存量 PBKDF2 哈希验证成功即改写为 bcrypt
    if needs_rehash(user.password_hash):
        user_repo.update_password(username, hash_password(password))

    # 2) 设备注册
    profile = DeviceProfile.from_b64(device_profile_b64)
    fp = profile.fingerprint
    device = DeviceRegistry(
        id="",  # repo 自动生成
        user_id=username,
        fingerprint=fp,
        hostname=profile.hostname or pc_name,
        os=profile.os,
        os_arch=profile.os_arch,
    )
    existing = device_repo.get_by_fingerprint(username, fp) if fp else None
    is_new = existing is None
    device_repo.upsert(device)

    # 3) 查询套餐
    codes = code_repo.find_active_by_username(username)
    license_ = License(username=username).merge(codes)

    # 4) 写入授权凭证（token 携带 uid，jwt-uid-claim 与 web 签发同口径）；
    #    challenge 随授权落库——此后仅 pair/exchange（持本机密钥者）可换 token
    token = sign_jwt(username, user_repo.get_id(username), ver=user.token_version)
    grant_repo.upsert(
        pc_hash=pc_hash,
        username=username,
        token=token,
        enrolled=is_new,
        fingerprint=fp,
        challenge=challenge,
    )

    return {
        "code": 0,
        "data": {
            "message": "授权成功",
            "tier": license_.effective_tier,
            "expires_at": license_.max_expires_at.isoformat() if license_.max_expires_at else "",
        },
    }
