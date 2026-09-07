"""退款冻结（s-pay-refund-freeze）测试：确认退款即冻结 / 取消解冻精确还原 /
到账两相位（排队 frozen→revoked、已起算 frozen→active）/ 扫描 F 冻结完整性自愈 /
排队位不受冻结影响。

设计依据：openspec/changes/s-pay-refund-freeze（冻结=可用性暂停；grant_start
不动；收回相位判定仍以 refund_requested_at 为锚）。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.application.payments.activate_code import calc_grant_start
from app.application.payments.refund_flow import (
    cancel_refund,
    complete_refund,
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


def _code_row(code_id: str) -> ActivationCodeORM | None:
    db = SessionLocal()
    try:
        return db.query(ActivationCodeORM).filter_by(code_id=code_id).first()
    finally:
        db.close()


def _code_status(code_id: str) -> str:
    row = _code_row(code_id)
    return row.status if row else "<missing>"


def _event_count(event_key: str) -> int:
    db = SessionLocal()
    try:
        return db.query(TradeEventORM).filter_by(event_key=event_key).count()
    finally:
        db.close()


def _event_type_count(event_type: str, order_no: str) -> int:
    """扫描 F 自愈事件的键带时间戳后缀，按 event_type+order_no 计数。"""
    db = SessionLocal()
    try:
        return db.query(TradeEventORM).filter_by(
            event_type=event_type, order_no=order_no).count()
    finally:
        db.close()


@pytest.fixture
def repos():
    db = SessionLocal()
    yield db, OrderRepo(db), TradeEventRepo(db), SqlCodeRepo(db)
    db.close()


# ═══ request_refund：确认退款即冻结 ═══

class TestRequestFreezes:
    def test_confirm_freezes_active_row_keeps_queue(self, repos):
        """确认退款：active→frozen；grant_start/expires_at 原样（排队位不动）。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_a")
        _mk_order("FZ1", uid)
        order = order_repo.find_by_order_no("FZ1")
        _mk_code("O-FZ1", uid, grant_start=datetime(2126, 8, 1),
                 expires_at=datetime(2126, 8, 31), order_id=order["id"])

        out = request_refund(order_repo, event_repo, code_repo, order, uid)
        db.commit()
        assert out["status"] == "refund_pending"
        row = _code_row("O-FZ1")
        assert row.status == "frozen" and row.status_detail == "frozen"
        assert row.grant_start == datetime(2126, 8, 1)
        assert row.expires_at == datetime(2126, 8, 31)

    def test_pending_activation_row_untouched(self, repos):
        """未激活行本就不可用，不冻结（freeze 只针对已激活可用行）。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_b")
        _mk_order("FZ2", uid)
        order = order_repo.find_by_order_no("FZ2")
        _mk_code("O-FZ2", uid, status="pending_activation", order_id=order["id"])

        request_refund(order_repo, event_repo, code_repo, order, uid)
        db.commit()
        assert _code_status("O-FZ2") == "pending_activation"

    def test_freeze_replay_idempotent(self, repos):
        """重复确认（第二次 RefundAlreadyActiveError）不重复副作用。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_c")
        _mk_order("FZ3", uid)
        order = order_repo.find_by_order_no("FZ3")
        _mk_code("O-FZ3", uid, grant_start=datetime(2126, 8, 1), order_id=order["id"])

        request_refund(order_repo, event_repo, code_repo, order, uid)
        from app.domain.payments.pricing import RefundAlreadyActiveError
        with pytest.raises(RefundAlreadyActiveError):
            request_refund(order_repo, event_repo, code_repo,
                           order_repo.find_by_order_no("FZ3"), uid)
        db.commit()
        assert _code_status("O-FZ3") == "frozen"


# ═══ cancel_refund：解冻精确还原 ═══

