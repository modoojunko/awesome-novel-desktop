"""dev 注入端点（D1-D6）：仅在 mock 网关模式注册，X-Admin-Token 鉴权。

设计依据：backend-detail-design.md §6.5。
Change 1 全链路演练的核心工具——模拟微信回调/查单/退款结果。
PAYMENTS_GATEWAY != mock（真实网关）时路由不存在——config 层空串回落
mock 的语义保证：显式设 wxpay/alipay 即下线全部 dev 端点。
"""
from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.config import settings
from app.interfaces.deps import get_db

_MOCK_MODE = settings.effective_gateway == "mock"

r = APIRouter(prefix="/api/dev/pay", tags=["dev-only"]) if _MOCK_MODE else APIRouter()


ADMIN_TOKEN = settings.ADMIN_TOKEN


def _check_admin(request: Request) -> bool:
    """X-Admin-Token 校验：令牌未配置时一律拒绝（空令牌不得放行），比较用恒定时原语。"""
    import secrets

    if not ADMIN_TOKEN:
        return False
    token = request.headers.get("X-Admin-Token", "")
    return secrets.compare_digest(token, ADMIN_TOKEN)


class InjectPaymentRequest(BaseModel):
    order_no: str
    transaction_id: str = ""
    payer_openid: str = ""


class InjectAmountMismatchRequest(BaseModel):
    order_no: str
    paid_amount_fen: int


class InjectRefundRequest(BaseModel):
    order_no: str
    status: str = "SUCCESS"  # SUCCESS / NOT_ENOUGH / ABNORMAL


if _MOCK_MODE:  # mock 模式才定义端点（真实网关下 r 为空 router，路由不存在）

    @r.post("/inject-payment")
    async def inject_payment(req: InjectPaymentRequest, request: Request, db=Depends(get_db)):
        """D1：模拟支付成功回调（mock 网关标记订单已付+触发发货）。"""
        if not _check_admin(request):
            return {"code": 401, "msg": "unauthorized"}
        gw = getattr(request.app.state, "payment_gateway", None)
        if not gw:
            return {"code": 500, "msg": "gateway not initialized"}
        gw.simulate_paid(req.order_no, req.transaction_id, req.payer_openid)
        # 触发发货
        from app.application.payments.fulfill_payment import fulfill_payment
        from app.infrastructure.repositories.payments_repo import (
            OrderRepo,
            TradeEventRepo,
        )
        order = OrderRepo(db).find_by_order_no(req.order_no)
        if not order:
            return {"code": 404, "msg": "order not found"}
        from app.infrastructure.repositories.factory import (
            code_repo as _code_repo_factory,
        )
        result = fulfill_payment(
            OrderRepo(db), TradeEventRepo(db), order,
            transaction_id=req.transaction_id or f"mock_tx_{req.order_no}",
            payer_openid=req.payer_openid,
            code_repo=_code_repo_factory(db),
        )
        return {"code": 0, "data": {"status": result.get("status")}}

    @r.post("/inject-amount-mismatch")
    async def inject_amount_mismatch(req: InjectAmountMismatchRequest, request: Request, db=Depends(get_db)):
        """D2：模拟金额不符（订单进 exception）。"""
        if not _check_admin(request):
            return {"code": 401, "msg": "unauthorized"}
        from app.domain.payments.order import Transition
        from app.infrastructure.repositories.payments_repo import (
            OrderRepo,
            TradeEventRepo,
        )
        t = Transition("pending", "amount_mismatch", "exception", "", "金额不符")
        result = OrderRepo(db).compare_and_transition(req.order_no, t)
        TradeEventRepo(db).append({
            "event_key": f"order:{req.order_no}:exception",
            "event_type": "order.exception",
            "order_no": req.order_no,
            "payload": {"expected": req.paid_amount_fen},
        })
        return {"code": 0, "data": {"status": "exception" if result else "cas_lost"}}

    @r.post("/inject-refund-result")
    async def inject_refund_result(req: InjectRefundRequest, request: Request, db=Depends(get_db)):
        """D3：模拟退款回调结果。"""
        if not _check_admin(request):
            return {"code": 401, "msg": "unauthorized"}
        gw = getattr(request.app.state, "payment_gateway", None)
        if not gw:
            return {"code": 500, "msg": "gateway not initialized"}
        if req.status == "SUCCESS":
            gw.simulate_refund_success(req.order_no)
        from app.application.payments.refund_flow import complete_refund
        from app.infrastructure.repositories.payments_repo import (
            OrderRepo,
            TradeEventRepo,
        )
        if req.status == "SUCCESS":
            from app.infrastructure.repositories.factory import (
                code_repo as _code_repo_factory,
            )
            result = complete_refund(OrderRepo(db), TradeEventRepo(db), req.order_no,
                                     code_repo=_code_repo_factory(db))
            return {"code": 0, "data": result}
        return {"code": 0, "data": {"refund_status": req.status}}

    @r.post("/inject-payerror")
    async def inject_payerror(request: Request):
        """D4：模拟支付失败（余额不足/取消）。"""
        if not _check_admin(request):
            return {"code": 401, "msg": "unauthorized"}
        body = await request.json()
        order_no = body.get("order_no", "")
        gw = getattr(request.app.state, "payment_gateway", None)
        if gw:
            gw.simulate_payerror(order_no)
        return {"code": 0, "data": {"pay_status": "PAYERROR"}}

    @r.post("/cron-run")
    async def cron_run(request: Request, db=Depends(get_db)):
        """D6：手动触发补偿扫描（R1-R4 等价，演练期专用；正式触发器见 pay-cron 云函数）。"""
        if not _check_admin(request):
            return {"code": 401, "msg": "unauthorized"}
        from datetime import datetime

        from app.application.payments.reconcile import daily_reconcile
        from app.application.payments.refund_flow import cooldown_submit
        from app.application.payments.scan_orders import (
            scan_paid_unfulfilled,
            scan_refund_followup,
            scan_timeout_close,
        )
        from app.infrastructure.repositories.payments_repo import (
            OrderRepo,
            ReconciliationReportRepo,
            TradeEventRepo,
        )

        gateway = getattr(request.app.state, "payment_gateway", None)
        notify = getattr(request.app.state, "notify_service", None)
        order_repo = OrderRepo(db)
        event_repo = TradeEventRepo(db)

        closed = scan_timeout_close(order_repo, event_repo, gateway)
        cooldown = [
            cooldown_submit(order_repo, event_repo, gateway, o)
            for o in order_repo.find_cooldown_expired(datetime.now(UTC))
        ]
        repaired = scan_paid_unfulfilled(order_repo, event_repo)
        refund_actions = scan_refund_followup(order_repo, event_repo, gateway, notify=notify)
        reconcile = daily_reconcile(
            db, gateway, order_repo, event_repo, ReconciliationReportRepo(db), notify=notify,
        )
        return {"code": 0, "data": {
            "closed": len(closed),
            "cooldown_submitted": len(cooldown),
            "repaired": len(repaired),
            "refund_actions": len(refund_actions),
            "reconcile": reconcile,
        }}

    @r.get("/gateway-state")
    async def gateway_state(request: Request):
        """D5：查看 mock 网关当前状态（调试用）。"""
        if not _check_admin(request):
            return {"code": 401, "msg": "unauthorized"}
        gw = getattr(request.app.state, "payment_gateway", None)
        if not gw:
            return {"code": 500, "msg": "gateway not initialized"}
        return {"code": 0, "data": {
            "orders": {k: v.get("status") for k, v in gw.orders.items()},
            "refunds": {k: v.get("status") for k, v in gw.refunds.items()},
        }}
