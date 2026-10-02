"""设备注册与激活管理 — 领域策略 + C端/门户 API 测试（DDD 重构版）

对应实现：
- ActivationPolicy.compute / compute_all   app/domain/devices/activation_policy.py
- tier_policy.get_device_limit             app/domain/licensing/tier_policy.py
- DeviceProfile 编解码                     app/domain/devices/device.py
- /api/authorize                           app/interfaces/client_api/authorize.py
- /api/devices/current · consume-enrolled  app/interfaces/client_api/devices.py
- /api/devices/my                          app/interfaces/web_api/devices.py

用法：
    cd server
    python -m pytest tests/test_device_activation.py -v
"""

import base64 as b64
import json
import uuid
from datetime import datetime, timedelta

from app.domain.devices import ActivationPolicy, DeviceProfile, DeviceRegistry
from app.domain.licensing import tier_policy
from app.models.base import SessionLocal
from app.models.device import DeviceRegistryORM
from app.models.grant import DeviceGrantORM
from app.models.user import UserORM

# ============================================================
# 构造工具
# ============================================================

def device_dict(fingerprint: str, last_active: str):
    """构造 ActivationPolicy.compute 用的设备实体（列表已按 last_active 降序排好）。"""
    return DeviceRegistry(
        id=fingerprint,
        user_id="u1",
        fingerprint=fingerprint,
        hostname=f"host-{fingerprint}",
        os="Windows 11",
        os_arch="x86_64",
        last_active_at=datetime.fromisoformat(last_active),
    )


def profile_b64(payload: dict) -> str:
    return b64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


# {"f": "ABC123", "h": "PC1"} 的固定编码（authorize 请求用）
FP_ABC_PC1 = profile_b64({"f": "ABC123", "h": "PC1", "o": "Windows 11", "a": "x86_64"})


def seed_raw_user(username: str):
    """直插无套餐用户（绕过 web 注册的赠码逻辑，用于 none 层）。"""
    s = SessionLocal()
    try:
        s.add(UserORM(username=username, password_hash="*"))
        s.commit()
    finally:
        s.close()


def seed_device_row(username: str, fingerprint: str, days_ago: float, hostname: str = "测试机"):
    s = SessionLocal()
    try:
        from app.models.user import UserORM
        u = s.query(UserORM.id).filter(UserORM.username == username).first()
        uid = u[0] if u else None
        s.add(
            DeviceRegistryORM(
                id=uuid.uuid4().hex,
                user_id=uid,
                fingerprint=fingerprint,
                hostname=hostname,
                os="Windows 11",
                os_arch="x86_64",
                last_active_at=datetime.now() - timedelta(days=days_ago),
                bound_at=datetime.now() - timedelta(days=days_ago + 1),
                updated_at=datetime.now() - timedelta(days=days_ago),
            )
        )
        s.commit()
    finally:
        s.close()


def seed_grant_row(pc_hash: str, username: str, fingerprint: str = "", enrolled: int = 0):
    s = SessionLocal()
    try:
        from app.models.user import UserORM
        u = s.query(UserORM.id).filter(UserORM.username == username).first()
        uid = u[0] if u else None
        s.add(
            DeviceGrantORM(
                pc_hash=pc_hash,
                user_id=uid,
                token="legacy-token",
                enrolled=enrolled,
                fingerprint=fingerprint,
            )
        )
        s.commit()
    finally:
        s.close()


def get_grant(pc_hash: str):
    s = SessionLocal()
    try:
        return s.query(DeviceGrantORM).filter(DeviceGrantORM.pc_hash == pc_hash).first()
    finally:
        s.close()


def count_devices(username: str) -> int:
    s = SessionLocal()
    try:
        from app.models.user import UserORM
        user = s.query(UserORM.id).filter(UserORM.username == username).first()
        if not user:
            return 0
        return (
            s.query(DeviceRegistryORM)
            .filter(DeviceRegistryORM.user_id == user[0])
            .count()
        )
    finally:
        s.close()


