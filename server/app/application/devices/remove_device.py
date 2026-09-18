"""移除设备。"""
from __future__ import annotations

from app.infrastructure.repositories.base import DeviceRepo, GrantRepo


def remove_device(device_repo: DeviceRepo, grant_repo: GrantRepo,
                  username: str, device_id: str) -> dict:
    # s-security-hardening R5：移除设备须同步清除其授权凭证（此前只删登记行，
    # 被移设备的令牌仍能通过 /api/verify 的设备校验）。
    target = next(
        (d for d in device_repo.list_by_user(username) if str(d.id) == str(device_id)),
        None,
    )
    device_repo.delete_by_id(device_id, username)
    if target is not None and target.fingerprint:
        grant_repo.delete_by_fingerprint(username, target.fingerprint)
    return {"code": 0, "data": {"success": True}}
