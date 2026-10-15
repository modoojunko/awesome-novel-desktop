"""c-prose-generation-headroom — 正文守卫/预算余量＋anthropic 路径内联思考剥离

- MiniMax M3（anthropic 兼容端点＋thinking）实测 effort=low 思考 >90s：正文守卫
  放宽 600s、max_tokens 32768（思考＋正文合计；llm.log 90.034s 判死行实证）
- 内联思考剥离同构扩展到 anthropic 路径：思考关断时端点把 `<think>` 内联进
  text_delta（用户原始泄漏形态）；`<think>` 段不算首字、不撤守卫
"""

import asyncio
import types

from ai_client import AIClient, AIThinkingTimeoutError


def test_prose_call_site_headroom_constants():
    from write.router import PROSE_FIRST_CONTENT_TIMEOUT, PROSE_MAX_TOKENS

    assert PROSE_FIRST_CONTENT_TIMEOUT == 600.0
    assert PROSE_MAX_TOKENS == 32768


# ── anthropic 流式：内联剥离＋守卫口径 ─────────────────────────────────


def _ev(type_, **kw):
    return types.SimpleNamespace(type=type_, **kw)


def _anthropic_stream_client(events):
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
            if not events:
                raise StopAsyncIteration
            return events.pop(0)

    client._client = types.SimpleNamespace(
        messages=types.SimpleNamespace(stream=lambda **kw: _Stream())
    )
    return client


def _anthropic_timed_stream_client(events, gap):
    client = AIClient(api_key="sk-test", api_format="anthropic",
                      base_url="https://example.com")
    served = {"n": 0}

    class _Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not events:
                raise StopAsyncIteration
            if served["n"]:
                await asyncio.sleep(gap)
            served["n"] += 1
            return events.pop(0)

    client._client = types.SimpleNamespace(
        messages=types.SimpleNamespace(stream=lambda **kw: _Stream())
    )
    return client


def _run(client, **kw):
    async def _go():
        out, err = [], None
        try:
            async for ev in client.chat_stream(
                model="m", system="",
                messages=[{"role": "user", "content": "hi"}], **kw
            ):
                out.append(ev)
        except AIThinkingTimeoutError as e:
            err = e
        return out, err

    return asyncio.new_event_loop().run_until_complete(_go())


def test_anthropic_inline_think_text_delta_stripped():
    events = [
        _ev("message_start", message=types.SimpleNamespace(
            usage=types.SimpleNamespace(input_tokens=9))),
        _ev("content_block_delta", delta=types.SimpleNamespace(
            type="text_delta", text="<think>盘算")),
        _ev("content_block_delta", delta=types.SimpleNamespace(
            type="text_delta", text="中</think>")),
        _ev("content_block_delta", delta=types.SimpleNamespace(
            type="text_delta", text="正文")),
        _ev("message_stop", usage=types.SimpleNamespace(output_tokens=5)),
    ]
    out, err = _run(_anthropic_stream_client(list(events)))
    assert err is None
    assert "".join(e.text for e in out if e.text) == "正文"
    assert any(e.is_done for e in out)


def test_anthropic_guard_not_disarmed_by_inline_think():
    # `<think>` 走 text_delta 也零产出且不撤守卫：思考涓流超限判死、零正文事件
    events = [
        _ev("message_start", message=types.SimpleNamespace(
            usage=types.SimpleNamespace(input_tokens=1))),
        *[
            _ev("content_block_delta", delta=types.SimpleNamespace(
                type="text_delta", text="<think>想"))
        ]
        + [_ev("content_block_delta", delta=types.SimpleNamespace(
            type="text_delta", text="继续想")) for _ in range(8)],
        _ev("message_stop", usage=types.SimpleNamespace(output_tokens=2)),
    ]
    client = _anthropic_timed_stream_client(events, gap=0.03)
    out, err = _run(client, first_content_timeout=0.05)
    assert err is not None and err.seconds >= 0.05
    assert not any(e.text for e in out)
    assert not any(e.is_done for e in out)


