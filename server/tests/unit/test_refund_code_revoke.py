"""退款收回（排队相位）测试：revoke_queued_for_order 三仓 CAS + complete_refund
并列收回 + 三入口重放幂等 + 边界（取消不洗回/拒退不收回/进行中不动）+ 扫描 E。

设计依据：openspec/changes/s-pay-refund-code-revoke（锚=refund_requested_at，
与折算金额锁定同锚，防冷静期窗口跨起算点翻转）。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.application.payments.refund_flow import (
    cancel_refund,
    complete_refund,
    cooldown_submit,
    request_refund,
)
from app.application.payments.scan_orders import scan_refund_followup
from app.infrastructure.payments.gateway import MockPaymentGateway, RefundStatus
from app.infrastructure.repositories.payments_repo import OrderRepo, TradeEventRepo
from app.infrastructure.repositories.sql.code_repo import SqlCodeRepo
from app.models.base import SessionLocal
from app.models.code import ActivationCodeORM
from app.models.payments import OrderORM, TradeEventORM
from app.models.user import UserORM

ANCHOR = datetime(2026, 9, 4, 12, 0, 0)  # naive UTC，测试统一锚


@pytest.fixture(scope="module", autouse=True)
def _ensure_tables():
    from app.models.base import Base, engine
    Base.metadata.create_all(bind=engine)
    yield


def _mk_user(username: str) -> int:
    db = SessionLocal()
    try:
        u = UserORM(username=username, password_hash="x")
        db.add(u)
        db.flush()
        uid = u.id
        db.commit()
        return uid
    finally:
        db.close()


def _mk_order(order_no: str, user_id: int, **overrides) -> dict:
    base = dict(
        order_no=order_no,
        user_id=user_id,
        sku_id=1,
        sku_snapshot={"tier_key": "pro", "period": "monthly", "period_days": 30,
                      "base_price_fen": 3000, "discount_permille": 1000,
                      "device_limit": 3},
        amount_fen=3000,
        status="fulfilled",
        prepay_status="created",
        agreement_version="v2026.08",
        agreed_at=datetime.now(UTC),
        transaction_id=f"tx_{order_no}",
        channel="wxpay",
        refund_status="none",
    )
    base.update(overrides)
    db = SessionLocal()
    try:
        db.add(OrderORM(**base))
        db.commit()
    finally:
        db.close()
    return base


def _mk_code(code_id: str, user_id: int, *, status: str = "active",
             grant_start=None, expires_at=None, order_id: int | None = None) -> None:
    db = SessionLocal()
    try:
        db.add(ActivationCodeORM(
            code_id=code_id, tier="pro", duration_days=30,
            status=status, status_detail=status, user_id=user_id,
            source="order", order_id=order_id,
            grant_start=grant_start, expires_at=expires_at,
            created_by="payment",
        ))
        db.commit()
    finally:
        db.close()


def _code_status(code_id: str) -> str:
    db = SessionLocal()
    try:
        row = db.query(ActivationCodeORM).filter_by(code_id=code_id).first()
        return row.status if row else "<missing>"
    finally:
        db.close()


def _event_count(event_key: str) -> int:
    db = SessionLocal()
    try:
        return db.query(TradeEventORM).filter_by(event_key=event_key).count()
    finally:
        db.close()


def _event_payload(event_key: str) -> dict:
    db = SessionLocal()
    try:
        row = db.query(TradeEventORM).filter_by(event_key=event_key).first()
        return row.payload if row else {}
    finally:
        db.close()


@pytest.fixture
def repos():
    db = SessionLocal()
    yield db, OrderRepo(db), TradeEventRepo(db), SqlCodeRepo(db)
    db.close()


# ═══ 仓储层：revoke_queued_for_order（sqlite 实现 + 边界）═══

class TestRevokeQueuedRepo:
    def test_queued_future_revoked(self, repos):
        _, _, _, code_repo = repos
        uid = _mk_user("rq_a")
        _mk_code("O-RQ1", uid, grant_start=datetime(2126, 8, 1))
        assert code_repo.revoke_queued_for_order("RQ1", anchor=ANCHOR) == 1
        assert _code_status("O-RQ1") == "revoked"

    def test_null_grant_start_revoked(self, repos):
        _, _, _, code_repo = repos
        uid = _mk_user("rq_b")
        _mk_code("O-RQ2", uid, grant_start=None)  # admin activate 形态
        assert code_repo.revoke_queued_for_order("RQ2", anchor=ANCHOR) == 1
        assert _code_status("O-RQ2") == "revoked"

    def test_consuming_kept(self, repos):
        _, _, _, code_repo = repos
        uid = _mk_user("rq_c")
        _mk_code("O-RQ3", uid, grant_start=datetime(2026, 8, 1), expires_at=ANCHOR + timedelta(days=20))
        assert code_repo.revoke_queued_for_order("RQ3", anchor=ANCHOR) == 0
        assert _code_status("O-RQ3") == "active"

    def test_boundary_equal_anchor_kept(self, repos):
        """grant_start == anchor：两侧判定式同为严格大于 → 已起算，不收回。"""
        _, _, _, code_repo = repos
        uid = _mk_user("rq_d")
        _mk_code("O-RQ4", uid, grant_start=ANCHOR)
        assert code_repo.revoke_queued_for_order("RQ4", anchor=ANCHOR) == 0
        assert _code_status("O-RQ4") == "active"

    def test_non_active_untouched(self, repos):
        _, _, _, code_repo = repos
        uid = _mk_user("rq_e")
        _mk_code("O-RQ5", uid, status="pending_activation", grant_start=None)
        assert code_repo.revoke_queued_for_order("RQ5", anchor=ANCHOR) == 0
        assert _code_status("O-RQ5") == "pending_activation"

    def test_replay_idempotent(self, repos):
        _, _, _, code_repo = repos
        uid = _mk_user("rq_f")
        _mk_code("O-RQ6", uid, grant_start=datetime(2126, 8, 31))
        assert code_repo.revoke_queued_for_order("RQ6", anchor=ANCHOR) == 1
        assert code_repo.revoke_queued_for_order("RQ6", anchor=ANCHOR) == 0

    def test_anchor_accepts_pg_http_iso_string(self, repos):
        """pg_http 行的锚是 ISO 字符串 → 仓储内归一（sqlite 路径同样容忍）。"""
        _, _, _, code_repo = repos
        uid = _mk_user("rq_g")
        _mk_code("O-RQ7", uid, grant_start=datetime(2126, 9, 30))
        assert code_repo.revoke_queued_for_order("RQ7", anchor="2026-09-04T12:00:00") == 1
        assert _code_status("O-RQ7") == "revoked"


# ═══ complete_refund：排队收回 + 事件 payload + 守卫独立 ═══

def _refunded_order(order_no: str, uid: int, **overrides) -> None:
    _mk_order(order_no, uid, status="refunded", refund_status="succeeded",
              refund_requested_at=ANCHOR, refunded_at=ANCHOR + timedelta(minutes=5),
              refund_amount_fen=3000, **overrides)


class TestCompleteRefundQueued:
    def test_queued_revoked_with_event_payload(self, repos):
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("cr_a")
        _refunded_order("CR1", uid)
        _mk_code("O-CR1", uid, grant_start=datetime(2126, 8, 1),
                 expires_at=datetime(2126, 8, 31))

        out = complete_refund(order_repo, event_repo, "CR1", "wx1", code_repo=code_repo)
        db.commit()
        assert out["status"] == "refunded"
        assert _code_status("O-CR1") == "revoked"
        assert _event_count("codes:O-CR1:revoked:queued") == 1
        payload = _event_payload("codes:O-CR1:revoked:queued")
        assert payload["phase"] == "queued"
        assert payload["anchor"] == ANCHOR.isoformat()  # 锚=refund_requested_at，非 now
        assert payload["grant_start"] == "2126-08-01T00:00:00"
        assert payload["expires_at"] == "2126-08-31T00:00:00"

    def test_consuming_untouched_no_event(self, repos):
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("cr_b")
        _refunded_order("CR2", uid)
        _mk_code("O-CR2", uid, grant_start=datetime(2026, 8, 1),
                 expires_at=datetime(2026, 9, 20))
        complete_refund(order_repo, event_repo, "CR2", "wx2", code_repo=code_repo)
        db.commit()
        assert _code_status("O-CR2") == "active"
        assert _event_count("codes:O-CR2:revoked:queued") == 0

    def test_replay_no_duplicate_events(self, repos):
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("cr_c")
        _refunded_order("CR3", uid)
        _mk_code("O-CR3", uid, grant_start=datetime(2126, 8, 1))
        for _ in range(3):
            complete_refund(order_repo, event_repo, "CR3", "wx3", code_repo=code_repo)
        db.commit()
        assert _event_count("codes:O-CR3:revoked:queued") == 1

    def test_revoke_independent_of_order_status_guard(self, repos):
        """收回移出 status≠refunded 守卫：订单已终态但码漏收的崩溃窗口可重入补收。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("cr_d")
        _refunded_order("CR4", uid)
        _mk_code("O-CR4", uid, grant_start=datetime(2126, 8, 1))  # 漏收态
        complete_refund(order_repo, event_repo, "CR4", "wx4", code_repo=code_repo)
        db.commit()
        assert _code_status("O-CR4") == "revoked"

    def test_unconsumed_still_revoked_alongside(self, repos):
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("cr_e")
        _refunded_order("CR5", uid)
        _mk_code("O-CR5", uid, status="pending_activation", grant_start=None)
        complete_refund(order_repo, event_repo, "CR5", "wx5", code_repo=code_repo)
        db.commit()
        assert _code_status("O-CR5") == "revoked"
        assert _event_count("codes:O-CR5:revoked") == 1  # 未激活支原有事件键不变