def authorize(client, username, password, pc_hash, device_profile=None, challenge=None):
    """s-security-hardening：授权必须携带 challenge（64 位小写 hex）；缺省自动生成。"""
    import hashlib
    import secrets

    if challenge is None:
        challenge = hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()
    body = {"username": username, "password": password, "pc_hash": pc_hash,
            "pc_name": "PC", "challenge": challenge}
    if device_profile is not None:
        body["device_profile"] = device_profile
    return client.post("/api/authorize", json=body)


# ============================================================
# Unit — ActivationPolicy.compute（设备列表按 last_active 降序传入）
# ============================================================

class TestActivationPolicy:
    def test_top_2_of_3(self):
        """3 台设备限额 2：前 2 激活，第 3 台 limit_exceeded。"""
        devices = [
            device_dict("A", "2026-07-28T14:00:00"),
            device_dict("B", "2026-07-27T10:00:00"),
            device_dict("C", "2026-07-26T08:00:00"),
        ]
        result_a = ActivationPolicy.compute(devices, 2, "A", "monthly")
        assert result_a["activated"] is True
        assert result_a["activated_count"] == 2
        assert result_a["total_count"] == 3

        result_c = ActivationPolicy.compute(devices, 2, "C", "monthly")
        assert result_c["activated"] is False
        assert result_c["reason"]["code"] == "limit_exceeded"

    def test_account_inactive_all_deactivated(self):
        """无套餐（tier=none）：所有设备未激活，reason=account_inactive。"""
        devices = [device_dict("A", "2026-07-28T14:00:00")]
        result = ActivationPolicy.compute(devices, 0, "A", "none")
        assert result["activated"] is False
        assert result["reason"]["code"] == "account_inactive"
        assert result["active_limit"] == 0
        assert result["activated_count"] == 0

    def test_empty_device_list(self):
        result = ActivationPolicy.compute([], 1, "", "monthly")
        assert result["activated"] is False
        assert result["total_count"] == 0
        assert result["activated_count"] == 0

    def test_compute_all_mixed_status(self):
        devices = [
            device_dict("A", "2026-07-28T14:00:00"),
            device_dict("B", "2026-07-27T10:00:00"),
        ]
        results = ActivationPolicy.compute_all(devices, 1, "monthly")
        assert results[0]["activated"] is True and results[0]["reason"] is None
        assert results[1]["activated"] is False
        assert results[1]["reason"]["code"] == "limit_exceeded"
        assert results[0]["is_current"] is True


class TestTierPolicy:
    def test_tier_limit_mapping(self):
        assert tier_policy.get_device_limit("none") == 0
        assert tier_policy.get_device_limit("trial") == 1
        assert tier_policy.get_device_limit("free") == 1
        assert tier_policy.get_device_limit("monthly") == 3
        assert tier_policy.get_device_limit("quarterly") == 3
        assert tier_policy.get_device_limit("yearly") == 5
        assert tier_policy.get_device_limit("lifetime") == 99
        assert tier_policy.get_device_limit("unknown") == 1  # fallback


class TestProfileCodec:
    def test_roundtrip(self):
        p = DeviceProfile("FP-001", "PC1", "Windows", "x86_64")
        decoded = DeviceProfile.from_b64(p.to_b64())
        assert decoded == p

    def test_empty_input(self):
        decoded = DeviceProfile.from_b64("")
        assert decoded.is_empty

    def test_missing_padding(self):
        encoded = profile_b64({"f": "FP-002", "h": "PC2"}).rstrip("=")
        assert "=" not in encoded
        assert DeviceProfile.from_b64(encoded).fingerprint == "FP-002"

    def test_invalid_base64(self):
        assert DeviceProfile.from_b64("!!!not-base64!!!").is_empty

    def test_valid_base64_not_json(self):
        encoded = b64.urlsafe_b64encode(b"not-json").decode()
        assert DeviceProfile.from_b64(encoded).is_empty

    def test_missing_fields_default_empty(self):
        encoded = profile_b64({"unknown": "value"})
        decoded = DeviceProfile.from_b64(encoded)
        assert decoded.fingerprint == "" and decoded.hostname == ""


