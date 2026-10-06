"""上游 404/405 的可诊断文案（内测「去AI味 405」案回归，2026-10-05）。

机理：模型服务对请求地址拒绝（Starlette 风格 405 `{'detail': 'Method Not Allowed'}`）
经 SDK 原样透传成 `Error code: 405 - {...}`，用户无从下手。修复后归一为 AIRequestError：
点名实际请求地址（`{base}/chat/completions` 或 `{base}/v1/messages`）与去处（模型配置）。
400 等其余状态保持 SDK 原始报错透传，不做改写（供应商业务信息不被二手化）。

Usage:
    cd client/backend && .venv/bin/python -m pytest tests/test_ai_client_upstream_errors.py -v
"""

import asyncio
import types

import httpx
import pytest
from anthropic import APIStatusError as AnthropicStatusError
from openai import APIStatusError as OpenAIStatusError

from ai_client import AIClient, AIRequestError


def _status_error(sdk_cls, url: str, status: int, body: dict | None = None):
    body = body if body is not None else {"detail": "Method Not Allowed"}
    resp = httpx.Response(status, request=httpx.Request("POST", url))
    return sdk_cls(f"Error code: {status} - {body}", response=resp, body=body)


async def _raise(exc: Exception):
    raise exc


def _openai_stub(client: AIClient, exc: Exception) -> None:
    client._client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=lambda **kw: _raise(exc))
        )
    )


def _anthropic_stub(client: AIClient, exc: Exception) -> None:
    client._client = types.SimpleNamespace(
        messages=types.SimpleNamespace(create=lambda **kw: _raise(exc))
    )


def _chat(client: AIClient):
    return asyncio.run(
        client.chat(model="haiku", system="s", messages=[{"role": "user", "content": "hi"}])
    )


def test_openai_chat_405_actionable_message():
    """openai 格式 405：文案含状态码、实际请求地址与「模型配置」去处。"""
    client = AIClient(
        api_key="sk-test", api_format="openai", base_url="https://api.example.com/v1"
    )
    _openai_stub(
        client,
        _status_error(OpenAIStatusError, "https://api.example.com/v1/chat/completions", 405),
    )
    with pytest.raises(AIRequestError) as ei:
        _chat(client)
    msg = str(ei.value)
    assert "HTTP 405" in msg
    assert "https://api.example.com/v1/chat/completions" in msg
    assert "模型配置" in msg


def test_anthropic_chat_405_names_messages_path():
    """anthropic 格式 405：文案点名的地址是 {base}/v1/messages（SDK 实际拼法）。"""
    client = AIClient(
        api_key="sk-test", api_format="anthropic", base_url="https://api.example.com"
    )
    _anthropic_stub(
        client, _status_error(AnthropicStatusError, "https://api.example.com/v1/messages", 405)
    )
    with pytest.raises(AIRequestError) as ei:
        _chat(client)
    msg = str(ei.value)
    assert "HTTP 405" in msg
    assert "https://api.example.com/v1/messages" in msg


def test_openai_stream_405_actionable():
    """流式路径同归一（正文生成本身走 stream，同故障面）。"""
    client = AIClient(
        api_key="sk-test", api_format="openai", base_url="https://api.example.com"
    )
    _openai_stub(
        client, _status_error(OpenAIStatusError, "https://api.example.com/chat/completions", 405)
    )

    async def _drain():
        async for _ in client.chat_stream(
            model="haiku", system="s", messages=[{"role": "user", "content": "hi"}]
        ):
            pass

    with pytest.raises(AIRequestError):
        asyncio.run(_drain())


def test_other_status_passthrough_unrewritten():
    """400 等非 404/405 不归一——保持 SDK 原始报错（供应商业务信息不被二手化）。"""
    client = AIClient(
        api_key="sk-test", api_format="openai", base_url="https://api.example.com"
    )
    _openai_stub(
        client,
        _status_error(
            OpenAIStatusError,
            "https://api.example.com/chat/completions",
            400,
            {"error": {"message": "bad model"}},
        ),
    )
    with pytest.raises(OpenAIStatusError) as ei:
        _chat(client)
    assert not isinstance(ei.value, AIRequestError)
