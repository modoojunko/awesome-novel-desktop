from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class DeviceRegistry:
    """设备注册实体。"""
    id: str
    user_id: str
    fingerprint: str
    hostname: str
    os: str
    os_arch: str
    last_active_at: datetime | None = None
    bound_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def display_name(self) -> str:
        return self.hostname or "未知设备"


@dataclass
class DeviceGrant:
    """设备授权凭证实体（对应 device_grants 表）。"""
    pc_hash: str
    username: str
    token: str
    enrolled: bool = False
    fingerprint: str = ""
    challenge: str = ""


@dataclass
class DeviceProfile:
    """设备指纹值对象。从 Base64 URL-safe 字符串解码。"""

    fingerprint: str
    hostname: str
    os: str
    os_arch: str

    @staticmethod
    def from_b64(encoded: str) -> DeviceProfile:
        """从 Base64 解码。解码失败返回空值。"""
        import base64
        import binascii
        import json
        if not encoded:
            return DeviceProfile("", "", "", "")
        try:
            padding = 4 - len(encoded) % 4
            if padding != 4:
                encoded += "=" * padding
            raw = base64.urlsafe_b64decode(encoded)
            data = json.loads(raw)
            return DeviceProfile(
                fingerprint=data.get("f", ""),
                hostname=data.get("h", ""),
                os=data.get("o", ""),
                os_arch=data.get("a", ""),
            )
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError, binascii.Error):
            return DeviceProfile("", "", "", "")

    def to_b64(self) -> str:
        """编码为 Base64 URL-safe 格式。"""
        import base64
        import json
        payload = {
            "f": self.fingerprint,
            "h": self.hostname,
            "o": self.os,
            "a": self.os_arch,
        }
        raw = json.dumps(payload, separators=(",", ":"))
        return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    @property
    def is_empty(self) -> bool:
        return not self.fingerprint and not self.hostname