# ═══ 三入口重放幂等（R1 cooldown_submit / R3 跟进 / complete_refund 直调）═══

class TestThreeEntryReplay:
    def _seed(self, order_no: str, username: str, status: str, refund_status: str):
        uid = _mk_user(username)
        _mk_order(order_no, uid, status=status, refund_status=refund_status,
                  refund_requested_at=ANCHOR, refund_amount_fen=3000)
        _mk_code(f"O-{order_no}", uid, grant_start=datetime(2126, 8, 1),
                 expires_at=datetime(2126, 8, 31))
        return uid

    def test_entry_r1_cooldown_submit(self, repos):
        db, order_repo, event_repo, code_repo = repos
        self._seed("RE1", "re1", "refund_pending", "cooldown")
        gw = MockPaymentGateway()
        gw.refunds["RE1"] = {"status": RefundStatus.SUCCESS.value, "wx_refund_id": "wxR1"}
        cooldown_submit(order_repo, event_repo, gw, order_repo.find_by_order_no("RE1"),
                        code_repo=code_repo)
        db.commit()
        assert _code_status("O-RE1") == "revoked"
        # 重放（同入口再扫一轮）
        cooldown_submit(order_repo, event_repo, gw, order_repo.find_by_order_no("RE1"),
                        code_repo=code_repo)
        assert _event_count("codes:O-RE1:revoked:queued") == 1

    def test_entry_r3_followup(self, repos):
        db, order_repo, event_repo, code_repo = repos
        self._seed("RE2", "re2", "refund_processing", "processing")
        gw = MockPaymentGateway()
        gw.refunds["RE2"] = {"status": RefundStatus.SUCCESS.value, "wx_refund_id": "wxR2"}
        scan_refund_followup(order_repo, event_repo, gw, code_repo=code_repo)
        db.commit()
        assert _code_status("O-RE2") == "revoked"
        scan_refund_followup(order_repo, event_repo, gw, code_repo=code_repo)
        assert _event_count("codes:O-RE2:revoked:queued") == 1

    def test_entry_direct_complete(self, repos):
        db, order_repo, event_repo, code_repo = repos
        self._seed("RE3", "re3", "refund_processing", "processing")
        complete_refund(order_repo, event_repo, "RE3", "wxR3", code_repo=code_repo)
        complete_refund(order_repo, event_repo, "RE3", "wxR3", code_repo=code_repo)
        db.commit()
        assert _event_count("codes:O-RE3:revoked:queued") == 1


