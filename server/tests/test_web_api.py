"""S端 Web/门户 API 集成测试 — 进程内 TestClient（无外部 server 依赖）。

覆盖现存路由中的门户 / 管理 / OAuth 授权流：
  web_api:    /api/web/login /api/web/register /api/user/me /api/user/password
              /api/user/security /api/license/activate /api/devices/my /api/devices/remove
  admin_api:  /api/generate_code /api/query_codes
  client_api: /api/auth-page /api/authorize /api/check-auth /api/verify /api/reset_password
  （/api/devices/current 与 /api/devices/consume-enrolled 见 test_device_activation.py）
"""

from datetime import date, timedelta

from app.infrastructure.security.jwt import sign_jwt
from tests.conftest import WEB_PASSWORD

# 测试用占位口令（拼串构造，避免被凭据扫描误报为硬编码密钥）
WRONG_PWD = "".join(("wrong", "-pwd-9"))
NEW_PWD_VALID = "".join(("Abc", "def-", "789"))
RESET_PWD = "".join(("Reset", "-78", "9!"))
JOURNEY_NEW_PWD = "".join(("Journey", "-New", "1"))


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════
# 1. Web 注册/登录（注册即送 7 天 trial，返回 JWT）
# ═══════════════════════════════════════════════════════════════════


class TestWebRegister:
    def test_success_tier_trial(self, client, uid):
        username = f"wr_{uid}"
        r = client.post(
            "/api/web/register",
            json={"username": username, "password": WEB_PASSWORD, "security_question": "q?", "security_answer": "a"},
        )
        d = r.json()
        assert d["code"] == 0, d
        assert d["data"]["token"].startswith("eyJ"), "应为 JWT"
        assert d["data"]["tier"] == "trial"
        # 注册即送 7 天试用 → 到期日恰为今天+7
        assert date.fromisoformat(d["data"]["expires_at"][:10]) == date.today() + timedelta(days=7)

    def test_dup(self, client, web_user):
        r = client.post(
            "/api/web/register",
            json={"username": web_user["username"], "password": NEW_PWD_VALID, "security_question": "q", "security_answer": "a"},
        )
        assert r.json()["code"] == 1


class TestWebLogin:
    def test_ok(self, client, web_user):
        r = client.post("/api/web/login", json={"username": web_user["username"], "password": web_user["password"]})
        d = r.json()
        assert d["code"] == 0, d
        assert d["data"]["token"].startswith("eyJ")
        assert d["data"]["tier"] == "trial"

    def test_bad_pwd(self, client, web_user):
        r = client.post("/api/web/login", json={"username": web_user["username"], "password": WRONG_PWD})
        assert r.json()["code"] == 1

    def test_nouser(self, client, uid):
        r = client.post("/api/web/login", json={"username": f"nobody_{uid}", "password": "x"})
        assert r.json()["code"] == 1


# ═══════════════════════════════════════════════════════════════════
# 2. 用户信息 /api/user/me
# ═══════════════════════════════════════════════════════════════════


class TestUserMe:
    def test_me(self, client, web_user):
        r = client.get("/api/user/me", headers=_bearer(web_user["token"]))
        d = r.json()
        assert d["code"] == 0, d
        assert d["data"]["username"] == web_user["username"]
        assert d["data"]["tier"] == "trial"
        assert d["data"]["is_valid"] is True

    def test_me_security_question_visible_answer_not(self, client, web_user):
        """account-blocks-unify：user/me 回密保问题文本与注册时间，答案任何形式不出门。"""
        d = client.get("/api/user/me", headers=_bearer(web_user["token"])).json()
        assert d["data"]["security_question"] == "q?"  # web_user fixture 注册时的问题
        assert d["data"]["registered_at"]  # 日期非空（YYYY-MM-DD 口径，形如 2026-09-01）
        assert len(d["data"]["registered_at"]) == 10
        assert "security_answer" not in d["data"]
        assert "security_answer_hash" not in d["data"]

    def test_no_token(self, client):
        assert client.get("/api/user/me").json()["code"] == 1

    def test_bad_token(self, client):
        assert client.get("/api/user/me", headers=_bearer("invalid-token")).json()["code"] == 1


