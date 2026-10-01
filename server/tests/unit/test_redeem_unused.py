"""redeem_unused（s-code-redeem）CAS 语义单测：unused→active 一次性绑定。

双断言：首次兑换成功且归属/到期落行；重复兑换/订单族码（pending_activation）
零改写——并发双兑只成一次是 spec 钉死的行为。
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.infrastructure.repositories.sql.code_repo import SqlCodeRepo
from app.models.base import SessionLocal
from app.models.code import ActivationCodeORM
from app.models.user import UserORM

GRANT_START = datetime(2026, 10, 5, 0, 0, 0)
EXPIRES_AT = datetime(2026, 11, 4, 0, 0, 0)
ACTIVATED_AT = datetime(2026, 10, 1, 12, 0, 0)


@pytest.fixture(scope="module", autouse=True)
def _ensure_tables():
    from app.models.base import Base, engine
    Base.metadata.create_all(bind=engine)
    yield


def _mk_unused_code(code_id: str, status: str = "unused") -> None:
    db = SessionLocal()
    try:
        db.add(ActivationCodeORM(
            code_id=code_id, tier="pro", duration_days=30, status=status,
            created_by="admin",
        ))
        db.commit()
    finally:
        db.close()


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


def _row(code_id: str) -> ActivationCodeORM | None:
    db = SessionLocal()
    try:
        return db.query(ActivationCodeORM).filter(
            ActivationCodeORM.code_id == code_id).first()
    finally:
        db.close()


def test_first_redeem_binds_and_activates():
    uid = _mk_user("redeemer_a")
    _mk_unused_code("AC-R1")
    repo = SqlCodeRepo(SessionLocal())
    assert repo.redeem_unused("AC-R1", uid, GRANT_START, EXPIRES_AT, ACTIVATED_AT) is True
    row = _row("AC-R1")
    assert row.status == "active"
    assert row.user_id == uid
    assert row.grant_start == GRANT_START
    assert row.expires_at == EXPIRES_AT
    assert row.activated_at == ACTIVATED_AT


def test_second_redeem_is_rejected_without_rewrite():
    uid_a = _mk_user("redeemer_b")
    uid_b = _mk_user("redeemer_c")
    _mk_unused_code("AC-R2")
    repo = SqlCodeRepo(SessionLocal())
    assert repo.redeem_unused("AC-R2", uid_a, GRANT_START, EXPIRES_AT, ACTIVATED_AT) is True
    # 他人并发/重复兑换：False，归属与到期不被改写
    assert repo.redeem_unused("AC-R2", uid_b, GRANT_START, EXPIRES_AT, ACTIVATED_AT) is False
    row = _row("AC-R2")
    assert row.user_id == uid_a
    assert row.expires_at == EXPIRES_AT


def test_order_family_status_not_redeemable():
    uid = _mk_user("redeemer_d")
    _mk_unused_code("AC-R3", status="pending_activation")
    repo = SqlCodeRepo(SessionLocal())
    assert repo.redeem_unused("AC-R3", uid, GRANT_START, EXPIRES_AT, ACTIVATED_AT) is False
    assert _row("AC-R3").status == "pending_activation"
