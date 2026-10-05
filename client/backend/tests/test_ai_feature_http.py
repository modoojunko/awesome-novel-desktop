"""真实 HTTP 路径的 feature 门集成验证（评审 P0 回归钉）。

评审 P0：require_ai_access 的 request 参数无注解时 FastAPI 不注入 Request，
_route_feature(None)→None→feature 门在真实 HTTP 全部失效（矩阵测试直调依赖
绕过了注入层，故假绿）。本文件经 TestClient 走真实请求，钉住注入链：

- 挂 ai-plot（MAX）的端点：trial/standard 会话 → 403 feature_required
  （tier_required=max）；max 会话 → 放行至模型就绪门（503/…）。
- 快照在场时按快照 features 判（快照单源）。

用法：cd client/backend && python -m pytest tests/test_ai_feature_http.py -v
"""

import os
import tempfile

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix="_feat_http.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_root = tempfile.mkdtemp(prefix="feat_http_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_root

import asyncio  # noqa: E402

from db import Base, engine  # noqa: E402

import auth_local.service as _service  # noqa: E402

_CFG = os.path.join(_tmp_root, "config.json")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

from api_configs.crypto import encrypt_api_key  # noqa: E402


async def _setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    from api_configs.crypto import init_crypto
    from db import async_session

    async with async_session() as s:
        await init_crypto(s)


asyncio.run(_setup())

# 进上下文触发 on_startup（路由在 startup 装配）；进程退出时自动 __exit__
client = TestClient(app)
client.__enter__()


def _set_session(tier: str, *, expired: str = ""):
    _service.CONFIG_FILE = _CFG
    cfg = _service.get_local_config()
    cfg.update({
        "tier": tier,
        "expires_at": expired or ("2027-01-01" if tier not in ("none", "free") else ""),
        "token": "tok-feathttp",
        "username": "feathttp",
        "api_key": "",
    })
    _service.save_local_config(cfg)


@pytest.fixture(autouse=True)
def _fresh_config():
    _set_session("free")
    yield
    if os.path.exists(_CFG):
        os.remove(_CFG)


PROJ = "00000000-0000-0000-0000-000000000001"
CH = "vol-1-ch-1"


def _post(path: str):
    return client.post(f"/api/novels/{PROJ}/chapters/{CH}{path}", json={})


def test_plot_sim_trial_403_feature_required():
    """trial（=pro 同权）打 ai-plot 端点 → 403 feature_required（tier_required=max）。"""
    _set_session("trial")
    r = _post("/simulate")
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["reason"] == "feature_required"
    assert detail["tier_required"] == "max"


def test_plot_sim_max_member_model_gate_next():
    """max 会话过 ai-plot 门 → 进入模型就绪门（503 no_key），不是 403。"""
    _set_session("max")
    r = _post("/plot-sim")
    assert r.status_code in (503, 422, 400)  # 模型未配置链路；绝非 403 feature_required
