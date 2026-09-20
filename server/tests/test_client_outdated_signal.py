"""s-auth-outdated-signal 场景测试——specs 六场景逐一对应。

场景映射：
S1 authorize challenge 缺失+密码对 → code=3+标记（Requirement: authorize 分档拒绝）
S2 密码错误 → code=1 不落标记
S3 服务重启标记不丢（新 session 直查表，TTL 内）
S4 check-auth 命中二信号（code=3 + client_outdated 载荷，TTL 覆盖轮询窗）
S5 旧 C端 收 code=3 不误清凭据（形态核对：code=3 非 1；清凭据逻辑只挂 code=1）
S6 pair/exchange 排除面（失败响应不含 outdated 字段）
另：有 grant 时标记不干扰已授权设备；标记过期退化为等待授权。
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import pytest


def _register(client, username: str, password: str) -> None:
    r = client.post("/api/web/register", json={
        "username": username, "password": password,
        "security_question": "q", "security_answer": "a"})
    assert r.json()["code"] == 0, r.text


def _auth_json(client, username, password, pc_hash, challenge=""):
    return client.post("/api/authorize", json={
        "username": username, "password": password, "pc_hash": pc_hash,
        "pc_name": "t", "device_profile": "", "challenge": challenge}).json()


@pytest.fixture()
def user(client):
    name = f"outdated_{secrets.token_hex(4)}"
    pwd = "Test-Pwd42!"
    _register(client, name, pwd)
    return name, pwd


def test_s1_challenge_missing_with_valid_password_returns_code3_and_marks(client, user):
    """S1：challenge 空+密码对 → code=3+reason+download_url；按 pc_hash 落标记。"""
    name, pwd = user
    body = _auth_json(client, name, pwd, "pc-out-1", challenge="")
    assert body["code"] == 3
    assert body["reason"] == "client_outdated"
    assert body["data"]["client_outdated"] is True
    assert body["data"]["download_url"]
    assert "版本过旧" not in body["msg"]  # 文案根因修正：动作导向


def test_s2_wrong_password_no_mark_no_outdated(client, user):
    """S2：密码错误 → code=1「用户名或密码错误」，不落标记、不暴露 outdated。"""
    name, _ = user
    body = _auth_json(client, name, "wrong-password", "pc-out-2")
    assert body["code"] == 1
    assert body["msg"] == "用户名或密码错误"
    # 无标记：check-auth 仍是等待授权
    assert client.get("/api/check-auth", params={"pc_hash": "pc-out-2"}).json()["code"] == 1


def test_s3_mark_survives_restart_within_ttl(client, user):
    """S3：落标记后新 session（模拟实例重启）TTL 内可读；过期不可读。"""
    from app.models.base import SessionLocal
    from app.models.outdated_mark import DeviceOutdatedMarkORM

    name, pwd = user
    _auth_json(client, name, pwd, "pc-out-3")
    # 新 session 直查（标记落库而非内存）
    with SessionLocal() as s:
        row = s.query(DeviceOutdatedMarkORM).filter(
            DeviceOutdatedMarkORM.pc_hash == "pc-out-3").first()
        assert row is not None, "标记必须持久化"
        # 过期路径：rejected_at 拨回 11 分钟前 → fresh=False
        row.rejected_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=11)
        s.commit()
    r = client.get("/api/check-auth", params={"pc_hash": "pc-out-3"}).json()
    assert r["code"] == 1 and r["msg"] == "等待授权", "TTL 过期退化为等待授权"


def test_s4_check_auth_carries_signal_within_polling_window(client, user):
    """S4：authorize 拒后 120s 轮询窗内每轮 check-auth 均得 code=3+载荷（TTL≥10min）。"""
    name, pwd = user
    _auth_json(client, name, pwd, "pc-out-4")
    for _ in range(3):  # 模拟多轮轮询
        body = client.get("/api/check-auth", params={"pc_hash": "pc-out-4"}).json()
        assert body["code"] == 3
        assert body["data"]["client_outdated"] is True
        assert body["data"]["download_url"]


def test_s5_code3_is_not_code1_so_legacy_client_keeps_credentials(client, user):
    """S5：信号形态为独立 code=3——旧 C端 清凭据逻辑只挂 code=1（auth_local
    service.py session_invalid 分支），code=3 走未知 code 兜底不清 token。"""
    name, pwd = user
    _auth_json(client, name, pwd, "pc-out-5")
    body = client.get("/api/check-auth", params={"pc_hash": "pc-out-5"}).json()
    assert body["code"] == 3  # 非 1：清凭据触发条件的形态断言


def test_s6_pair_exchange_failure_has_no_outdated_fields(client, user):
    """S6：pair/exchange 失败（密钥不符）响应不含 outdated 语义（排除面契约）。"""
    name, pwd = user
    secret = secrets.token_hex(32)
    challenge = hashlib.sha256(secret.encode()).hexdigest()
    ok = _auth_json(client, name, pwd, "pc-out-6", challenge=challenge)
    assert ok["code"] == 0
    bad = client.post("/api/pair/exchange", json={
        "pc_hash": "pc-out-6", "device_secret": secrets.token_hex(32)}).json()
    assert bad["code"] == 1
    flat = str(bad)
    for banned in ("client_outdated", "latest_version", "download_url"):
        assert banned not in flat


def test_grant_beats_mark_authorized_device_unaffected(client, user):
    """有 grant：已授权设备 check-auth 正常返回套餐（标记不干扰）。"""
    name, pwd = user
    secret = secrets.token_hex(32)
    challenge = hashlib.sha256(secret.encode()).hexdigest()
    # 先落一个标记（challenge 缺失拒绝一次）
    _auth_json(client, name, pwd, "pc-out-7")
    # 再正常授权同 pc_hash
    assert _auth_json(client, name, pwd, "pc-out-7", challenge=challenge)["code"] == 0
    body = client.get("/api/check-auth", params={"pc_hash": "pc-out-7"}).json()
    assert body["code"] == 0 and body["data"]["username"] == name
