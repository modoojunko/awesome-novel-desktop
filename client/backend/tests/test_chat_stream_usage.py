"""c-ai-usage-correctness — chat_stream 流式用量与健壮性

- OpenAI 兼容供应商流末 choices=[] 的 usage-only 块不得炸（曾 IndexError 且把
  成功生成记成 _fail）；done 事件按 completion/prompt 拆分
- 空流不炸（tokens=0）
- anthropic 双向拆分（message_start.input_tokens / message_stop.output_tokens）
"""

import asyncio
import types

import pytest

from ai_client import AIClient


def _run_async(agen_factory):
    async def _collect_inner():
        return await _collect(agen_factory)
    return _collect_inner


def _openai_client(chunks) -> AIClient:
    client = AIClient(api_key="sk-test", api_format="openai",
                      base_url="https://example.com/v1")

    async def create(**kwargs):
        async def _gen():
            for c in chunks:
                yield c
        return _gen()

    client._client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )
    return client


def _chunk(choices, usage=None):
    return types.SimpleNamespace(choices=choices, usage=usage)


def _delta_chunk(text):
    return _chunk([types.SimpleNamespace(delta=types.SimpleNamespace(content=text))])


@pytest.fixture
def client():
    return _openai_client([
        _delta_chunk("第一段"),
        _delta_chunk("第二段"),
        # 流末 usage-only 块（OpenAI 兼容供应商惯例）：choices=[] 且带用量
        _chunk([], usage=types.SimpleNamespace(
            total_tokens=300, prompt_tokens=100, completion_tokens=200)),
    ])


async def _collect(client, **kw):
    out = []
    async for ev in client.chat_stream(model="m", system="",
                                       messages=[{"role": "user", "content": "hi"}], **kw):
        out.append(ev)
    return out


def _run(client, **kw):
    async def _go():
        return await _collect(client, **kw)
    return asyncio.new_event_loop().run_until_complete(_go())


def test_usage_only_last_chunk_splits_tokens(client):
    events = _run(client)
    done = [e for e in events if e.is_done][-1]
    assert "".join(e.text for e in events if e.text) == "第一段第二段"
    assert done.tokens == 200 and done.tokens_in == 100  # 不再把 total=300 记输出侧


def test_empty_stream_yields_done_with_zero_tokens():
    client = _openai_client([])
    events = _run(client)
    assert len(events) == 1 and events[0].is_done and events[0].tokens == 0


def _anthropic_client(events_seq) -> AIClient:
    client = AIClient(api_key="sk-test", api_format="anthropic",
                      base_url="https://example.com")

    class _Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not events_seq:
                raise StopAsyncIteration
            return events_seq.pop(0)

    client._client = types.SimpleNamespace(
        messages=types.SimpleNamespace(stream=lambda **kw: _Stream())
    )
    return client


def test_anthropic_split_from_message_start_and_stop():
    def ev(type_, **kw):
        return types.SimpleNamespace(type=type_, **kw)

    stream_events = [
        ev("message_start", message=types.SimpleNamespace(
            usage=types.SimpleNamespace(input_tokens=42))),
        ev("content_block_delta", delta=types.SimpleNamespace(
            type="text_delta", text="正文")),
        ev("message_stop", usage=types.SimpleNamespace(output_tokens=17)),
    ]
    client = _anthropic_client(stream_events)
    out = _run(client)
    done = [e for e in out if e.is_done][-1]
    assert done.tokens == 17 and done.tokens_in == 42
