"""S端 支付 Web API（登录态）——附录 Z 联合契约。

设计依据：backend-detail-design.md §5.2 + 附录 Z。
Change 1 用 MockPaymentGateway；Change 2 替换真实网关。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.domain.payments.pricing import (
    AgreementStaleError,
    DomainError,
    PurchaseDisabledError,
    RefundAlreadyActiveError,
    RefundTooSmallError,
    RefundWindowExceeded,
    SkuNotFoundError,
)
from app.interfaces.deps import Db, get_db

r = APIRouter(prefix="/api/pay", tags=["payments"])


def _current_identity(request: Request) -> tuple[str, int] | None:
    """从 Authorization JWT 解析双持身份（username, uid）。

    三态口径（jwt-uid-claim）：
    - 未携带令牌 / 签名无效 → None，端点返回 4001 壳（s-payments 既定口径不变）；
    - 签名有效但缺/非法 uid（升级前旧格式 token）→ 抛 HTTP 401：前端 401 拦截
      自动登出回登录页——这是旧 token 的迁移机制；
    - 正常 → (username, uid)，业务表凭 uid 直查，零身份翻译。
    授权只认 token 里的 uid；user_id SHALL NOT 从请求参数收。
    """
    from fastapi import HTTPException

    from app.infrastructure.security.jwt import verify_jwt

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = verify_jwt(auth.removeprefix("Bearer "))
    if not payload:
        return None
    uid = payload.get("uid")
    if not isinstance(uid, int) or isinstance(uid, bool):
        raise HTTPException(status_code=401, detail="令牌格式过期，请重新登录")
    return payload.get("sub", ""), uid


# ── DTO ──

class CreateOrderRequest(BaseModel):
    sku_key: str
    agreement_version: str


class RefundRequest(BaseModel):
    reason: str = ""


class ActivateRequest(BaseModel):
    order_no: str


# ── 端点 ──

@r.get("/skus")
async def get_skus(request: Request, db: Db = Depends(get_db)):
    """Z.2 公开端点：商品目录（登录时含 current 态）。"""
    from app.infrastructure.repositories.payments_repo import SkuRepo, TierRepo
    sku_repo = SkuRepo(db)
    tier_repo = TierRepo(db)

    skus = sku_repo.find_on_sale()
    tiers = tier_repo.find_all()

    # 三态开关
    from app.infrastructure.repositories.factory import config_repo
    cfg = config_repo(db)
    enabled = cfg.get("payments.purchase.enabled") or "off"
    rehearsal_list = (cfg.get("payments.rehearsal.usernames") or "").split(",")

    # 构建响应（附录 Z.4 SkusView；s-pay-plans-picker：selling_points/is_planned 扩容，只增不删）
    import json as _json

    from app.domain.payments.pricing import calc_discount_display

    def _selling_points(raw) -> list[str]:
        """tiers.selling_points 列（JSON 数组文本）→ 字符串数组；失败/空回 []。"""
        if isinstance(raw, list):
            return [str(x) for x in raw]
        try:
            v = _json.loads(raw or "[]")
            return [str(x) for x in v] if isinstance(v, list) else []
        except (ValueError, TypeError):
            return []

    sku_list = []
    for s in skus:
        sku_list.append({
            "sku_key": s.get("sku_key", ""),
            "tier_key": s.get("tier_key", ""),
            "period": s.get("period", ""),
            "period_days": s.get("period_days", 0),
            "base_price_fen": s.get("base_price_fen", 0),
            "discount_display": calc_discount_display(s.get("discount_permille", 1000)),
            "price_fen": s.get("base_price_fen", 0) * s.get("discount_permille", 1000) // 1000,
            "device_limit": s.get("device_limit", 1),
        })

    popular = next((s["sku_key"] for s in sku_list if s.get("sku_key", "").endswith("yearly")), "")

    return {"code": 0, "data": {
        "purchase_enabled": enabled != "off",
        "agreement_version": "v2026.08",
        "tiers": [
            {"key": t.get("key"), "label": t.get("display_name"),
             "is_live": t.get("status") == "live",
             "is_planned": t.get("status") == "planned",
             "selling_points": _selling_points(t.get("selling_points"))}
            for t in tiers if t.get("status") != "retired"
        ],
        "skus": sku_list,
        "popular_sku": popular,
    }}


@r.post("/orders")
async def create_order(req: CreateOrderRequest, request: Request, db: Db = Depends(get_db)):
    """Z.3 下单（冻结快照+统一下单）。"""
    identity = _current_identity(request)
    if not identity:
        return {"code": 4001, "msg": "未登录"}
    username, user_id = identity

    from app.application.payments.create_order import create_order as _create
    from app.infrastructure.payments.gateway import MockPaymentGateway
    from app.infrastructure.repositories.payments_repo import (
        OrderRepo,
        SkuRepo,
        TradeEventRepo,
    )

    if not user_id:
        return {"code": 4001, "msg": "用户不存在"}

    gateway = getattr(request.app.state, "payment_gateway", MockPaymentGateway())

    # 三态开关 + 演练名单（global_config 单源；缺省 off=安全关闭）
    from app.infrastructure.repositories.factory import (
        config_repo as _config_repo_factory,
    )
    cfg = _config_repo_factory(db)
    purchase_enabled = cfg.get("payments.purchase.enabled") or "off"
    rehearsal_usernames = [u.strip() for u in (cfg.get("payments.rehearsal.usernames") or "").split(",") if u.strip()]

    try:
        result = _create(
            order_repo=OrderRepo(db),
            sku_repo=SkuRepo(db),
            event_repo=TradeEventRepo(db),
            gateway=gateway,
            user_id=user_id,
            sku_key=req.sku_key,
            agreement_version=req.agreement_version,
            purchase_enabled=purchase_enabled,
            rehearsal_usernames=rehearsal_usernames,
            caller_username=username,
        )
        return {"code": 0, "data": result}
    except PurchaseDisabledError:
        return {"code": 4012, "msg": "购买功能暂未开放"}
    except AgreementStaleError:
        return {"code": 4005, "msg": "协议已更新，请重新确认"}
    except SkuNotFoundError:
        return {"code": 4002, "msg": "套餐不存在或已下架"}
    except DomainError as e:
        return {"code": 4003, "msg": str(e)}


# 订单列表 status 参数白名单（orders-status-tabs：tab 归组映射在前端，接口保持"哑"）
_LIST_ORDER_STATUSES = {
    "pending", "paid", "fulfilled", "refund_pending",
    "refund_processing", "refunded", "closed", "exception",
}


@r.get("/orders")
async def list_orders(
    request: Request, db: Db = Depends(get_db),
    page: int = 1, page_size: int = 20, status: str = "",
):
    """Z.4 我的订单列表（创建时间倒序；status=逗号分隔状态白名单筛选，
    total=筛选全量计数，page/page_size 真分页——tab 分版 + 加载更多契约）。"""
    identity = _current_identity(request)
    if not identity:
        return {"code": 4001, "msg": "未登录"}
    username, user_id = identity

    from datetime import datetime

    from app.infrastructure.repositories.payments_repo import OrderRepo

    if not user_id:
        return {"code": 4001, "msg": "用户不存在"}

    # 未知值忽略；全部未知 → 空列表而非报错（契约 scenario）
    requested = [s.strip() for s in (status or "").split(",") if s.strip()]
    if requested and all(s not in _LIST_ORDER_STATUSES for s in requested):
        return {"code": 0, "data": {"items": [], "total": 0}}
    statuses = [s for s in requested if s in _LIST_ORDER_STATUSES] or None

    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    repo = OrderRepo(db)
    total = repo.count_by_user(user_id, statuses)
    orders = repo.find_by_user(user_id, statuses=statuses, limit=page_size, offset=(page - 1) * page_size)
    now = datetime.now(UTC).replace(tzinfo=None)  # naive UTC（与表列口径一致，同 _order_to_detail）

    items = []
    for o in orders:
        remaining_pay = None
        if o.get("status") == "pending" and o.get("created_at"):
            # pg_http 行的 created_at 是 ISO 字符串，直接相减 TypeError（#265 同款，_naive_utc 归一）
            elapsed = (now - _naive_utc(o["created_at"])).total_seconds()
            remaining_pay = max(0, int(900 - elapsed))
        rs = o.get("refund_status")
        refund_amt = o.get("refund_amount_fen") if rs in ("cooldown", "processing", "succeeded") else None
        items.append({
            "order_no": o["order_no"],
            "status": o.get("status"),
            "amount_fen": o.get("amount_fen"),
            "snapshot": o.get("sku_snapshot") or {},
            "created_at": o["created_at"].isoformat() if hasattr(o.get("created_at"), "isoformat") else str(o.get("created_at", "")),
            "paid_at": o["paid_at"].isoformat() if hasattr(o.get("paid_at"), "isoformat") else str(o.get("paid_at") or ""),
            "refunded_at": o["refunded_at"].isoformat() if hasattr(o.get("refunded_at"), "isoformat") else str(o.get("refunded_at") or ""),
            "refund_amount_fen": refund_amt,
            "remaining_pay_seconds": remaining_pay,
        })

    return {"code": 0, "data": {"items": items, "total": total}}


@r.get("/orders/pending")
async def get_pending_order(request: Request, db: Db = Depends(get_db)):
    """Z.3 恢复未支付订单。"""
    identity = _current_identity(request)
    if not identity:
        return {"code": 4001, "msg": "未登录"}
    username, user_id = identity

    from app.application.payments.create_order import ORDER_TTL_SECONDS
    from app.infrastructure.repositories.payments_repo import OrderRepo
    orders = OrderRepo(db).find_by_user(user_id, limit=1)

    def _alive(o: dict) -> bool:
        """pending 单是否仍在支付有效期内（过期单不恢复——防死码，同 create_order 复用口径）。"""
        if o.get("status") != "pending" or not o.get("code_url"):
            return False
        created = o.get("created_at")
        if isinstance(created, str):
            from app.infrastructure.repositories.pg_http.client import parse_dt
            created = parse_dt(created)
        if created is None:
            return False
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return datetime.now(UTC) < created + timedelta(seconds=ORDER_TTL_SECONDS)

    pending = next((o for o in orders if _alive(o)), None)
    if pending:
        return {"code": 0, "data": {
            "order_no": pending["order_no"],
            "sku_id": pending.get("sku_id"),
            "amount_fen": pending["amount_fen"],
        }}
    return {"code": 0, "data": None}


@r.get("/orders/{order_no}")
async def get_order(order_no: str, request: Request, db: Db = Depends(get_db)):
    """Z.5 订单详情（全量：状态/时间线/单号/退款进度）。"""
    identity = _current_identity(request)
    if not identity:
        return {"code": 4001, "msg": "未登录"}
    username, user_id = identity

    from app.infrastructure.repositories.payments_repo import OrderRepo

    order = OrderRepo(db).find_by_order_no(order_no)
    if not order:
        return {"code": 4004, "msg": "订单不存在"}

    # 属主校验（404 防枚举）
    if order.get("user_id") != user_id:
        return {"code": 4004, "msg": "订单不存在"}

    # 台账快照（到货行激活标注用）；order_id 空时不兜底（order_no 非 int 键查空无意义）
    from app.infrastructure.repositories.factory import code_repo as _code_repo_factory

    codes = _code_repo_factory(db).find_by_order(order.get("id")) if order.get("id") else []
    grant = None
    if codes:
        c = codes[0]
        grant = {
            "status": c.status,
            "activated_at": _iso_or_empty(c.activated_at),
            "expires_at": _iso_or_empty(c.expires_at),
            # 起算时刻：排队码（顺延到现有套餐之后）grant_start 在未来——前端据此区分「排队中/计时中」，
            # 剩余天数展示与退款折算口径均以它为界（折算域函数已按 grant_start>now 走全额退）
            "grant_start": _iso_or_empty(c.grant_start),
        }

    return {"code": 0, "data": _order_to_detail(order, grant=grant)}


@r.post("/orders/{order_no}/query")
async def query_order(order_no: str, request: Request, db: Db = Depends(get_db)):
    """手动查单（"我已支付帮我查"）。"""
    username, user_id = _current_identity(request) or ("", None)

    from app.application.payments.fulfill_payment import fulfill_payment
    from app.infrastructure.payments.gateway import MockPaymentGateway, PaymentStatus
    from app.infrastructure.repositories.payments_repo import OrderRepo, TradeEventRepo

    order = OrderRepo(db).find_by_order_no(order_no)
    if not order or order.get("user_id") != user_id:
        return {"code": 4004, "msg": "订单不存在"}

    gateway = getattr(request.app.state, "payment_gateway", MockPaymentGateway())
    result = gateway.query_payment(order_no)

    hint = {
        PaymentStatus.SUCCESS: "SUCCESS",
        PaymentStatus.NOTPAY: "NOTPAY",
        PaymentStatus.PAYERROR: "PAYERROR",
        PaymentStatus.CLOSED: "CLOSED",
    }.get(result.status, "DEGRADED")

    if result.status == PaymentStatus.SUCCESS and order["status"] in ("pending", "paid"):
        from app.infrastructure.repositories.factory import (
            code_repo as _code_repo_factory,
        )
        fulfill_payment(
            OrderRepo(db), TradeEventRepo(db), order,
            transaction_id=result.transaction_id,
            payer_openid=result.payer_openid,
            code_repo=_code_repo_factory(db),
        )

    return {"code": 0, "data": {"hit": result.status == PaymentStatus.SUCCESS, "hint": hint}}


@r.get("/orders/{order_no}/refund-preview")
async def refund_preview(order_no: str, request: Request, db: Db = Depends(get_db)):
    """退款预览（折算金额）。基准=台账行（未激活全额退）。"""
    username, user_id = _current_identity(request) or ("", None)

    from datetime import datetime

    from app.application.payments.refund_flow import resolve_refund_basis
    from app.domain.payments.refund import calc_refund_fen
    from app.infrastructure.repositories.factory import code_repo as _code_repo_factory
    from app.infrastructure.repositories.payments_repo import OrderRepo

    order = OrderRepo(db).find_by_order_no(order_no)
    if not order or order.get("user_id") != user_id:
        return {"code": 4004, "msg": "订单不存在"}

    if order["status"] not in ("fulfilled",):
        reason = "in_progress" if "refund" in order["status"] else "not_paid"
        return {"code": 0, "data": {"refundable": False, "reason": reason}}

    now = datetime.utcnow()  # naive UTC（折算域口径）
    snapshot = order.get("sku_snapshot") or {}
    total_sec = snapshot.get("period_days", 30) * 86400
    grant_start, expires, paid_at = resolve_refund_basis(
        _code_repo_factory(db), order, now)
    if expires is None:
        expires = now  # 全额分支占位

    quote = calc_refund_fen(
        amount_fen=order["amount_fen"],
        total_sec=total_sec,
        expires_at=expires,
        grant_start=grant_start,
        refund_at=now,
        paid_at=paid_at,
    )

    if not quote.refundable:
        reason_map = {"below_one_fen": "below_one_fen", "over_one_year": "over_one_year"}
        return {"code": 0, "data": {"refundable": False, "reason": reason_map.get(quote.reason, quote.reason)}}

    return {"code": 0, "data": {
        "refundable": True,
        "reason": "",
        "refund_fen": quote.refund_fen,
        "remaining_desc": quote.remaining_desc,
    }}


@r.post("/orders/{order_no}/refund")
async def request_refund(order_no: str, req: RefundRequest, request: Request, db: Db = Depends(get_db)):
    """确认退款（进入冷静期）。"""
    username, user_id = _current_identity(request) or ("", None)

    from app.application.payments.refund_flow import request_refund as _refund
    from app.infrastructure.repositories.factory import code_repo as _code_repo_factory
    from app.infrastructure.repositories.payments_repo import OrderRepo, TradeEventRepo

    order = OrderRepo(db).find_by_order_no(order_no)
    if not order or order.get("user_id") != user_id:
        return {"code": 4004, "msg": "订单不存在"}

    try:
        result = _refund(OrderRepo(db), TradeEventRepo(db), _code_repo_factory(db),
                         order, user_id, req.reason)
        if "error" in result:
            return {"code": 4008 if result["error"] == "below_one_fen" else 4009,
                    "msg": result["error"]}
        return {"code": 0, "data": result}
    except RefundAlreadyActiveError as e:
        return {"code": 4006, "msg": "退款已在进行中",
                "data": {"cooldown_remaining_seconds": e.cooldown_remaining}}
    except RefundTooSmallError:
        return {"code": 4008, "msg": "剩余时长不足折算"}
    except RefundWindowExceeded:
        return {"code": 4009, "msg": "已超过退款窗口"}


@r.post("/orders/{order_no}/refund/cancel")
async def cancel_refund(order_no: str, request: Request, db: Db = Depends(get_db)):
    """冷静期取消退款。"""
    username, user_id = _current_identity(request) or ("", None)

    from app.application.payments.refund_flow import cancel_refund as _cancel
    from app.infrastructure.repositories.factory import code_repo as _code_repo_factory
    from app.infrastructure.repositories.payments_repo import OrderRepo, TradeEventRepo

    order = OrderRepo(db).find_by_order_no(order_no)
    if not order or order.get("user_id") != user_id:
        return {"code": 4004, "msg": "订单不存在"}

    result = _cancel(OrderRepo(db), TradeEventRepo(db), order,
                     code_repo=_code_repo_factory(db))
    if "error" in result:
        if result["error"] == "already_submitted":
            return {"code": 4007, "msg": "冷静期已结束，退款已提交"}
        return {"code": 4006, "msg": result["error"]}
    return {"code": 0, "data": result}


@r.post("/orders/{order_no}/cancel")
async def cancel_order(order_no: str, request: Request, db: Db = Depends(get_db)):
    """取消订单（用户主动）。"""
    username, user_id = _current_identity(request) or ("", None)

    from app.domain.payments.order import Transition
    from app.infrastructure.repositories.payments_repo import OrderRepo

    order = OrderRepo(db).find_by_order_no(order_no)
    if not order or order.get("user_id") != user_id:
        return {"code": 4004, "msg": "订单不存在"}

    if order["status"] != "pending":
        return {"code": 4006, "msg": "订单状态不允许取消"}

    t = Transition("pending", "timeout_close", "closed", "", "用户取消")
    result = OrderRepo(db).compare_and_transition(order_no, t, extra_changes={"closed_at": datetime.now(UTC)})
    if result:
        return {"code": 0, "data": {"order_no": order_no, "status": "closed"}}
    return {"code": 4006, "msg": "取消失败"}


@r.get("/license")
async def get_license(request: Request, db: Db = Depends(get_db)):
    """Z.6 我的套餐总览：档位头汇总（含手工码）+ 订单来源套餐行计数。
    明细列表走 GET /license/codes 分页（license-grants-pagination：响应体不再内嵌全量）。"""
    identity = _current_identity(request)
    if not identity:
        return {"code": 4001, "msg": "未登录"}
    _, user_id = identity

    from app.domain.licensing.license import License
    from app.infrastructure.repositories.factory import code_repo

    # uid 直通（jwt-uid-claim）：_resolve_user_id 对 int 零开销，免 users 表翻译
    all_codes = code_repo(db).find_all_by_username(user_id)
    # 汇总口径保持原状（原 find_active_by_username 只喂 active 行）：unused 手工码
    # 不参与档位归属（merge 跳过清单不含 unused，直接喂会抬高档位头）
    lic = License(username="").merge([c for c in all_codes if c.status != "unused"])  # username 仅标识标签，merge/响应不用

    # code_count 与明细接口「全部」total 同过滤器（source='order'）——口径单源
    def _is_order_row(c):
        return getattr(c, "source", "admin") == "order"

    from datetime import UTC, datetime
    now = datetime.now(UTC).replace(tzinfo=None)  # naive UTC（表列口径，不依赖容器 TZ）
    remaining = 0
    if lic.max_expires_at:
        remaining = max(0, int((lic.max_expires_at - now).total_seconds()))

    return {"code": 0, "data": {
        "tier": lic.effective_tier,
        "remaining_sec": remaining,
        "remaining_desc": f"{remaining // 86400} 天",
        "max_expires_at": lic.max_expires_at.isoformat() if lic.max_expires_at else None,
        "pending_count": sum(1 for c in all_codes if _is_order_row(c) and c.status == "pending_activation"),
        "code_count": sum(1 for c in all_codes if _is_order_row(c)),
    }}


# 套餐明细 status 参数白名单（license-grants-pagination：tab 归组映射在前端，接口保持"哑"）
_LIST_CODE_STATUSES = {"pending_activation", "active", "frozen", "revoked"}


@r.get("/license/codes")
async def list_license_codes(
    request: Request, db: Db = Depends(get_db),
    page: int = 1, page_size: int = 20, status: str = "",
):
    """我的套餐明细分页（仅订单来源台账行；created_at 倒序——裁定不做状态分组，
    已收回行的视觉区分由前端置灰承载）。status=逗号分隔状态白名单筛选，
    total=筛选全量计数——tab 分版 + 加载更多契约（与订单列表同构）。"""
    identity = _current_identity(request)
    if not identity:
        return {"code": 4001, "msg": "未登录"}
    _, user_id = identity
    if not user_id:
        return {"code": 4001, "msg": "用户不存在"}

    # 未知值忽略；全部未知 → 空列表而非报错（契约 scenario，同 list_orders）
    requested = [s.strip() for s in (status or "").split(",") if s.strip()]
    if requested and all(s not in _LIST_CODE_STATUSES for s in requested):
        return {"code": 0, "data": {"items": [], "total": 0}}
    statuses = [s for s in requested if s in _LIST_CODE_STATUSES] or None

    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    from app.infrastructure.repositories.factory import code_repo
    from app.infrastructure.repositories.payments_repo import OrderRepo

    rows, total = code_repo(db).find_order_codes_page(
        user_id, statuses=statuses, limit=page_size, offset=(page - 1) * page_size)

    # order_no 供激活接口定位（页内行批量映射，与原 license 明细组装同款）
    orders_by_id = {}
    if rows:
        order_ids = {c.order_id for c in rows if c.order_id}
        if order_ids:
            orders_by_id = {o["id"]: o.get("order_no", "") for o in OrderRepo(db).find_by_ids(order_ids)}

    items = [{
        "code_id": c.code_id,
        "order_no": orders_by_id.get(c.order_id, ""),
        "tier": c.tier,
        "duration_days": c.duration_days,
        "status": c.status,
        "activated_at": _iso_or_empty(c.activated_at),
        "expires_at": _iso_or_empty(c.expires_at),
        "grant_start": _iso_or_empty(c.grant_start),
    } for c in rows]

    return {"code": 0, "data": {"items": items, "total": total}}


@r.post("/codes/activate")
async def activate(req: ActivateRequest, request: Request, db: Db = Depends(get_db)):
    """激活（到货-激活两段式第二段）。"""
    identity = _current_identity(request)
    if not identity:
        return {"code": 4001, "msg": "未登录"}
    username, user_id = identity

    from app.application.payments.activate_code import activate_code
    from app.infrastructure.repositories.factory import code_repo as _code_repo_factory
    from app.infrastructure.repositories.payments_repo import OrderRepo, TradeEventRepo

    try:
        result = activate_code(
            OrderRepo(db), TradeEventRepo(db), _code_repo_factory(db),
            req.order_no, user_id,
        )
        if "error" in result:
            return {"code": 4004, "msg": result["error"]}
        return {"code": 0, "data": result}
    except DomainError as e:
        return {"code": 4012, "msg": str(e)}


# ── 辅助 ──

def _naive_utc(value) -> datetime:
    """订单行时间列 → naive UTC：pg_http 是 ISO 字符串、sqlite 是 naive、aware 剥 tz。

    payments 域统一 naive 口径（表列/域函数一致，混比 aware/naive 会 TypeError）。
    """
    from app.infrastructure.repositories.pg_http.client import parse_dt

    dt = value if isinstance(value, datetime) else parse_dt(value)
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def _iso_or_empty(value) -> str:
    """时间列 → ISO 字符串（None→""；pg_http ISO 字符串/sqlite naive/aware 三形态归一）。"""
    dt = _naive_utc(value) if value else None
    return dt.isoformat() if dt else ""


def _order_to_detail(order: dict, grant: dict | None = None) -> dict:
    """订单 dict → 附录 Z.5 OrderDetailView。"""
    now = datetime.now(UTC).replace(tzinfo=None)  # naive UTC（折算域口径，同 refund-preview）

    remaining_pay = None
    if order.get("status") == "pending" and order.get("created_at"):
        elapsed = (now - _naive_utc(order["created_at"])).total_seconds()
        remaining_pay = max(0, int(900 - elapsed))  # 15 分钟 TTL

    refund = None
    rs = order.get("refund_status")
    if rs and rs != "none":
        cooldown = None
        if rs == "cooldown" and order.get("cooldown_ends_at"):
            cooldown = max(0, int((_naive_utc(order["cooldown_ends_at"]) - now).total_seconds()))
        refund = {
            "status": rs,
            "amount_fen": order.get("refund_amount_fen"),
            "cooldown_remaining_seconds": cooldown,
            "wx_refund_id": order.get("refund_wx_id"),
        }

    snapshot = order.get("sku_snapshot") or {}
    return {
        "order_no": order.get("order_no"),
        "status": order.get("status"),
        "sku_key": str(order.get("sku_id", "")),
        "snapshot": snapshot,
        "amount_fen": order.get("amount_fen"),
        "created_at": _iso_or_empty(order.get("created_at")),
        "paid_at": _iso_or_empty(order.get("paid_at")),
        "fulfilled_at": _iso_or_empty(order.get("fulfilled_at")),
        "refund_requested_at": _iso_or_empty(order.get("refund_requested_at")),
        "refunded_at": _iso_or_empty(order.get("refunded_at")),
        "fulfillment": grant,  # 到货快照：本单到货产出的码行激活状态投影（codes.order_id 反向引用，非订单属性；fulfilled=已到货的名词化）
        "agreement": {"version": order.get("agreement_version"), "agreed_at": str(order.get("agreed_at", ""))},
        "wx_transaction_id": order.get("transaction_id"),
        "remaining_pay_seconds": remaining_pay,
        "refund": refund,
    }
