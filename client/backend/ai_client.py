# backend/ai_client.py
"""AI client — provider-agnostic. Supports Anthropic and OpenAI API formats.

C/S 模式下从本地 config.json 动态读取 API Key/Base URL/Model，而不是从 config.py。
"""

import inspect
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from anthropic import APIConnectionError as AnthropicConnectionError
from anthropic import APIStatusError as AnthropicStatusError
from anthropic import APITimeoutError as AnthropicTimeoutError
from anthropic import AsyncAnthropic
from anthropic import Timeout as AnthropicTimeout
from openai import APIConnectionError as OpenAIConnectionError
from openai import APIStatusError as OpenAIStatusError
from openai import APITimeoutError as OpenAITimeoutError
from openai import AsyncOpenAI
from openai import Timeout as OpenAITimeout
from sqlalchemy import select

from api_configs.crypto import decrypt_api_key
from db import async_session
from models.api_config import ApiConfig
from models.project import Novel
from models.user import User

# 判定/短答复类调用默认**关闭思考**：实测（DeepSeek anthropic 端点）延迟
# 10s→1.4s、输出 tokens 2079→203；个别端点不认这个字段则去掉后重试一次，
# 并把该 base 记下来不再重复尝试。
_THINKING_UNSUPPORTED_BASES: set[str] = set()
_THINKING_DISABLED = {"type": "disabled"}

# 超时纪律（ai-client-timeout-and-usage-accounting D1）：不依赖 SDK 默认
# （600s + 重试，最坏一次点击 ~20 分钟）。read=90 覆盖判定类 4096 tokens
# 生成上限；流式 read 是「相邻事件间隔」上限而非总时长，长文持续出 chunk
# 不受影响，供应商挂起 120s 内判死。max_retries=1 收敛最坏等待 ≈3 分钟。
_CHAT_TIMEOUT = httpx.Timeout(connect=10.0, read=90.0, write=30.0, pool=10.0)
_STREAM_READ_TIMEOUT = 120.0

# 网络层失败（超时/连接不通）——归一为 AITimeoutError 对外统一语义。
_NETWORK_ERRORS: tuple[type[Exception], ...] = (
    OpenAITimeoutError,
    OpenAIConnectionError,
    AnthropicTimeoutError,
    AnthropicConnectionError,
    httpx.TimeoutException,
)


class AITimeoutError(Exception):
    """AI 调用网络层失败（超时/连接不通）——区别于供应商拒绝业务参数。"""


class AIRequestError(Exception):
    """上游 HTTP 层拒绝且可归因（404/405＝地址/接口格式不对）——区别于网络层 AITimeoutError。"""


# 上游 HTTP 拒绝（非网络层）：仅 404/405 归一化文案（内测 405 案），其余状态保持
# SDK 原始报错透传——避免把供应商的业务 4xx（限流/参数/鉴权细节）改写成二手信息。
_UPSTREAM_STATUS_ERRORS: tuple[type[Exception], ...] = (
    OpenAIStatusError,
    AnthropicStatusError,
)

# backend-logging（D7）：AI 调用链留痕。每次真实调用（无论成败）一行——
# 成功 INFO、失败 WARNING 带归一化分类；正文/Key 不落日志（只记结果与计数）。
logger = logging.getLogger(__name__)


def _classify_error(e: Exception) -> str:
    """失败分类与 _raise_normalized 同源：超时/上游拒绝/空响应/其他。

    入参可能是归一化后的 AITimeoutError/AIRequestError（chat/chat_stream 出口），
    也可能是原始异常（_guarded 内部路径）——两类都认。"""
    if isinstance(e, (AITimeoutError, *_NETWORK_ERRORS)):
        return "timeout"
    if isinstance(e, AIRequestError):
        return "upstream_reject"
    status = getattr(e, "status_code", None)
    if isinstance(e, _UPSTREAM_STATUS_ERRORS) and status is not None:
        return f"upstream_{status}"
    if isinstance(e, ValueError):
        return "empty_response"
    return type(e).__name__


def _host_of(base_url: str) -> str:
    """供应商主机（只取 host——完整 URL 含路径与可能的 query，不进日志）。"""
    try:
        return urlsplit(base_url).hostname or "-"
    except ValueError:
        return "-"


