"""activate_code：到货-激活两段式的第二段。

设计依据：backend-detail-design.md §4.12。
激活起点顺延：max(现有 active 行最远到期日, 今天)——囤套餐不计时、接续消耗。
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.domain.payments.pricing import NotActivatableError
from app.infrastructure.repositories.payments_repo import OrderRepo, TradeEventRepo


def calc_grant_start(active_codes: list, today: date | None = None) -> date:
    """计算激活起点 = max(现有 active 行最远到期日, 今天)。复用 licensing 顺延。"""
    t = today or datetime.now(UTC).date()
    max_exp = t
    for code in active_codes:
        exp = getattr(code, "expires_at", None)
        if exp:
            exp_date = exp.date() if isinstance(exp, datetime) else exp
            if isinstance(exp_date, datetime):  # 兜底：带时区等异形
                exp_date = exp_date.date()
            max_exp = max(max_exp, exp_date)
    return max_exp


def activate_code(
    order_repo: OrderRepo,
    event_repo: TradeEventRepo,
    code_repo,  # CodeRepo（licensing 域，注入）
    order_no: str,
    user_id: int,
) -> dict:
    """激活：codes 行 pending_activation→active（写入 grant_start/expires_at）。

    Returns:
        {code_id, grant_start, expires_at, tier}
    """
    now = datetime.now(UTC).replace(tzinfo=None)  # naive UTC（表列口径）
    order = order_repo.find_by_order_no(order_no)
    if not order:
        return {"error": "order_not_found"}
    if order["status"] not in ("fulfilled",):
        return {"error": "not_fulfilled"}

    # 找到该订单的台账行
    order_id = order.get("id") or order_no
    codes = code_repo.find_by_order(order_id)
    if not codes:
        return {"error": "code_not_found"}

    pending = [c for c in codes if c.status == "pending_activation"]
    if not pending:
        raise NotActivatableError()
    code = pending[0]

    snapshot = order.get("sku_snapshot") or {}
    period_days = snapshot.get("period_days", 30)
    tier = snapshot.get("tier_key", "pro")

    # 计算顺延起点——冻结行（退款处理中）一并计入：冻结只暂停可用性，
    # 不动排队位，取消退款后排队终点不变（s-pay-refund-freeze）
    family = [c for c in code_repo.find_all_by_username(user_id)
              if c.status in ("active", "frozen")]
    base = calc_grant_start(family)
    grant_start = datetime(base.year, base.month, base.day)
    expires_at = grant_start + timedelta(days=period_days)

    # CAS codes pending_activation→active（重复激活/已退 → False）
    updated = code_repo.activate_pending(code.code_id, grant_start, expires_at, now)
    if not updated:
        raise NotActivatableError()

    event_repo.append({
        "event_key": f"codes:{code.code_id}:activated",
        "event_type": "codes.activated",
        "order_no": order_no,
        "payload": {
            "grant_start": grant_start.isoformat(),
            "expires_at": expires_at.isoformat(),
            "tier": tier,
        },
        "created_at": now,
    })

    return {
        "code_id": code.code_id,
        "grant_start": grant_start.isoformat(),
        "expires_at": expires_at.isoformat(),
        "tier": tier,
    }
