"""导入所有模型，供 Alembic 自动检测。"""
from app.models.base import Base
from app.models.code import ActivationCodeORM
from app.models.config import GlobalConfigORM
from app.models.device import DeviceRegistryORM
from app.models.grant import DeviceGrantORM
from app.models.outdated_mark import DeviceOutdatedMarkORM
from app.models.payments import (
    InvoiceORM,
    OrderORM,
    ReconciliationReportORM,
    SkuORM,
    TierORM,
    TradeEventORM,
)
from app.models.user import UserORM

__all__ = [
    "ActivationCodeORM",
    "Base",
    "DeviceGrantORM",
    "DeviceOutdatedMarkORM",
    "DeviceRegistryORM",
    "GlobalConfigORM",
    "InvoiceORM",
    "OrderORM",
    "ReconciliationReportORM",
    "SkuORM",
    "TierORM",
    "TradeEventORM",
    "UserORM",
]
