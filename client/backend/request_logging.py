# backend/request_logging.py
"""请求日志中间件（backend-logging D6）：一行一条、含耗时。

纯 ASGI 中间件而非 BaseHTTPMiddleware：不缓冲、不碰流式响应体——正文流式现场
保护（#663）语义零干扰。注册次序契约：必须在 main.py 全部 add_middleware
（CORS、loginless guard）**之后**注册＝最外层，被安全中间件短路拦下的响应
（403 等）也要落行（攻击可见性是排障刚需）。/api/health 豁免（壳层就绪探测
与前端轮询不刷屏）。
"""

import logging
import time

logger = logging.getLogger("api.request")

_HEALTH_PATH = "/api/health"


class RequestLoggingMiddleware:
    """捕获 status＋perf_counter 耗时，响应完成后落一行 INFO。

    异常路径在 finally 兜底记 500（Starlette 的 ServerErrorMiddleware 在更外层
    把未捕获异常转成 500 响应，本层看不到那次 send，须自行推断）。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") == _HEALTH_PATH:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "-")
        path = scope.get("path", "-")
        status = 500
        start = time.perf_counter()

        async def send_wrapper(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info("%s %s %s %.0fms", method, path, status, duration_ms)
