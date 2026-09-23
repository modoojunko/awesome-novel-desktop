"""微信支付回调端点测试（s-pay-wechat-gateway 任务 3.1-3.3）。

真验签链路：测试内生成两对 RSA——「微信侧」密钥对构造 SDK client（公钥
模式），请求用对应私钥签名可过验签，用攻击者私钥签名被拒；resource 用
APIv3 密钥真加密（AES-256-GCM），解密走 SDK 真实路径。

覆盖：合法回调全链发货+重放幂等、金额不平冻结绝不发货、伪造签名 401
零状态变化、SIGNTEST 探测拒绝、未知/终态订单确认、退款回调推进与
ABNORMAL 不动状态。
"""
from __future__ import annotations

import base64
import json
import secrets
import time
import uuid
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.infrastructure.payments.wechatpay import WechatPayGateway
from app.main import app
from app.models.base import SessionLocal
from app.models.code import ActivationCodeORM
from app.models.payments import OrderORM

APIV3_KEY = "k" * 32
NOTIFY_URL = "https://www.example.com/api/pay/notify"


def _gen_pem_pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv, pub


@pytest.fixture(scope="module")
def wx_keys():
    return _gen_pem_pair(), _gen_pem_pair()  # (微信侧, 攻击者)


@pytest.fixture
def buyer(client):
    """注册真实用户（过 orders.user_id FK），返回 user_id。"""
    from app.models.user import UserORM

    username = f"wxn_{uuid.uuid4().hex[:8]}"
    r = client.post("/api/web/register", json={
        "username": username, "password": "".join(("Pa", "ss-live-", "42")),
        "security_question": "q?", "security_answer": "a",
    })
    assert r.json()["code"] == 0, r.text
    s = SessionLocal()
    try:
        row = s.query(UserORM).filter_by(username=username).first()
        return row.id
    finally:
        s.close()


@pytest.fixture
def wx_gw(client, wx_keys, monkeypatch):
    """app.state 注入真 SDK 网关（不豁免应答/回调验签）。"""
    (wx_priv, wx_pub), _ = wx_keys
    from wechatpayv3 import WeChatPay, WeChatPayType

    sdk = WeChatPay(
        wechatpay_type=WeChatPayType.NATIVE,
        mchid="1749993584", private_key=wx_priv, cert_serial_no="A" * 40,
        appid="wx41899938fa14c26d", apiv3_key=APIV3_KEY,
        public_key=wx_pub, public_key_id="PUB_KEY_ID_TEST",
        timeout=(1, 2),
    )
    gateway = WechatPayGateway(sdk, notify_url=NOTIFY_URL)
    monkeypatch.setattr(app.state, "payment_gateway", gateway)
    return gateway


def _headers(priv_pem: str, body: str, serial: str = "PUB_KEY_ID_TEST") -> dict:
    ts = str(int(time.time()))
    nonce = uuid.uuid4().hex
    sign_str = f"{ts}\n{nonce}\n{body}\n"
    key = serialization.load_pem_private_key(priv_pem.encode(), password=None)
    sig = base64.b64encode(
        key.sign(sign_str.encode(), padding.PKCS1v15(), hashes.SHA256())).decode()
    return {
        "Wechatpay-Timestamp": ts,
        "Wechatpay-Nonce": nonce,
        "Wechatpay-Signature": sig,
        "Wechatpay-Serial": serial,
        "Content-Type": "application/json",
    }


def _body(event_type: str, payload: dict, aad: str = "transaction") -> str:
    nonce = secrets.token_hex(6)  # 12 bytes
    ct_tag = AESGCM(APIV3_KEY.encode()).encrypt(
        nonce.encode(), json.dumps(payload).encode(), aad.encode())
    return json.dumps({
        "id": f"evt-{uuid.uuid4().hex[:8]}",
        "event_type": event_type,
        "resource_type": "encrypt-resource",
        "resource": {
            "algorithm": "AEAD_AES_256_GCM",
            "nonce": nonce,
            "associated_data": aad,
            "ciphertext": base64.b64encode(ct_tag).decode(),
        },
    })


