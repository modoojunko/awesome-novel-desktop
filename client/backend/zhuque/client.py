"""朱雀（腾讯 EdgeOne Makers 网关）AIGC 文本检测客户端。

c-zhuque-ai-detect：前端零直连——本模块是唯一出网点，base_url 可经
``ZHUQUE_API_BASE`` 环境变量覆写（测试/e2e 桩替换指向本地 stub）。

httpx.AsyncClient 直连（同 api_configs/connection.py 惯例，不进 AIClient/SDK——
anthropic 迁 httpx2 后拒收 httpx.Timeout 的坑只在 SDK 路径）。同步模式：
网关推理 5–15 秒为常态，read 给足 90s；上游分段数与本地非空段数不符时由
调用方（service.check_chapter）落 502。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

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
    try:
        async with httpx.AsyncClient(timeout=timeout()) as client:
            resp = await client.post(
                f"{base_url()}{CLASSIFY_PATH}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": text, "is_merge": True},
            )
    except httpx.TimeoutException as e:
        raise ZhuqueUpstreamError(0, "朱雀服务响应超时，请稍后重试") from e
    except httpx.HTTPError as e:
        raise ZhuqueUpstreamError(0, "无法连接朱雀服务，请检查网络后重试") from e

    if resp.status_code == 401 or resp.status_code == 403:
        raise ZhuqueUpstreamError(resp.status_code, "API Key 无效或已失效")
    if resp.status_code == 429:
        detail = _error_message(resp) or "触发限流或本月免费额度已用完（以腾讯云控制台为准）"
        raise ZhuqueUpstreamError(429, detail)
    if resp.status_code >= 500:
        raise ZhuqueUpstreamError(resp.status_code, "朱雀服务暂时不可用，请稍后重试")
    if resp.status_code != 200:
        raise ZhuqueUpstreamError(resp.status_code, f"朱雀返回异常（{resp.status_code}）")

    data = resp.json()
    if not isinstance(data, dict) or data.get("status") != "success":
        raise ZhuqueUpstreamError(
            resp.status_code, _error_message(resp) or "朱雀返回了无法解析的结果"
        )
    return data


def _error_message(resp: httpx.Response) -> str | None:
    try:
        err = resp.json().get("error") or {}
        msg = err.get("message")
        return str(msg) if msg else None
    except Exception:  # noqa: BLE001 — 非 JSON 体按无消息处理
        return None
