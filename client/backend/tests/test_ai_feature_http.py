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
from datetime import UTC, datetime  # noqa: E402

import auth_local.service as _service  # noqa: E402
from db import Base, engine  # noqa: E402

_CFG = os.path.join(_tmp_root, "config.json")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402 —— main 导入即注册全部模型到 Base.metadata


async def _setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    from api_configs.crypto import init_crypto
    from db import async_session

    async with async_session() as s:
        await init_crypto(s)


asyncio.run(_setup())

# startup（路由装配/db_lifecycle）挪进 session fixture：模块导入期启动 app 会
# 与 conftest 的共享测试库竞态（本次套件级红实测根因）。
client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def _startup():
    # 保存 middleware 原始 CONFIG_FILE（后续测试按 import 快照引用它，必须还原）
    import auth_local.middleware as _mw
    _orig = _mw.CONFIG_FILE
    with client:
        yield
    _mw.CONFIG_FILE = _orig


def _set_session(tier: str, *, expired: str = ""):
    # 双 CONFIG_FILE 同步重定向：middleware 有自己的模块级 CONFIG_FILE/token 校验
    # （不读 service.CONFIG_FILE），只改 service 侧会 401（本次套件红实测根因）。
    import auth_local.middleware as _mw
    _mw.CONFIG_FILE = _CFG
    _service.CONFIG_FILE = _CFG
    cfg = _service.get_local_config()
    cfg.update({
        "tier": tier,
        "expires_at": expired or ("2027-01-01" if tier not in ("none", "free") else ""),
        "token": "tok-feathttp",
        "username": "feathttp",
        # 会话新鲜度（middleware 30 天窗）：套件中别的测试可能把时钟/状态搅动，
        # 固定写「现在」保证 401 不因新鲜度拦截抢在档位门之前
        "last_login_at": datetime.now(UTC).isoformat(),
        "api_key": "",
    })
    _service.save_local_config(cfg)


@pytest.fixture(autouse=True)
def _fresh_config():
    import auth_local.middleware as _mw
    _orig = _mw.CONFIG_FILE
    _set_session("free")
    yield
    if os.path.exists(_CFG):
        os.remove(_CFG)
    _mw.CONFIG_FILE = _orig


PROJ = "00000000-0000-0000-0000-000000000001"
CH = "vol-1-ch-1"


def _post(path: str):
    return client.post(f"/api/novels/{PROJ}/chapters/{CH}{path}", json={},
                       headers={"Authorization": "Bearer tok-feathttp"})


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
    r = _post("/simulate")
    assert r.status_code in (503, 422, 400)  # 模型未配置链路；绝非 403 feature_required
