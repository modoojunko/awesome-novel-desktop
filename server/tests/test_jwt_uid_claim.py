"""jwt-uid-claim 契约测试：token 携带 uid、业务端点零身份翻译、旧格式 token 迁移。"""
from __future__ import annotations

import pytest

from app.infrastructure.security.jwt import sign_jwt

AGREEMENT_VERSION = "v2026.08"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestUidClaimEnforcement:
    """严格口径：业务端点三态（无令牌 4001 壳 / 旧格式真 401 / 新 token 正常）。"""

    def test_no_token_returns_4001_shell(self, client):
        """未登录：4001 业务壳（s-payments 既定口径不变，HTTP 200）。"""
        r = client.get("/api/pay/orders")
        assert r.status_code == 200
        assert r.json() == {"code": 4001, "msg": "未登录"}

    def test_garbage_token_returns_4001_shell(self, client):
        """签名无效令牌：与未登录同口径（4001 壳）。"""
        r = client.get("/api/pay/orders", headers=_auth("Bearer garbage.token.here"))
        assert r.status_code == 200
        assert r.json()["code"] == 4001

    @pytest.mark.parametrize("uid", [None, "7", True, 1.5])
    def test_old_or_illegal_uid_token_returns_http_401(self, client, web_user, uid):
        """签名有效但缺/非法 uid（旧格式/伪造变体）→ 真 401，前端拦截自动登出。"""
        from jose import jwt as jose_jwt

        from app.config import settings

        payload = {
            "sub": web_user["username"],
            "username": web_user["username"],
            "exp": 4102444800,
        }
        if uid is not None:
            payload["uid"] = uid
        old_token = jose_jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        r = client.get("/api/pay/orders", headers=_auth(old_token))
        assert r.status_code == 401

    def test_uid_authoritative_over_username(self, client, web_user):
        """uid 为权威身份：sub 与 uid 指向不同用户时，数据按 uid 归属。"""
        r = client.get(
            "/api/pay/orders",
            headers=_auth(sign_jwt("someone_else", 999999)),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        # uid=999999 名下无订单：看不到 web_user 的数据（也不报"用户不存在"）
        assert body["data"]["total"] == 0


class TestLenientDependencyUnaffected:
    """宽松依赖（get_current_user_or_none）对无 uid 的旧格式 token 保持放行。"""

    def test_user_me_with_old_format_token(self, client, web_user):
        """/api/user/me 走宽松依赖：旧格式 token 不因缺 uid 被拒。"""
        from jose import jwt as jose_jwt

        from app.config import settings

        old_token = jose_jwt.encode(
            {"sub": web_user["username"], "username": web_user["username"], "exp": 4102444800},
            settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
        )
        r = client.get("/api/user/me", headers=_auth(old_token))
        assert r.status_code == 200
        assert r.json()["code"] == 0


class TestRegisteredTokenCarriesUid:
    """签发链路：注册/登录返回的 token 携带 uid，业务请求零翻译正常工作。"""

    def test_register_token_works_on_orders(self, client, web_user):
        r = client.get("/api/pay/orders", headers=_auth(web_user["token"]))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"] == {"items": [], "total": 0}

    def test_login_token_works_on_license(self, client, web_user):
        r = client.post(
            "/api/web/login",
            json={"username": web_user["username"], "password": web_user["password"]},
        )
        assert r.json()["code"] == 0
        token = r.json()["data"]["token"]
        r = client.get("/api/pay/license", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["code"] == 0
        # 2026-10-03 起行计数含激活码兑换来源：注册即送 trial（已激活非 unused）计入 → 1
        assert r.json()["data"]["code_count"] == 1
