from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from app.models.base import Base
from app.models.types import BigIntPK


class ActivationCodeORM(Base):
    """权益台账行（原激活码表扩展：支付发货+两段式激活）。"""
    __tablename__ = "codes"

    code_id         = Column(String(32), primary_key=True)
    tier            = Column(String(32), nullable=False, index=True)
    duration_days   = Column(Integer, nullable=False)
    status          = Column(String(32), default="unused", server_default="unused", index=True)
    user_id         = Column(BigIntPK, ForeignKey("users.id"), nullable=True, index=True)
    # 支付发货扩展（a002 加列）
    source          = Column(String(12), nullable=False, default="admin", server_default="admin")
    order_id        = Column(BigIntPK, nullable=True, index=True)
    grant_start     = Column(DateTime, nullable=True)
    status_detail   = Column(String(24), nullable=True, default="unused", server_default="unused")
    activated_at    = Column(DateTime, nullable=True)
    expires_at      = Column(DateTime, nullable=True)
    # 账号注销联动（account-deletion）：权益级退款申请时刻（空=未申请）
    refund_requested_at = Column(DateTime, nullable=True)
    # 发码批次（s-code-issue）：批次单号；NULL=历史存量桶（建批前发放的手工码）
    batch_id       = Column(String(32), nullable=True, index=True)
    created_at      = Column(DateTime, server_default=func.now())
    created_by      = Column(String(64), default="", server_default="")


class CodeBatchORM(Base):
    """发码批次单（s-code-issue）：一次发放一张单，三态台账的事实源在 codes 行。"""
    __tablename__ = "code_batches"

    id              = Column(BigIntPK, autoincrement=True, primary_key=True)
    batch_id        = Column(String(32), nullable=False, unique=True, index=True)
    tier            = Column(String(32), nullable=False)
    duration_days   = Column(Integer, nullable=False)
    count           = Column(Integer, nullable=False)
    channel         = Column(String(64), default="", server_default="")
    note            = Column(String(255), default="", server_default="")
    created_by      = Column(String(64), default="", server_default="")
    budget_consumed = Column(Integer, nullable=False, default=0, server_default="0")
    created_at      = Column(DateTime, server_default=func.now())
