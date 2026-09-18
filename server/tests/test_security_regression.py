"""S端 安全回归（s-security-hardening）：把审计复现的利用链钉成用例，先红后绿。

链 1：PostgREST 过滤器注入——未登录以操作符形似的 pc_hash 轮询 check-auth 取得他人令牌。
链 2：PostgREST 过滤器注入——reset_password 的 username 注入读一行、写多行（批量改密）。

pg_http 侧用 httpx.MockTransport 断言**出站过滤器形态**（本审计同款手法：把"值被当指令"
变成可断言的红绿），端到端用 TestClient + 替换 pg 客户端单例。
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import httpx

from app.infrastructure.repositories.pg_http.client import PgRestClient
from app.infrastructure.repositories.pg_http.user_repo import PgHttpUserRepo
from app.infrastructure.security.password import hash_password

ENDPOINT = "https://env.api.tcloudbasegateway.com/v1/rdb/rest"
VICTIM = "victim"
VICTIM_ID = 7
VICTIM_ANSWER = "a"

# 以操作符 token 开头 / 含过滤器语法字符的注入载荷（形态与审计复现一致）
INJECT_NEQ = "neq.anything"
INJECT_IN = 'in.("me","victim")'


def _requests_of(handler_calls: list[tuple[str, str]], table: str) -> list[str]:
    return [url for method, url in handler_calls if f"/{table}" in url]


def _eq_matches(param_value: str, actual: str) -> bool:
    """最小 PostgREST 语义模拟：`eq.<v>` 只匹配字面相等；操作符形态（neq./in./...）跨行匹配。

    桩必须模拟过滤语义，否则"修复后应查无此设备"无法验证（无过滤的桩会恒返回该行）。
    """
    if param_value.startswith("eq."):
        return param_value[3:] == actual
    return True  # 旧实现把操作符原样透传 → 跨行命中（漏洞语义）


# ══════════════════════════════════════════════════════════════════
# 链 1：check-auth 不得因过滤器注入泄露他人令牌
# ══════════════════════════════════════════════════════════════════

class TestCheckAuthFilterInjection:
    """未登录请求 `GET /api/check-auth?pc_hash=<操作符形似值>`。

    修复前：出站过滤器为 `pc_hash=neq.anything`（匹配一切非该值的行）→ 命中他人 grant 行
    → 端点把该行 token 原样返回（=未登录全站账号接管）。
    修复后：出站过滤器为 `pc_hash=eq.neq.anything`（字面等值）→ 查无此设备 → 等待授权。
    """

    def _pg_mock(self, calls: list[tuple[str, str]]) -> PgRestClient:
        """按表分发的 PostgREST 替身：device_grants 命中一条他人记录，其余返回最小可跑数据。"""

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, unquote(str(request.url))))
            path, params = request.url.path, request.url.params
            if path.endswith("/device_grants"):
                if not _eq_matches(params.get("pc_hash", ""), "victim-machine-hash"):
                    return httpx.Response(200, json=[])  # 字面不匹配 → 查无此设备
                return httpx.Response(200, json=[{
                    "pc_hash": "victim-machine-hash",
                    "user_id": VICTIM_ID,
                    "token": "JWT-OF-VICTIM",
                    "enrolled": 1,
                    "fingerprint": "fp",
                }])
            if path.endswith("/users"):
                return httpx.Response(200, json=[{
                    "id": VICTIM_ID, "username": VICTIM, "password_hash": "x",
                    "status": "active", "deletion_status": "正常",
                }])
            if path.endswith("/codes"):
                return httpx.Response(200, json=[{
                    "code_id": "C1", "tier": "pro", "duration_days": 0, "status": "active",
                    "user_id": VICTIM_ID, "expires_at": "2030-01-01T00:00:00",
                }])
            if path.endswith("/tiers"):
                return httpx.Response(200, json=[])
            if path.endswith("/orders"):
                return httpx.Response(200, json=[])
            _ = params  # 参数已随 URL 记录，供断言
            return httpx.Response(200, json=[])

        return PgRestClient(ENDPOINT, "test-key", transport=httpx.MockTransport(handler))

    def test_operator_like_pc_hash_rejected_at_entry(self, client, monkeypatch):
        """入口护栏层：操作符形似 pc_hash 在进数据层之前即被拒（400 + {code,msg} 信封）。"""
        from app.config import settings
        from app.infrastructure.repositories import pg_http as pg_http_pkg

        calls: list[tuple[str, str]] = []
        monkeypatch.setattr(settings, "DB_BACKEND", "pg_http")
        monkeypatch.setattr(pg_http_pkg, "_pg_client", self._pg_mock(calls))

        r = client.get("/api/check-auth", params={"pc_hash": INJECT_NEQ})

        assert r.status_code == 400, r.text
        body = r.json()
        assert body["code"] == 1 and "设备标识" in body["msg"], body
        assert "JWT-OF-VICTIM" not in r.text
        assert not _requests_of(calls, "device_grants"), "危险形态不得触达数据层"

    def test_grant_lookup_is_literal_at_data_layer(self, monkeypatch):
        """数据层（纵深）：直连仓储时操作符形似值按字面等值 → 查无此设备、不返回他人行。

        护栏是外层；本用例锁内层契约（RawFilter 改造）——即使未来有人绕过入口，
        跨行命中也不会发生。
        """
        from app.infrastructure.repositories import pg_http as pg_http_pkg
        from app.infrastructure.repositories.pg_http.grant_repo import PgHttpGrantRepo

        calls: list[tuple[str, str]] = []
        monkeypatch.setattr(pg_http_pkg, "_pg_client", self._pg_mock(calls))

        grant = PgHttpGrantRepo(pg_http_pkg.get_pg_client()).get(INJECT_NEQ)

        grant_urls = _requests_of(calls, "device_grants")
        assert grant_urls and f"pc_hash=eq.{INJECT_NEQ}" in grant_urls[0], grant_urls
        assert grant is None, "字面不匹配时不得返回他人 grant 行"


# ══════════════════════════════════════════════════════════════════
# 链 2：reset_password 不得读他人行密保、不得批量改写
# ══════════════════════════════════════════════════════════════════

class TestResetPasswordFilterInjection:
    """以 `in.("me","victim")` 形态的 username 请求找回密码。

    修复前：GET 命中他人行（按首行返回）→ 密保答案对上即可通过 → PATCH 同样以注入过滤器
    更新**多行**密码哈希（一次提交批量改密）。
    修复后：GET/PATCH 过滤器均为字面等值，只可能影响名为该字面串的账号（不存在则查无）。
    """

    def _pg_mock(self, calls: list[tuple[str, str]], answer_hash: str) -> PgRestClient:
        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, unquote(str(request.url))))
            if request.url.path.endswith("/users"):
                if request.method == "PATCH":
                    return httpx.Response(200, json=[{"username": VICTIM}])
                if not _eq_matches(request.url.params.get("username", ""), VICTIM):
                    return httpx.Response(200, json=[])  # 字面不匹配 → 查无此账号
                return httpx.Response(200, json=[{
                    "id": VICTIM_ID, "username": VICTIM, "password_hash": "x",
                    "status": "active", "security_answer_hash": answer_hash,
                    "deletion_status": "正常",
                }])
            return httpx.Response(200, json=[])

        return PgRestClient(ENDPOINT, "test-key", transport=httpx.MockTransport(handler))

    def test_reset_password_username_injection_is_literal(self, client, monkeypatch):
        from app.config import settings
        from app.infrastructure.repositories import pg_http as pg_http_pkg

        calls: list[tuple[str, str]] = []
        monkeypatch.setattr(settings, "DB_BACKEND", "pg_http")
        monkeypatch.setattr(pg_http_pkg, "_pg_client",
                            self._pg_mock(calls, hash_password(VICTIM_ANSWER)))

        client.post("/api/reset_password", json={
            "username": INJECT_IN, "security_answer": VICTIM_ANSWER, "new_password": "newpass123",
        })

        user_urls = _requests_of(calls, "users")
        assert user_urls, "reset_password 应查询 users"
        for url in user_urls:
            assert f"username=eq.{INJECT_IN}" in url, url
            assert "username=in." not in url, url

    def test_repo_update_password_wraps_value_literally(self):
        """仓储层最小回归：注入载荷进 update 过滤器时也必须是字面等值。"""
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=[])

        repo = PgHttpUserRepo(PgRestClient(ENDPOINT, "k", transport=httpx.MockTransport(handler)))
        repo.update_password(INJECT_NEQ, "NEWHASH")
        url = unquote(str(requests[0].url))
        assert f"username=eq.{INJECT_NEQ}" in url, url


# ══════════════════════════════════════════════════════════════════
# 仓储层方言门禁：不得存在未显式声明的操作符字面值
# ══════════════════════════════════════════════════════════════════

_OPERATOR_STARTS = ("eq.", "neq.", "gt.", "gte.", "lt.", "lte.", "in.(", "is.", "not.", "textSearch.")
_STR_LIT = re.compile(r'(?P<pre>RawFilter\()?(?P<lit>f?"(?:[^"\\]|\\.)*")')


def test_no_unwrapped_operator_literals_in_repositories():
    """门禁：仓储层操作符表达式必须经 RawFilter 显式声明（client.py 自身除外）。

    防止未来新增查询时"顺手写 f'eq.…' 或裸操作符串"悄悄复辟注入面。
    """
    offenders: list[str] = []
    root = Path(__file__).resolve().parents[1] / "app" / "infrastructure" / "repositories"
    for path in sorted(root.rglob("*.py")):
        if path.name == "client.py":  # 规则实现处：eq. 前缀在此构造
            continue
        src = path.read_text(encoding="utf-8")
        for m in _STR_LIT.finditer(src):
            lit = m.group("lit")
            body = lit[2:-1] if lit.startswith('f"') else lit[1:-1]
            if body.startswith(_OPERATOR_STARTS) and not m.group("pre"):
                line = src[: m.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(root)}:{line}: {lit}")
    assert not offenders, "未包装的操作符字面值（请用 RawFilter 显式声明）：\n" + "\n".join(offenders)


# ══════════════════════════════════════════════════════════════════
# 入口危险形态拦截（护栏层）
# ══════════════════════════════════════════════════════════════════

class TestIdentifierGuards:
    def test_operator_like_order_no_path_rejected(self, client):
        r = client.get("/api/pay/orders/neq.nobody")
        assert r.status_code == 400, r.text
        body = r.json()
        assert body["code"] == 1 and "订单号" in body["msg"], body

    def test_operator_like_pc_hash_query_rejected(self, client):
        r = client.get("/api/check-auth", params={"pc_hash": 'in.("a","b")'})
        assert r.status_code == 400, r.text
        assert "设备标识" in r.json()["msg"]

    def test_empty_pc_hash_still_allowed(self, client):
        """门户预热固定发空 pc_hash——必须放行（业务码「缺少 pc_hash」）。"""
        r = client.get("/api/check-auth", params={"pc_hash": ""})
        assert r.status_code == 200
        assert r.json()["code"] == 1

    def test_legacy_shaped_pc_hash_still_allowed(self, client):
        """存量设备码/测试夹具有非 hex 形态——只拦危险形态，不做白名单。

        值取本用例专用串：全量会话共享同一个测试库，其他用例可能已播种 grant 行
        （此时业务码为 0=已授权），断言只关心"未被护栏拒绝"。
        """
        r = client.get("/api/check-auth", params={"pc_hash": "hash-sec-regression"})
        assert r.status_code == 200, r.text
        assert r.json()["code"] in (0, 1), r.json()

    def test_operator_like_sku_key_body_rejected(self, client, web_user):
        r = client.post("/api/pay/orders", json={"sku_key": "neq.x", "agreement_version": "v2026.08"},
                        headers={"Authorization": f"Bearer {web_user['token']}"})
        assert r.status_code == 400, r.text
        assert "套餐标识" in r.json()["msg"]

    def test_operator_like_code_id_body_rejected(self, client, web_user):
        r = client.post("/api/user/deletion/refund-request", json={"code_id": "in.(a,b)"},
                        headers={"Authorization": f"Bearer {web_user['token']}"})
        assert r.status_code == 400, r.text
        assert "权益编号" in r.json()["msg"]


class TestRegisterUsernameWhitelist:
    def test_new_register_rejects_illegal_forms(self, client):
        for bad in ("中文名", "has space", "a.b", "ab", "x" * 33, "a,b"):
            r = client.post("/api/web/register", json={"username": bad, "password": "pass123456"})
            assert r.json()["code"] == 1, (bad, r.text)
            assert "用户名" in r.json()["msg"], (bad, r.text)

    def test_legacy_odd_username_can_still_login(self, client, db_session):
        """白名单只约束新注册：存量怪名（含点号）登录/业务照常。"""
        from app.infrastructure.security.password import hash_password
        from app.models.user import UserORM

        legacy = "old.user"
        db_session.add(UserORM(username=legacy, password_hash=hash_password("legacypass1"),
                               status="active"))
        db_session.commit()
        r = client.post("/api/web/login", json={"username": legacy, "password": "legacypass1"})
        assert r.json()["code"] == 0, r.text


# ══════════════════════════════════════════════════════════════════
# 激活属主校验（P1-B）：不能替他人订单推进激活
# ══════════════════════════════════════════════════════════════════

class TestActivationOwnership:
    def _register(self, client, username: str) -> dict:
        r = client.post("/api/web/register", json={"username": username, "password": "pass123456"})
        assert r.json()["code"] == 0, r.text
        return {"Authorization": f"Bearer {r.json()['data']['token']}"}

    def _seed_fulfilled_with_code(self, db_session, username: str, order_no: str) -> str:
        """播种：到货态订单 + 该单的 pending_activation 台账行（发货两段式第一段产物）。"""
        from app.infrastructure.repositories.factory import user_repo
        from app.models.code import ActivationCodeORM
        from app.models.payments import OrderORM

        uid = user_repo(db_session).get_id(username)
        order = OrderORM(
            order_no=order_no, user_id=uid, sku_id=1,
            sku_snapshot={"tier_key": "pro", "period_days": 365},
            amount_fen=7200, status="fulfilled", agreement_version="v2026.08",
            agreed_at=datetime.now(UTC).replace(tzinfo=None),
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db_session.add(order)
        db_session.flush()
        code_id = f"O-{order_no}"
        db_session.add(ActivationCodeORM(
            code_id=code_id, tier="pro", duration_days=365, status="pending_activation",
            status_detail="pending_activation", user_id=uid, source="order",
            order_id=order.id, created_by="payment",
            created_at=datetime.now(UTC).replace(tzinfo=None),
        ))
        db_session.commit()
        return code_id

    def test_activating_others_order_is_rejected_and_row_untouched(self, client, db_session, uid):
        victim = f"vic_{uid}"
        attacker = f"atk_{uid}"
        self._register(client, victim)
        attacker_auth = self._register(client, attacker)

        order_no = f"S20260918-{'A' * 16}"
        code_id = self._seed_fulfilled_with_code(db_session, victim, order_no)

        r = client.post("/api/pay/codes/activate", headers=attacker_auth, json={"order_no": order_no})
        body = r.json()
        assert body["code"] != 0, body  # 按订单不存在处理（不可区分存在性）

        from app.models.code import ActivationCodeORM
        row = db_session.get(ActivationCodeORM, code_id)
        db_session.refresh(row)
        assert row.status == "pending_activation", "他人台账行不得被推进激活"

    def test_owner_activation_still_works(self, client, db_session, uid):
        owner = f"own_{uid}"
        auth = self._register(client, owner)
        order_no = f"S20260918-{'B' * 16}"
        code_id = self._seed_fulfilled_with_code(db_session, owner, order_no)

        r = client.post("/api/pay/codes/activate", headers=auth, json={"order_no": order_no})
        body = r.json()
        assert body["code"] == 0, body
        assert body["data"]["code_id"] == code_id

        from app.models.code import ActivationCodeORM
        row = db_session.get(ActivationCodeORM, code_id)
        db_session.refresh(row)
        assert row.status == "active"


# ══════════════════════════════════════════════════════════════════
# 口令存储升级（P2-A）：bcrypt + 存量兼容与惰性升级 + 归一化 + 72 字节上限
# ══════════════════════════════════════════════════════════════════

class TestPasswordStorageUpgrade:
    def _legacy_hash(self, plain: str) -> str:
        """按历史算法（PBKDF2 + 全局固定盐）构造存量哈希（兼容性回归用）。"""
        import hashlib

        return hashlib.pbkdf2_hmac(
            "sha256", plain.encode(), b"ainovel_local_test", 100_000
        ).hex()

    def test_new_hash_is_bcrypt_with_random_salt(self):
        from app.infrastructure.security.password import hash_password

        h1, h2 = hash_password("pass123456"), hash_password("pass123456")
        assert h1.startswith("$2") and h2.startswith("$2")
        assert h1 != h2  # 随机盐：同明文不同哈希

    def test_legacy_hash_login_upgrades_in_place(self, client, db_session, uid):
        """存量 PBKDF2 哈希：登录成功且被惰性改写为 bcrypt（下次登录走新算法）。"""
        from app.models.user import UserORM

        username = f"lgc_{uid}"
        db_session.add(UserORM(username=username,
                               password_hash=self._legacy_hash("legacypass1"), status="active"))
        db_session.commit()

        r = client.post("/api/web/login", json={"username": username, "password": "legacypass1"})
        assert r.json()["code"] == 0, r.text

        row = db_session.query(UserORM).filter_by(username=username).first()
        db_session.refresh(row)
        assert row.password_hash.startswith("$2")
        # 改写后的哈希仍可验证同一口令
        from app.infrastructure.security.password import verify_password

        assert verify_password("legacypass1", row.password_hash)

    def test_empty_and_invalid_hashes_fail_closed(self):
        """空哈希（注销置空）/非法哈希：验证失败且不抛（不冒泡 500）。"""
        from app.infrastructure.security.password import verify_password

        assert verify_password("x", "") is False
        assert verify_password("x", "*") is False
        assert verify_password("x", "$2b$12$truncated") is False

    def test_overlong_password_rejected_at_entries(self, client, web_user):
        """>72 字节在注册/改密/重置三处显式拒绝（不得静默截断）。"""
        long_pwd = "超" * 40  # 120 字节
        r = client.post("/api/web/register", json={"username": "len_check_user", "password": long_pwd})
        assert r.json()["code"] == 1 and "72" in r.json()["msg"]

        auth = {"Authorization": f"Bearer {web_user['token']}"}
        r = client.put("/api/user/password", headers=auth,
                       json={"old_password": web_user["password"], "new_password": long_pwd})
        assert r.json()["code"] == 1 and "72" in r.json()["msg"]

    def test_security_answer_normalization(self, client, uid):
        """密保答案：设置「 Hangzhou 」后，大小写/空白变体均通过；不同答案拒绝。"""
        username = f"ans_{uid}"
        r = client.post("/api/web/register", json={
            "username": username, "password": "pass123456",
            "security_question": "q", "security_answer": " Hangzhou "})
        assert r.json()["code"] == 0, r.text

        for variant in ("hangzhou", "HANGZHOU", " Hangzhou "):
            r = client.post("/api/reset_password", json={
                "username": username, "security_answer": variant, "new_password": "newpass123"})
            assert r.json()["code"] == 0, (variant, r.text)
            # 改回原口令供下一轮变体使用（reset 会覆盖密码，密保答案不变）
            client.post("/api/web/login", json={"username": username, "password": "newpass123"})

        r = client.post("/api/reset_password", json={
            "username": username, "security_answer": "wrong-answer", "new_password": "x1x1x1x1"})
        assert r.json()["code"] == 1


# ══════════════════════════════════════════════════════════════════
# 会话撤销（P2-B）：改密/改密保/注销 → 版本前进 → 存量令牌即刻失效
# ══════════════════════════════════════════════════════════════════

class TestSessionRevocation:
    def _register_and_pair(self, client, uid: str) -> tuple[dict, str, str]:
        from tests.conftest import pair_device

        username = f"rev_{uid}"
        r = client.post("/api/web/register", json={"username": username, "password": "pass123456"})
        assert r.json()["code"] == 0, r.text
        web_token = r.json()["data"]["token"]
        dev = pair_device(client, username, "pass123456", f"rev_pc_{uid}")
        return {"username": username, "password": "pass123456", "web_token": web_token,
                "auth": {"Authorization": f"Bearer {web_token}"}}, dev["pc_hash"], dev["token"]

    def test_password_change_revokes_old_tokens(self, client, uid):
        user, pc, dev_token = self._register_and_pair(client, uid)

        r = client.put("/api/user/password", headers=user["auth"],
                       json={"old_password": user["password"], "new_password": "newpass987"})
        assert r.json()["code"] == 0, r.text

        # 旧 web 令牌：pay 面 401（严格依赖）、user 面 视同未登录
        assert client.get("/api/pay/license", headers=user["auth"]).status_code == 401
        assert client.get("/api/user/me", headers=user["auth"]).json()["code"] == 1
        # 新令牌（重新登录）正常
        login = client.post("/api/web/login",
                            json={"username": user["username"], "password": "newpass987"}).json()
        assert login["code"] == 0
        assert client.get("/api/pay/license",
                          headers={"Authorization": f"Bearer {login['data']['token']}"}).json()["code"] == 0

    def test_security_answer_change_revokes_old_tokens(self, client, uid):
        user, _, _ = self._register_and_pair(client, uid)
        r = client.put("/api/user/security", headers=user["auth"],
                       json={"security_question": "q", "security_answer": "new answer"})
        assert r.json()["code"] == 0, r.text
        assert client.get("/api/pay/license", headers=user["auth"]).status_code == 401

    def test_legacy_token_without_ver_survives(self, client, uid, db_session):
        """存量令牌（无 ver 声明按 0）在版本仍为 0 时照常放行——升级零登出。"""
        from datetime import UTC, datetime, timedelta

        from jose import jwt as jose_jwt

        from app.config import settings
        from tests.conftest import pair_device

        username = f"lgc2_{uid}"
        r = client.post("/api/web/register", json={"username": username, "password": "pass123456"})
        assert r.json()["code"] == 0
        pair_device(client, username, "pass123456", f"lgc2_pc_{uid}")

        from app.models.user import UserORM

        real_uid = db_session.query(UserORM.id).filter_by(username=username).first()[0]
        payload = {"sub": username, "username": username, "uid": real_uid,  # 无 ver
                   "exp": int((datetime.now(UTC) + timedelta(days=1)).timestamp())}
        legacy = jose_jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
        resp = client.get("/api/pay/license", headers={"Authorization": f"Bearer {legacy}"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == 0

    def test_device_removal_does_not_revoke_web_session(self, client, uid):
        """移除单设备只解绑该设备（登记行 + 授权凭证删除），MUST NOT 自增版本牵连其他端。"""
        import base64
        import json as _json

        from tests.conftest import pair_device

        username = f"rmv_{uid}"
        r = client.post("/api/web/register", json={"username": username, "password": "pass123456"})
        web_token = r.json()["data"]["token"]
        profile = base64.urlsafe_b64encode(_json.dumps(
            {"f": "fp-rmv", "h": "移除测试机", "o": "windows", "a": "x64"},
            separators=(",", ":")).encode()).decode().rstrip("=")
        dev = pair_device(client, username, "pass123456", f"rmv_pc_{uid}",
                          device_profile=profile)

        my = client.get("/api/devices/my", headers={"Authorization": f"Bearer {web_token}"}).json()
        device_id = my["data"][0]["id"]
        r = client.post("/api/devices/remove", json={"id": device_id},
                        headers={"Authorization": f"Bearer {web_token}"})
        assert r.json()["code"] == 0

        # web 令牌仍有效（未因移除设备被撤销）
        assert client.get("/api/pay/license",
                          headers={"Authorization": f"Bearer {web_token}"}).json()["code"] == 0
        # 被移除设备的令牌：设备校验失败（verify 的 device_valid=False）
        v = client.post("/api/verify", json={"username": username, "token": dev["token"],
                                             "pc_hash": dev["pc_hash"]}).json()
        assert v["data"]["device_valid"] is False
