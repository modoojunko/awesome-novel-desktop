"""中间件：访问日志、request_id、CORS、速率限制。"""
from __future__ import annotations

import logging
import os
import time
import uuid
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.infrastructure.logging import RequestIDFilter

logger = logging.getLogger("api.access")


def _login_rate_limit() -> int:
    """登录限流阈值：RATE_LIMIT_LOGIN_PER_MIN，缺省/空/非正整数一律回落 30。

    生产部署链路不注入该变量，行为与历史版本完全一致；仅本地测试栈
    （docker-compose）注入高值吸收 e2e 登录突发（e2e-speedup-infra）。
    """
    raw = os.environ.get("RATE_LIMIT_LOGIN_PER_MIN", "").strip()
    if not raw:
        return 30
    try:
        value = int(raw)
    except ValueError:
        return 30
    return value if value > 0 else 30


class RateLimitMiddleware(BaseHTTPMiddleware):
    """基于 IP 的速率限制。"""

    SENSITIVE_PATHS = {"/api/authorize", "/api/web/login"}
    # 5→30：吸收 E2E 套件的登录突发（/api/web/login）；C端 轮询走 GET
    # /api/check-auth 不受限，30/min/IP 仍可防爆破，避免误伤多管理员同网段
    LIMIT = _login_rate_limit()
    WINDOW = 60  # 秒

    def __init__(self, app):
        super().__init__(app)
        self._history: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.SENSITIVE_PATHS and request.method == "POST":
            ip = request.client.host if request.client else "unknown"
            now = time.time()
            cutoff = now - self.WINDOW
            self._history[ip] = [t for t in self._history[ip] if t > cutoff]
            if len(self._history[ip]) >= self.LIMIT:
                logger.warning("event=rate_limit_exceeded ip=%s path=%s", ip, request.url.path)
                return JSONResponse(
                    status_code=429,
                    content={"code": 2, "msg": "请求过于频繁，请稍后再试"},
                )
            self._history[ip].append(now)
        return await call_next(request)


class AccessLogMiddleware(BaseHTTPMiddleware):
    """记录所有请求的访问日志 + 设置 request_id contextvar。"""

    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:6]
        RequestIDFilter.set(request_id)
        start = time.time()
        response = await call_next(request)
        dur_ms = int((time.time() - start) * 1000)
        logger.info(
            "%s %s -> %s dur=%dms",
            request.method, request.url.path, response.status_code, dur_ms,
        )
        return response


class ApiPathNormalizeMiddleware:
    """域名按路径路由兼容层：补回被网关剥掉的 /api 前缀。

    线上统一域名上配了「/api/ → S端后端」的路由规则，转发时会剥掉这截
    /api（后端收到的请求不带它）；而后端路由本身以 /api 开头硬编码声明。
    本中间件在进入路由前，把「命中既有路由的非 /api 形态」请求内部改写为
    带 /api 的形态——即同一路由同时接受 带前缀/剥前缀 两种进法：
      /web/login   （网关剥过）→ 内部按 /api/web/login 匹配
      /api/web/login（直连云托管域名，保持原样）
    仅匹配启动时收集到的路由表（静态路径精确匹配；含 {param} 的动态路径
    按段匹配——段数相等且非参数段一致，如
      /pay/orders/S123   （网关剥过）→ 内部按 /api/pay/orders/{order_no} 匹配
    ），其余路径原样放行。
    """

    def __init__(self, app, api_paths: frozenset[str]):
        self.app = app
        self._exact = {p for p in api_paths if "{" not in p}
        self._templates = [p.split("/") for p in api_paths if "{" in p]

    def _matches(self, candidate: str) -> bool:
        if candidate in self._exact:
            return True
        segs = candidate.split("/")
        for tpl in self._templates:
            if len(tpl) != len(segs):
                continue
            if all(a.startswith("{") or a == b for a, b in zip(tpl, segs)):
                return True
        return False

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path and not path.startswith("/api/") and self._matches(f"/api{path}"):
                scope = dict(scope)
                scope["path"] = f"/api{path}"
                if "raw_path" in scope:
                    scope["raw_path"] = scope["path"].encode()
                logger.info("event=api_path_normalized from=%s to=%s", path, scope["path"])
        await self.app(scope, receive, send)


def register_middleware(app, api_paths: frozenset[str] | None = None):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if api_paths is not None:
        # 最外层注册 = 最先执行：限流/访问日志看到的都是归一化后的路径
        app.add_middleware(ApiPathNormalizeMiddleware, api_paths=api_paths)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AccessLogMiddleware)
