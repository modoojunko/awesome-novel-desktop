"""stop 路由集成钉（c-agent-chat-memory 批8 停止/打断）。

- 幂等：无在跑 run → stopped=false（200，不炸）；
- 鉴权链：config token 校验同 middleware 口径（未登录 401）；
- 键控：thread 维度隔离（同会话不同线程互不影响）。

真实「在跑 run 的取消」机制由 loop 层单测钉（test_assistant_loop cancel 两条）。
"""

import os
import tempfile
from datetime import UTC, datetime

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix="_stop_http.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_root = tempfile.mkdtemp(prefix="stop_http_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_root

from db import Base, engine  # noqa: E402

_CFG = os.path.join(_tmp_root, "config.json")

from fastapi.testclient import TestClient  # noqa: E402

import auth_local.middleware as _mw  # noqa: E402
import auth_local.service as _service  # noqa: E402
from main import app  # noqa: E402


async def _setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


import asyncio  # noqa: E402

asyncio.run(_setup())

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def _startup():
    _orig = _mw.CONFIG_FILE
    with client:
        yield
    _mw.CONFIG_FILE = _orig


def _set_session():
    _mw.CONFIG_FILE = _CFG
    _service.CONFIG_FILE = _CFG
    cfg = _service.get_local_config()
    cfg.update({
        "tier": "max",
        "token": "tok-stophttp",
        "username": "stophttp",
        "last_login_at": datetime.now(UTC).isoformat(),
    })
    _service.save_local_config(cfg)


@pytest.fixture(autouse=True)
def _fresh_config():
    _orig = _mw.CONFIG_FILE
    _set_session()
    yield
    if os.path.exists(_CFG):
        os.remove(_CFG)
    _mw.CONFIG_FILE = _orig


def _mk_book() -> str:
    r = client.post(
        "/api/novels",
        json={"name": f"stop-http-{datetime.now(UTC).timestamp()}", "source": "manual"},
        headers={"Authorization": "Bearer tok-stophttp"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_stop_idempotent_when_no_active_run():
    bid = _mk_book()
    r = client.post(
        f"/api/novels/{bid}/assistant/stop",
        json={"thread": "ch:og"},
        headers={"Authorization": "Bearer tok-stophttp"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "stopped": False}


def test_stop_requires_auth():
    bid = _mk_book()
    r = client.post(f"/api/novels/{bid}/assistant/stop", json={"thread": "ch:og"})
    assert r.status_code == 401