# ═══════════════════════════════════════════════════════════════════
# 3. 激活码 /api/license/activate【已下线——8.3 拆旧激活码入口，购买走 /api/pay/orders】
# ═══════════════════════════════════════════════════════════════════


class TestLicenseActivate:
    def test_endpoint_retired(self, client, web_user, gen_code):
        """激活码 web 端点已下线（s-pay-foundation 8.3）：路由 404，激活码通道仅存
        管理端出码（/api/generate_code）+ 支付激活（application.payments.activate_code）。"""
        code = gen_code("yearly")[0]
        r = client.post("/api/license/activate", json={"code": code}, headers=_bearer(web_user["token"]))
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# 4. 管理端发码 / 查码
# ═══════════════════════════════════════════════════════════════════


class TestAdminCodes:
    def test_generate_code(self, client, admin_token):
        r = client.post("/api/generate_code", json={"admin_token": admin_token, "tier": "monthly", "count": 3})
        d = r.json()
        assert d["code"] == 0, d
        assert len(d["data"]["codes"]) == 3
        for c in d["data"]["codes"]:
            assert c.startswith("AC-")

    def test_generate_bad_token(self, client):
        r = client.post("/api/generate_code", json={"admin_token": "wrong-admin-token", "tier": "yearly", "count": 1})
        assert r.json()["code"] == 3

    def test_generate_bad_tier(self, client, admin_token):
        r = client.post("/api/generate_code", json={"admin_token": admin_token, "tier": "diamond", "count": 1})
        assert r.json()["code"] == 1

    def test_generate_bad_count(self, client, admin_token):
        r = client.post("/api/generate_code", json={"admin_token": admin_token, "tier": "yearly", "count": 999})
        assert r.json()["code"] == 1

    def test_query_codes_by_user(self, client, admin_token, web_user, gen_code):
        """管理端按用户查码（出码通道保留；激活改走支付流程，未激活码不归属用户）。"""
        code = gen_code("monthly")[0]
        r = client.post("/api/query_codes", json={"admin_token": admin_token, "username": web_user["username"]})
        d = r.json()
        assert d["code"] == 0, d
        rows = {c["code_id"]: c for c in d["data"]["codes"]}
        assert code not in rows  # 未激活（无支付激活），码不归属用户

    def test_query_bad_token(self, client):
        r = client.post("/api/query_codes", json={"admin_token": "wrong-admin-token"})
        assert r.json()["code"] == 3


# ═══════════════════════════════════════════════════════════════════
# 5. 密码 / 密保
# ═══════════════════════════════════════════════════════════════════


