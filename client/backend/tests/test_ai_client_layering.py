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


class _EmptyThenText:
    """模拟供应商偶发「只回思考不回文本」：第一次空，第二次正常。"""

    def __init__(self, **kwargs):
        self.calls = 0

    async def create(self, **kw):
        self.calls += 1
        if self.calls == 1:
            block = type("B", (), {"type": "thinking", "text": ""})()
        else:
            block = type("B", (), {"type": "text", "text": "ok"})()
        return type("R", (), {"content": [block], "stop_reason": "end_turn"})()


class TestEmptyTextNotSilent:
    def test_no_text_block_raises(self, monkeypatch):
        monkeypatch.setattr(ai_client_module, "AsyncAnthropic", _FakeEmptyAnthropic)
        c = AIClient(
            api_key="sk-x",
            base_url="https://api.example.com/anthropic",
            model="m",
            api_format="anthropic",
        )
        with pytest.raises(ValueError, match="模型未返回文本内容"):
            _run_async(
                c.chat(model="haiku", system="", messages=[{"role": "user", "content": "x"}])
            )


class _FakeEmptyAnthropic:
    def __init__(self, **kwargs):
        class _Messages:
            @staticmethod
            async def create(**kw):
                block = type("B", (), {"type": "thinking", "text": ""})()
                return type("R", (), {"content": [block], "stop_reason": "end_turn"})()

        self.messages = _Messages()


class TestJudgeChatRetry:
    def test_retries_once_on_empty_then_succeeds(self):
        from settings.ai_router import _judge_chat

        class _C:
            def __init__(self):
                self.n = 0

            async def chat(self, **kw):
                self.n += 1
                if self.n == 1:
                    raise ValueError("模型未返回文本内容（返回块：['thinking']），请重试")
                return '{"missing": []}'

        c = _C()
        out = _run_async(_judge_chat(c, model="haiku", system="", messages=[]))
        assert out == '{"missing": []}'
        assert c.n == 2

    def test_other_errors_not_retried(self):
        from settings.ai_router import _judge_chat

        class _C:
            def __init__(self):
                self.n = 0

            async def chat(self, **kw):
                self.n += 1
                raise ValueError("连接超时")

        c = _C()
        with pytest.raises(ValueError, match="连接超时"):
            _run_async(_judge_chat(c, model="haiku", system="", messages=[]))
        assert c.n == 1

    def test_empty_twice_still_raises(self):
        from settings.ai_router import _judge_chat

        class _C:
            def __init__(self):
                self.n = 0

            async def chat(self, **kw):
                self.n += 1
                raise ValueError("模型未返回文本内容，请重试")

        c = _C()
        with pytest.raises(ValueError, match="模型未返回文本内容"):
            _run_async(_judge_chat(c, model="haiku", system="", messages=[]))
        assert c.n == 2


class _FakeThinkingRejecting:
    """模拟不认 thinking 字段的端点：第一次带 thinking 报 400，去掉后成功。"""

    def __init__(self, **kwargs):
        self.recorder = _Recorder("anthropic")
        create = self.recorder._create
        self.calls = 0

        class _Messages:
            @staticmethod
            async def create(**kw):
                outer.calls += 1
                if "thinking" in kw:
                    raise ValueError("400 Bad Request: unknown field 'thinking'")
                return await create(**kw)

        outer = self
        self.messages = _Messages()


class TestThinkingDisabledByDefault:
    def test_anthropic_default_disables_thinking(self, anthropic_client):
        _run_async(
            anthropic_client.chat(
                model="haiku", system="", messages=[{"role": "user", "content": "x"}]
            )
        )
        kwargs = anthropic_client._client.recorder.kwargs
        assert kwargs["thinking"] == {"type": "disabled"}

    def test_unsupported_endpoint_retries_without_and_remembers(self, monkeypatch):
        import ai_client as mod

        mod._THINKING_UNSUPPORTED_BASES.clear()
        monkeypatch.setattr(mod, "AsyncAnthropic", _FakeThinkingRejecting)
        c = AIClient(
            api_key="sk-x", base_url="https://no-thinking.example/anthropic",
            model="m", api_format="anthropic",
        )
        _run_async(c.chat(model="haiku", system="", messages=[{"role": "user", "content": "x"}]))
        # 第二次调用：已记住不支持 → 不再带 thinking（也不再触发一次失败重试）
        before = c._client.calls
        _run_async(c.chat(model="haiku", system="", messages=[{"role": "user", "content": "x"}]))
        assert c._client.calls - before == 1
        assert "https://no-thinking.example/anthropic" in mod._THINKING_UNSUPPORTED_BASES

    def test_stream_also_disables_thinking(self, monkeypatch):
        sent: dict = {}

        class _Stream:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def __aiter__(self):
                async def gen():
                    if False:
                        yield None

                return gen()

        class _Anthropic:
            def __init__(self, **kw):
                class _Messages:
                    @staticmethod
                    def stream(**kw):
                        sent.update(kw)
                        return _Stream()

                self.messages = _Messages()

        monkeypatch.setattr(ai_client_module, "AsyncAnthropic", _Anthropic)
        c = AIClient(
            api_key="sk-x", base_url="https://api.example.com/anthropic",
            model="m", api_format="anthropic",
        )

        async def drain():
            async for _ in c.chat_stream(
                model="haiku", system="", messages=[{"role": "user", "content": "x"}]
            ):
                pass

        _run_async(drain())
        assert sent["thinking"] == {"type": "disabled"}
