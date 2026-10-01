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


def _sensitive_path(path: str) -> bool:
    """敏感路径判定：带前缀形态与剥 /api 前缀形态同判（网关转发形态=剥前缀）。

    在限流器内部归一化，不依赖中间件注册顺序——实测本仓 Starlette 1.6/FastAPI 组合下
    add_middleware 的实际嵌套顺序与"后 add 者在外层"的经典假设不符，
    而"限流先于归一化执行"正是 2026-09-18 审计的绕过成因（/web/login 35 次全 200）。
    判定只看固定清单，未引入路由表依赖：候选 = "/api" + path。
    """
    if path in RateLimitMiddleware.SENSITIVE_PATHS:
        return True
    return not path.startswith("/api/") and f"/api{path}" in RateLimitMiddleware.SENSITIVE_PATHS


def _trusted_proxy_hops() -> int:
    """可信反代跳数：TRUSTED_PROXY_HOPS，缺省/空/非法一律 0（=不信任 XFF，回落 client.host）。

    0 与历史行为一致（直连/无 XFF 场景）。>0 时取 X-Forwarded-For 的**右起第 hops 跳**
    （最近可信代理注入的那一跳）——取最左段是错的：本仓反代用
    `$proxy_add_x_forwarded_for`（追加语义），最左段由客户端自带、可伪造，
    按它计数等于把限流桶交给攻击者（轮换该头即换桶）。
    生产（云托管网关）XFF 行为实测后再开启（见 _log_proxy_probe）。
    """
    raw = os.environ.get("TRUSTED_PROXY_HOPS", "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return max(0, value)


def _client_key(request) -> str:
    """限流/背压的来源键：默认真实对端；配置可信跳数后按 XFF 右起第 hops 跳取。"""
    hops = _trusted_proxy_hops()
    peer = request.client.host if request.client else "unknown"
    if hops <= 0:
        return peer
    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if len(parts) >= hops:
        import ipaddress

        candidate = parts[-hops]
        # 去 IPv6 方括号/IPv4:port 端口后校验；解析失败回落真实对端
        for probe in (candidate, candidate.strip("[]"), candidate.rsplit(":", 1)[0]):
            try:
                return str(ipaddress.ip_address(probe))
            except ValueError:
                continue
    return peer


_PROXY_PROBE_DONE = False


def _log_proxy_probe(request) -> None:
    """XFF 行为探针（临时，实测期）：信任跳数未开且带 XFF 时记录真实链路。

    用于实测云托管网关/本地反代的 XFF 注入语义，回填 design Open Question 后移除。
    每进程仅采样一次——网关注入语义对部署形态是常量，无需逐请求记录刷日志。
    """
    global _PROXY_PROBE_DONE
    if _PROXY_PROBE_DONE or _trusted_proxy_hops() > 0:
        return
    xff = request.headers.get("x-forwarded-for", "")
    if not xff:
        return
    _PROXY_PROBE_DONE = True
    peer = request.client.host if request.client else "unknown"
    logger.info("event=proxy_probe peer=%s xff=%s x_real_ip=%s",
                peer, xff, request.headers.get("x-real-ip", ""))


class RateLimitMiddleware(BaseHTTPMiddleware):
    """基于来源键的速率限制（凭据校验类端点）。"""

    # 清单覆盖全部凭据校验入口（s-security-hardening）：登录/注册/设备授权/密保找回/
    # 改密/注销受理与撤销/配对交换/激活码兑换（s-code-redeem：凭码开通权益，
    # 同属可爆破凭据入口）。路径按**归一化后**形态书写——前缀归一化中间件在
    # 本中间件外层执行（见 register_middleware），剥 /api 前缀的形态与带前缀形态同桶。
    # 新增凭据校验端点必须同步加入清单（tests/test_rate_limit_bypass.py 有对拍测试防漏）。
    SENSITIVE_PATHS = {
        "/api/web/login",
        "/api/web/register",
        "/api/authorize",
        "/api/reset_password",
        "/api/user/password",
        "/api/user/deletion",
        "/api/user/deletion/revoke",
        "/api/pair/exchange",
        "/api/pay/codes/redeem",
    }
    # 30：吸收 E2E 套件的登录突发（/api/web/login）；C端 轮询走 GET
    # /api/check-auth 不受限，30/min/IP 仍可防爆破，避免误伤多管理员同网段
    LIMIT = _login_rate_limit()
    WINDOW = 60  # 秒

    def __init__(self, app):
        super().__init__(app)
        self._history: dict[str, list[float]] = defaultdict(list)

    def _prune(self, now: float) -> None:
        """淘汰窗口外的历史键，防长跑实例内存随来源数增长。"""
        if len(self._history) < 1024:
            return
        cutoff = now - self.WINDOW
        for key in [k for k, stamps in self._history.items() if not stamps or stamps[-1] <= cutoff]:
            self._history.pop(key, None)

    async def dispatch(self, request: Request, call_next):
        _log_proxy_probe(request)
        if _sensitive_path(request.url.path) and request.method == "POST":
            ip = _client_key(request)
            now = time.time()
            cutoff = now - self.WINDOW
            self._history[ip] = [t for t in self._history[ip] if t > cutoff]
            self._prune(now)
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
    """注册顺序沿用历史（CORS → 前缀归一化 → 限流 → 访问日志的**实际执行序**由
    add_middleware 的嵌套语义决定，本仓实测为后 add 者在外层）。

    注意：限流与归一化的先后**不再是正确性依赖**——敏感路径判定已内置两形态归一
    （见 _sensitive_path），注册顺序各版本一致的行为由该函数保证；
    访问日志保留在最外层（429 与原始路径照常可见）。
    """
    # CORS 显式白名单（s-security-baseline R6）：默认空=不允许浏览器跨域。
    # 生产 MUST 显式列入门户实际域名（统一域名 www 与静态托管默认域）；
    # 浏览器调用全部同源（门户 /api 分流、本地 nginx 反代、vite proxy、C端 走本机后端），
    # CORS 仅对"静态托管默认域直访门户"这一形态有意义。
    allow_origins = [o.strip() for o in os.environ.get("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    if api_paths is not None:
        app.add_middleware(ApiPathNormalizeMiddleware, api_paths=api_paths)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AccessLogMiddleware)
