"""CloudBase PG HTTP API 设备注册仓储。"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx

from app.domain.devices import DeviceRegistry
from app.infrastructure.repositories.pg_http.client import (
    PgRestClient,
    is_unique_violation,
    parse_dt,
    to_iso,
)

_TABLE = "device_registry"


class PgHttpDeviceRepo:
    def __init__(self, client: PgRestClient):
        self.client = client

    @staticmethod
    def _to_domain(doc: dict) -> DeviceRegistry:
        return DeviceRegistry(
            id=doc["id"],
            user_id=doc["user_id"],
            fingerprint=doc.get("fingerprint", "") or "",
            hostname=doc.get("hostname", "") or "",
            os=doc.get("os", "") or "",
            os_arch=doc.get("os_arch", "") or "",
            last_active_at=parse_dt(doc.get("last_active_at")),
            bound_at=parse_dt(doc.get("bound_at")),
            created_at=parse_dt(doc.get("created_at")),
            updated_at=parse_dt(doc.get("updated_at")),
        )

    def get_by_fingerprint(self, user_id: str, fingerprint: str) -> DeviceRegistry | None:
        doc = self.client.find_one(_TABLE, {"user_id": user_id, "fingerprint": fingerprint})
        return self._to_domain(doc) if doc else None

    def list_by_user(self, user_id: str) -> list[DeviceRegistry]:
        docs = self.client.find(_TABLE, {"user_id": user_id}, sort=[("last_active_at", "desc")])
        return [self._to_domain(d) for d in docs]

    def _update_existing(self, device: DeviceRegistry, now: datetime,
                         existing: dict) -> DeviceRegistry:
        """按 (user_id, fingerprint) 覆盖展示字段并读回真实行（id/bound_at 以库内为准）。"""
        self.client.update(
            _TABLE,
            {"user_id": device.user_id, "fingerprint": device.fingerprint},
            {
                "hostname": device.hostname,
                "os": device.os,
                "os_arch": device.os_arch,
                "last_active_at": to_iso(now),
                "updated_at": to_iso(now),
            },
        )
        doc = self.client.find_one(
            _TABLE, {"user_id": device.user_id, "fingerprint": device.fingerprint})
        merged = doc or existing
        return DeviceRegistry(
            id=merged.get("id", ""),
            user_id=device.user_id,
            fingerprint=device.fingerprint,
            hostname=device.hostname,
            os=device.os,
            os_arch=device.os_arch,
            last_active_at=now,
            bound_at=parse_dt(merged.get("bound_at")),
            created_at=parse_dt(merged.get("created_at")),
            updated_at=now,
        )

    def upsert(self, device: DeviceRegistry) -> DeviceRegistry:
        now = datetime.now(UTC).replace(tzinfo=None)
        existing = self.client.find_one(_TABLE, {
            "user_id": device.user_id, "fingerprint": device.fingerprint,
        })
        if existing:
            return self._update_existing(device, now, existing)
        # 省略时间戳字段：数据库 DEFAULT now()
        doc_id = uuid.uuid4().hex
        try:
            self.client.insert(_TABLE, {
                "id": doc_id,
                "user_id": device.user_id,
                "fingerprint": device.fingerprint,
                "hostname": device.hostname,
                "os": device.os,
                "os_arch": device.os_arch,
            })
        except httpx.HTTPStatusError as exc:
            if not is_unique_violation(exc):
                raise
            # find→insert 间隙被并发请求抢先插入同 (user_id, fingerprint)，
            # 唯一约束拦下本条——回落为更新，既不 500 也不留重复行
            return self._update_existing(device, now, {})
        return DeviceRegistry(
            id=doc_id,
            user_id=device.user_id,
            fingerprint=device.fingerprint,
            hostname=device.hostname,
            os=device.os,
            os_arch=device.os_arch,
            last_active_at=now,
            bound_at=now,
            created_at=now,
            updated_at=now,
        )

    def delete_by_id(self, device_id: str, user_id: str) -> bool:
        return self.client.delete(_TABLE, {"id": device_id, "user_id": user_id}) > 0

    def delete_all_for_user(self, user_id: str) -> int:
        """注销执行：清空该用户全部设备绑定。返回行数。"""
        return self.client.delete(_TABLE, {"user_id": user_id})
