"""补偿扫描三用例：T1（关单）+ T2（paid 未 fulfilled）+ T3（退款跟进含扫描 D）。

设计依据：backend-detail-design.md §4.7。
全部幂等——扫描重放安全。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.application.payments.fulfill_payment import fulfill_payment
from app.application.payments.refund_flow import _naive, complete_refund
from app.domain.payments.order import Transition
from app.infrastructure.payments.gateway import (
    PaymentGateway,
    PaymentStatus,
    RefundStatus,
)
from app.infrastructure.repositories.payments_repo import OrderRepo, TradeEventRepo


def scan_timeout_close(
    order_repo: OrderRepo,
    event_repo: TradeEventRepo,
    gateway: PaymentGateway,
    code_repo=None,
    ttl_seconds: int = 900,
) -> list[dict]:
    """T1：扫描超时 pending 单 → 先查单（关单铁律）→ 关单或补发货。"""
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=ttl_seconds)
    pending_orders = order_repo.find_pending_expirable(cutoff)
    results = []

    for order in pending_orders:
        order_no = order["order_no"]

        # 关单铁律：先查单
        query = gateway.query_payment(order_no)
        if query.status == PaymentStatus.SUCCESS:
            # 迟付——补发货（复活路径）
            result = fulfill_payment(
                order_repo, event_repo, order,
                transaction_id=query.transaction_id,
                payer_openid=query.payer_openid,
                paid_at=now,
                code_repo=code_repo,
            )
            results.append({"order_no": order_no, "action": "revived_fulfilled"})
        else:
            # 未付——微信关单
            close = gateway.close_payment(order_no)
            if close.already_paid:
                # 竞态：关单时发现已付
                query2 = gateway.query_payment(order_no)
                result = fulfill_payment(
                    order_repo, event_repo, order,
                    transaction_id=query2.transaction_id,
                    paid_at=now,
                    code_repo=code_repo,
                )
                results.append({"order_no": order_no, "action": "close_race_fulfilled"})
            elif close.success:
                t3 = Transition("pending", "timeout_close", "closed", "", "超时关单")
                order_repo.compare_and_transition(order_no, t3, extra_changes={
                    "closed_at": now,
                })
                event_repo.append({
                    "event_key": f"order:{order_no}:closed",
                    "event_type": "order.closed",
                    "order_no": order_no,
                })
                results.append({"order_no": order_no, "action": "closed"})

    return results


def scan_paid_unfulfilled(
    order_repo: OrderRepo,
    event_repo: TradeEventRepo,
    code_repo=None,
) -> list[dict]:
    """T2：扫描 paid 但未 fulfilled 的订单 → 补发货。"""
    paid_orders = order_repo.find_paid_unfulfilled()
    results = []

    for order in paid_orders:
        result = fulfill_payment(
            order_repo, event_repo, order,
            transaction_id=order.get("transaction_id", ""),
            paid_at=order.get("paid_at"),
            code_repo=code_repo,
        )
        results.append({"order_no": order["order_no"], "action": "fulfilled"})

    return results


def scan_refund_followup(
    order_repo: OrderRepo,
    event_repo: TradeEventRepo,
    gateway: PaymentGateway,
    notify: Any = None,
    code_repo=None,
) -> list[dict]:
    """T3：退款跟进——NOT_ENOUGH 重试 + 查退款结果 + 扫描 D 半截恢复
    + 扫描 E 漏网收敛（含 frozen 行相位判定）+ 扫描 F 冻结完整性自愈。

    全部幂等：扫描重放安全（complete_refund 全量可重入）。
    """
    now = datetime.now(UTC)
    results: list[dict] = []

    # ── processing 订单：查退款结果 / NOT_ENOUGH 重试 ──
    for order in order_repo.find_refund_processing():
        order_no = order["order_no"]
        # out_refund_no = order_no（设计 §2.5：一单一退，复用同号）
        query = gateway.query_refund(order_no)

        if query.status == RefundStatus.SUCCESS:
            complete_refund(order_repo, event_repo, order_no, query.wx_refund_id,
                            code_repo=code_repo)
            results.append({"order_no": order_no, "action": "refund_completed"})
        elif getattr(query, "error_kind", "") == "not_found":
            # 受理丢失：refund_processing 但微信侧查无此退款单（申请可能未受理成功）
            # ——告警转人工核查商户平台，勿当处理中干等
            _notify(notify, f"退款受理丢失 {order_no}",
                    "微信侧查无此退款单，可能申请未受理成功，请人工核查商户平台。")
            event_repo.append({
                "event_key": f"refund:{order_no}:receipt_lost:{int(now.timestamp())}",
                "event_type": "refund.receipt_lost",
                "order_no": order_no,
            })
            results.append({"order_no": order_no, "action": "refund_not_found_alerted"})
        elif query.status == RefundStatus.NOT_ENOUGH:
            # 自动重试：重新提交微信（NOT_ENOUGH=商户未结算资金不足，次日通常恢复）
            attempts = (order.get("refund_not_enough") or 0) + 1
            retry = gateway.create_refund(
                out_refund_no=order_no,
                out_trade_no=order_no,
                refund_fen=order["refund_amount_fen"],
                total_fen=order["amount_fen"],
                reason=order.get("refund_reason", ""),
                notify_url="",
            )
            if retry.status == RefundStatus.SUCCESS:
                complete_refund(order_repo, event_repo, order_no, retry.wx_refund_id,
                                code_repo=code_repo)
                results.append({"order_no": order_no, "action": "retry_completed"})
                continue
            order_repo.update_fields(order_no, {"refund_not_enough": attempts})
            event_repo.append({
                "event_key": f"refund:{order_no}:not_enough_{attempts}",
                "event_type": "refund.not_enough_retry",
                "order_no": order_no,
                "payload": {"attempts": attempts},
            })
            results.append({"order_no": order_no, "action": "not_enough_retry",
                            "attempts": attempts})
        elif query.status == RefundStatus.ABNORMAL:
            # 人工处置通道：告警但不改状态（绝不自动重提）
            _notify(notify, f"退款异常 {order_no}",
                    "微信退款单状态 ABNORMAL，需人工核实处置。")
            event_repo.append({
                "event_key": f"refund:{order_no}:abnormal_notified:{int(now.timestamp())}",
                "event_type": "refund.abnormal",
                "order_no": order_no,
            })
            results.append({"order_no": order_no, "action": "abnormal_notified"})

    # ── 扫描 D：refund_status=succeeded 但 status≠refunded（半截恢复）──
    for order in order_repo.find_refund_half_done():
        order_no = order["order_no"]
        complete_refund(order_repo, event_repo, order_no,
                        order.get("refund_wx_id") or "", code_repo=code_repo)
        results.append({"order_no": order_no, "action": "half_done_repaired"})

    # ── 扫描 E：orders 已 refunded 终态但订单来源码仍 active+排队中 → 收回 ──
    # 与 complete_refund 共用同一收回方法（锚=refund_requested_at，已起算豁免）：
    # 既收敛历史存量漏网行，也兜底「complete_refund 漏收后订单已终态」的窗口。
    # frozen 行同口径（冻结只是可用性暂停，相位判定不受影响）。
    if code_repo is not None:
        for order in order_repo.find_refund_succeeded():
            order_no = order["order_no"]
            anchor = _naive(order.get("refund_requested_at"))
            if anchor is None:
                # 锚缺失=数据异常（退款流程必写 refund_requested_at）：跳过不猜锚，
                # 防误判已起算行；该行每轮空扫 0 行，无副作用
                continue
            queued = code_repo.revoke_queued_for_order(order_no, anchor=anchor)
            if queued:
                row = code_repo.get(f"O-{order_no}")
                event_repo.append({
                    "event_key": f"codes:O-{order_no}:revoked:queued",
                    "event_type": "codes.revoked",
                    "order_no": order_no,
                    "payload": {
                        "phase": "queued",
                        "anchor": anchor.isoformat() if anchor else None,
                        "grant_start": row.grant_start.isoformat() if row and row.grant_start else None,
                        "expires_at": row.expires_at.isoformat() if row and row.expires_at else None,
                    },
                })
                results.append({"order_no": order_no, "action": "queued_code_revoked"})
            # 已起算行恢复：排队/未激活行已收回，剩余 frozen 行即已起算行
            # （确认退款时冻结、退款成功应保留剩余权益）——补 complete_refund
            # 3c 崩溃半截。幂等：无 frozen 行返回 0。
            restored = code_repo.unfreeze_for_order(order_no)
            if restored:
                event_repo.append({
                    "event_key": f"codes:O-{order_no}:restored",
                    "event_type": "codes.restored",
                    "order_no": order_no,
                })
                results.append({"order_no": order_no, "action": "frozen_code_restored"})

        # ── 扫描 F：冻结完整性（s-pay-refund-freeze）──
        # F-a 退款在途单的 active 行补冻结（确认退款时冻结写半截）；
        # F-b frozen 行的订单已不在退款流程 → 补解冻（取消时解冻写半截；
        #      refunded 单不走此支——其 frozen 行归扫描 E 按锚相位判定，
        #      防止把该收回的排队行洗活）。
        # 自愈属状态迁移，按台账口径追加事件；键带秒级时间戳——一单可经
        # 多轮退款，固定键会吞掉后续轮次的账（CAS 赢者才记账，重放不重复）。
        for order in order_repo.find_refund_in_flight():
            frozen = code_repo.freeze_for_order(order["order_no"])
            if frozen:
                event_repo.append({
                    "event_key": f"codes:O-{order['order_no']}:frozen:{int(now.timestamp())}",
                    "event_type": "codes.frozen",
                    "order_no": order["order_no"],
                    "payload": {"heal": "scan_f", "order_status": order.get("status")},
                })
                results.append({"order_no": order["order_no"], "action": "code_frozen"})
        for row in code_repo.find_frozen():
            order_no = row.code_id[2:] if row.code_id.startswith("O-") else ""
            if not order_no:
                continue
            order = order_repo.find_by_order_no(order_no)
            if order is None or order.get("status") != "fulfilled":
                continue  # 在途/已退款单的 frozen 行分别归 F-a/扫描 E 管
            unfrozen = code_repo.unfreeze_for_order(order_no)
            if unfrozen:
                event_repo.append({
                    "event_key": f"codes:O-{order_no}:unfrozen:{int(now.timestamp())}",
                    "event_type": "codes.unfrozen",
                    "order_no": order_no,
                    "payload": {"heal": "scan_f", "order_status": order.get("status")},
                })
                results.append({"order_no": order_no, "action": "code_unfrozen"})

    return results


def _notify(notify: Any, title: str, markdown: str) -> None:
    if notify is not None:
        notify.send(title, markdown)
