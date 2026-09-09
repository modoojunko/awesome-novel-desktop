"""客户端层（D11 ④）契约：temperature 透传 + json_mode 按 api_format 落地。

- `temperature` SHALL 透传给 provider（判定类 0.3 / 长文类 0.7 由业务层传）
- `json_mode` 是**语义参数**：openai → `response_format={"type":"json_object"}`；
  anthropic → **不得出现**（直接透传会 400），靠 prompt + 归一化兜底
- `resolve()`：本书模型对 `haiku/sonnet/review` 别名生效，字面模型名直接透传
"""

import asyncio

import pytest

import ai_client as ai_client_module
from ai_client import AIClient


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Recorder:
    """记录 create() 收到的 kwargs，返回最小可用响应。"""

    def __init__(self, kind: str):
        self.kind = kind
        self.kwargs: dict = {}

    async def _create(self, **kwargs):
        self.kwargs = kwargs
        if self.kind == "openai":
            msg = type("M", (), {"content": "ok"})()
            choice = type("C", (), {"message": msg})()
            usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 2})()
            return type("R", (), {"choices": [choice], "usage": usage})()
        block = type("B", (), {"type": "text", "text": "ok"})()
        usage = type("U", (), {"input_tokens": 1, "output_tokens": 2})()
        return type("R", (), {"content": [block], "usage": usage})()


class _FakeOpenAI:
    def __init__(self, **kwargs):
        self.recorder = _Recorder("openai")
        create = self.recorder._create

        class _Completions:
            @staticmethod
            async def create(**kw):
                return await create(**kw)

        self.chat = type("Chat", (), {"completions": _Completions()})()


class _FakeAnthropic:
    """模拟 anthropic 0.x SDK：messages.create 显式声明 temperature。"""

    def __init__(self, **kwargs):
        self.recorder = _Recorder("anthropic")
        create = self.recorder._create

        class _Messages:
            @staticmethod
            async def create(temperature=None, **kw):
                if temperature is not None:
                    kw["temperature"] = temperature
                return await create(**kw)

        self.messages = _Messages()


@pytest.fixture
def openai_client(monkeypatch):
    monkeypatch.setattr(ai_client_module, "AsyncOpenAI", _FakeOpenAI)
    c = AIClient(api_key="sk-x", base_url="https://api.example.com/v1", model="gpt-4o")
    return c


@pytest.fixture
def anthropic_client(monkeypatch):
    monkeypatch.setattr(ai_client_module, "AsyncAnthropic", _FakeAnthropic)
    c = AIClient(
        api_key="sk-x",
        base_url="https://api.example.com/anthropic",
        model="claude-x",
        api_format="anthropic",
    )
    return c


class TestJsonMode:
    def test_openai_json_mode_sets_response_format(self, openai_client):
        _run_async(
            openai_client.chat(
                model="haiku",
                system="",
                messages=[{"role": "user", "content": "x"}],
                json_mode=True,
            )
        )
        assert openai_client._client.recorder.kwargs["response_format"] == {
            "type": "json_object"
        }

    def test_openai_without_json_mode_no_response_format(self, openai_client):
        _run_async(
            openai_client.chat(
                model="haiku", system="", messages=[{"role": "user", "content": "x"}]
            )
        )
        assert "response_format" not in openai_client._client.recorder.kwargs

    def test_anthropic_never_gets_response_format(self, anthropic_client):
        _run_async(
            anthropic_client.chat(
                model="haiku",
                system="",
                messages=[{"role": "user", "content": "x"}],
                json_mode=True,
            )
        )
        kwargs = anthropic_client._client.recorder.kwargs
        assert "response_format" not in kwargs
        assert "json_mode" not in kwargs


class TestTemperature:
    def test_temperature_passthrough_openai(self, openai_client):
        _run_async(
            openai_client.chat(
                model="haiku",
                system="",
                messages=[{"role": "user", "content": "x"}],
                temperature=0.3,
            )
        )
        assert openai_client._client.recorder.kwargs["temperature"] == 0.3

    def test_temperature_passthrough_anthropic(self, anthropic_client):
        _run_async(
            anthropic_client.chat(
                model="haiku",
                system="",
                messages=[{"role": "user", "content": "x"}],
                temperature=0.7,
            )
        )
        assert anthropic_client._client.recorder.kwargs["temperature"] == 0.7


class TestResolve:
    def test_alias_resolves_to_book_model(self, openai_client):
        assert openai_client.resolve("haiku") == "gpt-4o"
        assert openai_client.resolve("sonnet") == "gpt-4o"
        assert openai_client.resolve("review") == "gpt-4o"

    def test_literal_model_passthrough(self, openai_client):
        assert openai_client.resolve("gpt-4o-mini") == "gpt-4o-mini"

    def test_model_property_exposes_effective(self, openai_client):
        assert openai_client.model == "gpt-4o"


class _FakeAnthropicNoTemperature:
    """模拟 anthropic 1.x SDK：messages.create 不接受 temperature。"""

    def __init__(self, **kwargs):
        self.recorder = _Recorder("anthropic")
        create = self.recorder._create

        class _Messages:
            @staticmethod
            async def create(**kw):
                assert "temperature" not in kw, "1.x SDK 不接受 temperature"
                return await create(**kw)

        self.messages = _Messages()


@pytest.fixture
def anthropic_v1_client(monkeypatch):
    monkeypatch.setattr(ai_client_module, "AsyncAnthropic", _FakeAnthropicNoTemperature)
    return AIClient(
        api_key="sk-x",
        base_url="https://api.example.com/anthropic",
        model="claude-x",
        api_format="anthropic",
    )


class TestAnthropicTemperatureCompat:
    """跨 SDK 版本：1.x 无 temperature 入参 → 落到 extra_body（否则 TypeError→502）。"""

    def test_v1_sdk_temperature_goes_to_extra_body(self, anthropic_v1_client):
        _run_async(
            anthropic_v1_client.chat(
                model="haiku",
                system="",
                messages=[{"role": "user", "content": "x"}],
                temperature=0.3,
            )
        )
        kwargs = anthropic_v1_client._client.recorder.kwargs
        assert kwargs["extra_body"]["temperature"] == 0.3
        assert "temperature" not in kwargs

    def test_v0_sdk_keeps_temperature_kwarg(self, anthropic_client):
        _run_async(
            anthropic_client.chat(
                model="haiku",
                system="",
                messages=[{"role": "user", "content": "x"}],
                temperature=0.7,
            )
        )
        kwargs = anthropic_client._client.recorder.kwargs
        assert kwargs["temperature"] == 0.7
        assert "extra_body" not in kwargs

    def test_existing_extra_body_merged(self, anthropic_v1_client):
        _run_async(
            anthropic_v1_client.chat(
                model="haiku",
                system="",
                messages=[{"role": "user", "content": "x"}],
                temperature=0.3,
                extra_body={"top_k": 5},
            )
        )
        body = anthropic_v1_client._client.recorder.kwargs["extra_body"]
        assert body == {"top_k": 5, "temperature": 0.3}