# ============================================================
# API — POST /api/authorize（设备注册）
# ============================================================

class TestAuthorizeAPI:
    def test_new_device_registration(self, client, web_user):
        """首次授权 → 创建设备记录 → enrolled=1。"""
        resp = authorize(client, web_user["username"], web_user["password"], "hash-001", FP_ABC_PC1)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["tier"] == "trial"  # web 注册赠送 7 天试用

        assert count_devices(web_user["username"]) == 1
        grant = get_grant("hash-001")
        assert grant is not None and grant.enrolled == 1
        assert grant.fingerprint == "ABC123"

    def test_duplicate_device_registration(self, client, web_user):
        """同指纹重复授权 → 复用记录 → enrolled=0。"""
        authorize(client, web_user["username"], web_user["password"], "hash-001", FP_ABC_PC1)
        resp = authorize(client, web_user["username"], web_user["password"], "hash-002", FP_ABC_PC1)
        assert resp.json()["code"] == 0

        assert count_devices(web_user["username"]) == 1
        assert get_grant("hash-002").enrolled == 0

    def test_no_device_profile(self, client, web_user):
        """旧版 C端 不传 device_profile → 空指纹注册。"""
        resp = authorize(client, web_user["username"], web_user["password"], "hash-003")
        assert resp.json()["code"] == 0
        assert count_devices(web_user["username"]) == 1

    def test_invalid_base64_profile(self, client, web_user):
        """非法 Base64 → 解码为空指纹，不阻断授权。"""
        resp = authorize(client, web_user["username"], web_user["password"], "hash-004", "!!!bad!!!")
        assert resp.json()["code"] == 0
        assert get_grant("hash-004").fingerprint == ""

    def test_wrong_password(self, client, web_user):
        resp = authorize(client, web_user["username"], "wrong-pass", "hash-005", FP_ABC_PC1)
        assert resp.json()["code"] == 1


# ============================================================
# API — GET /api/devices/current（C端 设备状态）
# ============================================================

class TestDevicesCurrentAPI:
    def _get(self, client, pc_hash, token):
        return client.get(
            "/api/devices/current",
            params={"pc_hash": pc_hash},
            headers={"Authorization": f"Bearer {token}"},
        ).json()

    def test_activated(self, client, web_user):
        """trial 用户单设备 → activated=true，限额 1。"""
        authorize(client, web_user["username"], web_user["password"], "hash-101", FP_ABC_PC1)
        data = self._get(client, "hash-101", web_user["token"])
        assert data["activated"] is True
        assert data["device_count"] == 1
        assert data["active_limit"] == 1

    def test_limit_exceeded(self, client, web_user):
        """pro（限额 5，归一化后 monthly→pro）第 6 台设备 → limit_exceeded。

        激活码 web 端点已下线（8.3）：直接播种已激活码行使账号达到 pro 档。
        """
        from app.models.code import ActivationCodeORM

        s = SessionLocal()
        try:
            u = s.query(UserORM.id).filter(UserORM.username == web_user["username"]).first()
            s.add(ActivationCodeORM(
                code_id="CODE-LIMITEX-1",
                tier="monthly",
                duration_days=30,
                status="active",
                user_id=u[0],
                activated_at=datetime.now() - timedelta(days=1),
                expires_at=datetime.now() + timedelta(days=29),
            ))
            s.commit()
        finally:
            s.close()

        # seed 6 台（pro limit=5），FP-0 最旧 → 排序后第 6 位，不在 top-5 内
        for i, days in enumerate((6.0, 5.0, 4.0, 3.0, 2.0, 1.0)):
            seed_device_row(web_user["username"], f"FP-{i}", days)
        seed_grant_row("hash-102", web_user["username"], fingerprint="FP-0")

        data = self._get(client, "hash-102", web_user["token"])
        assert data["activated"] is False
        assert data["reason"]["code"] == "limit_exceeded"
        assert data["active_limit"] == 5

    def test_account_inactive(self, client, uid):
        """无套餐用户（无任何激活码）→ account_inactive。"""
        username = f"none_{uid}"
        seed_raw_user(username)
        seed_device_row(username, "FP-X", 1.0)
        seed_grant_row("hash-103", username, fingerprint="FP-X")

        # 无套餐用户没有可用的 JWT —— 用 web_user 的 token 触发 401 分支之外，
        # 这里直接以应用层方式验证（接口 401 见下一条）
        from app.application.devices.get_device_status import get_device_status
        from app.infrastructure.repositories.factory import (
            code_repo,
            device_repo,
            grant_repo,
        )
        s = SessionLocal()
        try:
            result = get_device_status(
                grant_repo(s), device_repo(s), code_repo(s),
                username=username, pc_hash="hash-103",
            )
        finally:
            s.close()
        assert result["activated"] is False
        assert result["reason"]["code"] == "account_inactive"

    def test_unauthorized_401(self, client):
        resp = client.get("/api/devices/current", params={"pc_hash": "hash-x"})
        assert resp.status_code == 401
        assert resp.json()["code"] == -1