# ═══ 边界：取消不洗回 / 进行中不动 / 拒退不收回 / 域函数边界 ═══

class TestRefundBoundaries:
    def test_cancel_does_not_resurrect_revoked(self, repos):
        """cancel_refund 只做 orders CAS，revoked 行结构性洗不回。"""
        _, order_repo, event_repo, code_repo = repos
        uid = _mk_user("bd_a")
        cooldown_end = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
        _mk_order("BD1", uid, status="refund_pending", refund_status="cooldown",
                  refund_requested_at=ANCHOR, refund_amount_fen=3000,
                  cooldown_ends_at=cooldown_end)
        _mk_code("O-BD1", uid, grant_start=datetime(2126, 8, 1))
        code_repo.revoke_queued_for_order("BD1", anchor=ANCHOR)
        assert _code_status("O-BD1") == "revoked"

        out = cancel_refund(order_repo, event_repo, order_repo.find_by_order_no("BD1"))
        assert out["status"] == "fulfilled"
        assert _code_status("O-BD1") == "revoked"

    def test_processing_code_frozen_not_phased(self, repos):
        """refund_pending/processing 期间相位不迁移（码不被收回），但确认退款
        即冻结（s-pay-refund-freeze）：扫描 F 补冻结后行处于 frozen 态。"""
        _, order_repo, event_repo, code_repo = repos
        uid = _mk_user("bd_b")
        _mk_order("BD2", uid, status="refund_processing", refund_status="processing",
                  refund_requested_at=ANCHOR, refund_amount_fen=3000)
        _mk_code("O-BD2", uid, grant_start=datetime(2126, 8, 1))
        gw = MockPaymentGateway()
        gw.refunds["BD2"] = {"status": RefundStatus.NOT_ENOUGH.value}
        gw.next_refund_status = RefundStatus.NOT_ENOUGH  # 重试仍不足，停 processing
        scan_refund_followup(order_repo, event_repo, gw, code_repo=code_repo)
        assert _code_status("O-BD2") == "frozen"

    def test_below_one_fen_rejection_revokes_nothing(self, repos):
        """折算拒退（below_one_fen）在 request_refund 即返回，不触发任何收回调用。"""
        _, order_repo, event_repo, code_repo = repos
        uid = _mk_user("bd_c")
        _mk_order("BD3", uid, status="fulfilled")
        order_id = order_repo.find_by_order_no("BD3")["id"]
        grant_start = datetime(2026, 9, 1)
        expires_at = grant_start + timedelta(seconds=2)  # 剩余 2s → 折算不足 1 分
        _mk_code("O-BD3", uid, grant_start=grant_start, expires_at=expires_at,
                 order_id=order_id)

        class _SpyRepo:
            def __init__(self, inner):
                self.inner = inner
                self.calls: list[str] = []
            def __getattr__(self, name):
                return getattr(self.inner, name)
            def revoke_unconsumed_for_order(self, order_no):
                self.calls.append("unconsumed")
                return self.inner.revoke_unconsumed_for_order(order_no)
            def revoke_queued_for_order(self, order_no, anchor):
                self.calls.append("queued")
                return self.inner.revoke_queued_for_order(order_no, anchor)

        spy = _SpyRepo(code_repo)
        out = request_refund(order_repo, event_repo, spy, order_repo.find_by_order_no("BD3"), uid)
        assert out["error"] == "below_one_fen"
        assert spy.calls == []
        assert _code_status("O-BD3") == "active"

    def test_domain_boundary_grant_start_equals_refund_at_is_consuming(self):
        """域函数：grant_start == refund_at → 已起算折算分支（非全额退）。"""
        from app.domain.payments.refund import calc_refund_fen
        quote = calc_refund_fen(
            amount_fen=3000, total_sec=30 * 86400,
            expires_at=ANCHOR + timedelta(days=30),
            grant_start=ANCHOR, refund_at=ANCHOR,
            paid_at=ANCHOR - timedelta(days=1),
        )
        assert quote.refundable and quote.refund_fen == 3000  # 剩余=全月 → 折算=封顶实付
        quote2 = calc_refund_fen(
            amount_fen=3000, total_sec=30 * 86400,
            expires_at=ANCHOR + timedelta(days=15),
            grant_start=ANCHOR - timedelta(days=15), refund_at=ANCHOR,
            paid_at=ANCHOR - timedelta(days=16),
        )
        assert quote2.refundable and quote2.refund_fen == 1500  # 剩余一半 → 折算一半


