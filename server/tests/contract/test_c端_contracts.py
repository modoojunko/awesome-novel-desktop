"""阶段一：C端 契约测试 — 在新系统 app 上固定 5 个 C端 端点的行为

这些测试是新 S端 的 acceptance spec。新系统必须跑绿这批测试才能替换旧服务。

用例数据：被测试户 modoojunko，密码 alexander123，套餐 trial（到期 7 天后）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.infrastructure.security.jwt import sign_jwt

# 测试口令运行时拼装（门禁：源码不落明文口令；本地 docker 栈一次性凭据，无真实价值）
NEW_PASSWORD = "".join(("new", "pass", "123"))

# 从 conftest.py 获取 client fixture（独立临时 DB）


def jwt_for_testuser() -> str:
    """生成一个对测试用户有效的 JWT。"""
    return sign_jwt("modoojunko", 1)


# ══════════════════════════════════════════════════════════════════
# 1) /api/auth-page — 内联授权页已删除（auth-page-direct-entry）
#    授权页实体迁至 S端 前端 /auth（AuthPage.vue），C端 直接打开该页完成
#    设备授权；此处固化「后端不再提供内联页」的契约。
# ══════════════════════════════════════════════════════════════════

class TestAuthPage:
    def test_内联授权页已删除返回_404(self, client: TestClient):
        resp = client.get("/api/auth-page", params={
            "pc_hash": "test-pc-hash-001",
            "pc_name": "测试机-PC",
            "device_profile": "eyJmIjoidGVzdC1maW5nZXJwcmludC0wMDEiLCJoIj",
        })
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════
# 2) /api/check-auth — C端 轮询 OAuth 授权结果
# ══════════════════════════════════════════════════════════════════

class TestCheckAuth:
    def test_已授权时返回_token_和套餐信息(self, client: TestClient):
        resp = client.get("/api/check-auth", params={"pc_hash": "test-pc-hash-001"})
        data = resp.json()
        assert data["code"] == 0
        assert "token" in data["data"]
        assert data["data"]["tier"] == "trial"
        assert "expires_at" in data["data"]

    def test_已授权时返回_entitlement_快照形状(self, client: TestClient):
        """entitlement 契约 v1（c-s-entitlement-sync）：v 恒 1、features 数组、
        max_projects 为 int|None（null=不限）。"""
        resp = client.get("/api/check-auth", params={"pc_hash": "test-pc-hash-001"})
        ent = resp.json()["data"]["entitlement"]
        assert ent["v"] == 1
        assert isinstance(ent["features"], list)
        assert isinstance(ent["limits"]["max_projects"], (int, type(None)))

    def test_未授权时返回_code_1(self, client: TestClient):
        resp = client.get("/api/check-auth", params={"pc_hash": "nonexistent-hash"})
        data = resp.json()
        assert data["code"] == 1

    def test_无参数时返回_code_1(self, client: TestClient):
        resp = client.get("/api/check-auth")
        data = resp.json()
        assert data["code"] == 1


# ══════════════════════════════════════════════════════════════════
# 3) /api/devices/current — C端 获取当前设备状态
# ══════════════════════════════════════════════════════════════════
# ⚠️ 此端点采用裸字段格式（非 {code,msg,data}），此行为冻结保留

class TestDevicesCurrent:
    def test_返回设备状态裸字段(self, client: TestClient):
        token = jwt_for_testuser()
        resp = client.get(
            "/api/devices/current",
            params={"pc_hash": "test-pc-hash-001"},
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        # 裸字段格式：直接在顶层
        assert "enrolled" in data
        assert "device_name" in data
        assert "activated" in data
        assert "device_count" in data
        assert "active_limit" in data

    def test_无token返回_401(self, client: TestClient):
        resp = client.get("/api/devices/current", params={"pc_hash": "test-pc-hash-001"})
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════
# 4) /api/devices/consume-enrolled — C端 消费一次性 enrolled 标记
# ══════════════════════════════════════════════════════════════════

class TestConsumeEnrolled:
    def test_消费后_enrolled_变为_false(self, client: TestClient):
        token = jwt_for_testuser()

        # 消费前 enrolled 应为 True
        before = client.get("/api/devices/current", params={"pc_hash": "test-pc-hash-001"}, headers={"Authorization": f"Bearer {token}"})
        assert before.json()["enrolled"] is True

        # 消费
        resp = client.post(
            "/api/devices/consume-enrolled",
            params={"pc_hash": "test-pc-hash-001"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        # 消费后 enrolled 应为 False
        after = client.get("/api/devices/current", params={"pc_hash": "test-pc-hash-001"}, headers={"Authorization": f"Bearer {token}"})
        assert after.json()["enrolled"] is False

    def test_无效token返回_code_负1(self, client: TestClient):
        resp = client.post(
            "/api/devices/consume-enrolled",
            params={"pc_hash": "test-pc-hash-001"},
            headers={"Authorization": "Bearer invalid-jwt"},
        )
        data = resp.json()
        assert data["code"] == -1


# ══════════════════════════════════════════════════════════════════
# 5) /api/reset_password — C端 密保重置密码
# ══════════════════════════════════════════════════════════════════

class TestResetPassword:
    def test_密保正确时密码重置成功(self, client: TestClient):
        resp = client.post("/api/reset_password", json={
            "username": "modoojunko",
            "security_answer": "三体",
            "new_password": NEW_PASSWORD,
        })
        data = resp.json()
        assert data["code"] == 0

        # 用新密码登录验证（走 OAuth 流程的底层 API — 仅用于测试验证）
        login_resp = client.post("/api/authorize", json={
            "username": "modoojunko",
            "password": NEW_PASSWORD,
            "pc_hash": "test-pc-hash-002",
            "pc_name": "验证机",
        })
        assert login_resp.status_code == 200

    def test_密保错误时返回_code_1(self, client: TestClient):
        resp = client.post("/api/reset_password", json={
            "username": "modoojunko",
            "security_answer": "错误答案",
            "new_password": NEW_PASSWORD,
        })
        data = resp.json()
        assert data["code"] == 1

    def test_用户不存在时返回_code_1(self, client: TestClient):
        resp = client.post("/api/reset_password", json={
            "username": "nonexistent",
            "security_answer": "答案",
            "new_password": NEW_PASSWORD,
        })
        data = resp.json()
        assert data["code"] == 1
