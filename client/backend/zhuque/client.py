"""朱雀（腾讯 EdgeOne Makers 网关）AIGC 文本检测客户端。

c-zhuque-ai-detect：前端零直连——本模块是唯一出网点，base_url 可经
``ZHUQUE_API_BASE`` 环境变量覆写（测试/e2e 桩替换指向本地 stub）。

httpx.AsyncClient 直连（同 api_configs/connection.py 惯例，不进 AIClient/SDK——
anthropic 迁 httpx2 后拒收 httpx.Timeout 的坑只在 SDK 路径）。同步模式：
网关推理 5–15 秒为常态，read 给足 90s；上游分段数与本地非空段数不符时由
调用方（service.check_chapter）落 502。

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

# llm.log 专项档挂载点（logging_setup._LLM_LOGGERS 同名登记）
logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ai-gateway.edgeone.link"
CLASSIFY_PATH = "/v1/providers/zhuque-text/classify"


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
    """调 classify：返回网关 JSON（status=success）；失败抛 ZhuqueUpstreamError。"""
    url = f"{base_url()}{CLASSIFY_PATH}"
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout()) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": text, "is_merge": True},
            )
    except httpx.TimeoutException as e:
        _log_classify(url, start, status=0, chars=len(text), result="timeout")
        raise ZhuqueUpstreamError(0, "朱雀服务响应超时，请稍后重试") from e
    except httpx.HTTPError as e:
        _log_classify(
            url, start, status=0, chars=len(text),
            result="network_error", error=str(e),
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
        )
        raise
    _log_classify(url, start, status=resp.status_code, chars=len(text), result="ok")
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
) -> None:
    """classify 一行留痕：成功 INFO / 失败 WARNING。正文只记 chars（隐私红线）。"""
    parts = urlparse(url)
    logger.log(
        logging.INFO if result == "ok" else logging.WARNING,
        "event=llm_probe kind=zhuque_classify vendor=zhuque format=- host=%s path=%s"
        " model=- status=%d duration_ms=%.0f chars=%d result=%s%s",
        parts.netloc, parts.path or "/", status,
        (time.perf_counter() - start) * 1000, chars, result,
        f" error={error[:120]}" if error else "",
    )


def _error_message(resp: httpx.Response) -> str | None:
    try:
        err = resp.json().get("error") or {}
        msg = err.get("message")
        return str(msg) if msg else None
    except Exception:  # noqa: BLE001 — 非 JSON 体按无消息处理
        return None