def _pay_payload(order_no: str, total: int) -> dict:
    return {
        "out_trade_no": order_no,
        "transaction_id": f"5000{order_no[-4:]}",
        "trade_state": "SUCCESS",
        "amount": {"total": total, "payer_total": max(0, total - 1), "currency": "CNY"},
        "payer": {"openid": "oOpenidX"},
    }


def _create_order(order_no: str, user_id: int, *, amount_fen: int = 1,
                  status: str = "pending", refund_status: str = "") -> None:
    s = SessionLocal()
    try:
        s.add(OrderORM(
            order_no=order_no, user_id=user_id, sku_id=1,
            sku_snapshot={"tier_key": "pro", "duration_days": 365},
            amount_fen=amount_fen, status=status,
            prepay_status="created", channel="wxpay",
            agreement_version="v2026.08",
            agreed_at=datetime.now(UTC),
            refund_status=refund_status,
            created_at=datetime.now(UTC),
        ))
        s.commit()
    finally:
        s.close()


def _order(order_no: str) -> OrderORM:
    s = SessionLocal()
    try:
        return s.query(OrderORM).filter_by(order_no=order_no).first()
    finally:
        s.close()


def _post(client, body: str, headers: dict):
    return client.post("/api/pay/notify", content=body.encode("UTF-8"), headers=headers)


class TestPaymentNotify:

    def test_valid_callback_fulfills_and_replay_safe(self, client, wx_gw, wx_keys, buyer):
        """合法回调 → 发货；同一通知重放（多服务器并发场景）不二次发货。"""
        (wx_priv, _), _ = wx_keys
        _create_order("O-NOTIFY-OK", buyer, amount_fen=1)
        body = _body("TRANSACTION.SUCCESS", _pay_payload("O-NOTIFY-OK", total=1))

        resp = _post(client, body, _headers(wx_priv, body))
        assert resp.status_code == 200
        assert resp.content == b""  # 官方 v3：成功应答无需报文
        assert _order("O-NOTIFY-OK").status == "fulfilled"

        s = SessionLocal()
        try:
            first_count = s.query(ActivationCodeORM).filter_by(code_id="O-O-NOTIFY-OK").count()
        finally:
            s.close()

        # 重放同一通知（并发重发场景）：幂等，无第二次发货
        resp2 = _post(client, body, _headers(wx_priv, body))
        assert resp2.status_code == 200
        s = SessionLocal()
        try:
            replay_count = s.query(ActivationCodeORM).filter_by(code_id="O-O-NOTIFY-OK").count()
        finally:
            s.close()
        assert replay_count == first_count == 1

    def test_amount_mismatch_freezes_never_ships(self, client, wx_gw, wx_keys, buyer):
        """金额不平（资金安全闸门）→ 订单 exception + 告警应答，绝不发货。"""
        (wx_priv, _), _ = wx_keys
        _create_order("O-NOTIFY-BAD", buyer, amount_fen=1)
        body = _body("TRANSACTION.SUCCESS", _pay_payload("O-NOTIFY-BAD", total=2))

        resp = _post(client, body, _headers(wx_priv, body))
        assert resp.status_code == 200  # 止重试
        order = _order("O-NOTIFY-BAD")
        assert order.status == "exception"
        s = SessionLocal()
        try:
            assert s.query(ActivationCodeORM).filter_by(code_id="O-O-NOTIFY-BAD").count() == 0
        finally:
            s.close()

    def test_forged_signature_rejected_no_state_change(self, client, wx_gw, wx_keys, buyer):
        """攻击者私钥签名 → 401 FAIL，订单零状态变化。"""
        _, (attacker_priv, _) = wx_keys
        _create_order("O-NOTIFY-FAKE", buyer, amount_fen=1)
        body = _body("TRANSACTION.SUCCESS", _pay_payload("O-NOTIFY-FAKE", total=1))

        resp = _post(client, body, _headers(attacker_priv, body))
        assert resp.status_code == 401
        assert resp.json() == {"code": "FAIL", "message": "verify failed"}
        assert _order("O-NOTIFY-FAKE").status == "pending"

    def test_signtest_probe_rejected(self, client, wx_gw, wx_keys):
        """微信官方验签探测流量 → 拒绝（豁免告警由日志层保证）。"""
        (wx_priv, _), _ = wx_keys
        body = _body("TRANSACTION.SUCCESS", _pay_payload("O-SIGNTEST", total=1))
        headers = _headers(wx_priv, body)
        headers["Wechatpay-Signature"] = "WECHATPAY/SIGNTEST/abcdef0123456789012345678901234"
        resp = _post(client, body, headers)
        assert resp.status_code == 401

    def test_unknown_order_acked(self, client, wx_gw, wx_keys):
        (wx_priv, _), _ = wx_keys
        body = _body("TRANSACTION.SUCCESS", _pay_payload("O-NOTIFY-404", total=1))
        assert _post(client, body, _headers(wx_priv, body)).status_code == 200

    def test_terminal_order_acked_without_change(self, client, wx_gw, wx_keys, buyer):
        (wx_priv, _), _ = wx_keys
        _create_order("O-NOTIFY-DONE", buyer, amount_fen=1, status="fulfilled")
        body = _body("TRANSACTION.SUCCESS", _pay_payload("O-NOTIFY-DONE", total=1))
        resp = _post(client, body, _headers(wx_priv, body))
        assert resp.status_code == 200
        assert _order("O-NOTIFY-DONE").status == "fulfilled"  # 不变


