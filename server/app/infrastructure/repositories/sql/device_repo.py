"""SQL（SQLAlchemy/SQLite）设备注册仓储。

2026-08-30 代理键迁移：user_id 列从 String(username) 改为 BigInteger(users.id)。
仓储层接受 username 字符串，内部经 UserORM 解析为 user_id。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.devices import DeviceRegistry
from app.models.device import DeviceRegistryORM
from app.models.user import UserORM


class SqlDeviceRepo:
    def __init__(self, db: Session):
        self.db = db

    def _resolve_user_id(self, username_or_id) -> int | None:
        """接受 username(str) 或 user_id(int)，统一返回 user_id(int)。"""
        if isinstance(username_or_id, int):
            return username_or_id
        row = self.db.query(UserORM.id).filter(UserORM.username == username_or_id).first()
        return row[0] if row else None

    def _to_domain(self, row: DeviceRegistryORM) -> DeviceRegistry:
        return DeviceRegistry(
            id=row.id,
            user_id=row.user_id,
            fingerprint=row.fingerprint or "",
            hostname=row.hostname or "",
            os=row.os or "",
            os_arch=row.os_arch or "",
            last_active_at=row.last_active_at,
            bound_at=row.bound_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def get_by_fingerprint(self, username: str, fingerprint: str) -> DeviceRegistry | None:
        uid = self._resolve_user_id(username)
        if uid is None:
            return None
        row = self.db.query(DeviceRegistryORM).filter(
            DeviceRegistryORM.user_id == uid,
            DeviceRegistryORM.fingerprint == fingerprint,
        ).first()
        return self._to_domain(row) if row else None

    def list_by_user(self, username: str) -> list[DeviceRegistry]:
        uid = self._resolve_user_id(username)
        if uid is None:
            return []
        rows = (
            self.db.query(DeviceRegistryORM)
            .filter(DeviceRegistryORM.user_id == uid)
            .order_by(DeviceRegistryORM.last_active_at.desc())
            .all()
        )
        return [self._to_domain(r) for r in rows]

    def _find_row(self, uid: int, fingerprint: str) -> DeviceRegistryORM | None:
        return self.db.query(DeviceRegistryORM).filter(
            DeviceRegistryORM.user_id == uid,
            DeviceRegistryORM.fingerprint == fingerprint,
        ).first()

    def upsert(self, device: DeviceRegistry) -> DeviceRegistry:
        uid = self._resolve_user_id(device.user_id)
        if uid is None:
            return device  # 用户不存在，跳过
        existing = self._find_row(uid, device.fingerprint)
        now = datetime.now(UTC).replace(tzinfo=None)
        if existing:
            return self._apply_update(existing, device, now)
        row = DeviceRegistryORM(
            id=uuid.uuid4().hex,
            user_id=uid,
            fingerprint=device.fingerprint,
            hostname=device.hostname,
            os=device.os,
            os_arch=device.os_arch,
            last_active_at=now,
            bound_at=now,
            updated_at=now,
        )
        self.db.add(row)
        try:
            self.db.flush()
        except IntegrityError:
            # find→flush 间隙被并发请求抢先插入同 (user_id, fingerprint)，唯一约束
            # uq_user_fingerprint 拦下本条——回滚后回落为更新，不 500。回滚会连带丢弃
            # 本请求先前的未提交变更（authorize 里的惰性密码升级属可重试优化，无数据损失）。
            self.db.rollback()
            existing = self._find_row(uid, device.fingerprint)
            if existing is None:
                raise
            return self._apply_update(existing, device, now)
        return self._to_domain(row)

    def _apply_update(self, row: DeviceRegistryORM, device: DeviceRegistry,
                      now: datetime) -> DeviceRegistry:
        row.hostname = device.hostname
        row.os = device.os
        row.os_arch = device.os_arch
        row.last_active_at = now
        row.updated_at = now
        return self._to_domain(row)

    def delete_by_id(self, device_id: str, username: str) -> bool:
        uid = self._resolve_user_id(username)
        if uid is None:
            return False
        result = self.db.query(DeviceRegistryORM).filter(
            DeviceRegistryORM.id == device_id,
            DeviceRegistryORM.user_id == uid,
        ).delete()
        return result > 0

    def delete_all_for_user(self, user_id: str) -> int:
        """注销执行：清空该用户全部设备绑定。返回行数。"""
        result = self.db.query(DeviceRegistryORM).filter(
            DeviceRegistryORM.user_id == user_id,
        ).delete(synchronize_session=False)
        self.db.commit()
        return result
