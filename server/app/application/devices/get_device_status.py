"""C端 设备状态查询（裸字段格式，冻结不改变）。"""
from __future__ import annotations

import logging

from app.domain.devices import ActivationPolicy
from app.domain.licensing import License, tier_policy
from app.infrastructure.repositories.base import CodeRepo, DeviceRepo, GrantRepo


def get_device_status(
    grant_repo: GrantRepo,
    device_repo: DeviceRepo,
    code_repo: CodeRepo,
    username: str,
    pc_hash: str,
    db=None,
) -> dict:
    """返回设备状态（裸字段格式）。"""
    grant = grant_repo.get(pc_hash)
    enrolled = grant.enrolled if grant else False
    fp = grant.fingerprint if grant else ""

    codes = code_repo.find_active_by_username(username)
    license_ = License(username=username).merge(codes)
    tier = license_.effective_tier
    active_limit = _device_limit(db, tier)

    devices = device_repo.list_by_user(username)
    target_fp = fp or (devices[0].fingerprint if devices else "")

    device_name = "未知设备"
    for d in devices:
        if d.fingerprint == target_fp:
            device_name = d.display_name
            break

    activation = ActivationPolicy.compute(devices, active_limit, target_fp, tier)

    return {
        "enrolled": enrolled,
        "device_name": device_name,
        "activated": activation["activated"],
        "reason": activation["reason"],
        "device_count": activation["total_count"],
        "active_limit": activation["active_limit"],
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