# ============================================================
# API — GET /api/devices/my（门户设备列表）+ client 面 consume-enrolled
# ============================================================

class TestDevicePortalAPI:
    def test_list_mixed_status(self, client, web_user):
        """trial 限额 1：两台设备 → 1 激活 1 超限。"""
        seed_device_row(web_user["username"], "FP-A", 0.5, hostname="主开发机")
        seed_device_row(web_user["username"], "FP-B", 2.0, hostname="办公本")

        r = client.get(
            "/api/devices/my",
            headers={"Authorization": f"Bearer {web_user['token']}"},
        )
        data = r.json()
        assert data["code"] == 0
        assert data["total_count"] == 2
        assert data["activated_count"] == 1
        assert data["active_limit"] == 1

        by_host = {d["hostname"]: d for d in data["data"]}
        assert by_host["主开发机"]["activated"] is True
        assert by_host["办公本"]["activated"] is False
        assert by_host["办公本"]["reason"]["code"] == "limit_exceeded"

    def test_consume_enrolled(self, client, web_user):
        """新设备授权 enrolled=1 → 消费后置 0。"""
        authorize(client, web_user["username"], web_user["password"], "hash-201", FP_ABC_PC1)
        assert get_grant("hash-201").enrolled == 1

        r = client.post(
            "/api/devices/consume-enrolled",
            params={"pc_hash": "hash-201"},
            headers={"Authorization": f"Bearer {web_user['token']}"},
        )
        assert r.json()["code"] == 0
        assert get_grant("hash-201").enrolled == 0


class TestSqlDeviceRepoUpsertRace:
    def test_conflict_falls_back_to_update(self, monkeypatch):
        """find→flush 间隙被并发抢先插入：唯一约束 uq_user_fingerprint 拦下 insert，
        回落为更新而非 500，设备表不留重复行。"""
        from app.infrastructure.repositories.sql.device_repo import SqlDeviceRepo

        seed_raw_user("race-user")
        # 「并发方」已落库的行（预置在库里，repo 首查被模拟为扑空 → 走 insert → 撞约束）
        seed_device_row("race-user", "FP-RACE", days_ago=0.01, hostname="旧主机名")

        s = SessionLocal()
        try:
            repo = SqlDeviceRepo(s)
            real_find = repo._find_row
            calls = {"n": 0}

            def find_with_race_window(uid, fp):
                calls["n"] += 1
                if calls["n"] == 1:
                    return None  # 模拟竞态：本请求首查时那行「还没出现」
                return real_find(uid, fp)

            monkeypatch.setattr(repo, "_find_row", find_with_race_window)
            device = repo.upsert(DeviceRegistry(
                id="", user_id="race-user", fingerprint="FP-RACE",
                hostname="新主机名", os="macOS", os_arch="arm64"))
            assert device.hostname == "新主机名"
            assert device.id  # 回读真实行 id
            s.commit()
        finally:
            s.close()

        assert count_devices("race-user") == 1