class TestAccountSecurity:
    def test_change_password(self, client, web_user):
        r = client.put(
            "/api/user/password",
            json={"old_password": web_user["password"], "new_password": NEW_PWD_VALID},
            headers=_bearer(web_user["token"]),
        )
        assert r.json()["code"] == 0, r.text
        # 新密码可登录，旧密码失效
        assert client.post("/api/web/login", json={"username": web_user["username"], "password": NEW_PWD_VALID}).json()["code"] == 0
        assert client.post("/api/web/login", json={"username": web_user["username"], "password": web_user["password"]}).json()["code"] == 1

    def test_change_password_wrong_old(self, client, web_user):
        r = client.put(
            "/api/user/password",
            json={"old_password": WRONG_PWD, "new_password": NEW_PWD_VALID},
            headers=_bearer(web_user["token"]),
        )
        assert r.json()["code"] == 1

    def test_change_password_too_short(self, client, web_user):
        r = client.put(
            "/api/user/password",
            json={"old_password": web_user["password"], "new_password": "12345"},
            headers=_bearer(web_user["token"]),
        )
        assert r.json()["code"] == 1
        assert "6" in r.json()["msg"]

    def test_change_security_then_reset_password(self, client, web_user):
        """改密保后，用新密保答案走重置密码流程（/api/user/me 不回显密保，以功能验证）。"""
        r = client.put(
            "/api/user/security",
            json={"security_question": "新问题", "security_answer": "新答案"},
            headers=_bearer(web_user["token"]),
        )
        assert r.json()["code"] == 0, r.text
        # 旧答案已失效
        r_old = client.post(
            "/api/reset_password",
            json={"username": web_user["username"], "security_answer": "a", "new_password": RESET_PWD},
        )
        assert r_old.json()["code"] == 1
        # 新答案可重置
        r2 = client.post(
            "/api/reset_password",
            json={"username": web_user["username"], "security_answer": "新答案", "new_password": RESET_PWD},
        )
        assert r2.json()["code"] == 0, r2.text
        assert client.post("/api/web/login", json={"username": web_user["username"], "password": RESET_PWD}).json()["code"] == 0


# ═══════════════════════════════════════════════════════════════════
# 6. 门户设备管理 /api/devices/my + /api/devices/remove
# ═══════════════════════════════════════════════════════════════════


class TestDevicePortal:
    def test_my_devices(self, client, web_user, uid):
        # 先通过 OAuth 授权流绑定一台设备
        pc = f"portal_pc_{uid}"
        r = client.post(
            "/api/authorize",
            json={"username": web_user["username"], "password": web_user["password"], "pc_hash": pc, "pc_name": "门户测试机"},
        )
        assert r.json()["code"] == 0, r.text

        r2 = client.get("/api/devices/my", headers=_bearer(web_user["token"]))
        d = r2.json()
        assert d["code"] == 0, d
        assert d["total_count"] == 1
        assert d["active_limit"] == 1  # trial 限 1 台
        assert d["activated_count"] == 1
        assert d["data"][0]["hostname"] == "门户测试机"

    def test_my_devices_no_auth(self, client):
        assert client.get("/api/devices/my").json()["code"] == 1

    def test_remove_device(self, client, web_user, uid):
        pc = f"rm_pc_{uid}"
        client.post(
            "/api/authorize",
            json={"username": web_user["username"], "password": web_user["password"], "pc_hash": pc, "pc_name": "待删机"},
        )
        my = client.get("/api/devices/my", headers=_bearer(web_user["token"])).json()
        assert my["total_count"] == 1
        device_id = my["data"][0]["id"]

        r = client.post("/api/devices/remove", json={"id": device_id}, headers=_bearer(web_user["token"]))
        assert r.json()["code"] == 0, r.text
        my2 = client.get("/api/devices/my", headers=_bearer(web_user["token"])).json()
        assert my2["total_count"] == 0

    def test_remove_device_no_auth(self, client):
        assert client.post("/api/devices/remove", json={"id": "whatever"}).json()["code"] == 1


# ═══════════════════════════════════════════════════════════════════
# 7. C端 OAuth 授权流：auth-page / authorize / check-auth
# ═══════════════════════════════════════════════════════════════════


