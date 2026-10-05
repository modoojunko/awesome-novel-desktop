"""定价纯函数 + tier 归属 + order_no 生成 + sku_snapshot 构造。"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime

# ── 定价 ──

def calc_price_fen(base_price_fen: int, discount_permille: int) -> int:
    """SKU 定价：基准 × 折扣（千分比），四舍五入到分。"""
    return (base_price_fen * discount_permille + 500) // 1000


def calc_discount_display(discount_permille: int) -> str:
    """折扣千分比 → 展示文案（'8折' / '9折' / ''）。"""
    if discount_permille >= 1000:
        return ""
    tenth = discount_permille / 100
    if tenth == int(tenth):
        return f"{int(tenth)}折"
    return f"{tenth}折"


@dataclass(frozen=True)
class SkuSnapshot:
    """下单瞬间快照（sku_snapshot JSONB 的结构定义）。"""
    tier_key: str
    tier_display: str
    period: str
    period_days: int
    base_price_fen: int
    discount_permille: int
    device_limit: int

    def to_dict(self) -> dict:
        return {
            "tier_key": self.tier_key,
            "tier_display": self.tier_display,
            "period": self.period,
            "period_days": self.period_days,
            "base_price_fen": self.base_price_fen,
            "discount_permille": self.discount_permille,
            "device_limit": self.device_limit,
        }


# ── tier 归属 ──

# legacy tier 别名（现状 codes 表有 monthly/quarterly/yearly 等，统一映射到 pro）
_TIER_ALIASES: dict[str, str] = {
    "monthly": "pro",
    "quarterly": "pro",
    "yearly": "pro",
    "lifetime": "pro",
}

# tier 等级序（越高越高级）
_TIER_RANK: dict[str, int] = {
    "none": 0,
    "free": 5,
    "trial": 10,
    "pro": 20,
    "max": 30,
}

# rank 单源 = tiers.rank 列（tier-catalog）：应用层启动时注入 lookup（读 DB，带
# 类级 TTL 缓存）；本模块保持领域纯函数——SHALL NOT 直连 infrastructure。
# lookup 返回 None/抛异常 → 退 _TIER_RANK 常量并告警（DB 不可用兜底，spec 允许）。
import logging as _logging

_logger = _logging.getLogger(__name__)

_rank_lookup = None


def configure_rank_lookup(fn) -> None:
    """注入 rank 读取器：fn() -> dict[tier_key, rank] | None。应用启动时调用一次。"""
    global _rank_lookup
    _rank_lookup = fn


def _lookup_ranks() -> dict[str, int] | None:
    if _rank_lookup is None:
        return None
    try:
        m = _rank_lookup()
        return m if isinstance(m, dict) and m else None
    except Exception:  # noqa: BLE001 —— DB 不可用兜底，不向上抛
        _logger.warning(event="tier_rank_db_unavailable", msg="rank 读库失败，退代码常量")
        return None


def normalize_tier(tier: str) -> str:
    """legacy tier → 标准档位 key。"""
    return _TIER_ALIASES.get(tier, tier)


def tier_rank(tier: str) -> int:
    """档位等级序（归属计算用）：DB rank 列单源，缺行/读库失败退常量。"""
    t = normalize_tier(tier)
    m = _lookup_ranks()
    if m is not None:
        if t not in m:
            _logger.warning(event="tier_rank_missing", tier=t,
                            msg="tiers 表缺该档 rank 行——按 0 处理（保守，不静默升档）")
            return 0
        return int(m[t])
    return _TIER_RANK.get(t, 0)


def resolve_effective_tier(active_codes: list) -> str:
    """从已激活（含排队中）的 codes 行中取最高档。

    Args:
        active_codes: 已激活/排队中的 codes 行（有 tier 属性）
    """
    m = _lookup_ranks()
    best_tier = "none"
    best_rank = 0
    for code in active_codes:
        t = normalize_tier(getattr(code, "tier", "none"))
        if m is not None:
            if t not in m:
                _logger.warning(event="tier_rank_missing", tier=t,
                                msg="tiers 表缺该档 rank 行——该码不计入归属（保守）")
                r = 0
            else:
                r = int(m[t])
        else:
            r = _TIER_RANK.get(t, 0)
        if r > best_rank:
            best_rank = r
            best_tier = t
    return best_tier


# ── order_no 生成 ──

def gen_order_no(now_utc: datetime, rng=None) -> str:
    """'S' + YYYYMMDD(UTC) + '-' + 16位大写hex。

    64 bit 熵，不可预测/不可遍历。
    撞号由 UNIQUE 约束兜底（概率 2^-64）；rng 可注入用于测试。
    """
    rand = rng or secrets
    date_part = now_utc.strftime("%Y%m%d")
    hex_part = rand.token_hex(8).upper()
    return f"S{date_part}-{hex_part}"


# ── 冷静期 ──

COOLDOWN_SECONDS = 300  # 5 分钟


def calc_cooldown_ends_at(now_utc: datetime) -> datetime:
    """冷静期终点 = now + 300s。"""
    from datetime import timedelta
    return now_utc + timedelta(seconds=COOLDOWN_SECONDS)


# ── 领域异常 ──

class DomainError(Exception):
    """领域层基础异常。"""


class SkuNotFoundError(DomainError):
    def __init__(self, sku_key: str):
        super().__init__(f"SKU not found or retired: {sku_key}")


class PurchaseDisabledError(DomainError):
    def __init__(self):
        super().__init__("Purchase entry is disabled")


class AgreementStaleError(DomainError):
    def __init__(self):
        super().__init__("Agreement version stale, please re-confirm")


class RefundWindowExceeded(DomainError):
    def __init__(self):
        super().__init__("Refund window exceeded (1 year)")


class RefundTooSmallError(DomainError):
    def __init__(self):
        super().__init__("Remaining too small to refund (<1 fen)")


class RefundAlreadyActiveError(DomainError):
    def __init__(self, cooldown_remaining: int = 0):
        self.cooldown_remaining = cooldown_remaining
        super().__init__("Refund already active")


class NotActivatableError(DomainError):
    def __init__(self):
        super().__init__("Code is not in pending_activation state")


class ActivationBusyError(DomainError):
    def __init__(self):
        super().__init__("Another activation is in progress")