# ═══ 扫描 E：存量收敛 + 豁免 + 防误伤 ═══

class TestScanE:
    def test_hit_revoke_and_action(self, repos):
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("se_a")
        _refunded_order("SE1", uid)
        _mk_code("O-SE1", uid, grant_start=datetime(2126, 8, 1),
                 expires_at=datetime(2126, 8, 31))

        out = scan_refund_followup(order_repo, event_repo, MockPaymentGateway(),
                                   code_repo=code_repo)
        db.commit()
        assert {"order_no": "SE1", "action": "queued_code_revoked"} in out
        assert _code_status("O-SE1") == "revoked"
        assert _event_count("codes:O-SE1:revoked:queued") == 1

    def test_replay_zero_new(self, repos):
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("se_b")
        _refunded_order("SE2", uid)
        _mk_code("O-SE2", uid, grant_start=datetime(2126, 8, 1))
        for _ in range(2):
            out = scan_refund_followup(order_repo, event_repo, MockPaymentGateway(),
                                       code_repo=code_repo)
        db.commit()
        assert {"order_no": "SE2", "action": "queued_code_revoked"} not in out
        assert _event_count("codes:O-SE2:revoked:queued") == 1

    def test_consuming_exempt(self, repos):
        _, order_repo, event_repo, code_repo = repos
        uid = _mk_user("se_c")
        _refunded_order("SE3", uid)
        _mk_code("O-SE3", uid, grant_start=datetime(2026, 8, 1),
                 expires_at=datetime(2026, 9, 20))
        out = scan_refund_followup(order_repo, event_repo, MockPaymentGateway(),
                                   code_repo=code_repo)
        assert _code_status("O-SE3") == "active"
        assert all(r["order_no"] != "SE3" for r in out)

    def test_fulfilled_order_queued_code_untouched(self, repos):
        """防误伤回归锚：未退款 fulfilled 单的排队码不进扫描 E 数据源。"""
        _, order_repo, event_repo, code_repo = repos
        uid = _mk_user("se_d")
        _mk_order("SE4", uid, status="fulfilled")
        _mk_code("O-SE4", uid, grant_start=datetime(2126, 8, 1))
        scan_refund_followup(order_repo, event_repo, MockPaymentGateway(),
                             code_repo=code_repo)
        assert _code_status("O-SE4") == "active"

    def test_missing_anchor_skipped(self, repos):
        """锚缺失（数据异常）行跳过不猜锚，防误收已起算权益。"""
        _, order_repo, event_repo, code_repo = repos
        uid = _mk_user("se_e")
        _mk_order("SE5", uid, status="refunded", refund_status="succeeded",
                  refunded_at=ANCHOR, refund_amount_fen=3000)  # 无 refund_requested_at
        _mk_code("O-SE5", uid, grant_start=datetime(2026, 8, 1))  # 已起算形态
        scan_refund_followup(order_repo, event_repo, MockPaymentGateway(),
                             code_repo=code_repo)
        assert _code_status("O-SE5") == "active"


