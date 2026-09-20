from __future__ import annotations

from sqlalchemy import Column, DateTime, String, func

from app.models.base import Base


class DeviceOutdatedMarkORM(Base):
    """客户端需更新标记（s-auth-outdated-signal）：authorize 以 client_outdated
    分档拒绝后按 pc_hash 落库；check-auth 无 grant 且 TTL 内有标记 → code=3。
    落库而非内存：云托管 MinNum=0 缩容冷启动/实例切换不得丢信号。"""

    __tablename__ = "device_outdated_marks"

    pc_hash     = Column(String(128), primary_key=True)
    rejected_at = Column(DateTime, nullable=False, server_default=func.now())
