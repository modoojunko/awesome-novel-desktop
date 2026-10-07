"""backend-logging：请求日志中间件判据（openspec/changes/c-backend-daily-logging 2.3）。

一行一条含耗时；/api/health 豁免；最外层次序（被内层 403 短路的请求仍落行）；
流式响应不被缓冲；异常路径 finally 记 500。
"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from request_logging import RequestLoggingMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def _deny_localguard(request, call_next):  # 模拟 loginless guard（内层）
        if request.url.path == "/denied":
            return JSONResponse(status_code=403, content={"detail": "仅限本机访问"})
        return await call_next(request)

    # 契约（D6）：必须在全部 add_middleware 之后注册＝最外层
    app.add_middleware(RequestLoggingMiddleware)

    @app.post("/ok")
    async def _ok():
        return {"status": "ok"}

    @app.get("/api/health")
    async def _health():
        return {"status": "ok"}

    @app.get("/boom")
    async def _boom():
        raise RuntimeError("kaboom")

    async def _chunks():
        for part in ("甲", "乙", "丙"):
            yield part

    @app.get("/stream")
    async def _stream():
        return StreamingResponse(_chunks(), media_type="text/plain")

    return app


@pytest.fixture()
def records(caplog):
    caplog.set_level(logging.INFO, logger="api.request")
    return caplog


def test_post_success_logs_one_line_with_duration(records):
    client = TestClient(_build_app())
    resp = client.post("/ok")
    assert resp.status_code == 200
    lines = [r for r in records.records if r.name == "api.request"]
    assert len(lines) == 1, f"一次调用一行（实际 {len(lines)}）"
    msg = lines[0].getMessage()
    assert "POST /ok 200" in msg and "ms" in msg


def test_inner_403_short_circuit_still_logged(records):
    """外层次序判据：被安全中间件短路拦下的 403 也要落行（攻击可见性）。"""
    client = TestClient(_build_app())
    resp = client.get("/denied")
    assert resp.status_code == 403
    msgs = [r.getMessage() for r in records.records if r.name == "api.request"]
    assert any("GET /denied 403" in m for m in msgs), msgs


def test_health_exempt(records):
    client = TestClient(_build_app())
    for _ in range(3):
        client.get("/api/health")
    assert [r for r in records.records if r.name == "api.request"] == [], "探活不落行"


def test_streaming_not_buffered(records):
    client = TestClient(_build_app())
    with client.stream("GET", "/stream") as resp:
        body = b"".join(resp.iter_raw()).decode("utf-8")
    assert body == "甲乙丙", "流式体必须逐块透传（顺序与完整性）"
    msgs = [r.getMessage() for r in records.records if r.name == "api.request"]
    assert len(msgs) == 1 and "GET /stream 200" in msgs[0]


def test_uncaught_exception_logs_500(records):
    client = TestClient(_build_app(), raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500
    msgs = [r.getMessage() for r in records.records if r.name == "api.request"]
    assert any("GET /boom 500" in m for m in msgs), "异常路径 finally 兜底记 500"
