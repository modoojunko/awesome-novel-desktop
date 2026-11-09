"""朱雀（腾讯 EdgeOne Makers 网关）AIGC 文本检测客户端。

c-zhuque-ai-detect：前端零直连——本模块是唯一出网点，base_url 可经
``ZHUQUE_API_BASE`` 环境变量覆写（测试/e2e 桩替换指向本地 stub）。

httpx.AsyncClient 直连（同 api_configs/connection.py 惯例，不进 AIClient/SDK——
anthropic 迁 httpx2 后拒收 httpx.Timeout 的坑只在 SDK 路径）。同步模式：
网关推理 5–15 秒为常态，read 给足 90s；上游分段数与本地非空段数不符时由
调用方（service.check_chapter）落 502。

连接相位失败（connect 超时/网络不可达）强制 IPv4 回退重试一次（2026-11-09
真机案：网关 AAAA 可解析但 v6 路由黑洞，v6 优先连接挂满 connect 超时）——
读超时与 HTTP 状态映射不受影响。

留痕（c-llm-call-log）：classify 每次调用恰一行 `llm_probe` 日志（llm.log 专项档
＋app.log 双写）——正文只记字符数（chars），永不落内容；行含 host＋上游状态码
＋耗时＋结果分类。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from http_client import build_async_client

# llm.log 专项档挂载点（logging_setup._LLM_LOGGERS 同名登记）
logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ai-gateway.edgeone.link"
CLASSIFY_PATH = "/v1/providers/zhuque-text/classify"

# 连接相位错误＝IPv4 回退的触发面：connect 超时／连接被拒／网络不可达。读超时
# 不在面内——那是网关推理慢，换地址族无意义（换什么协议都还是要等它算完）。
_CONNECT_PHASE_ERRORS = (httpx.ConnectTimeout, httpx.ConnectError)


def base_url() -> str:
    return os.environ.get("ZHUQUE_API_BASE", DEFAULT_BASE_URL).rstrip("/")


class ZhuqueUpstreamError(Exception):
    """上游可映射错误：status 为上游 HTTP 状态（0=网络/超时）。"""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def timeout() -> httpx.Timeout:
    return httpx.Timeout(connect=10, read=90, write=30, pool=10)


async def classify(text: str, api_key: str) -> dict[str, Any]:
    """调 classify：返回网关 JSON（status=success）；失败抛 ZhuqueUpstreamError。

    连接相位失败（connect 超时／网络不可达）IPv4 回退重试一次（_CONNECT_PHASE_ERRORS
    注）；读超时／HTTP 错误语义不变。留痕仍每调用恰一行，动用回退时行尾 fallback=ipv4。
    """
    url = f"{base_url()}{CLASSIFY_PATH}"
    start = time.perf_counter()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"text": text, "is_merge": True}
    fallback_used = False
    try:
        try:
            async with build_async_client(timeout=timeout()) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except _CONNECT_PHASE_ERRORS:
            # IPv6 黑洞兜底（2026-11-09 真机案）：网关 AAAA 可解析但 v6 路由黑洞
            # （SYN 无应答），本机 v6 优先、httpx 无 happy-eyeballs——首连挂满
            # connect 超时。local_address 绑 v4 通配 → 连接恒 AF_INET（构造零
            # 网络 I/O，回退路径才建）；回退请求的异常原样上抛走下方既有映射。
            fallback_used = True
            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
            async with build_async_client(timeout=timeout(), transport=transport) as client:
                resp = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as e:
        _log_classify(url, start, status=0, chars=len(text), result="timeout",
                      fallback="ipv4" if fallback_used else "")
        raise ZhuqueUpstreamError(0, "朱雀服务响应超时，请稍后重试") from e
    except httpx.HTTPError as e:
        _log_classify(
            url, start, status=0, chars=len(text),
            result="network_error", error=str(e),
            fallback="ipv4" if fallback_used else "",
        )
        raise ZhuqueUpstreamError(0, "无法连接朱雀服务，请检查网络后重试") from e

    try:
        data = _parse_classify(resp)
    except ZhuqueUpstreamError as e:
        # 200 体不符契约（无法解析）单独记 bad_response，其余按状态码机械映射
        result = "bad_response" if 200 <= e.status < 300 else _result_of(e.status)
        _log_classify(
            url, start, status=resp.status_code, chars=len(text),
            result=result, error=e.message,
            fallback="ipv4" if fallback_used else "",
        )
        raise
    _log_classify(url, start, status=resp.status_code, chars=len(text), result="ok",
                  fallback="ipv4" if fallback_used else "")
    return data


def _parse_classify(resp: httpx.Response) -> dict[str, Any]:
    """classify 响应判定（无副作用纯判定）：成功返回网关 JSON；失败抛 ZhuqueUpstreamError。"""
    if resp.status_code == 401 or resp.status_code == 403:
        raise ZhuqueUpstreamError(resp.status_code, "API Key 无效或已失效")
    if resp.status_code == 429:
        detail = _error_message(resp) or "触发限流或本月免费额度已用完（以腾讯云控制台为准）"
        raise ZhuqueUpstreamError(429, detail)
    if resp.status_code >= 500:
        raise ZhuqueUpstreamError(resp.status_code, "朱雀服务暂时不可用，请稍后重试")
    if resp.status_code != 200:
        raise ZhuqueUpstreamError(resp.status_code, f"朱雀返回异常（{resp.status_code}）")

    try:
        data = resp.json()
    except ValueError:
        # 非 JSON 200 体按「无法解析」受控上抛（原实现裸抛 JSONDecodeError → 500）
        raise ZhuqueUpstreamError(
            resp.status_code, _error_message(resp) or "朱雀返回了无法解析的结果"
        ) from None
    if not isinstance(data, dict) or data.get("status") != "success":
        raise ZhuqueUpstreamError(
            resp.status_code, _error_message(resp) or "朱雀返回了无法解析的结果"
        )
    return data


def _result_of(status: int) -> str:
    """上游 HTTP 状态码 → 结果分类（与 connection 探针同口径）。"""
    if 200 <= status < 300:
        return "ok"
    if status in (401, 403):
        return "auth_error"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "server_error"
    if status == 0:
        return "network_error"
    return "http_error"


def _log_classify(
    url: str,
    start: float,
    *,
    status: int,
    chars: int,
    result: str,
    error: str | None = None,
    fallback: str = "",
) -> None:
    """classify 一行留痕：成功 INFO / 失败 WARNING。正文只记 chars（隐私红线）。

    fallback 非空（"ipv4"）＝本次调用动用了 IPv6 黑洞兜底——行尾 fallback=ipv4，
    定诊「首连挂 connect 超时、回退接通」用；未回退＝行形状与既有完全一致。"""
    # 畸形 base 兜底同 connection._probe_target（评审 P2 同批加固；本处 URL 由
    # env/常量构造，生产不可达，纯防御）
    try:
        parts = urlparse(url)
    except ValueError:
        parts = None
    host, path = (parts.netloc, parts.path or "/") if parts else ("-", "-")
    logger.log(
        logging.INFO if result == "ok" else logging.WARNING,
        "event=llm_probe kind=zhuque_classify vendor=zhuque format=- host=%s path=%s"
        " model=- status=%d duration_ms=%.0f chars=%d result=%s%s%s",
        host, path, status,
        (time.perf_counter() - start) * 1000, chars, result,
        f" error={error[:120]}" if error else "",
        f" fallback={fallback}" if fallback else "",
    )


def _error_message(resp: httpx.Response) -> str | None:
    try:
        err = resp.json().get("error") or {}
        msg = err.get("message")
        return str(msg) if msg else None
    except Exception:  # noqa: BLE001 — 非 JSON 体按无消息处理
        return None
