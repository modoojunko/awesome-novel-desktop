"""payments 域 ORM 模型：tiers/skus/orders + codes 扩展列。

users 代理键改造后的模型统一：所有 FK 引用 users.id（BigInteger）。
orders 含退款列族（退款=订单流程环节，无独立 refunds 表）。
"""
from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from app.models.base import Base
from app.models.types import BigIntPK


class TierORM(Base):
    __tablename__ = "tiers"

    id = Column(BigIntPK, autoincrement=True, primary_key=True)
    key = Column(String(32), nullable=False, unique=True)
    display_name = Column(String(64), nullable=False)
    rank = Column(Integer, nullable=False)  # 等级序：max(30) > pro(20) > trial(10)
    selling_points = Column(Text, nullable=False, default="[]", server_default="[]")
    # 档位权益配置 JSON：{"features":[...],"limits":{"max_projects":null|int}}。
    # 单列 JSON（c-s-entitlement-sync）：加权益维度零 DDL；缺配置/坏 JSON 由
    # ENTITLEMENT_DEFAULTS 兜底（check-auth 组装处）。
    entitlement = Column(Text, nullable=False, default="{}", server_default="{}")
    status = Column(String(16), nullable=False, default="live", server_default="live")
    created_at = Column(DateTime, server_default=__import__("sqlalchemy").func.now())
    updated_at = Column(DateTime, server_default=__import__("sqlalchemy").func.now())


class SkuORM(Base):
    __tablename__ = "skus"

    id = Column(BigIntPK, autoincrement=True, primary_key=True)
    sku_key = Column(String(64), nullable=False, unique=True)
    tier_id = Column(BigIntPK, ForeignKey("tiers.id"), nullable=False)
    period = Column(String(16), nullable=False)  # monthly/quarterly/yearly
    period_days = Column(Integer, nullable=False)
    base_price_fen = Column(Integer, nullable=False)
    discount_permille = Column(Integer, nullable=False, default=1000, server_default="1000")
    device_limit = Column(Integer, nullable=False, default=1, server_default="1")
    on_sale = Column(Boolean, nullable=False, default=True, server_default="true")
    sort = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, server_default=__import__("sqlalchemy").func.now())
    updated_at = Column(DateTime, server_default=__import__("sqlalchemy").func.now())


class OrderORM(Base):
    """订单（根对象）：含退款环节列族 + sku_snapshot。"""
    __tablename__ = "orders"

    id = Column(BigIntPK, autoincrement=True, primary_key=True)
    order_no = Column(String(32), nullable=False, unique=True, index=True)
    user_id = Column(BigIntPK, ForeignKey("users.id"), nullable=False)
    sku_id = Column(BigIntPK, nullable=False)  # 无 FK（SKU 可 retired）
    sku_snapshot = Column(JSON, nullable=False)   # 下单瞬间快照
    amount_fen = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False, default="pending", server_default="pending", index=True)
    prepay_status = Column(String(12), nullable=False, default="none", server_default="none")
    code_url = Column(Text, nullable=True)
    attach_sent = Column(Text, nullable=True)
    transaction_id = Column(String(64), nullable=True)
    payer_openid = Column(String(128), nullable=True)
    channel = Column(String(12), nullable=False, default="wxpay", server_default="wxpay")
    agreement_version = Column(String(16), nullable=False)
    agreed_at = Column(DateTime, nullable=False)

    # 退款环节列族（合并进 orders）
    refund_status = Column(String(16), nullable=True)
    refund_amount_fen = Column(Integer, nullable=True)
    refund_reason = Column(Text, nullable=False, default="", server_default="")
    refund_operator = Column(String(64), nullable=True)
    refund_wx_id = Column(String(64), nullable=True)
    refund_not_enough = Column(Integer, nullable=False, default=0, server_default="0")
    refund_requested_at = Column(DateTime, nullable=True)
    refund_accepted_at = Column(DateTime, nullable=True)

    # 时间戳
    created_at = Column(DateTime, server_default=__import__("sqlalchemy").func.now())
    paid_at = Column(DateTime, nullable=True)
    fulfilled_at = Column(DateTime, nullable=True)
    refunded_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    cooldown_ends_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=__import__("sqlalchemy").func.now())


class TradeEventORM(Base):
    __tablename__ = "trade_events"

    event_id = Column(BigIntPK, autoincrement=True, primary_key=True)
    event_key = Column(String(255), nullable=False, unique=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    order_no = Column(String(32), nullable=True, index=True)
    refund_no = Column(String(32), nullable=True)
    payload = Column(JSON, nullable=True)
    operator = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=__import__("sqlalchemy").func.now())


class ReconciliationReportORM(Base):
    __tablename__ = "reconciliation_reports"

    bill_date = Column(Date, primary_key=True)
    internal_count = Column(Integer, nullable=False)
    wx_count = Column(Integer, nullable=False)
    internal_total_fen = Column(Integer, nullable=False)
    wx_total_fen = Column(Integer, nullable=False)
    refund_count = Column(Integer, nullable=False)
    refund_total_fen = Column(Integer, nullable=False)
    mismatch_detail = Column(JSON, nullable=True)
    status = Column(String(16), nullable=False, default="pending", server_default="pending", index=True)
    created_at = Column(DateTime, server_default=__import__("sqlalchemy").func.now())


class InvoiceORM(Base):
    """发票台账（功能暂缓，表随建占位）。"""
    __tablename__ = "invoices"

    invoice_id = Column(BigIntPK, autoincrement=True, primary_key=True)
    order_id = Column(BigIntPK, nullable=False)
    refund_id = Column(BigIntPK, nullable=True)
    kind = Column(String(8), nullable=False)  # blue/red
    title = Column(JSON, nullable=False, default={})
    amount_fen = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False, default="requested", server_default="requested")
    invoice_no = Column(String(64), nullable=True, unique=True)
    red_invoice_no = Column(String(64), nullable=True)
    issued_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=__import__("sqlalchemy").func.now())
    updated_at = Column(DateTime, server_default=__import__("sqlalchemy").func.now())