# ═══ find_refund_succeeded（1.4）═══

class TestFindRefundSucceeded:
    def test_returns_only_refunded_succeeded(self, repos):
        _, order_repo, _, _ = repos
        uid = _mk_user("frs_a")
        _refunded_order("FRS1", uid)
        _mk_order("FRS2", uid, status="fulfilled")
        _mk_order("FRS3", uid, status="refund_processing", refund_status="processing")
        nos = {o["order_no"] for o in order_repo.find_refund_succeeded()}
        assert "FRS1" in nos and "FRS2" not in nos and "FRS3" not in nos


# ═══ pg_http 实现（1.3：两支 CAS 构造）═══

class TestPgHttpRevokeQueued:
    def _repo(self, requests: list):
        import httpx

        from app.infrastructure.repositories.pg_http.client import PgRestClient
        from app.infrastructure.repositories.pg_http.code_repo import PgHttpCodeRepo

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=[{"code_id": "O-PG1"}])  # 1 行
        client = PgRestClient("https://e.example", "k", transport=httpx.MockTransport(handler))
        return PgHttpCodeRepo(client)

    def test_two_branch_cas_filters(self):
        import httpx
        requests: list[httpx.Request] = []
        repo = self._repo(requests)
        n = repo.revoke_queued_for_order("PG1", anchor=datetime(2026, 9, 4, 12, 0, 0))
        assert n == 2  # mock 两支各回 1 行
        assert len(requests) == 2
        p0, p1 = requests[0].url.params, requests[1].url.params
        assert p0["code_id"] == "eq.O-PG1" and p1["code_id"] == "eq.O-PG1"
        assert p0["status"] == "in.(active,frozen)" and p1["status"] == "in.(active,frozen)"
        assert p0["grant_start"] == "is.null"
        assert p1["grant_start"] == "gt.2026-09-04T12:00:00"  # naive iso，无时区尾缀

    def test_aware_anchor_normalized(self):
        import httpx
        requests: list[httpx.Request] = []
        repo = self._repo(requests)
        aware = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)
        repo.revoke_queued_for_order("PG1", anchor=aware)
        assert requests[1].url.params["grant_start"] == "gt.2026-09-04T12:00:00"

    def test_pg_http_find_refund_succeeded_filters(self):
        import httpx

        from app.infrastructure.repositories.payments_repo import OrderRepo
        from app.infrastructure.repositories.pg_http.client import PgRestClient
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=[])
        client = PgRestClient("https://e.example", "k", transport=httpx.MockTransport(handler))
        OrderRepo(client).find_refund_succeeded()
        p = requests[0].url.params
        assert p["status"] == "eq.refunded"
        assert p["refund_status"] == "eq.succeeded"