class TestCancelUnfreezes:
    def test_cancel_restores_frozen_row(self, repos):
        """取消退款：frozen→active，起算/到期信息不变。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_d")
        cooldown_end = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
        _mk_order("FZ4", uid, status="refund_pending", refund_status="cooldown",
                  refund_requested_at=ANCHOR, refund_amount_fen=3000,
                  cooldown_ends_at=cooldown_end)
        _mk_code("O-FZ4", uid, grant_start=datetime(2126, 8, 1),
                 expires_at=datetime(2126, 8, 31))
        code_repo.freeze_for_order("FZ4")

        out = cancel_refund(order_repo, event_repo,
                            order_repo.find_by_order_no("FZ4"), code_repo=code_repo)
        db.commit()
        assert out["status"] == "fulfilled"
        row = _code_row("O-FZ4")
        assert row.status == "active" and row.status_detail == "active"
        assert row.grant_start == datetime(2126, 8, 1)
        assert row.expires_at == datetime(2126, 8, 31)

    def test_cancel_never_touches_revoked(self, repos):
        """取消路径只解冻 frozen，revoked 行结构性洗不回。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_e")
        cooldown_end = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
        _mk_order("FZ5", uid, status="refund_pending", refund_status="cooldown",
                  refund_requested_at=ANCHOR, refund_amount_fen=3000,
                  cooldown_ends_at=cooldown_end)
        _mk_code("O-FZ5", uid, grant_start=datetime(2126, 8, 1))
        code_repo.revoke_queued_for_order("FZ5", anchor=ANCHOR)

        cancel_refund(order_repo, event_repo,
                      order_repo.find_by_order_no("FZ5"), code_repo=code_repo)
        db.commit()
        assert _code_status("O-FZ5") == "revoked"


# ═══ complete_refund：到账两相位（含 frozen 起点）═══

class TestCompleteRefundFromFrozen:
    def test_frozen_queued_revoked(self, repos):
        """排队中行（冻结态）随全额退款收回，事件 payload 留存起算信息。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_f")
        _mk_order("FZ6", uid, status="refund_pending", refund_status="cooldown",
                  refund_requested_at=ANCHOR, refund_amount_fen=3000)
        _mk_code("O-FZ6", uid, grant_start=datetime(2126, 8, 1),
                 expires_at=datetime(2126, 8, 31))
        code_repo.freeze_for_order("FZ6")

        complete_refund(order_repo, event_repo, "FZ6", "wx6", code_repo=code_repo)
        db.commit()
        assert _code_status("O-FZ6") == "revoked"
        assert _event_count("codes:O-FZ6:revoked:queued") == 1
        assert _event_count("codes:O-FZ6:restored") == 0

    def test_frozen_started_restored(self, repos):
        """已起算行（冻结态）退款成功后恢复 active——剩余权益继续有效。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_g")
        _mk_order("FZ7", uid, status="refund_pending", refund_status="cooldown",
                  refund_requested_at=ANCHOR, refund_amount_fen=1500)
        _mk_code("O-FZ7", uid, grant_start=datetime(2026, 8, 1),
                 expires_at=datetime(2026, 9, 20))
        code_repo.freeze_for_order("FZ7")

        complete_refund(order_repo, event_repo, "FZ7", "wx7", code_repo=code_repo)
        db.commit()
        row = _code_row("O-FZ7")
        assert row.status == "active" and row.status_detail == "active"
        assert row.grant_start == datetime(2026, 8, 1)
        assert row.expires_at == datetime(2026, 9, 20)
        assert _event_count("codes:O-FZ7:restored") == 1
        assert _event_count("codes:O-FZ7:revoked:queued") == 0

    def test_restore_replay_no_duplicate_event(self, repos):
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_h")
        _mk_order("FZ8", uid, status="refunded", refund_status="succeeded",
                  refund_requested_at=ANCHOR, refunded_at=ANCHOR,
                  refund_amount_fen=1500)
        _mk_code("O-FZ8", uid, grant_start=datetime(2026, 8, 1),
                 expires_at=datetime(2026, 9, 20))
        code_repo.freeze_for_order("FZ8")

        for _ in range(2):
            complete_refund(order_repo, event_repo, "FZ8", "wx8", code_repo=code_repo)
        db.commit()
        assert _event_count("codes:O-FZ8:restored") == 1


# ═══ 排队位不受冻结影响 ═══

