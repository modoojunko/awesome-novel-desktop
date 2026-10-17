"""拆书模型调用失败策略（c-deconstruct-resilience D1）——错误分类＋重试/退避口径单源。

口径（design.md D1 矩阵）：
- 瞬时错误（timeout / rate_limit / upstream_5xx）：有限重试＋指数退避（全抖动），
  429 优先遵循 Retry-After；单元重试穷尽才计入熔断——单个 429 不熔断；
- 确定性错误（auth 401/403、config 400 参数、route 404/405）：一次定生死，重试无意义；
- content_filter（1301/contentFilter）：不重试，由管线按单元隔离（跳过＋告警）；
- truncated / invalid_output（空 200、非 JSON、JSON 不完整）：不原样重试，
  由管线拆组或提预算（bisect），同输入同预算重发注定同败（真机实证：
  characters/world reduce 输出 8192 截断后 3 连败）；
- 拆书链 SDK 层 max_retries=0（resolve_client 构造时传 0），重试只住本模块一层，
  杜绝「管线 3 次 × SDK 2 次」的乘法放大。

错误分类测试锚点：GLM 内容审核拒绝的报错形态是
「Error code: 400 - {'contentFilter': [...]}」——文本判 contentFilter 必须先于
按 status_code=400 的 config 归类。
"""

from __future__ import annotations

import asyncio
import os
import random

# ── 错误类别（error.kind；任务级与单元级共用同一词表）───────────────────────
KIND_TIMEOUT = "timeout"
KIND_RATE_LIMIT = "rate_limit"
KIND_UPSTREAM = "upstream"
KIND_AUTH = "auth"
KIND_CONFIG = "config"
KIND_ROUTE = "route"
KIND_CONTENT_FILTER = "content_filter"
KIND_INVALID_OUTPUT = "invalid_output"
KIND_TRUNCATED = "truncated"
KIND_UNKNOWN = "unknown"

# 瞬时类：单元级有限重试；穷尽后计入熔断连续失败。
# unknown 归瞬时：身份不明的异常更像网络/SDK 抖动；确定性业务错误（鉴权/参数/
# 路由/审核/截断）都带得上面的正名形态，不会落到 unknown——这是存量「未知也重试」
# 口径的保留（test_unit_retry_then_success 的 RuntimeError 3 发钉）。
# invalid_output（空 200 / 输出不是 JSON）也归瞬时：模型非确定性，同输入重试
# 换得正常输出是常态（存量口径）；truncated（JSON 不完整/finish_reason=length）
# 是预算型确定性失败，重试同尺寸注定同败——走拆半/提预算，不进这里。
TRANSIENT_KINDS = frozenset({KIND_TIMEOUT, KIND_RATE_LIMIT, KIND_UPSTREAM, KIND_UNKNOWN,
                             KIND_INVALID_OUTPUT})

# 单元总尝试次数（含首发；替换旧 SEGMENT_RETRIES=2 的「+1」写法）
RETRY_MAX_ATTEMPTS = 3
BACKOFF_BASE = 1.0
BACKOFF_CAP = 30.0
RETRY_AFTER_CAP = 120.0

# 文案（失败面板按 kind 出口；可点击出口由前端拼装）
KIND_LABELS = {
    KIND_TIMEOUT: "模型响应超时",
    KIND_RATE_LIMIT: "模型限流（429）",
    KIND_UPSTREAM: "模型服务暂不可用",
    KIND_AUTH: "API Key 无效或无权限",
    KIND_CONFIG: "请求参数或模型配置不被接受",
    KIND_ROUTE: "接口地址或格式不对",
    KIND_CONTENT_FILTER: "内容被模型安全审核拒绝",
    KIND_INVALID_OUTPUT: "模型返回了无法解析的输出",
    KIND_TRUNCATED: "输出超出预算被截断",
    KIND_UNKNOWN: "未知错误",
}


class UnitError(Exception):
    """带分类的单元级失败——管线据此决定重试 / 隔离 / 熔断 / 降级。"""

    def __init__(self, kind: str, message: str, retry_after: float | None = None):
        self.kind = kind
        self.message = message
        self.retry_after = retry_after
        super().__init__(message)

    @property
    def transient(self) -> bool:
        return self.kind in TRANSIENT_KINDS


def classify(e: Exception) -> str:
    """异常 → 错误类别。文本判定（contentFilter/429/JSON 形态）先于状态码兜底。"""
    from ai_client import AITimeoutError  # 局部导入：ai_client 不反向依赖本模块

    if isinstance(e, UnitError):
        return e.kind
    msg = str(e)
    low = msg.lower()
    status = getattr(e, "status_code", None)
    if isinstance(e, AITimeoutError):
        return KIND_TIMEOUT
    if "contentfilter" in low or "1301" in msg:
        # 先于 400：GLM 拒绝形态是「Error code: 400 - {'contentFilter': …}」
        return KIND_CONTENT_FILTER
    if status == 429 or "429" in msg or "rate limit" in low:
        return KIND_RATE_LIMIT
    if status in (401, 403):
        return KIND_AUTH
    if status == 400:
        return KIND_CONFIG
    if status in (404, 405):
        return KIND_ROUTE
    if isinstance(status, int) and status >= 500:
        return KIND_UPSTREAM
    if "模型输出 JSON 不完整" in msg:
        return KIND_TRUNCATED
    if "模型输出不是 JSON" in msg or "模型未返回文本内容" in msg:
        return KIND_INVALID_OUTPUT
    if isinstance(e, (TimeoutError, ConnectionError)):
        return KIND_TIMEOUT
    return KIND_UNKNOWN


def _status_of(e: Exception) -> int | None:
    status = getattr(e, "status_code", None)
    return status if isinstance(status, int) else None


def retry_after_of(e: Exception) -> float | None:
    """429 的 Retry-After（秒）；拿不到返回 None。SDK 状态错误挂 response.headers。"""
    response = getattr(e, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        raw = headers.get("retry-after") or headers.get("Retry-After")
        return min(float(raw), RETRY_AFTER_CAP) if raw else None
    except (TypeError, ValueError):
        return None


def backoff_seconds(attempt: int, retry_after: float | None = None) -> float:
    """第 attempt 次失败后的等待秒数：Retry-After 优先，其余指数退避＋全抖动。

    DECONSTRUCT_BACKOFF_SCALE（默认 1）整体缩放——测试环境 conftest 置 0，
    退避语义单测用捕获入参断言，不吃真实等待。
    """
    try:
        scale = float(os.environ.get("DECONSTRUCT_BACKOFF_SCALE", "1") or 1)
    except ValueError:
        scale = 1.0
    if retry_after:
        return retry_after * scale
    delay = min(BACKOFF_CAP, BACKOFF_BASE * (2 ** max(0, attempt - 1)))
    return random.uniform(0, delay) * scale


async def cancellable_sleep(seconds: float, cancel_event: asyncio.Event | None) -> None:
    """可被取消打断的退避等待——取消不再等完整退避周期。"""
    if cancel_event is None:
        await asyncio.sleep(seconds)
        return
    try:
        await asyncio.wait_for(cancel_event.wait(), timeout=seconds)
    except TimeoutError:
        return
