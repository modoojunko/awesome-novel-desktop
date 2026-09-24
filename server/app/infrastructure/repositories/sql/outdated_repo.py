"""SQL 客户端需更新标记仓储（s-auth-outdated-signal）。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.outdated_mark import DeviceOutdatedMarkORM

# TTL ≥ C端 登录轮询窗（60×2s）+ 重试余量；读时比较，无清理任务
OUTDATED_MARK_TTL = timedelta(minutes=10)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class SqlOutdatedMarkRepo:
    def __init__(self, db: Session):
        self.db = db

    def mark(self, pc_hash: str) -> None:
        """按 pc_hash upsert 拒绝时间（同机重复拒绝刷新 TTL 窗）。"""
        row = self.db.query(DeviceOutdatedMarkORM).filter(
            DeviceOutdatedMarkORM.pc_hash == pc_hash).first()
        now = _utcnow().replace(tzinfo=None)
        if row:
            row.rejected_at = now
        else:
            self.db.add(DeviceOutdatedMarkORM(pc_hash=pc_hash, rejected_at=now))

    def fresh(self, pc_hash: str) -> bool:
        """TTL 内存在有效标记。"""
        if not pc_hash:
            return False
        row = self.db.query(DeviceOutdatedMarkORM).filter(
            DeviceOutdatedMarkORM.pc_hash == pc_hash).first()
        if row is None or row.rejected_at is None:
            return False
        rejected = _as_utc(row.rejected_at)
        return _utcnow() - rejected <= OUTDATED_MARK_TTL