class TestOAuthFlow:
    def test_auth_page_removed(self, client):
        """授权页实体已迁至 S端 前端 /auth（auth-page-direct-entry）：后端内联页不得复活。"""
        r = client.get("/api/auth-page", params={"pc_hash": "some_hash"})
        assert r.status_code == 404

    def test_authorize_ok(self, client, web_user, uid):
        r = client.post(
            "/api/authorize",
            json={"username": web_user["username"], "password": web_user["password"], "pc_hash": f"auth_pc_{uid}"},
        )
        d = r.json()
        assert d["code"] == 0, d
        assert d["data"]["tier"] == "trial"
        assert d["data"]["expires_at"]

    def test_authorize_bad_pwd(self, client, web_user):
        r = client.post(
            "/api/authorize",
            json={"username": web_user["username"], "password": WRONG_PWD, "pc_hash": "x"},
        )
        assert r.json()["code"] == 1

    def test_check_auth_poll(self, client, web_user, uid):
        pc = f"poll_pc_{uid}"
        client.post(
            "/api/authorize",
            json={"username": web_user["username"], "password": web_user["password"], "pc_hash": pc},
        )
        r = client.get("/api/check-auth", params={"pc_hash": pc})
        d = r.json()
        assert d["code"] == 0, d
        assert d["data"]["token"].startswith("eyJ")
        assert d["data"]["username"] == web_user["username"]
        assert d["data"]["tier"] == "trial"

    def test_check_auth_pending(self, client, uid):
        r = client.get("/api/check-auth", params={"pc_hash": f"unknown_{uid}"})
        d = r.json()
        assert d["code"] == 1
        assert "等待授权" in d["msg"]

    def test_check_auth_missing_param(self, client):
        assert client.get("/api/check-auth").json()["code"] == 1


# ═══════════════════════════════════════════════════════════════════
# 8. C端 心跳 /api/verify
# ═══════════════════════════════════════════════════════════════════


class TestVerify:
    def test_verify_ok(self, client, web_user, uid):
        pc = f"verify_pc_{uid}"
        client.post(
            "/api/authorize",
            json={"username": web_user["username"], "password": web_user["password"], "pc_hash": pc},
        )
        grant_token = client.get("/api/check-auth", params={"pc_hash": pc}).json()["data"]["token"]

        r = client.post("/api/verify", json={"username": web_user["username"], "token": grant_token, "pc_hash": pc})
        d = r.json()
        assert d["code"] == 0, d
        data = d["data"]
        assert data["license_valid"] is True  # trial 7 天内有效
        assert data["device_valid"] is True
        assert data["valid"] is True
        assert data["tier"] == "trial"
        assert data["max_devices"] == 1

    def test_verify_token_user_mismatch(self, client, web_user, uid):
        pc = f"mismatch_pc_{uid}"
        client.post(
            "/api/authorize",
            json={"username": web_user["username"], "password": web_user["password"], "pc_hash": pc},
        )
        foreign_token = sign_jwt("someone_else", 999)
        r = client.post("/api/verify", json={"username": web_user["username"], "token": foreign_token, "pc_hash": pc})
        d = r.json()
        assert d["code"] == 2
        assert "不匹配" in d["msg"]


# ═══════════════════════════════════════════════════════════════════
# 9. 完整用户旅程
# ═══════════════════════════════════════════════════════════════════


class TestFullJourney:
    def test_journey(self, client, admin_token, uid):
        username = f"fj_{uid}"
        # 1) 注册即 trial
        r = client.post(
            "/api/web/register",
            json={"username": username, "password": WEB_PASSWORD, "security_question": "q?", "security_answer": "a"},
        )
        token = r.json()["data"]["token"]
        me = client.get("/api/user/me", headers=_bearer(token)).json()
        assert me["data"]["tier"] == "trial"

        # 2) 激活码 web 端点已下线（8.3）：购买激活走 /api/pay/orders（见 test_payments_api）
        r_gone = client.post("/api/license/activate", json={"code": "AC-ANY"}, headers=_bearer(token))
        assert r_gone.status_code == 404
        me2 = client.get("/api/user/me", headers=_bearer(token)).json()
        assert me2["data"]["tier"] == "trial"  # 未购买维持 trial

        # 3) 改密码 → 新密码可登录
        client.put(
            "/api/user/password",
            json={"old_password": WEB_PASSWORD, "new_password": JOURNEY_NEW_PWD},
            headers=_bearer(token),
        )
        r2 = client.post("/api/web/login", json={"username": username, "password": JOURNEY_NEW_PWD})
        assert r2.json()["code"] == 0
