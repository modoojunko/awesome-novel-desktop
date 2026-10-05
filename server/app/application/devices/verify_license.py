"""检查 License 和设备绑定状态（C端 心跳验证）。"""
from __future__ import annotations

from app.application.identity.deletion_service import (
    deletion_payload,
    lazy_execute_if_due,
)
from app.domain.licensing import License, tier_policy
from app.infrastructure.repositories.base import (
    CodeRepo,
    DeviceRepo,
    GrantRepo,
    UserRepo,
)


def verify_license(
    user_repo: UserRepo,
    code_repo: CodeRepo,
    device_repo: DeviceRepo,
    grant_repo: GrantRepo,
    username: str,
    pc_hash: str,
    token: str,
    db=None,
) -> dict:
    """验证 License + 设备绑定状态（C端 心跳用）。"""
    from app.infrastructure.security.jwt import verify_jwt

    # 1) 验证 token（JWT 校验 + username 比对）
    payload = verify_jwt(token)
    if not payload:
        return {"code": 2, "msg": "Token 无效"}
    token_username = payload.get("sub", "")
    if token_username != username:
        return {"code": 2, "msg": "Token 与用户名不匹配"}

    # 2) 用户存在性（惰性触发到期执行后再判，design D2 主路径）
    lazy_execute_if_due(user_repo, code_repo, device_repo, grant_repo, username)
    user = user_repo.get(username)
    if not user:
        return {"code": 1, "msg": "用户不存在"}

    # 2.5) 注销状态门禁（account-deletion）：已注销/撤销期均拒绝，C端按会话失效处理
    # （spec R4：撤销期内付费与套餐功能 MUST NOT 正常使用；本地作品不受影响由客户端提示）
    if user.is_deleted():
        return {"code": 1, "msg": "该账号已注销",
                "data": {"session_invalid": True, "deleted": True, "works_local_only": True}}
    if user.is_deletion_pending():
        return {"code": 2, "msg": "账号注销进行中，请到网页控制台撤销或等待到期",
                "data": {"session_invalid": True, "deletion_pending": True,
                         **deletion_payload(user)}}

    # 3) License 有效性（实时聚合 codes 表）
    codes = code_repo.find_active_by_username(username)
    license_ = License(username=username).merge(codes)
    license_valid = license_.is_valid()

    # 4) 设备绑定校验（域对象 username 已由 grant_repo 从 user_id 反查回 username）
    grant = grant_repo.get(pc_hash)
    device_valid = grant is not None and grant.username == username
    valid = license_valid and device_valid

    # 5) 设备总数
    devices = device_repo.list_by_user(username)

    return {
        "code": 0,
        "data": {
            "valid": valid,
            "license_valid": license_valid,
            "device_valid": device_valid,
            "expires_at": license_.max_expires_at.isoformat() if license_.max_expires_at else "",
            "tier": license_.effective_tier,
            "devices_count": len(devices),
            "max_devices": _device_limit(db, license_.effective_tier),
        },
    }


def _device_limit(db, tier: str) -> int:
    """设备限额：tiers.device_limit 列单源（60s TTL 缓存）；行缺/DB 不可用退
    tier_policy 兜底。db=None 时直接走兜底（调用方未迁移完的兼容路径）。"""
    if db is not None:
        try:
            from app.infrastructure.repositories.payments_repo import TierRepo
            for row in TierRepo(db).find_all_cached():
                if row.get("key") == tier:
                    raw = row.get("device_limit")
                    if raw is None:
                        break
                    return int(raw)
        except Exception:  # noqa: BLE001 —— 兜底路径
            logging.getLogger(__name__).warning("event=tier_limit_fallback tier=%s", tier)
    return tier_policy.get_device_limit(tier)
