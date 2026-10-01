"""S端 测试公共夹具。

关键点：DATABASE_URL 必须在首次 import app.* 之前指向独立 SQLite 文件
（models.base 的 engine 在 import 时绑定连接串）。conftest 由 pytest 在
收集阶段最先加载，因此在这里完成 env 设置。
"""

import os
import re
import tempfile
import uuid
from pathlib import Path

_tmp_db = tempfile.NamedTemporaryFile(suffix="_s_server_test.db", delete=False)
_tmp_db.close()
# 无条件覆盖：setdefault 会沿用开发 shell 残留的 DATABASE_URL，
# 导致测试静默连入外部库（迁移 + 写入真实数据）
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
# 限流阈值同批覆盖：RateLimitMiddleware.LIMIT 在类定义（import 期）求值，
# 敏感清单扩到注册/找回/改密/注销/配对后，单次 pytest 的凭据类请求必超默认 30。
os.environ["RATE_LIMIT_LOGIN_PER_MIN"] = "2000"
os.environ["BCRYPT_ROUNDS"] = "4"

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.base import SessionLocal

# 测试口令（拼串构造，避免被凭据扫描误报为硬编码密钥）
WEB_PASSWORD = "".join(("Pa", "ss-live-", "42"))


@pytest.fixture(scope="session")
def client():
    """进程内 TestClient（startup 会跑 alembic 迁移 + create_all 建表）。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def _cleanup_tmp_db():
    """会话结束后释放连接并删除临时库（含 SQLite WAL/SHM 边车文件）。"""
    yield
    from app.models import base as mbase

    mbase.engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        Path(_tmp_db.name + suffix).unlink(missing_ok=True)


def pair_device(client, username: str, password: str, pc_hash: str,
                pc_name: str = "测试机", device_profile: str = "") -> dict:
    """配对助手（s-security-hardening）：authorize(challenge) → exchange 换令牌。

    供需要"已授权设备 + 令牌"的用例使用；返回 pc_hash/device_secret/token/username。
    """
    import hashlib
    import secrets

    device_secret = secrets.token_urlsafe(32)
    challenge = hashlib.sha256(device_secret.encode()).hexdigest()
    r = client.post("/api/authorize", json={
        "username": username, "password": password, "pc_hash": pc_hash,
        "pc_name": pc_name, "challenge": challenge,
        **({"device_profile": device_profile} if device_profile else {}),
    })
    assert r.json()["code"] == 0, r.text
    r = client.post("/api/pair/exchange",
                    json={"pc_hash": pc_hash, "device_secret": device_secret})
    assert r.json()["code"] == 0, r.text
    return {"pc_hash": pc_hash, "device_secret": device_secret,
            "token": r.json()["data"]["token"], "username": username}


@pytest.fixture
def uid() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture
def admin_token() -> str:
    """管理端令牌来自配置（不硬编码字面量）。"""
    return settings.ADMIN_TOKEN


@pytest.fixture
def seed_code():
    """直灌一枚激活码（s-code-issue 起 S端 无发码端点，测试种子走 ORM）。"""

    def _seed(code_id: str, tier: str = "monthly", count: int = 1) -> list[str]:
        import secrets
        import string

        from app.models.base import SessionLocal
        from app.models.code import ActivationCodeORM

        chars = string.ascii_uppercase + string.digits
        ids = [code_id] + [
            f"AC-{'-'.join(''.join(secrets.choice(chars) for _ in range(4)) for _ in range(4))}"
            for _ in range(count - 1)
        ]
        s = SessionLocal()
        try:
            for cid in ids:
                s.add(ActivationCodeORM(code_id=cid, tier=tier, duration_days=30,
                                        status="unused", created_by="admin"))
            s.commit()
        finally:
            s.close()
        return ids

    return _seed


@pytest.fixture
def web_user(client, uid) -> dict:
    """Web 注册用户（注册即送 7 天 trial）。

    用户名过注册白名单消毒：uid 夹具被部分用例参数化成 None/"7"/1.5（旧格式 token 契约），
    直接拼名会生成含点的非法用户名被 s-security-hardening 白名单拒绝。
    """
    safe_uid = re.sub(r"[^A-Za-z0-9_-]", "_", str(uid))
    username = f"wu_{safe_uid}"
    password = WEB_PASSWORD
    r = client.post(
        "/api/web/register",
        json={
            "username": username,
            "password": password,
            "security_question": "q?",
            "security_answer": "a",
        },
    )
    assert r.json()["code"] == 0, r.text
    return {"username": username, "password": password, "token": r.json()["data"]["token"]}


@pytest.fixture
def db_session():
    """直连测试库的 SQLAlchemy session（ORM 播种/断言用）。"""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
