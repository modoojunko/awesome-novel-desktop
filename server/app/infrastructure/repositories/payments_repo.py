"""payments 仓储层：order/trade_event/sku/tier 仓储（pg_http + sqlite 双模式）。

表即状态机：OrderRepo.compare_and_transition 是核心 CAS 原语。
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.domain.payments.order import Transition


def _dt(value) -> datetime:
    """pg_http 返回的 ISO 字符串/已解析 datetime 统一为 aware datetime（UTC）。"""
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


class OrderRepo:
    """orders 表仓储（含退款列族）。sqlite/pg_http 双模式。"""

    def __init__(self, db):
        self._db = db  # Session（sqlite）或 PgRestClient（pg_http）

    def create(self, order: dict) -> dict | None:
        """INSERT；撞唯一约束返回 None。"""
        if isinstance(self._db, Session):
            from app.models.payments import OrderORM
            orm = OrderORM(**order)
            self._db.add(orm)
            self._db.flush()
            self._db.refresh(orm)
            return {c.name: getattr(orm, c.name) for c in orm.__table__.columns}
        else:
            return self._db.insert_returning("orders", order)

    def find_by_order_no(self, order_no: str) -> dict | None:
        if isinstance(self._db, Session):
            from app.models.payments import OrderORM
            orm = self._db.query(OrderORM).filter_by(order_no=order_no).first()
            if not orm:
                return None
            return {c.name: getattr(orm, c.name) for c in orm.__table__.columns}
        else:
            return self._db.find_one("orders", {"order_no": order_no})

    def find_by_ids(self, ids: list) -> list[dict]:
        """按代理 id 批量取（license 明细 order_no 映射用）。"""
        if not ids:
            return []
        if isinstance(self._db, Session):
            from app.models.payments import OrderORM
            orms = self._db.query(OrderORM).filter(OrderORM.id.in_(list(ids))).all()
            return [{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in orms]
        else:
            return self._db.find("orders", filter={"id": f"in.({','.join(str(i) for i in ids)})"})

    def find_by_user(
        self, user_id: int, statuses: list[str] | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        """statuses=状态白名单（None/空=全部；订单列表 tab 筛选用）。"""
        if isinstance(self._db, Session):
            from app.models.payments import OrderORM
            q = self._db.query(OrderORM).filter_by(user_id=user_id)
            if statuses:
                q = q.filter(OrderORM.status.in_(statuses))
            orms = (
                q.order_by(OrderORM.created_at.desc())
                .offset(offset).limit(limit).all()
            )
            return [{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in orms]
        else:
            filt: dict = {"user_id": user_id}
            if statuses:
                filt["status"] = f"in.({','.join(statuses)})"
            return self._db.find(
                "orders",
                filter=filt,
                sort=[("created_at", "desc")],
                limit=limit,
                offset=offset,
            )

    def count_by_user(self, user_id: int, statuses: list[str] | None = None) -> int:
        """订单列表 total 口径：与 find_by_user 同筛选（statuses=None=全部）。"""
        if isinstance(self._db, Session):
            from app.models.payments import OrderORM
            q = self._db.query(OrderORM).filter_by(user_id=user_id)
            if statuses:
                q = q.filter(OrderORM.status.in_(statuses))
            return q.count()
        else:
            filt: dict = {"user_id": user_id}
            if statuses:
                filt["status"] = f"in.({','.join(statuses)})"
            return self._db.count("orders", filter=filt)

    def find_by_user_page(
        self, user_id: int, statuses: list[str] | None = None,
        limit: int = 20, offset: int = 0,
    ) -> tuple[list[dict], int]:
        """订单列表单往返取数（orders-page-latency）：(当前页行, total)。

        筛选/排序/分页窗口与 find_by_user + count_by_user 分步调用完全同口径。
        pg_http：count 与取行合并为一次请求（Prefer: count=exact）；
        网关不回 Content-Range 时降级为单独计数（语义不变，多一趟往返）。
        sqlite：一次查询自计数+切片（个人订单量级，与 count() 降级同款假设）。
        """
        if isinstance(self._db, Session):
            from app.models.payments import OrderORM
            q = self._db.query(OrderORM).filter_by(user_id=user_id)
            if statuses:
                q = q.filter(OrderORM.status.in_(statuses))
            rows = q.order_by(OrderORM.created_at.desc()).all()
            return (
                [{c.name: getattr(o, c.name) for c in o.__table__.columns}
                 for o in rows[offset:offset + limit]],
                len(rows),
            )
        else:
            filt: dict = {"user_id": user_id}
            if statuses:
                filt["status"] = f"in.({','.join(statuses)})"
            rows, total = self._db.find(
                "orders",
                filter=filt,
                sort=[("created_at", "desc")],
                limit=limit,
                offset=offset,
                want_count=True,
            )
            if total is None:
                total = self._db.count("orders", filter=filt)
            return rows, total

    def find_pending_expirable(self, cutoff: datetime) -> list[dict]:
        """扫描 pending 且超时的订单（T1 关单）。"""
        if isinstance(self._db, Session):
            from sqlalchemy import and_

            from app.models.payments import OrderORM
            orms = self._db.query(OrderORM).filter(
                and_(OrderORM.status == "pending", OrderORM.created_at < cutoff)
            ).all()
            return [{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in orms]
        else:
            return self._db.find("orders", filter={"status": "pending"})

    def find_paid_unfulfilled(self) -> list[dict]:
        """扫描 paid 但未 fulfilled 的订单（T2 补偿发货）。"""
        if isinstance(self._db, Session):
            from app.models.payments import OrderORM
            orms = self._db.query(OrderORM).filter_by(status="paid").all()
            return [{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in orms]
        else:
            return self._db.find("orders", filter={"status": "paid"})

    def find_paid_between(self, start: datetime, end: datetime) -> list[dict]:
        """对账内部账：paid_at 落在 [start, end) 且非 exception 的订单。"""
        if isinstance(self._db, Session):
            from sqlalchemy import and_

            from app.models.payments import OrderORM
            orms = self._db.query(OrderORM).filter(
                and_(
                    OrderORM.paid_at >= start,
                    OrderORM.paid_at < end,
                    OrderORM.status != "exception",
                )
            ).all()
            return [{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in orms]
        else:
            # pg_http 简化：paid 非空行拉回内存按时间窗过滤（Change 1 量级可接受）
            # PostgREST 的 IS NOT NULL 语法是 not.is.null（not_null 会被当 eq 字面量解析成 timestamp 比较而 400）
            all_paid = self._db.find("orders", filter={"paid_at": "not.is.null"})
            return [
                r for r in all_paid
                if r.get("paid_at") and start <= _dt(r["paid_at"]) < end
                and r.get("status") != "exception"
            ]

    def find_refund_succeeded_between(self, start: datetime, end: datetime) -> list[dict]:
        """对账内部退款账：refunded_at 落在 [start, end) 且退款成功的订单。"""
        if isinstance(self._db, Session):
            from sqlalchemy import and_

            from app.models.payments import OrderORM
            orms = self._db.query(OrderORM).filter(
                and_(
                    OrderORM.refund_status == "succeeded",
                    OrderORM.refunded_at >= start,
                    OrderORM.refunded_at < end,
                )
            ).all()
            return [{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in orms]
        else:
            rows = self._db.find("orders", filter={"refund_status": "succeeded"})
            return [
                r for r in rows
                if r.get("refunded_at") and start <= _dt(r["refunded_at"]) < end
            ]

    def find_refund_processing(self) -> list[dict]:
        """T3：退款受理中（提交微信后未终结）的订单。"""
        if isinstance(self._db, Session):
            from app.models.payments import OrderORM
            orms = self._db.query(OrderORM).filter(
                OrderORM.refund_status == "processing"
            ).all()
            return [{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in orms]
        else:
            return self._db.find("orders", filter={"refund_status": "processing"})

    def find_refund_half_done(self) -> list[dict]:
        """扫描 D：退款成功但订单状态未到 refunded（半截恢复）。"""
        if isinstance(self._db, Session):
            from app.models.payments import OrderORM
            orms = self._db.query(OrderORM).filter(
                OrderORM.refund_status == "succeeded",
                OrderORM.status != "refunded",
            ).all()
            return [{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in orms]
        else:
            return self._db.find("orders", filter={"refund_status": "succeeded"})

    def find_refund_succeeded(self) -> list[dict]:
        """扫描 E：全部退款成功终态单（refunded + refund_status=succeeded）。
        与 find_refund_succeeded_between 同源口径、无时间窗——
        供排队中权益码漏网自愈扫描取数（含历史存量）。"""
        if isinstance(self._db, Session):
            from app.models.payments import OrderORM
            orms = self._db.query(OrderORM).filter(
                OrderORM.status == "refunded",
                OrderORM.refund_status == "succeeded",
            ).all()
            return [{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in orms]
        else:
            return self._db.find(
                "orders",
                filter={"status": "refunded", "refund_status": "succeeded"},
            )

    def find_cooldown_expired(self, now: datetime) -> list[dict]:
        """扫描冷静期到期的订单（§4.9b 到点提交）。"""
        if isinstance(self._db, Session):
            from sqlalchemy import and_

            from app.models.payments import OrderORM
            orms = self._db.query(OrderORM).filter(
                and_(
                    OrderORM.status == "refund_pending",
                    OrderORM.cooldown_ends_at <= now,
                )
            ).all()
            return [{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in orms]
        else:
            return self._db.find("orders", filter={"status": "refund_pending"})

    def attention_flags(self, user_id: int) -> dict:
        """check-auth 账号动态（设计 A4）：退款进行中（含冷静期）/ 有冻结待核对订单。"""
        if isinstance(self._db, Session):
            from sqlalchemy import and_, or_

            from app.models.payments import OrderORM
            refund_active = self._db.query(OrderORM.id).filter(
                and_(
                    OrderORM.user_id == user_id,
                    or_(
                        OrderORM.status == "refund_pending",
                        OrderORM.refund_status == "processing",
                    ),
                )
            ).first() is not None
            verify = self._db.query(OrderORM.id).filter(
                and_(OrderORM.user_id == user_id, OrderORM.status == "exception")
            ).first() is not None
            return {"refund_processing": refund_active, "verify_pending": verify}
        else:
            processing = self._db.find(
                "orders",
                filter={"user_id": user_id, "refund_status": "processing"},
                limit=1,
            )
            cooldown = self._db.find(
                "orders",
                filter={"user_id": user_id, "status": "refund_pending"},
                limit=1,
            )
            exception = self._db.find(
                "orders",
                filter={"user_id": user_id, "status": "exception"},
                limit=1,
            )
            return {
                "refund_processing": bool(processing or cooldown),
                "verify_pending": bool(exception),
            }

    def compare_and_transition(
        self, order_no: str, transition: Transition, extra_changes: dict | None = None,
    ) -> dict | None:
        """核心 CAS 原语：执行状态转移，赢返回更新后行，输返回 None。

        Args:
            order_no: 订单号
            transition: 领域层转移定义（含 CAS WHERE 条件）
            extra_changes: 额外要写的列（如 paid_at/cooldown_ends_at）
        """
        changes = {"status": transition.to_status, **(extra_changes or {})}
        if isinstance(self._db, Session):
            from sqlalchemy import and_

            from app.models.payments import OrderORM
            # 解析 CAS WHERE（"status IN ('pending','closed')" 或 "status = 'pending'"）
            conditions = [OrderORM.order_no == order_no]
            if "IN" in transition.cas_where:
                # "status IN ('pending','closed')" → __in__
                values = transition.cas_where.split("IN")[1].strip("() ")
                vals = [v.strip("' ") for v in values.split(",")]
                conditions.append(OrderORM.status.in_(vals))
            elif "=" in transition.cas_where:
                # "status = 'pending'" → ==
                val = transition.cas_where.split("=")[1].strip("' ")
                conditions.append(OrderORM.status == val)

            orm = self._db.query(OrderORM).filter(and_(*conditions)).first()
            if not orm:
                return None
            for k, v in changes.items():
                setattr(orm, k, v)
            self._db.flush()
            self._db.refresh(orm)
            return {c.name: getattr(orm, c.name) for c in orm.__table__.columns}
        else:
            # pg_http：使用 CAS 扩展方法
            # 简化：只用 from_status 做 CAS 条件（复杂条件由调用方预检）
            return self._db.compare_and_update(
                "orders",
                pk_filter={"order_no": order_no},
                cas_condition={"status": transition.from_status},
                changes=changes,
            )

    def update_fields(self, order_no: str, changes: dict) -> None:
        """直接更新指定列（不做 CAS，用于幂等补写）。"""
        if isinstance(self._db, Session):
            from app.models.payments import OrderORM
            self._db.query(OrderORM).filter_by(order_no=order_no).update(changes)
            self._db.flush()
        else:
            self._db.update("orders", {"order_no": order_no}, changes)


class TradeEventRepo:
    """trade_events 仓储（append-only，event_key 幂等）。"""

    def __init__(self, db):
        self._db = db

    def append(self, event: dict) -> bool:
        """INSERT；撞 event_key 唯一约束返回 False（幂等重放）。"""
        if isinstance(self._db, Session):
            from app.models.payments import TradeEventORM
            existing = self._db.query(TradeEventORM).filter_by(
                event_key=event["event_key"]).first()
            if existing:
                return False
            orm = TradeEventORM(**event)
            self._db.add(orm)
            self._db.flush()
            return True
        else:
            return self._db.insert_or_conflict("trade_events", event)

    def find_by_order(self, order_no: str) -> list[dict]:
        if isinstance(self._db, Session):
            from app.models.payments import TradeEventORM
            orms = (
                self._db.query(TradeEventORM)
                .filter_by(order_no=order_no)
                .order_by(TradeEventORM.created_at)
                .all()
            )
            return [{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in orms]
        else:
            return self._db.find(
                "trade_events",
                filter={"order_no": order_no},
                sort=[("created_at", "asc")],
            )


class SkuRepo:
    """skus 仓储。"""

    def __init__(self, db):
        self._db = db

    def find_on_sale(self) -> list[dict]:
        if isinstance(self._db, Session):
            from app.models.payments import SkuORM, TierORM
            rows = (
                self._db.query(SkuORM, TierORM)
                .join(TierORM, SkuORM.tier_id == TierORM.id)
                .filter(SkuORM.on_sale == True, TierORM.status == "live")
                .order_by(SkuORM.sort)
                .all()
            )
            result = []
            for sku, tier in rows:
                d = {c.name: getattr(sku, c.name) for c in sku.__table__.columns}
                d["tier_key"] = tier.key
                d["tier_display"] = tier.display_name
                d["tier_rank"] = tier.rank
                result.append(d)
            return result
        else:
            # pg_http 无联表：先取 live 档集，再按 tier_id 过滤+富集——与 sqlite 分支口径
            # 一致（planned/retired 档 SKU 不泄入目录；tier_key 由档行富集而非端点默认值）
            tiers = self._db.find("tiers", filter={"status": "eq.live"}, sort=[("rank", "asc")])
            by_id = {t.get("id"): t for t in tiers}
            rows = self._db.find("skus", filter={"on_sale": True}, sort=[("sort", "asc")])
            result = []
            for d in rows:
                tier = by_id.get(d.get("tier_id"))
                if tier is None:
                    continue
                d = dict(d)
                d["tier_key"] = tier.get("key", "")
                d["tier_display"] = tier.get("display_name", "")
                d["tier_rank"] = tier.get("rank", 0)
                result.append(d)
            return result

    def find_by_key(self, sku_key: str) -> dict | None:
        if isinstance(self._db, Session):
            from app.models.payments import SkuORM
            orm = self._db.query(SkuORM).filter_by(sku_key=sku_key).first()
            if not orm:
                return None
            return {c.name: getattr(orm, c.name) for c in orm.__table__.columns}
        else:
            return self._db.find_one("skus", {"sku_key": sku_key})


class TierRepo:
    """tiers 仓储。"""

    # 档位权益配置进程内缓存：key -> (monotonic, 解析后的 dict 或 None)。
    # 配置变更频率极低（改配置=运维事件），TTL 60s 避免每次 check-auth 刷新
    # 多一跳 pg_http（保住 #288 单往返优化）。
    _ENTITLEMENT_CACHE: dict = {}
    _ENTITLEMENT_TTL = 60.0

    def __init__(self, db):
        self._db = db

    def find_all(self) -> list[dict]:
        if isinstance(self._db, Session):
            from app.models.payments import TierORM
            orms = self._db.query(TierORM).order_by(TierORM.rank).all()
            return [{c.name: getattr(o, c.name) for c in o.__table__.columns} for o in orms]
        else:
            return self._db.find("tiers", sort=[("rank", "asc")])

    def find_entitlement_by_key(self, tier_key: str) -> dict | None:
        """档位权益配置（TTL 缓存）。

        返回解析后的 dict（{"features":[...], "limits":{...}}）；
        档位行不存在/未配置/坏 JSON 返回 None（调用方走 ENTITLEMENT_DEFAULTS 兜底）。
        """
        import json
        import time as _time

        now = _time.monotonic()
        cached = TierRepo._ENTITLEMENT_CACHE.get(tier_key)
        if cached is not None and now - cached[0] < TierRepo._ENTITLEMENT_TTL:
            return cached[1]

        parsed = None
        for row in self.find_all():
            if row.get("key") != tier_key:
                continue
            raw = row.get("entitlement")
            if raw:
                try:
                    doc = json.loads(raw)
                    if isinstance(doc, dict):
                        parsed = doc
                except ValueError:
                    parsed = None
            break

        TierRepo._ENTITLEMENT_CACHE[tier_key] = (now, parsed)
        return parsed


class ReconciliationReportRepo:
    """reconciliation_reports 仓储（按日 UPSERT——对账报告属派生报表，可重算覆盖）。"""

    def __init__(self, db):
        self._db = db

    def upsert(self, report: dict) -> None:
        bill_date = report["bill_date"]  # date 对象或 'YYYY-MM-DD'
        if isinstance(self._db, Session):
            from datetime import date
            if isinstance(bill_date, str):
                bill_date = date.fromisoformat(bill_date)
            from app.models.payments import ReconciliationReportORM
            orm = self._db.query(ReconciliationReportORM).filter_by(
                bill_date=bill_date).first()
            if orm is None:
                orm = ReconciliationReportORM(bill_date=bill_date)
                self._db.add(orm)
            for k, v in report.items():
                if k != "bill_date":
                    setattr(orm, k, v)
            self._db.flush()
        else:
            # pg_http：upsert 语义 = 先删后插（派生报表可重算，无外键挂靠）
            self._db.delete("reconciliation_reports", {"bill_date": str(bill_date)})
            self._db.insert("reconciliation_reports", {**report, "bill_date": str(bill_date)})

    def find_by_date(self, bill_date: str) -> dict | None:
        if isinstance(self._db, Session):
            from datetime import date

            from app.models.payments import ReconciliationReportORM
            orm = self._db.query(ReconciliationReportORM).filter_by(
                bill_date=date.fromisoformat(bill_date)).first()
            if not orm:
                return None
            return {c.name: getattr(orm, c.name) for c in orm.__table__.columns}
        else:
            return self._db.find_one("reconciliation_reports", {"bill_date": bill_date})