def _upstream_route_message(exc: Exception, provider: str, base_url: str) -> str:
    """404/405 对外文案：点名实际请求地址与去处，替掉无信息量的裸 `Error code: 405 - {...}`。"""
    status = getattr(exc, "status_code", "?")
    base = (base_url or "").rstrip("/") or "（未填）"
    path = "/chat/completions" if provider == "openai" else "/v1/messages"
    fmt = "OpenAI" if provider == "openai" else "Anthropic"
    return (
        f"模型服务拒绝了请求（HTTP {status}）：当前配置（{fmt} 格式）下实际请求 "
        f"{base}{path}。请到「模型配置」核对 Base URL 与接口格式是否和厂商文档一致"
        "——常见原因是 Base URL 填成了网站地址，或该地址不提供对话接口。"
    )


def _stream_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=10.0, read=_STREAM_READ_TIMEOUT, write=30.0, pool=10.0
    )


# anthropic ≥1.4 把传输层从 httpx 换成 httpx2，并主动拒收任何 MRO 根模块为 httpx
# 的对象（实测构造与请求两级都抛 TypeError）；openai ≥3 传输层同样迁到 httpx2
# （自家 Timeout 即 httpx2.Timeout），当前版本尚容忍 httpx.Timeout。两个 provider
# 都统一换算成各自 re-export 的 Timeout 类：anthropic 是硬要求，openai 是同口径
# 防御（防其后续收紧）。旧版 SDK 的 Timeout 就是 httpx.Timeout，同一写法等价，
# 故不需要按版本分支。逐相位换算以保住 connect/read 的不同口径。
_SDK_TIMEOUTS: dict[str, Any] = {"anthropic": AnthropicTimeout, "openai": OpenAITimeout}


def _to_sdk_timeout(provider: str, t: Any) -> Any:
    """把超时换算成该 provider 传输栈认得的 Timeout 对象。"""
    if not isinstance(t, httpx.Timeout):
        return t  # 非 httpx.Timeout（如秒数）SDK 本来就认，原样透传
    cls = _SDK_TIMEOUTS[provider]
    return cls(connect=t.connect, read=t.read, write=t.write, pool=t.pool)


@dataclass
class StreamEvent:
    text: str = ""
    is_done: bool = False
    # 输出侧 tokens（c-ai-usage-correctness：语义收窄，OpenAI 流不再误记 total）
    tokens: int = 0
    # 输入侧 tokens（anthropic=message_start.input_tokens；OpenAI=prompt_tokens）
    tokens_in: int = 0
    error: str = ""