def test_anthropic_guard_disarmed_by_first_prose_after_think():
    # thinking_delta 与 `<think>` 段都不算首字；自闭标签后的正文到达才撤守卫——
    # 其后的慢事件只有撤了守卫才活得过去（不撤必在 deadline 判死）
    client = AIClient(api_key="sk-test", api_format="anthropic",
                      base_url="https://example.com")

    def _msg_start():
        return _ev("message_start", message=types.SimpleNamespace(
            usage=types.SimpleNamespace(input_tokens=1)))

    def _td(text=None, thinking=None):
        return _ev("content_block_delta", delta=types.SimpleNamespace(
            type="text_delta" if text else "thinking_delta",
            text=text, thinking=thinking))

    script = [
        (_msg_start(), 0.0),
        (_td(thinking="正规思考块"), 0.005),
        (_td(thinking="正规思考块"), 0.005),
        (_td(thinking="正规思考块"), 0.005),
        (_td(text="<think>内联思考"), 0.005),   # 剥离中，不撤守卫
        (_td(text="</think>首字"), 0.005),      # t≈0.02 < 0.05：正文首字，撤守卫
        (_td(text="其余"), 0.12),               # 不撤守卫此处必判死
        (_ev("message_stop", usage=types.SimpleNamespace(output_tokens=7)), 0.12),
    ]
    queue = list(script)

    class _Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not queue:
                raise StopAsyncIteration
            ev, delay = queue.pop(0)
            if delay:
                await asyncio.sleep(delay)
            return ev

    client._client = types.SimpleNamespace(
        messages=types.SimpleNamespace(stream=lambda **kw: _Stream())
    )
    out, err = _run(client, first_content_timeout=0.05)
    assert err is None
    assert "".join(e.text for e in out if e.text) == "首字其余"
    assert any(e.is_done for e in out)


def test_anthropic_separate_thinking_blocks_still_dropped_verbatim():
    # 独立 thinking 块形态（GLM/DeepSeek anthropic）：text 通道无 `<think>`，逐字不动
    events = [
        _ev("message_start", message=types.SimpleNamespace(
            usage=types.SimpleNamespace(input_tokens=1))),
        _ev("content_block_delta", delta=types.SimpleNamespace(
            type="thinking_delta", thinking="思考")),
        _ev("content_block_delta", delta=types.SimpleNamespace(
            type="text_delta", text="正文原样")),
        _ev("message_stop", usage=types.SimpleNamespace(output_tokens=3)),
    ]
    out, err = _run(_anthropic_stream_client(list(events)))
    assert err is None
    assert "".join(e.text for e in out if e.text) == "正文原样"


# ── anthropic 非流式：出口剥前缀 ───────────────────────────────────────


def _anthropic_chat_client(blocks):
    client = AIClient(api_key="sk-test", api_format="anthropic",
                      base_url="https://example.com")

    async def create(**kwargs):
        return types.SimpleNamespace(
            content=blocks, usage=None, stop_reason="end_turn")

    client._client = types.SimpleNamespace(
        messages=types.SimpleNamespace(create=create))
    return client


def test_anthropic_nonstream_strips_inline_think():
    async def _go():
        return await _anthropic_chat_client([
            types.SimpleNamespace(type="thinking", thinking="独立块"),
            types.SimpleNamespace(type="text", text="<think>内联</think>正文"),
        ]).chat(model="m", system="", messages=[{"role": "user", "content": "hi"}])

    assert asyncio.new_event_loop().run_until_complete(_go()) == "正文"


def test_anthropic_nonstream_plain_verbatim():
    async def _go():
        return await _anthropic_chat_client([
            types.SimpleNamespace(type="text", text="普通正文"),
        ]).chat(model="m", system="", messages=[{"role": "user", "content": "hi"}])

    assert asyncio.new_event_loop().run_until_complete(_go()) == "普通正文"