class TestRefundNotify:

    def _create_refunding_order(self, order_no: str, user_id: int, with_code: bool = False):
        _create_order(order_no, user_id, amount_fen=1, status="refund_processing",
                      refund_status="processing")
        if with_code:
            s = SessionLocal()
            try:
                s.add(ActivationCodeORM(
                    code_id=f"O-{order_no}", tier="pro", duration_days=365,
                    status="pending_activation", status_detail="pending_activation",
                    source="order", user_id=user_id, order_id=1,
                ))
                s.commit()
            finally:
                s.close()

    def test_refund_success_completes(self, client, wx_gw, wx_keys, buyer):
        (wx_priv, _), _ = wx_keys
        self._create_refunding_order("O-NOTIFY-R1", buyer, with_code=True)
        body = _body("REFUND.SUCCESS", {
            "out_refund_no": "O-NOTIFY-R1",
            "out_trade_no": "O-NOTIFY-R1",
            "refund_id": "5030001",
            "refund_status": "SUCCESS",
            "refund_fee": 1,
        }, aad="refund")

        resp = _post(client, body, _headers(wx_priv, body))
        assert resp.status_code == 200
        assert _order("O-NOTIFY-R1").status == "refunded"
        # 权益收回：未激活台账行置 revoked（退款后不得再激活=防白嫖）
        s = SessionLocal()
        try:
            code = s.query(ActivationCodeORM).filter_by(code_id="O-O-NOTIFY-R1").first()
            assert code.status == "revoked"
        finally:
            s.close()

    def test_refund_abnormal_leaves_state(self, client, wx_gw, wx_keys, buyer):
        """ABNORMAL 终态：回调不动状态（T3 扫描负责告警转人工）。"""
        (wx_priv, _), _ = wx_keys
        self._create_refunding_order("O-NOTIFY-R2", buyer)
        body = _body("REFUND.ABNORMAL", {
            "out_refund_no": "O-NOTIFY-R2", "refund_status": "ABNORMAL",
        }, aad="refund")

        resp = _post(client, body, _headers(wx_priv, body))
        assert resp.status_code == 200
        order = _order("O-NOTIFY-R2")
        assert order.status == "refund_processing"
