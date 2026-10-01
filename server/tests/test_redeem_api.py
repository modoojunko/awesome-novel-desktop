"""兑换端点（s-code-redeem）API 测试：/api/pay/codes/redeem。

覆盖：未登录 4001、成功（含小写/空白归一化）、无效码统一文案（不泄露存在性）、
已被使用 4004。码行直灌 ORM 种子（不依赖 admin 发码端点）。
"""
from __future__ import annotations

import pytest

from app.models.base import SessionLocal
from app.models.code import ActivationCodeORM


def _auth(web_user: dict) -> dict:
    return {"Authorization": f"Bearer {web_user['token']}"}


def _seed_code(code_id: str, tier: str = "pro", duration_days: int = 30,
               status: str = "unused") -> None:
    s = SessionLocal()
    try:
        s.add(ActivationCodeORM(
            code_id=code_id, tier=tier, duration_days=duration_days,
            status=status, created_by="admin",
        ))
        s.commit()
    finally:
        s.close()


def _redeem(client, web_user: dict, code: str):
    return client.post("/api/pay/codes/redeem", headers=_auth(web_user),
                       json={"code": code})


def test_redeem_requires_login(client):
    r = client.post("/api/pay/codes/redeem", json={"code": "AC-AB12-CD34-EF56-AA00"})
    assert r.json()["code"] == 4001


def _mk_code_id(uid: str, tag: str = "0") -> str:
    """uid → 合法 AC-XXXX-XXXX-XXXX-XXXX（4 组、每组恰 4 位，tag 区分用例）。"""
    g1 = (uid[:4].upper() + "0000")[:4]
    g2 = (uid[4:8].upper() + "0000")[:4]
    return f"AC-{g1}-{g2}-{tag}X9Z-Q7Q7"


def test_redeem_success_normalized(client, web_user, uid):
    code_id = _mk_code_id(uid, "1")
    _seed_code(code_id)
    r = _redeem(client, web_user, f"  {code_id.lower()}  ")
    body = r.json()
    assert body["code"] == 0, body
    data = body["data"]
    assert data["code_id"] == code_id
    assert data["tier"] == "pro"
    # 起算与到期成对，间隔=码行天数（不锚绝对日期：新用户可能带 trial 顺延）
    from datetime import datetime
    gs = datetime.fromisoformat(data["grant_start"])
    ex = datetime.fromisoformat(data["expires_at"])
    assert (ex - gs).days == 30


def test_redeem_invalid_shape_and_missing_same_message(client, web_user):
    for bad in ("HELLO", "AC-ZZZZ-ZZZZ-ZZZZ-ZZZZ", ""):
        r = _redeem(client, web_user, bad)
        assert r.json() == {"code": 4004, "msg": "无效的激活码"}, bad


def test_redeem_used_code_rejected(client, web_user, uid):
    code_id = _mk_code_id(uid, "2")
    _seed_code(code_id)
    assert _redeem(client, web_user, code_id).json()["code"] == 0
    r = _redeem(client, web_user, code_id)
    assert r.json() == {"code": 4004, "msg": "激活码已被使用"}


@pytest.mark.parametrize("payload", [{"nope": 1}, {"code": 12345}])
def test_redeem_bad_payload_rejected(client, web_user, payload):
    r = client.post("/api/pay/codes/redeem", headers=_auth(web_user), json=payload)
    assert r.status_code in (400, 422)
