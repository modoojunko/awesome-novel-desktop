"""SQL（SQLAlchemy/SQLite）设备授权凭证仓储。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.devices import DeviceGrant
from app.models.grant import DeviceGrantORM
from app.models.user import UserORM


class SqlGrantRepo:
    def __init__(self, db: Session):
        self.db = db

    def _get_user_id(self, username: str) -> int | None:
        row = self.db.query(UserORM.id).filter(UserORM.username == username).first()
        return row[0] if row else None

    def _to_domain(self, row: DeviceGrantORM) -> DeviceGrant:
        # user_id → username（域对象仍用 username 字符串做身份）
        user = self.db.query(UserORM.username).filter(UserORM.id == row.user_id).first()
        return DeviceGrant(
            pc_hash=row.pc_hash,
            username=user[0] if user else "",
            token=row.token,
            enrolled=bool(row.enrolled),
            fingerprint=row.fingerprint or "",
            challenge=row.challenge or "",
        )

    def get(self, pc_hash: str) -> DeviceGrant | None:
        row = self.db.query(DeviceGrantORM).filter(DeviceGrantORM.pc_hash == pc_hash).first()
        return self._to_domain(row) if row else None

    def upsert(
        self, pc_hash: str, username: str, token: str, enrolled: bool, fingerprint: str,
        *, challenge: str | None = None,
    ) -> None:
        user_id = self._get_user_id(username)
        if user_id is None:
            return  # 用户不存在，不写 grant

        row = self.db.query(DeviceGrantORM).filter(DeviceGrantORM.pc_hash == pc_hash).first()
        if row:
            row.user_id = user_id
            row.token = token
            row.enrolled = 1 if enrolled else 0
            row.fingerprint = fingerprint
            row.challenge = challenge or None  # 重新授权即轮换配对密钥
        else:
            row = DeviceGrantORM(
                pc_hash=pc_hash,
                user_id=user_id,
                token=token,
                enrolled=1 if enrolled else 0,
                fingerprint=fingerprint,
                challenge=challenge or None,
            )
            self.db.add(row)

    def set_enrolled(self, pc_hash: str, username: str, enrolled: bool) -> None:
        user_id = self._get_user_id(username)
        if user_id is None:
            return
        self.db.query(DeviceGrantORM).filter(
            DeviceGrantORM.pc_hash == pc_hash,
            DeviceGrantORM.user_id == user_id,
        ).update({"enrolled": 1 if enrolled else 0})

    def delete_all_for_user(self, username: str) -> int:
        """注销执行：清空该用户全部设备授权。返回行数。"""
        user_id = self._get_user_id(username)
        if user_id is None:
            return 0
        result = self.db.query(DeviceGrantORM).filter(
            DeviceGrantORM.user_id == user_id,
        ).delete(synchronize_session=False)
        self.db.commit()
        return result

    def delete_by_fingerprint(self, username: str, fingerprint: str) -> int:
        """移除设备时同步清除该设备授权凭证（s-security-hardening R5）。"""
        user_id = self._get_user_id(username)
        if user_id is None or not fingerprint:
            return 0
        rows = self.db.query(DeviceGrantORM).filter(
            DeviceGrantORM.user_id == user_id,
            DeviceGrantORM.fingerprint == fingerprint,
        ).all()
        for row in rows:
            self.db.delete(row)
        return len(rows)
