"""登录限流阈值 env 化（e2e-speedup-infra）— 函数级 + 独立 app 行为级。

RATE_LIMIT_LOGIN_PER_MIN：缺省/空/非正整数一律回落默认 30（生产不变）。
滑动窗口口径（60s、仅 POST、仅敏感路径、429 形状）不变。

注：LIMIT 在类定义时求值（进程启动口径），故行为级测试直接在独立
Starlette 实例上覆写 LIMIT，不依赖 monkeypatch 改已导入模块的类属性。
"""

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.interfaces.middleware import RateLimitMiddleware, _login_rate_limit


def test_default_limit_is_30(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_LOGIN_PER_MIN", raising=False)
    assert _login_rate_limit() == 30


@pytest.mark.parametrize("raw", ["", "   ", "abc", "0", "-5"])
def test_invalid_values_fall_back_to_30(monkeypatch, raw):
    monkeypatch.setenv("RATE_LIMIT_LOGIN_PER_MIN", raw)
    assert _login_rate_limit() == 30


def test_env_override_takes_effect(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_LOGIN_PER_MIN", "600")
    assert _login_rate_limit() == 600


def _mini_client(limit: int) -> TestClient:
    async def login(request):
        return JSONResponse({"code": 0})

    app = Starlette(routes=[Route("/api/web/login", login, methods=["POST", "GET"])])
    client = TestClient(RateLimitMiddleware(app))
    client.app_state_mw = None  # noqa: 占位说明——LIMIT 经实例属性覆写（影子类属性）
    # RateLimitMiddleware 的 LIMIT 在类体求值；此处按测试阈值覆写实例生效。
    # 通过 MRO 找到被 wrap 的中间件实例：
    mw = _unwrap_middleware(client)
    mw.LIMIT = limit
    return client


def _unwrap_middleware(client: TestClient) -> RateLimitMiddleware:
    """从 TestClient 的 middleware_stack 里找到 RateLimitMiddleware 实例。"""
    node = client.app
    while node is not None:
        if isinstance(node, RateLimitMiddleware):
            return node
        node = getattr(node, "app", None)
    raise AssertionError("RateLimitMiddleware not found in stack")


def test_threshold_blocks_with_429_shape():
    client = _mini_client(limit=2)
    assert client.post("/api/web/login", json={}).status_code == 200
    assert client.post("/api/web/login", json={}).status_code == 200
    r = client.post("/api/web/login", json={})
    assert r.status_code == 429
    assert r.json() == {"code": 2, "msg": "请求过于频繁，请稍后再试"}


def test_get_on_sensitive_path_not_limited():
    client = _mini_client(limit=1)
    for _ in range(5):
        assert client.get("/api/web/login").status_code == 200


def test_window_semantics_unchanged():
    assert RateLimitMiddleware.WINDOW == 60
    assert "/api/web/login" in RateLimitMiddleware.SENSITIVE_PATHS
    assert "/api/authorize" in RateLimitMiddleware.SENSITIVE_PATHS
