# backend/ai_client.py
"""AI client — provider-agnostic. Supports Anthropic and OpenAI API formats.

C/S 模式下从本地 config.json 动态读取 API Key/Base URL/Model，而不是从 config.py。
"""

import inspect
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from sqlalchemy import select

from api_configs.crypto import decrypt_api_key
from db import async_session
from models.api_config import ApiConfig
from models.project import Novel
from models.user import User


@dataclass
class StreamEvent:
    text: str = ""
    is_done: bool = False
    tokens: int = 0
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
    ):
        self._provider = "anthropic"  # default
        self._client: Any | None = None
        self._model = model
        self._init_client(api_key, base_url, api_format)

    def _init_client(self, api_key: str, base_url: str, api_format: str | None = None):
        """Initialize the underlying API client with the given credentials.

        api_format 显式优先（"openai" | "anthropic"）；None 时退回旧版行为：
        按 base_url 含 "anthropic" 推断（存量 User.api_key / config.json 兜底路径
        无格式信息，保持原推断）。
        """
        if not api_key:
            raise ValueError("未配置 API Key，请在设置页面填写")

        if api_format == "anthropic" or (
            api_format is None and "anthropic" in base_url.lower()
        ):
            self._provider = "anthropic"
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = AsyncAnthropic(**kwargs)
        else:
            self._provider = "openai"
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = AsyncOpenAI(**kwargs)

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
        **kwargs: Any,
    ) -> str:
        """Non-streaming. Returns full response text.

        usage: 可选 dict，调用成功后填充 {"tokens_in", "tokens_out"}，供 TokenLog 记录。
        """
        model = self.resolve(model)
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
            response = await self._client.chat.completions.create(
                model=model,
                messages=openai_messages,
                max_tokens=max_tokens,
                extra_body=extra,
                **kwargs,
            )
            if usage is not None:
                u = getattr(response, "usage", None)
                usage["tokens_in"] = getattr(u, "prompt_tokens", 0) or 0
                usage["tokens_out"] = getattr(u, "completion_tokens", 0) or 0
            return response.choices[0].message.content or ""
        else:
            kwargs.pop("json_mode", None)  # Anthropic 无 response_format，靠 prompt + 归一化兜底
            kwargs = self._anthropic_kwargs(kwargs)
            response = await self._client.messages.create(
                model=model,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                **kwargs,
            )
            if usage is not None:
                u = getattr(response, "usage", None)
                usage["tokens_in"] = getattr(u, "input_tokens", 0) or 0
                usage["tokens_out"] = getattr(u, "output_tokens", 0) or 0
            for block in response.content:
                if getattr(block, "type", "") == "text" and block.text:
                    return block.text
            return ""

    async def chat_stream(
        self,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        """Streaming chat. Yields StreamEvent with text, is_done, tokens."""
        model = self.resolve(model)
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
            stream = await self._client.chat.completions.create(
                model=model,
                messages=openai_messages,
                max_tokens=max_tokens,
                stream=True,
                extra_body=extra,
                **kwargs,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield StreamEvent(text=delta.content)
            yield StreamEvent(
                is_done=True,
                tokens=getattr(chunk, "usage", None) and chunk.usage.total_tokens or 0,
            )
        else:
            kwargs = self._anthropic_kwargs(kwargs)
            async with self._client.messages.stream(
                model=model,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                **kwargs,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        delta_type = getattr(event.delta, "type", "")
                        if delta_type == "text_delta":
                            yield StreamEvent(text=event.delta.text)
                    elif event.type == "message_stop":
                        tokens = 0
                        if hasattr(event, "usage") and event.usage:
                            tokens = event.usage.output_tokens
                        yield StreamEvent(is_done=True, tokens=tokens)


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
                result = await session.execute(
                    select(ApiConfig)
                    .where(
                        ApiConfig.user_id == user_id,
                        ApiConfig.status == "active",
                        ApiConfig.api_key != "",
                    )
                    .order_by(ApiConfig.created_at.desc())
                    .limit(1)
                )
                cfg = result.scalar_one_or_none()
                if cfg:
                    plain_key = decrypt_api_key(cfg.api_key)
                    if plain_key:
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
                # No user_id: find any user with a config
                result = await session.execute(
                    select(ApiConfig)
                    .where(ApiConfig.status == "active", ApiConfig.api_key != "")
                    .order_by(ApiConfig.created_at.desc())
                    .limit(1)
                )
                cfg = result.scalar_one_or_none()
                if cfg:
                    plain_key = decrypt_api_key(cfg.api_key)
                    if plain_key:
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

    业务层唯一合法入口（除建书期 `ai_prefill`/`suggest_meta` 豁免）。
    `ai_model` 权威、与 `ai_config_id` 绑定同一配置；调用方 `chat(model="haiku")`
    经 `resolve()` 落到本书模型，**不要在业务层传字面模型名**。

    前置未就绪（无书/未绑/配置已删/无 Key）抛 `ValueError`——业务层应先挂
    `require_novel_model` 门控，正常路径不会走到这里。
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
        plain_key = decrypt_api_key(cfg.api_key)
        if not plain_key:
            raise ValueError("本书绑定的 API 配置没有可用 Key")
        return AIClient(
            api_key=plain_key,
            base_url=cfg.base_url,
            model=novel.ai_model,
            api_format=getattr(cfg, "api_format", None),
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
