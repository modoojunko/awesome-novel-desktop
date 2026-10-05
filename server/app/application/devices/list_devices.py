"""列出用户所有设备（含激活状态）。"""
from __future__ import annotations

from app.domain.devices import ActivationPolicy
from app.domain.licensing import License, tier_policy
from app.infrastructure.repositories.base import CodeRepo, DeviceRepo
from app.infrastructure.repositories.payments_repo import TierRepo


def list_devices(device_repo: DeviceRepo, code_repo: CodeRepo, username: str,
                 db=None) -> dict:
    devices = device_repo.list_by_user(username)
    codes = code_repo.find_active_by_username(username)
    license_ = License(username=username).merge(codes)
    tier = license_.effective_tier
    active_limit = _device_limit(db, tier)

    result = ActivationPolicy.compute_all(devices, active_limit, tier)
    activated_count = sum(1 for d in result if d["activated"])

    return {
        "code": 0,
        "data": result,
        "total_count": len(result),
        "activated_count": activated_count,
        "active_limit": active_limit,
    }


def _device_limit(db, tier: str) -> int:
    """设备限额：tiers.device_limit 列单源（60s TTL 缓存）；行缺/DB 不可用退
    tier_policy 兜底（tier-catalog spec 允许的兜底口径）。"""
    if db is not None:
        try:
            for row in TierRepo(db).find_all_cached():
                if row.get("key") == tier:
                    return int(row.get("device_limit") or 1)
        except Exception:  # noqa: BLE001 —— 兜底路径
            pass
    return tier_policy.get_device_limit(tier)