class AIClient:
    """Provider-agnostic AI client.

    Config (api_key, base_url, model) is passed at construction time.
    Use get_ai_client_for_user() to create one from DB, or get_ai_client()
    for the backward-compatible singleton with DB-first + config.json fallback.
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "deepseek-v4-flash",
        api_format: str | None = None,
        timeout: httpx.Timeout | None = None,
        max_retries: int = 1,
        vendor: str = "",
    ):
        self._provider = "anthropic"  # default
        self._client: Any | None = None
        self._model = model
        self._base_url = base_url
        # 留痕行身份字段（c-llm-call-log）：ApiConfig.vendor，工厂层传入；
        # `__new__` 直装的测试实例可无此属性，_log_call 侧 getattr 兜底
        self._vendor = vendor or ""
        self._init_client(api_key, base_url, api_format, timeout, max_retries)

    def _init_client(
        self,
        api_key: str,
        base_url: str,
        api_format: str | None = None,
        timeout: httpx.Timeout | None = None,
        max_retries: int = 1,
    ):
        """Initialize the underlying API client with the given credentials.

        api_format 显式优先（"openai" | "anthropic"）；None 时退回旧版行为：
        按 base_url 含 "anthropic" 推断（存量 User.api_key / config.json 兜底路径
        无格式信息，保持原推断）。
        timeout/max_retries 显式设置，不依赖 SDK 默认（600s×重试）。
        """
        if not api_key:
            raise ValueError("未配置 API Key，请在设置页面填写")

        provider = "anthropic" if (
            api_format == "anthropic"
            or (api_format is None and "anthropic" in base_url.lower())
        ) else "openai"

        common = {
            "timeout": _to_sdk_timeout(provider, timeout or _CHAT_TIMEOUT),
            "max_retries": max_retries,
        }
        if provider == "anthropic":
            self._provider = "anthropic"
            kwargs = {"api_key": api_key, **common}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = AsyncAnthropic(**kwargs)
        else:
            self._provider = "openai"
            kwargs = {"api_key": api_key, **common}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = AsyncOpenAI(**kwargs)

    def _raise_normalized(self, e: Exception) -> None:
        """异常归一：网络层 → AITimeoutError；上游 404/405 → AIRequestError；其余原样上抛。

        属性只在 404/405 分支读取——业务异常（含裸实例测试路径）不触碰 provider/base_url。
        """
        if isinstance(e, _NETWORK_ERRORS):
            raise AITimeoutError(f"AI 服务连接超时或失败：{e}") from e
        if isinstance(e, _UPSTREAM_STATUS_ERRORS) and getattr(e, "status_code", None) in (
            404,
            405,
        ):
            raise AIRequestError(
                _upstream_route_message(e, self._provider, self._base_url)
            ) from e
        raise e

    async def _guarded(self, coro):
        """网络层失败归一为 AITimeoutError；上游 404/405 归一为 AIRequestError（可诊断）。"""
        try:
            return await coro
        except Exception as e:  # noqa: BLE001 — 归一目标外的异常原样重抛（_raise_normalized 尾行 raise）
            self._raise_normalized(e)

    def _log_call(
        self,
        operation: str,
        model: str,
        start: float,
        *,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        error: Exception | None = None,
        attempt: int = 1,
    ) -> None:
        """一次 provider 调用出口的留痕行（D7）：成功 INFO / 失败 WARNING。

        operation 由调用方传入（与 TokenLog 同名）；不落 API Key 与正文——
        请求侧只计字符数由调用方掌握，本行只含结果与计数。error 截 200 字符
        （httpx 异常文本含上游 URL，无 Key——header 鉴权）。
        """
        duration_ms = (time.perf_counter() - start) * 1000
        op = operation or "-"
        mdl = model or self._model or "-"
        vendor = getattr(self, "_vendor", "") or "-"  # c-llm-call-log 身份字段
        host = _host_of(self._base_url)
        if error is None:
            logger.info(
                "event=ai_call op=%s model=%s vendor=%s host=%s attempt=%s duration_ms=%.0f"
                " tokens_in=%d tokens_out=%d result=ok",
                op, mdl, vendor, host, attempt, duration_ms, tokens_in or 0, tokens_out or 0,
            )
        else:
            logger.warning(
                "event=ai_call op=%s model=%s vendor=%s host=%s attempt=%s duration_ms=%.0f"
                " result=%s error=%s",
                op, mdl, vendor, host, attempt, duration_ms,
                _classify_error(error), str(error)[:200],
            )

    def _supports_temperature(self) -> bool:
        """Anthropic 1.x SDK 的 messages.create 不再接受 temperature（须走 extra_body）。"""
        cached = getattr(self, "_temp_supported", None)
        if cached is None:
            try:
                cached = "temperature" in inspect.signature(
                    self._client.messages.create
                ).parameters
            except (TypeError, ValueError, AttributeError):
                cached = True
            self._temp_supported = cached
        return cached

    def _with_thinking_disabled(self, kwargs: dict) -> dict:
        """默认关闭思考（判定类短答复不划算全预算在推理上）。"""
        base = self._base_url or ""
        if base not in _THINKING_UNSUPPORTED_BASES:
            kwargs.setdefault("thinking", dict(_THINKING_DISABLED))
        return kwargs

    def _remember_thinking_unsupported(self) -> None:
        if self._base_url:
            _THINKING_UNSUPPORTED_BASES.add(self._base_url)

    def _is_thinking_rejection(self, exc: Exception) -> bool:
        return "thinking" in str(exc).lower()

    def _anthropic_kwargs(self, kwargs: dict) -> dict:
        """把 Anthropic 侧不支持的入参落到 extra_body（跨 SDK 版本兼容）。"""
        temperature = kwargs.pop("temperature", None)
        if temperature is None:
            return kwargs
        if self._supports_temperature():
            kwargs["temperature"] = temperature
        else:
            extra = dict(kwargs.pop("extra_body", None) or {})
            extra["temperature"] = temperature
            kwargs["extra_body"] = extra
        return kwargs

    @property
    def model(self) -> str:
        """本客户端实际使用的模型 id（计量/日志用，勿用于业务判断）。"""
        return self._model

    def resolve(self, model_name: str) -> str:
        """Map haiku/sonnet → actual model ID.

        如果传入了自定义模型名，直接使用；否则使用配置的模型。
        """
        if model_name in ("haiku", "sonnet", "review"):
            return self._model
        return model_name

    async def chat(
        self,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        usage: dict | None = None,
        operation: str = "",
        **kwargs: Any,
    ) -> str:
        """Non-streaming. Returns full response text.

        usage: 可选 dict，调用成功后填充 {"tokens_in", "tokens_out"}，供 TokenLog 记录。
        operation: 业务动作名（backend-logging D7 留痕行用，与 TokenLog 同名）。
        """
        model = self.resolve(model)
        start = time.perf_counter()
        if self._provider == "openai":
            openai_messages: list[dict[str, Any]] = []
            if system:
                openai_messages.append({"role": "system", "content": system})
            for m in messages:
                openai_messages.append({"role": m["role"], "content": m["content"]})
            extra = {"thinking": {"type": "disabled"}}
            if "thinking" in kwargs:
                extra["thinking"] = kwargs.pop("thinking")
            # json_mode 分层归属（D12）：业务层只传语义参数，客户端层按 api_format 落地
            if kwargs.pop("json_mode", False):
                kwargs["response_format"] = {"type": "json_object"}
            try:
                response = await self._guarded(
                    self._client.chat.completions.create(
                        model=model,
                        messages=openai_messages,
                        max_tokens=max_tokens,
                        extra_body=extra,
                        **kwargs,
                    )
                )
            except Exception as e:
                self._log_call(operation, model, start, error=e)
                raise
            if usage is not None:
                u = getattr(response, "usage", None)
                # OpenAI 的 prompt_tokens **已含**缓存命中部分（details.cached_tokens
                # 是它的子集），故不再另加，避免重复计数。
                usage["tokens_in"] = getattr(u, "prompt_tokens", 0) or 0
                usage["tokens_out"] = getattr(u, "completion_tokens", 0) or 0
            choices = list(getattr(response, "choices", None) or [])
            if not choices:
                # choices 空（usage-only 响应等）＝无产物：按失败留痕，不记 ok
                # （与 anthropic 无 text 块同口径，评审 P3）
                self._log_call(
                    operation, model, start,
                    tokens_in=(usage or {}).get("tokens_in", 0),
                    tokens_out=(usage or {}).get("tokens_out", 0),
                    error=ValueError("模型未返回文本内容"),
                )
                raise ValueError("模型未返回文本内容（choices 空），请重试")
            self._log_call(
                operation, model, start,
                tokens_in=(usage or {}).get("tokens_in", 0),
                tokens_out=(usage or {}).get("tokens_out", 0),
            )
            return choices[0].message.content or ""
        else:
            kwargs.pop("json_mode", None)  # Anthropic 无 response_format，靠 prompt + 归一化兜底
            kwargs = self._anthropic_kwargs(kwargs)
            kwargs = self._with_thinking_disabled(kwargs)
            attempt = 1
            try:
                response = await self._guarded(
                    self._client.messages.create(
                        model=model,
                        system=system,
                        messages=messages,
                        max_tokens=max_tokens,
                        **kwargs,
                    )
                )
            except Exception as e:  # noqa: BLE001 — 端点不认 thinking 时去掉再试一次
                if isinstance(e, AITimeoutError):
                    self._log_call(operation, model, start, error=e, attempt=attempt)
                    raise  # 网络层失败不做 thinking 重试
                if "thinking" in kwargs and self._is_thinking_rejection(e):
                    self._remember_thinking_unsupported()
                    self._log_call(operation, model, start, error=e, attempt=attempt)
                    kwargs.pop("thinking", None)
                    attempt = 2
                    response = await self._guarded(
                        self._client.messages.create(
                            model=model,
                            system=system,
                            messages=messages,
                            max_tokens=max_tokens,
                            **kwargs,
                        )
                    )
                else:
                    self._log_call(operation, model, start, error=e, attempt=attempt)
                    raise
            if usage is not None:
                u = getattr(response, "usage", None)
                # Anthropic 的 input_tokens **不含**缓存命中/写入的部分，二者另字段计。
                # 漏掉它们会让「同一模板重复调用」的输入被系统性少算
                # （实测同一 prompt：首调 913；二次 145 + cache_read 768 = 仍 913）。
                usage["tokens_in"] = (
                    (getattr(u, "input_tokens", 0) or 0)
                    + (getattr(u, "cache_read_input_tokens", 0) or 0)
                    + (getattr(u, "cache_creation_input_tokens", 0) or 0)
                )
                usage["tokens_out"] = getattr(u, "output_tokens", 0) or 0
            for block in response.content:
                if getattr(block, "type", "") == "text" and block.text:
                    self._log_call(
                        operation, model, start,
                        tokens_in=(usage or {}).get("tokens_in", 0),
                        tokens_out=(usage or {}).get("tokens_out", 0),
                        attempt=attempt,
                    )
                    return block.text
            # 无 text 块（偶发：预算全用在思考 / 供应商只回 thinking）——
            # 明确报错让上层可重试，**不得静默返回空串**（会被当成「非法 JSON」）；
            # ok 行在文本确认后落（评审 P3：先记 ok 再抛错会让日志与调用方 _fail 矛盾）
            blocks = [getattr(b, "type", "?") for b in (response.content or [])]
            self._log_call(
                operation, model, start,
                tokens_in=(usage or {}).get("tokens_in", 0),
                tokens_out=(usage or {}).get("tokens_out", 0),
                attempt=attempt,
                error=ValueError("模型未返回文本内容"),
            )
            raise ValueError(
                f"模型未返回文本内容（返回块：{blocks or '空'}，stop_reason="
                f"{getattr(response, 'stop_reason', '?')}），请重试"
            )

    async def chat_stream(
        self,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
        operation: str = "",
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        """Streaming chat. Yields StreamEvent with text, is_done, tokens.

        operation: 业务动作名（backend-logging D7 留痕行用，与 TokenLog 同名）。
        """
        model = self.resolve(model)
        start = time.perf_counter()
        if self._provider == "openai":
            kwargs.pop("json_mode", None)  # 流式不落 response_format
            openai_messages: list[dict[str, Any]] = []
            if system:
                openai_messages.append({"role": "system", "content": system})
            for m in messages:
                openai_messages.append({"role": m["role"], "content": m["content"]})
            extra = {"thinking": {"type": "disabled"}}
            if "thinking" in kwargs:
                extra["thinking"] = kwargs.pop("thinking")
            try:
                stream = await self._client.chat.completions.create(
                    model=model,
                    messages=openai_messages,
                    max_tokens=max_tokens,
                    stream=True,
                    extra_body=extra,
                    timeout=_to_sdk_timeout("openai", _stream_timeout()),
                    **kwargs,
                )
                done_out, done_in = 0, 0
                async for chunk in stream:
                    # 兼容供应商流末会发 choices=[] 的 usage-only 块——裸取 [0] 是
                    # IndexError（不在 _NETWORK_ERRORS 内，会把成功生成记成 _fail）
                    usage = getattr(chunk, "usage", None)
                    if usage is not None:
                        done_out = getattr(usage, "completion_tokens", 0) or 0
                        done_in = getattr(usage, "prompt_tokens", 0) or 0
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield StreamEvent(text=delta.content)
                self._log_call(
                    operation, model, start, tokens_in=done_in, tokens_out=done_out
                )
                yield StreamEvent(is_done=True, tokens=done_out, tokens_in=done_in)
            except Exception as e:  # noqa: BLE001 — 归一目标外的异常原样重抛（_raise_normalized 尾行 raise）
                self._log_call(operation, model, start, error=e)
                self._raise_normalized(e)
        else:
            kwargs = self._anthropic_kwargs(kwargs)
            kwargs = self._with_thinking_disabled(kwargs)
            try:
                async with self._client.messages.stream(
                    model=model,
                    system=system,
                    messages=messages,
                    max_tokens=max_tokens,
                    timeout=_to_sdk_timeout("anthropic", _stream_timeout()),
                    **kwargs,
                ) as stream:
                    tokens_in = 0
                    async for event in stream:
                        if event.type == "message_start":
                            usage = getattr(event.message, "usage", None)
                            tokens_in = getattr(usage, "input_tokens", 0) or 0
                        elif event.type == "content_block_delta":
                            delta_type = getattr(event.delta, "type", "")
                            if delta_type == "text_delta":
                                yield StreamEvent(text=event.delta.text)
                        elif event.type == "message_stop":
                            tokens = 0
                            if hasattr(event, "usage") and event.usage:
                                tokens = event.usage.output_tokens
                            self._log_call(
                                operation, model, start,
                                tokens_in=tokens_in, tokens_out=tokens,
                            )
                            yield StreamEvent(is_done=True, tokens=tokens, tokens_in=tokens_in)
            except Exception as e:  # noqa: BLE001 — 归一目标外的异常原样重抛（_raise_normalized 尾行 raise）
                self._log_call(operation, model, start, error=e)
                self._raise_normalized(e)


async def get_ai_client_for_user(user_id: str | None = None) -> AIClient:
    """Get AI client configured with a user's API settings.

    Priority:
    1. Project's configured ApiConfig (if project_id provided — see get_ai_client_for_project)
    2. Any active ApiConfig for the user
    3. Old User.api_key / api_base_url / api_model (migration fallback)
    4. config.json (legacy fallback)
    """
    try:
        async with async_session() as session:
            if user_id:
                # Check for active ApiConfig records (new system)
                # key-crypto-selfcontained：候选取全量倒序逐个解密（原 limit(1)
                # 在「最新一条死文、第二条活」时误落 User 兜底）
                result = await session.execute(
                    select(ApiConfig)
                    .where(
                        ApiConfig.user_id == user_id,
                        ApiConfig.status == "active",
                        ApiConfig.api_key != "",
                        # c-zhuque-ai-detect：朱雀检测配置不是写作大模型，兜底选取 SHALL NOT 命中
                        ApiConfig.vendor != "zhuque",
                    )
                    .order_by(ApiConfig.created_at.desc())
                )
                for cfg in result.scalars().all():
                    plain_key = decrypt_api_key(cfg.api_key)
                    if not plain_key:
                        continue
                    models_list: list[str] = []
                    if cfg.models:
                        try:
                            parsed = json.loads(cfg.models)
                            if isinstance(parsed, list):
                                models_list = parsed
                        except (json.JSONDecodeError, TypeError):
                            pass
                    # Use first model as the default, or empty
                    model = models_list[0] if models_list else ""
                    return AIClient(
                        api_key=plain_key,
                        base_url=cfg.base_url,
                        model=model or "",
                        api_format=getattr(cfg, "api_format", None),
                        vendor=getattr(cfg, "vendor", "") or "",
                    )

                # Fallback: old User.api_key (migration period)
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                if user and user.api_key:
                    return AIClient(
                        api_key=user.api_key,
                        base_url=user.api_base_url,
                        model=user.api_model,
                    )
            else:
                # No user_id: find any user with a config（同上：逐个可解密判定）
                result = await session.execute(
                    select(ApiConfig)
                    .where(
                        ApiConfig.status == "active",
                        ApiConfig.api_key != "",
                        ApiConfig.vendor != "zhuque",  # c-zhuque-ai-detect：同上，朱雀行不进兜底
                    )
                    .order_by(ApiConfig.created_at.desc())
                )
                for cfg in result.scalars().all():
                    plain_key = decrypt_api_key(cfg.api_key)
                    if not plain_key:
                        continue
                    models_list: list[str] = []
                    if cfg.models:
                        try:
                            parsed = json.loads(cfg.models)
                            if isinstance(parsed, list):
                                models_list = parsed
                        except (json.JSONDecodeError, TypeError):
                            pass
                    model = models_list[0] if models_list else ""
                    return AIClient(
                        api_key=plain_key,
                        base_url=cfg.base_url,
                        model=model,
                        api_format=getattr(cfg, "api_format", None),
                        vendor=getattr(cfg, "vendor", "") or "",
                    )

                # Fallback: any user with old api_key
                result = await session.execute(
                    select(User)
                    .where(User.api_key != "", User.api_key.isnot(None))
                    .limit(1)
                )
                user = result.scalar_one_or_none()
                if user:
                    return AIClient(
                        api_key=user.api_key,
                        base_url=user.api_base_url,
                        model=user.api_model,
                    )
    except Exception:  # noqa: BLE001, S110
        pass

    # Final fallback: read from config.json
    from auth_local.service import get_local_config

    cfg = get_local_config()
    return AIClient(
        api_key=cfg.get("api_key", ""),
        base_url=cfg.get("api_base_url", ""),
        model=cfg.get("api_model", "deepseek-v4-flash"),
    )


async def get_ai_client_for_novel(novel_id: str) -> AIClient:
    """客户端层（D11 ④）：按**本书绑定**的配置与模型构造客户端。

    业务层唯一合法入口（除建书期 `世界 AI 起草（v2 通用起草端点）`/`suggest_meta` 豁免）。
    `ai_model` 权威、与 `ai_config_id` 绑定同一配置；调用方 `chat(model="haiku")`
    经 `resolve()` 落到本书模型，**不要在业务层传字面模型名**。

    前置未就绪（无书/未绑/配置已删/无 Key——含 Key 密文解不开）抛 `ValueError`
    ——业务层应先挂 `require_novel_model` 门控，正常路径不会走到这里。

    门禁（grep ④，key-crypto-selfcontained）：本函数每个调用文件，其所在路由
    模块（或上游路由模块）须出现 `require_novel_model` 或 `ensure_novel_model_ready`
    （路径无 project_id 的场景如 story/，用后者从会话引擎取值）。豁免：`tests/`、
    `ai_prefill.py`、`novels/router.py` suggest-meta、`archive/service.py`、
    `archive/reconcile.py` 与 `archive/dossier.py`（try/except 降级路径，非门控对象
    ——章档提取按「模型就绪即跑、未就绪放行归档」语义，c-chapter-dossier D8）。
    """
    async with async_session() as session:
        novel = await session.get(Novel, novel_id)
        if novel is None:
            raise ValueError("书籍不存在")
        if not novel.ai_config_id or not novel.ai_model:
            raise ValueError("本书尚未选择模型")
        cfg = await session.get(ApiConfig, novel.ai_config_id)
        if cfg is None:
            raise ValueError("本书绑定的 API 配置已删除，请重新选择模型")
        if getattr(cfg, "vendor", None) == "zhuque":  # c-zhuque-ai-detect：绑定侧防注入兜底
            raise ValueError("本书绑定的 API 配置已删除，请重新选择模型")
        plain_key = decrypt_api_key(cfg.api_key)
        if not plain_key:
            raise ValueError("本书绑定的 API 配置没有可用 Key")
        return AIClient(
            api_key=plain_key,
            base_url=cfg.base_url,
            model=novel.ai_model,
            api_format=getattr(cfg, "api_format", None),
            vendor=getattr(cfg, "vendor", "") or "",
        )


async def get_ai_client() -> AIClient:
    """Backward-compatible alias. Tries DB first, falls back to config.json."""
    try:
        return await get_ai_client_for_user()
    except Exception:  # noqa: BLE001
        from auth_local.service import get_local_config

        cfg = get_local_config()
        return AIClient(
            api_key=cfg.get("api_key", ""),
            base_url=cfg.get("api_base_url", ""),
            model=cfg.get("api_model", "deepseek-v4-flash"),
        )


async def create_ai_client() -> AIClient:
    """Alias for get_ai_client() — for callers that use this name."""
    return await get_ai_client()


async def resolve_model(name: str) -> str:
    client = await get_ai_client()
    return client.resolve(name)
