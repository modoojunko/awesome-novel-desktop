"""redeem_code（s-code-redeem）应用服务单测：真实 sqlite 仓直测。

覆盖：成功兑换＋留痕、顺延衔接、重复/他人已兑、形态不匹配/不存在统一无效、
归一化（小写＋空白）、0 天废码拒绝。
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.application.payments.redeem_code import redeem_code
from app.infrastructure.repositories.payments_repo import TradeEventRepo
from app.infrastructure.repositories.sql.code_repo import SqlCodeRepo
from app.models.base import SessionLocal
from app.models.code import ActivationCodeORM
from app.models.payments import TradeEventORM
from app.models.user import UserORM

TODAY = datetime(2026, 10, 1).date()


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


def _mk_code(code_id: str, duration_days: int = 30, tier: str = "pro",
             status: str = "unused", user_id=None, expires_at=None) -> None:
    db = SessionLocal()
    try:
        db.add(ActivationCodeORM(
            code_id=code_id, tier=tier, duration_days=duration_days,
            status=status, user_id=user_id, expires_at=expires_at,
            created_by="admin",
        ))
        db.commit()
    finally:
        db.close()


def _repos():
    db = SessionLocal()
    return SqlCodeRepo(db), TradeEventRepo(db), db


def _events(event_key: str) -> list[TradeEventORM]:
    db = SessionLocal()
    try:
        return db.query(TradeEventORM).filter_by(event_key=event_key).all()
    finally:
        db.close()


def test_redeem_success_writes_row_and_event():
    uid = _mk_user("rd_a")
    _mk_code("AC-AA00-0000-AAAA-X9X9", duration_days=30)
    repo, events, db = _repos()
    try:
        r = redeem_code(repo, events, " AC-aa00-0000-aaaa-x9x9 ", uid, today=TODAY)
        db.commit()  # 模拟请求域提交（服务层不 commit，与 activate_code 同约定）
    finally:
        db.close()
    assert r == {"code_id": "AC-AA00-0000-AAAA-X9X9", "tier": "pro",
                 "grant_start": "2026-10-01T00:00:00",
                 "expires_at": "2026-10-31T00:00:00"}
    ev = _events("codes:AC-AA00-0000-AAAA-X9X9:redeemed")
    assert len(ev) == 1
    assert ev[0].event_type == "codes.redeemed"
    assert ev[0].payload["tier"] == "pro"
    assert ev[0].payload["source"] == "redeem"


def test_redeem_defers_after_existing_active_row():
    uid = _mk_user("rd_b")
    _mk_code("AC-BB00-0000-BBBB-X9X9", duration_days=30)
    _mk_code("AC-OLD0-0000-OLDD-X9X9", duration_days=365, status="active", user_id=uid,
             expires_at=datetime(2027, 1, 10, 0, 0, 0))
    repo, events, db = _repos()
    try:
        r = redeem_code(repo, events, "AC-BB00-0000-BBBB-X9X9", uid, today=TODAY)
        db.commit()
    finally:
        db.close()
    assert r["grant_start"] == "2027-01-10T00:00:00"
    assert r["expires_at"] == "2027-02-09T00:00:00"


def test_redeem_twice_second_rejected_single_event():
    uid = _mk_user("rd_c")
    _mk_code("AC-CC00-0000-CCCC-X9X9")
    repo, events, db = _repos()
    try:
        assert redeem_code(repo, events, "AC-CC00-0000-CCCC-X9X9", uid, today=TODAY)["code_id"]
        assert redeem_code(repo, events, "AC-CC00-0000-CCCC-X9X9", uid, today=TODAY) == {
            "error": "already_used"}
        db.commit()
    finally:
        db.close()
    assert len(_events("codes:AC-CC00-0000-CCCC-X9X9:redeemed")) == 1


def test_redeem_by_other_user_after_bound_rejected():
    uid_a = _mk_user("rd_d")
    uid_b = _mk_user("rd_e")
    _mk_code("AC-DD00-0000-DDDD-X9X9")
    repo, events, db = _repos()
    try:
        assert redeem_code(repo, events, "AC-DD00-0000-DDDD-X9X9", uid_a, today=TODAY)["code_id"]
        assert redeem_code(repo, events, "AC-DD00-0000-DDDD-X9X9", uid_b, today=TODAY) == {
            "error": "already_used"}
        db.commit()
    finally:
        db.close()


def test_invalid_shape_and_missing_code_same_error():
    uid = _mk_user("rd_f")
    repo, events, db = _repos()
    try:
        assert redeem_code(repo, events, "HELLO", uid) == {"error": "invalid_code"}
        assert redeem_code(repo, events, "AC-AB12-CD34-EF56", uid) == {"error": "invalid_code"}  # 3 组旧形态拒
        assert redeem_code(repo, events, "AC-ZZZZ-ZZZZ-ZZZZ", uid) == {"error": "invalid_code"}
        assert redeem_code(repo, events, "", uid) == {"error": "invalid_code"}
    finally:
        db.close()


def test_zero_duration_legacy_code_rejected():
    uid = _mk_user("rd_g")
    _mk_code("AC-EE00-0000-EEEE-X9X9", duration_days=0)
    repo, events, db = _repos()
    try:
        assert redeem_code(repo, events, "AC-EE00-0000-EEEE-X9X9", uid, today=TODAY) == {
            "error": "invalid_code"}
    finally:
        db.close()
