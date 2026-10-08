# backend/http_client.py
"""出网 HTTP 客户端统一工厂（c-httpx-socks-fallback）。

后端全部出网 httpx 调用经此构造（AsyncClient×7＋同步 Client×2；openai/anthropic
SDK 内部自建 client 不经此——由 httpx[socks] 依赖覆盖）。

为什么需要工厂：httpx trust_env=True 读系统代理与环境变量，SOCKS 形态代理在
构造期即 `import socksio`——打包产物缺该包时 AsyncClient/Client 构造直接抛
ImportError，调用期 except（Timeout/RequestError）接不住，业务端点 500
（2026-10-08 用户实机实锤：SOCKS 系统代理下 check-auth/update-check 连续 500、
登录检测永久失败）。工厂把构造期异常收敛为「降级 trust_env=False 直连重建」：
代理配置问题最坏退化为直连，绝不 500（spec outbound-http-client）。

两条实现硬约束（design D3，破坏即静默炸测试/漏参数）：
- 晚绑定：必须以 `httpx.AsyncClient(...)`/`httpx.Client(...)` 模块属性形态调用，
  不得 `from httpx import AsyncClient` 导入期绑定——既有测试夹具
  `monkeypatch.setattr(<模块>.httpx, "AsyncClient", fake)` 依赖属性拦截。
- kwargs 全量透传：timeout/follow_redirects/transport 等原样传给真 client。
"""

import logging
import urllib.parse
import urllib.request
from typing import Any

import httpx

logger = logging.getLogger("http_client")


def _redact(url: str) -> str:
    """单条代理 URL 脱敏：只留 scheme＋host:port，剔除 userinfo。

    代理 URL 可能内嵌凭据（socks5://user:pass@host:port），app.log 是回传用户的
    求诊文件——ai_client._host_of 判例：完整 URL 不进日志。
    """
    try:
        u = urllib.parse.urlsplit(url if "//" in url else f"//{url}", scheme="http")
        host = u.hostname or "?"
        if u.port:
            host = f"{host}:{u.port}"
        return f"{u.scheme}://{host}"
    except ValueError:
        return "<malformed>"


def _proxy_summary() -> str:
    """当前进程可见的代理配置摘要（降级留痕用；无凭据）。"""
    try:
        proxies = dict(urllib.request.getproxies())
    except Exception:  # noqa: BLE001 — 摘要失败不影响降级本身
        return "<getproxies failed>"
    if not proxies:
        return "none"
    return ",".join(f"{k}={_redact(str(v))}" for k, v in sorted(proxies.items()))


def _log_degrade(exc: Exception) -> None:
    logger.warning(
        "event=outbound_client_degrade exc=%s proxies=%s —— 降级直连（trust_env=False）",
        exc,
        _proxy_summary(),
    )


def build_async_client(**kwargs: Any) -> httpx.AsyncClient:
    """出网 AsyncClient 统一入口；构造期异常降级 trust_env=False 直连重建。

    只接构造期异常（代理配置类：ImportError/畸形代理 ValueError 等）；构造成功后
    的使用期异常不接——那是各调用点既有错误路径（Timeout/RequestError → code=-1）。
    """
    try:
        return httpx.AsyncClient(**kwargs)
    except Exception as exc:  # noqa: BLE001 — 降级是本工厂的存在理由，见模块 docstring
        _log_degrade(exc)
        return httpx.AsyncClient(**{**kwargs, "trust_env": False})


def build_sync_client(**kwargs: Any) -> httpx.Client:
    """出网同步 Client 统一入口；降级语义与 build_async_client 相同。"""
    try:
        return httpx.Client(**kwargs)
    except Exception as exc:  # noqa: BLE001 — 同上
        _log_degrade(exc)
        return httpx.Client(**{**kwargs, "trust_env": False})