class TestQueueIgnoresFreeze:
    def test_calc_grant_start_counts_frozen(self, repos):
        """顺延起点计算必须把 frozen 行计入（merge 会跳过，排队计算不许跳）。"""
        class _Row:
            def __init__(self, expires_at):
                self.expires_at = expires_at

        base = calc_grant_start([_Row(datetime(2126, 8, 31))])
        assert base == datetime(2126, 8, 31).date()

    def test_activation_during_freeze_window_keeps_queue(self, repos):
        """冻结窗口内 activate_code 的取数口径（active+frozen 家族）含冻结行。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_i")
        _mk_order("FZ9", uid)
        _mk_code("O-FZ9", uid, grant_start=datetime(2126, 8, 1),
                 expires_at=datetime(2126, 8, 31))
        code_repo.freeze_for_order("FZ9")

        family = [c for c in code_repo.find_all_by_username(uid)
                  if c.status in ("active", "frozen")]
        assert len(family) == 1
        assert calc_grant_start(family) == datetime(2126, 8, 31).date()


# ═══ 扫描 F：冻结完整性自愈 ═══

class TestScanFreezeIntegrity:
    def test_scan_a_refreezes_half_done(self, repos):
        """F-a：退款在途但行仍 active（冻结写半截）→ 补冻结+落账，重跑 0 新增。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_j")
        _mk_order("FZ10", uid, status="refund_pending", refund_status="cooldown",
                  refund_requested_at=ANCHOR, refund_amount_fen=3000)
        _mk_code("O-FZ10", uid, grant_start=datetime(2126, 8, 1))

        out = scan_refund_followup(order_repo, event_repo, MockPaymentGateway(),
                                   code_repo=code_repo)
        db.commit()
        assert {"order_no": "FZ10", "action": "code_frozen"} in out
        assert _code_status("O-FZ10") == "frozen"
        assert _event_type_count("codes.frozen", "FZ10") == 1
        out2 = scan_refund_followup(order_repo, event_repo, MockPaymentGateway(),
                                    code_repo=code_repo)
        assert {"order_no": "FZ10", "action": "code_frozen"} not in out2
        assert _event_type_count("codes.frozen", "FZ10") == 1  # 重放不加账

    def test_scan_b_unfreezes_canceled(self, repos):
        """F-b：已取消回 fulfilled 的 frozen 行 → 补解冻+落账。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_k")
        _mk_order("FZ11", uid, status="fulfilled", refund_status="canceled",
                  refund_requested_at=ANCHOR, refund_amount_fen=3000)
        _mk_code("O-FZ11", uid, grant_start=datetime(2126, 8, 1))
        code_repo.freeze_for_order("FZ11")

        out = scan_refund_followup(order_repo, event_repo, MockPaymentGateway(),
                                   code_repo=code_repo)
        db.commit()
        assert {"order_no": "FZ11", "action": "code_unfrozen"} in out
        assert _code_status("O-FZ11") == "active"
        assert _event_type_count("codes.unfrozen", "FZ11") == 1

    def test_scan_b_does_not_touch_in_flight_or_refunded(self, repos):
        """F-b 只还原 fulfilled：在途单保持冻结；refunded 单归扫描 E 相位判定。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_l")
        _mk_order("FZ12", uid, status="refund_processing", refund_status="processing",
                  refund_requested_at=ANCHOR, refund_amount_fen=3000)
        _mk_code("O-FZ12", uid, grant_start=datetime(2126, 8, 1))
        _mk_order("FZ13", uid, status="refunded", refund_status="succeeded",
                  refund_requested_at=ANCHOR, refunded_at=ANCHOR,
                  refund_amount_fen=3000)
        _mk_code("O-FZ13", uid, grant_start=datetime(2026, 8, 1),
                 expires_at=datetime(2026, 9, 20))
        code_repo.freeze_for_order("FZ12")
        code_repo.freeze_for_order("FZ13")

        scan_refund_followup(order_repo, event_repo, MockPaymentGateway(),
                             code_repo=code_repo)
        db.commit()
        assert _code_status("O-FZ12") == "frozen"      # 在途：保持冻结
        assert _code_status("O-FZ13") == "active"      # refunded 已起算：扫描 E 恢复

    def test_scan_e_frozen_queued_revoked(self, repos):
        """扫描 E：refunded 单残留的 frozen 排队行 → 收回（含 :queued 事件）。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_m")
        _mk_order("FZ14", uid, status="refunded", refund_status="succeeded",
                  refund_requested_at=ANCHOR, refunded_at=ANCHOR,
                  refund_amount_fen=3000)
        _mk_code("O-FZ14", uid, grant_start=datetime(2126, 8, 1),
                 expires_at=datetime(2126, 8, 31))
        code_repo.freeze_for_order("FZ14")

        out = scan_refund_followup(order_repo, event_repo, MockPaymentGateway(),
                                   code_repo=code_repo)
        db.commit()
        assert {"order_no": "FZ14", "action": "queued_code_revoked"} in out
        assert _code_status("O-FZ14") == "revoked"
        assert _event_count("codes:O-FZ14:revoked:queued") == 1

    def test_scan_e_frozen_started_restored(self, repos):
        """扫描 E：refunded 单残留的 frozen 已起算行 → 恢复 active。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_n")
        _mk_order("FZ15", uid, status="refunded", refund_status="succeeded",
                  refund_requested_at=ANCHOR, refunded_at=ANCHOR,
                  refund_amount_fen=1500)
        _mk_code("O-FZ15", uid, grant_start=datetime(2026, 8, 1),
                 expires_at=datetime(2026, 9, 20))
        code_repo.freeze_for_order("FZ15")

        out = scan_refund_followup(order_repo, event_repo, MockPaymentGateway(),
                                   code_repo=code_repo)
        db.commit()
        assert {"order_no": "FZ15", "action": "frozen_code_restored"} in out
        assert _code_status("O-FZ15") == "active"

    def test_cooldown_submit_direct_success_keeps_frozen_path(self, repos):
        """受理即终态路径：cooldown_submit→complete_refund 对 frozen 行两相位生效。"""
        db, order_repo, event_repo, code_repo = repos
        uid = _mk_user("fz_o")
        cooldown_end = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        _mk_order("FZ16", uid, status="refund_pending", refund_status="cooldown",
                  refund_requested_at=ANCHOR, refund_amount_fen=3000,
                  cooldown_ends_at=cooldown_end)
        _mk_code("O-FZ16", uid, grant_start=datetime(2126, 8, 1))
        code_repo.freeze_for_order("FZ16")

        gw = MockPaymentGateway()
        gw.refunds["FZ16"] = {"status": RefundStatus.SUCCESS.value, "wx_refund_id": "wx9"}
        from app.application.payments.refund_flow import cooldown_submit
        cooldown_submit(order_repo, event_repo, gw,
                        order_repo.find_by_order_no("FZ16"), code_repo=code_repo)
        db.commit()
        assert _code_status("O-FZ16") == "revoked"


