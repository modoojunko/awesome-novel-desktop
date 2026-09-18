"""微信支付回调端点（APIv3，s-pay-wechat-gateway）。

流程（design §3，与官方文档逐条核对）：
SIGNTEST 探测拦截 → 验签（微信支付公钥）+ AES-256-GCM 解密（APIv3 密钥）
→ 按 event_type 分流（支付/退款回调 resource 字段结构不同）→ 金额核对
（不平转 exception 冻结，绝不发货）→ 幂等转状态机 → 官方 v3 应答规范：
成功 200/204 无需报文，失败 4xx/5xx + FAIL body（`{"code":"SUCCESS"}`
是 V2 语义，禁用）。

微信可能多台服务器几秒内并发重发同一通知——发货/退款推进全部幂等
（CAS + 幂等键），重放安全。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.application.payments.fulfill_payment import fulfill_payment
from app.application.payments.refund_flow import complete_refund
from app.config import settings
from app.domain.payments.order import Transition
from app.infrastructure.repositories.factory import code_repo as _code_repo_factory
from app.infrastructure.repositories.payments_repo import OrderRepo, TradeEventRepo
from app.interfaces.deps import Db, get_db

r = APIRouter()

logger = logging.getLogger("app.payments.notify")

# 微信官方验签探测流量（签名以此前缀开头），拒绝但豁免告警与背压计数
_SIGNTEST_PREFIX = "WECHATPAY/SIGNTEST/"

# 已发货/终态订单集合：重复回调直接确认（官方：已处理过直接返回成功）
_TERMINAL_STATUSES = {"paid", "fulfilled", "refunded", "closed"}

# ── 验签失败背压（s-security-hardening R：防伪造回调刷满验签算力）──
# 独立计数桶（与登录限流互不影响）；SIGNTEST 豁免；微信失败重试节奏
# 15s/15s/30s/3m… 远低于阈值，不会误伤真实回调。
_NOTIFY_FAIL_THRESHOLD = 10   # 60 秒内验签失败次数阈值
_NOTIFY_FAIL_WINDOW = 60.0
_NOTIFY_BLOCK_SECONDS = 600.0
_NOTIFY_FAIL_TIMES: dict[str, list[float]] = {}
_NOTIFY_BLOCKED: dict[str, float] = {}   # key → 解封时刻（monotonic）


def _reset_backpressure() -> None:
    """测试用：清空背压状态。"""
    _NOTIFY_FAIL_TIMES.clear()
    _NOTIFY_BLOCKED.clear()


def _notify_allowlist_networks() -> list:
    import ipaddress

    raw = settings.WXPAY_NOTIFY_ALLOWLIST.strip()
    if not raw:
        return []
    return [ipaddress.ip_network(part.strip(), strict=False) for part in raw.split(",") if part.strip()]


def _source_allowed(ip: str, networks: list) -> bool:
    import ipaddress

    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in networks)


def _is_blocked(key: str) -> bool:
    import time as _t

    return _t.monotonic() < _NOTIFY_BLOCKED.get(key, 0.0)


def _record_verify_failure(request: Request, key: str) -> None:
    """验签失败计数：达阈值 → 告警；来源键可信时并暂封（不可信只告警不阻断，
    防止把真实微信出口或全网封掉）。跨过阈值只告警一次（计数清零重新累积）。"""
    import time as _t

    now = _t.monotonic()
    times = [t for t in _NOTIFY_FAIL_TIMES.get(key, []) if now - t <= _NOTIFY_FAIL_WINDOW]
    times.append(now)
    _NOTIFY_FAIL_TIMES[key] = times
    if len(times) < _NOTIFY_FAIL_THRESHOLD:
        return
    _NOTIFY_FAIL_TIMES[key] = []
    from app.interfaces.middleware import _trusted_proxy_hops

    trusted = _trusted_proxy_hops() > 0
    if trusted:
        _NOTIFY_BLOCKED[key] = now + _NOTIFY_BLOCK_SECONDS
    notify = getattr(request.app.state, "notify_service", None)
    if notify is not None:
        action = "已暂封该来源 10 分钟" if trusted else "来源不可信，仅告警不阻断"
        notify.send(f"微信回调验签连续失败 {len(times)}+ 次",
                    f"来源 {key}；{action}。请核查验签配置（证书/密钥）是否正确。")


def _fail(status_code: int, message: str) -> JSONResponse:
    """官方失败应答：4xx/5xx + FAIL body → 微信按节奏重试。"""
    return JSONResponse(status_code=status_code,
                        content={"code": "FAIL", "message": message})


@r.post("/api/pay/notify")
async def wxpay_notify(request: Request, db: Db = Depends(get_db)):
    from app.interfaces.middleware import _client_key

    body = await request.body()
    headers = dict(request.headers)  # Starlette 输出小写键，SDK 已兼容 fastapi 形式
    # SDK 要求显式签名算法头（缺失即抛异常），微信新回调可省略此头——
    # 默认官方算法名 WECHATPAY2-SHA256-RSA2048
    headers.setdefault("wechatpay-signature-type", "WECHATPAY2-SHA256-RSA2048")
    gateway = request.app.state.payment_gateway

    # 可选来源白名单（配置即强制）：名单外 403——不验签不解密不告警
    client_ip = _client_key(request)
    networks = _notify_allowlist_networks()
    if networks and not _source_allowed(client_ip, networks):
        logger.warning("event=wxpay.notify.allowlist_rejected ip=%s", client_ip)
        return _fail(403, "forbidden")

    # 背压暂封中的来源：直接 429（对微信等价于失败重试）
    if _is_blocked(client_ip):
        return _fail(429, "rate limited")

    # 验签探测流量：按验签失败拒绝，豁免告警与背压计数（配置回调地址时的例行探测）
    if (headers.get("wechatpay-signature") or "").startswith(_SIGNTEST_PREFIX):
        return _fail(401, "signature rejected")

    data = gateway.callback(headers=headers, body=body)
    if data is None:
        # 验签失败或解密失败：不产生任何状态变化，让微信重试
        _record_verify_failure(request, client_ip)
        logger.warning("event=wxpay.notify.verify_failed ip=%s", client_ip)
        return _fail(401, "verify failed")

    event_type = data.get("event_type", "")
    resource = data.get("resource") or {}
    if event_type.startswith("TRANSACTION."):
        return _handle_transaction(request, db, resource)
    if event_type.startswith("REFUND."):
        return _handle_refund(db, resource)
    # 未知事件类型：无业务含义，应答成功止重试
    return Response(status_code=200)


def _handle_transaction(request: Request, db, resource: dict):
    """支付结果回调：金额核对（资金安全闸门）→ 幂等发货。"""
    order_repo = OrderRepo(db)
    event_repo = TradeEventRepo(db)
    order_no = resource.get("out_trade_no", "")
    order = order_repo.find_by_order_no(order_no)
    if not order:
        # 订单不存在（伪造单号验签也过不了，真来自微信则防无限重试）
        return Response(status_code=200)
    if order.get("status") in _TERMINAL_STATUSES:
        # 已处理过：直接确认（重放安全）
        return Response(status_code=200)

    # 金额核对：只信 amount.total（绝不用 payer_total——用券实付小于订单金额）
    amount_total = (resource.get("amount") or {}).get("total")
    if amount_total is None or int(amount_total) != order.get("amount_fen"):
        logger.error("event=wxpay.notify.amount_mismatch order=%s wx_total=%s local=%s",
                     order_no, amount_total, order.get("amount_fen"))
        # 与 domain/payments/order.py 的既有金额闸门迁移一致
        order_repo.compare_and_transition(
            order_no, Transition("pending", "amount_mismatch", "exception", "", "回调金额不符"),
            extra_changes={})
        event_repo.append({
            "event_key": f"order:{order_no}:amount_mismatch",
            "event_type": "order.amount_mismatch",
            "order_no": order_no,
            "payload": {"wx_total": amount_total},
        })
        _notify(request, f"金额不符 {order_no}",
                f"微信回调金额 {amount_total} 与订单 {order.get('amount_fen')} 不平，已冻结待人工处置")
        # 止重试：钱在微信侧人工处置，重试无益
        return Response(status_code=200)

    fulfill_payment(
        order_repo, event_repo, order,
        transaction_id=resource.get("transaction_id", ""),
        payer_openid=(resource.get("payer") or {}).get("openid", ""),
        code_repo=_code_repo_factory(db),
    )
    return Response(status_code=200)


def _handle_refund(db, resource: dict):
    """退款结果回调（REFUND.SUCCESS/ABNORMAL/CLOSED）：幂等推进。"""
    if resource.get("refund_status") != "SUCCESS":
        # ABNORMAL/CLOSED 终态：T3 扫描已有告警处置路径，回调不重复造状态
        logger.warning("event=wxpay.notify.refund_not_success refund_no=%s status=%s",
                       resource.get("out_refund_no", ""), resource.get("refund_status"))
        return Response(status_code=200)
    complete_refund(
        OrderRepo(db), TradeEventRepo(db),
        resource.get("out_refund_no", ""),
        wx_refund_id=resource.get("refund_id", ""),
        code_repo=_code_repo_factory(db),
    )
    return Response(status_code=200)


def _notify(request: Request, title: str, markdown: str) -> None:
    notify = getattr(request.app.state, "notify_service", None)
    if notify is not None:
        notify.send(title, markdown)