# ═══ pg_http 契约（CAS 条件构造与 sqlite 实现对拍）═══

class TestPgHttpFreezeContract:
    def _repo(self, requests: list):
        import httpx

        from app.infrastructure.repositories.pg_http.client import PgRestClient
        from app.infrastructure.repositories.pg_http.code_repo import PgHttpCodeRepo

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=[{
                "code_id": "O-PGF1", "tier": "pro", "duration_days": 30,
                "status": "frozen", "user_id": 1, "source": "order",
            }])
        client = PgRestClient("https://e.example", "k", transport=httpx.MockTransport(handler))
        return PgHttpCodeRepo(client)

    def test_freeze_cas_filter(self):
        import httpx
        requests: list[httpx.Request] = []
        repo = self._repo(requests)
        assert repo.freeze_for_order("PGF1") == 1
        p = requests[0].url.params
        assert p["code_id"] == "eq.O-PGF1"
        assert p["status"] == "eq.active"

    def test_unfreeze_cas_filter(self):
        import httpx
        requests: list[httpx.Request] = []
        repo = self._repo(requests)
        assert repo.unfreeze_for_order("PGF1") == 1
        p = requests[0].url.params
        assert p["code_id"] == "eq.O-PGF1"
        assert p["status"] == "eq.frozen"

    def test_find_frozen_filter(self):
        import httpx
        requests: list[httpx.Request] = []
        repo = self._repo(requests)
        assert len(repo.find_frozen()) == 1
        p = requests[0].url.params
        assert p["status"] == "eq.frozen"

    def test_find_refund_in_flight_filter(self):
        import httpx

        from app.infrastructure.repositories.payments_repo import OrderRepo
        from app.infrastructure.repositories.pg_http.client import PgRestClient
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=[])
        client = PgRestClient("https://e.example", "k", transport=httpx.MockTransport(handler))
        OrderRepo(client).find_refund_in_flight()
        assert requests[0].url.params["status"] == "in.(refund_pending,refund_processing)"
