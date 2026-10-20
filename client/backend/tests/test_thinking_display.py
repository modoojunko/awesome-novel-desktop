"""c-thinking-display — 思考事件通道＋可观测元数据

- StreamEvent.thinking 独立通道：三来源（openai 内联 <think>、openai
  reasoning_content、anthropic thinking_delta）统一为思考事件，与正文事件
  零混入；think→prose→think 交错（M2 系官方口径）零串道
- 思考事件不构成首字、不撤首字守卫；tokens 记账口径不变
- ai_call 行思考元数据（thinking_ms/first_char_ms/thinking_chars）；
  思考全文 SHALL NOT 落日志
- MiniMax anthropic 用量解析：tokens_out 以 message_delta.usage 为准
- write 路由：thinking SSE 转发；守卫判死 error 带 kind=thinking_timeout
  ＋thinking 标记
"""

import asyncio
import types

from ai_client import AIClient, AIThinkingTimeoutError, StreamEvent, strip_inline_think


def _run_async(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── openai 兼容形态 ──────────────────────────────────────────────────────


def _openai_client(chunks, **client_kw) -> AIClient:
    client = AIClient(api_key="sk-test", api_format="openai",
                      base_url="https://example.com/v1", **client_kw)

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


def _delta(text=None, reasoning=None, finish=None):
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(
            delta=types.SimpleNamespace(
                content=text, reasoning_content=reasoning),
            finish_reason=finish,
        )],
        usage=None,
    )


async def _collect(client, **kw):
    out = []
    async for ev in client.chat_stream(model="m", system="",
                                       messages=[{"role": "user", "content": "hi"}], **kw):
        out.append(ev)
    return out


def _run(client, **kw):
    async def _go():
        return await _collect(client, **kw)
    return _run_async(_go())


# ── anthropic 形态 ───────────────────────────────────────────────────────


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


def _ev(type_, **kw):
    return types.SimpleNamespace(type=type_, **kw)


# ── 2.1/2.4 内联 <think>：透出＋交错零串道 ───────────────────────────────


class TestInlineThinkChannel:
    def test_leading_think_becomes_thinking_events(self):
        chunks = [_delta("<think>夜雨的意象"), _delta("要压住心虚。</think>"),
                  _delta("夜雨落在青瓦上。")]
        out = _run(_openai_client(chunks))
        thinking = "".join(e.thinking for e in out if e.thinking)
        text = "".join(e.text for e in out if e.text)
        assert thinking == "夜雨的意象要压住心虚。"
        assert text == "夜雨落在青瓦上。"
        # 通道零混入：思考事件不带正文、正文事件不带思考
        assert all("<think>" not in e.text and "</think>" not in e.text
                   for e in out if e.text)

    def test_interleave_think_prose_think_zero_crossing(self):
        # M2 系交错思考官方口径：闭标签后再开标签，第二段思考走思考通道
        chunks = [_delta("<think>先想。"), _delta("</think>第一段。"),
                  _delta("<think>再想。"), _delta("</think>第二段。")]
        out = _run(_openai_client(chunks))
        thinking = "".join(e.thinking for e in out if e.thinking)
        text = "".join(e.text for e in out if e.text)
        assert thinking == "先想。再想。"
        assert text == "第一段。第二段。"
        assert "再想" not in text and "先想" not in text

    def test_split_tag_across_chunks_still_channels(self):
        # 标签裂在 chunk 边界：开闭标签各裂一次，通道口径不变
        chunks = [_delta("<th"), _delta("ink>想A。</th"), _delta("ink>正"),
                  _delta("<think>想B。</think>文")]
        out = _run(_openai_client(chunks))
        thinking = "".join(e.thinking for e in out if e.thinking)
        text = "".join(e.text for e in out if e.text)
        assert thinking == "想A。想B。"
        assert text == "正文"

    def test_plain_prose_zero_delay_and_untouched(self):
        # 普通模型首 chunk 零延迟直通；含「<」但不构成标签的文本原样交付
        chunks = [_delta("沈砚把书册搬回架上。"), _delta("笔记写着 <th"), _delta("in 注。")]
        out = _run(_openai_client(chunks))
        text = "".join(e.text for e in out if e.text)
        assert text == "沈砚把书册搬回架上。笔记写着 <thin 注。"
        assert not [e for e in out if e.thinking]

    def test_non_stream_strip_inline_think_still_works(self):
        # 非流式出口共用同一状态机：透出改造不得破坏既有语义
        assert strip_inline_think("<think>想。</think>正文") == "正文"
        assert strip_inline_think("普通文本") == "普通文本"


# ── 2.2 reasoning_content 并行通道 ───────────────────────────────────────


class TestReasoningContentChannel:
    def test_reasoning_and_content_no_duplication(self):
        chunks = [_delta(reasoning="构思第一段"), _delta(text="第一段"),
                  _delta(reasoning="构思第二段"), _delta(text="第二段")]
        out = _run(_openai_client(chunks))
        thinking = "".join(e.thinking for e in out if e.thinking)
        text = "".join(e.text for e in out if e.text)
        assert thinking == "构思第一段构思第二段"
        assert text == "第一段第二段"
        # 两通道无重复：正文逐字等于 content 拼接，思考逐字等于 reasoning 拼接
        # （字段级分流，事件级零交叉）；「构思」不落正文
        assert "构思" not in text
        seq = [("t", e.thinking) if e.thinking else ("p", e.text)
               for e in out if e.thinking or e.text]
        assert [k for k, _ in seq] == ["t", "p", "t", "p"]

    def test_thinking_events_do_not_withdraw_guard(self):
        # 思考事件不算首字、不撤守卫：思考持续产出而正文未到，超限判死
        import asyncio as _aio

        class _Slow:
            def __init__(self, text=None, reasoning=None):
                self.delta = types.SimpleNamespace(content=text, reasoning_content=reasoning)
                self.finish_reason = None

        async def create(**kwargs):
            async def _gen():
                for _ in range(3):
                    await _aio.sleep(0.04)
                    yield _chunk([_Slow(reasoning="想")])
                yield _chunk([_Slow(text="晚了")])
            return _gen()

        client = AIClient(api_key="sk-test", api_format="openai",
                          base_url="https://example.com/v1")
        client._client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        out, err = [], None
        try:
            out = _run(client, first_content_timeout=0.05)
        except AIThinkingTimeoutError as e:
            err = e
        assert err is not None, "思考事件不撤守卫：应判死"
        assert not [e for e in out if e.text]


# ── 2.3/2.6 anthropic thinking_delta ＋ MiniMax 用量解析 ─────────────────


class TestAnthropicThinkingChannel:
    def test_thinking_delta_text_delta_split_and_minimax_usage(self):
        # MiniMax anthropic 形态：tokens 只在 message_delta.usage 回报，
        # message_stop 无 usage——此前 tokens_out 恒 0（2.6 修复钉）
        stream = [
            _ev("message_start", message=types.SimpleNamespace(
                usage=types.SimpleNamespace(input_tokens=12642))),
            _ev("content_block_start", index=0,
                content_block=types.SimpleNamespace(type="thinking")),
            _ev("content_block_delta", delta=types.SimpleNamespace(
                type="thinking_delta", thinking="先谋篇")),
            _ev("content_block_delta", delta=types.SimpleNamespace(
                type="thinking_delta", thinking="后落笔")),
            _ev("content_block_delta", delta=types.SimpleNamespace(
                type="text_delta", text="夜雨落在青瓦上。")),
            _ev("message_delta", delta=types.SimpleNamespace(stop_reason="end_turn"),
                usage=types.SimpleNamespace(output_tokens=4310)),
            _ev("message_stop"),
        ]
        out = _run(_anthropic_client(list(stream)))
        thinking = "".join(e.thinking for e in out if e.thinking)
        text = "".join(e.text for e in out if e.text)
        assert thinking == "先谋篇后落笔"
        assert text == "夜雨落在青瓦上。"
        done = [e for e in out if e.is_done][-1]
        assert done.tokens == 4310 and done.tokens_in == 12642

    def test_interleave_thinking_text_zero_crossing(self):
        # think→prose→think 交错（M2 系）：事件按到达顺序各走各道
        stream = [
            _ev("content_block_delta", delta=types.SimpleNamespace(
                type="thinking_delta", thinking="想一")),
            _ev("content_block_delta", delta=types.SimpleNamespace(
                type="text_delta", text="写一")),
            _ev("content_block_delta", delta=types.SimpleNamespace(
                type="thinking_delta", thinking="想二")),
            _ev("content_block_delta", delta=types.SimpleNamespace(
                type="text_delta", text="写二")),
            _ev("message_stop"),
        ]
        out = _run(_anthropic_client(stream))
        seq = [("t", e.thinking) if e.thinking else ("p", e.text)
               for e in out if e.thinking or e.text]
        assert seq == [("t", "想一"), ("p", "写一"), ("t", "想二"), ("p", "写二")]

    def test_thinking_does_not_withdraw_guard(self):
        import asyncio as _aio

        events = [
            _ev("content_block_delta", delta=types.SimpleNamespace(
                type="thinking_delta", thinking="想")),
            _ev("content_block_delta", delta=types.SimpleNamespace(
                type="thinking_delta", thinking="还想")),
        ]

        class _SlowStream:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not events:
                    raise StopAsyncIteration
                await _aio.sleep(0.04)  # 真实间隔：守卫时钟才有机会过线
                return events.pop(0)

        client = AIClient(api_key="sk-test", api_format="anthropic",
                          base_url="https://example.com")
        client._client = types.SimpleNamespace(
            messages=types.SimpleNamespace(stream=lambda **kw: _SlowStream()))
        out, err = [], None
        try:
            async def _go():
                async for ev in client.chat_stream(
                    model="m", system="",
                    messages=[{"role": "user", "content": "hi"}],
                    first_content_timeout=0.05,
                ):
                    out.append(ev)
            _run_async(_go())
        except AIThinkingTimeoutError as e:
            err = e
        assert err is not None, "thinking_delta 不撤守卫：应判死"
        assert not [e for e in out if e.text]


# ── 2.5 ai_call 行思考元数据 ─────────────────────────────────────────────


class TestCallLogMetadata:
    def test_metadata_fields_on_thinking_stream(self, caplog):
        import logging

        stream = [
            _ev("message_start", message=types.SimpleNamespace(
                usage=types.SimpleNamespace(input_tokens=10))),
            _ev("content_block_delta", delta=types.SimpleNamespace(
                type="thinking_delta", thinking="谋篇布局")),
            _ev("content_block_delta", delta=types.SimpleNamespace(
                type="text_delta", text="正文若干")),
            _ev("message_delta", delta=types.SimpleNamespace(stop_reason="end_turn"),
                usage=types.SimpleNamespace(output_tokens=8)),
            _ev("message_stop"),
        ]
        with caplog.at_level(logging.INFO, logger="ai_client"):
            _run(_anthropic_client(stream))
        line = [r.message for r in caplog.records if "event=ai_call" in r.message][-1]
        assert "thinking_ms=" in line and "first_char_ms=" in line
        assert "thinking_chars=4" in line
        # 思考全文不落日志：正文与思考内容都不得出现
        assert "谋篇布局" not in line and "正文若干" not in line

    def test_zero_thinking_stream_reports_zero_metadata(self, caplog):
        import logging

        stream = [
            _ev("content_block_delta", delta=types.SimpleNamespace(
                type="text_delta", text="直出正文")),
            _ev("message_stop"),
        ]
        with caplog.at_level(logging.INFO, logger="ai_client"):
            _run(_anthropic_client(stream))
        line = [r.message for r in caplog.records if "event=ai_call" in r.message][-1]
        assert "thinking_ms=0" in line and "thinking_chars=0" in line


# ── 3.1 write 路由：thinking 转发＋守卫判死 kind 标记 ────────────────────


class _FakeThinkingStream:
    """thinking→text→done 的假流（路由级转发钉）。"""

    async def chat_stream(self, **kwargs):
        yield StreamEvent(thinking="先谋篇")
        yield StreamEvent(text="夜雨落在青瓦上。")
        yield StreamEvent(is_done=True, tokens=10, tokens_in=5, finish_reason="end_turn")


class _FakeGuardDeathStream:
    """思考持续产出→守卫判死的假流。"""

    async def chat_stream(self, **kwargs):
        yield StreamEvent(thinking="想了很久")
        raise AIThinkingTimeoutError(601.0)




def _router_sse(monkeypatch, fake_client):
    """路由级 SSE 采集（harness 沿用 test_ai_timeout_accounting 的覆盖口径）。"""
    import uuid

    from fastapi.testclient import TestClient

    from auth_local.deps import require_ai_access, require_novel_model
    from auth_local.middleware import get_current_user
    from db import async_session as _sess
    from db import get_db
    from main import app

    async def _fake(novel_id=None):
        return fake_client

    monkeypatch.setattr("ai_client.get_ai_client_for_novel", _fake)

    async def _override_get_db():
        async with _sess() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    uid = "td-" + uuid.uuid4().hex[:6]  # 每测唯一用户：书架满额门禁不跨测计数
    app.dependency_overrides[get_current_user] = lambda: {"id": uid}
    app.dependency_overrides[require_ai_access] = lambda: True
    app.dependency_overrides[require_novel_model] = lambda: True
    try:
        with TestClient(app) as client:
            name = "td-" + uuid.uuid4().hex[:6]
            r = client.post("/api/novels", json={"name": name})
            assert r.status_code in (200, 201), r.text
            pid = r.json()["id"]
            r = client.post(f"/api/novels/{pid}/volumes",
                            json={"vol_num": 1, "title": "第一卷"})
            assert r.status_code in (200, 201), r.text
            r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters",
                            json={"title": "第1章"})
            assert r.status_code in (200, 201), r.text
            ref = r.json()["chapter_ref"]
            r = client.post(f"/api/novels/{pid}/chapters/{ref}/write", json={})
            return r.text
    finally:
        app.dependency_overrides.clear()


class TestRouterThinkingForward:
    def test_thinking_forwarded_as_sse_events(self, monkeypatch):
        body = _router_sse(monkeypatch, _FakeThinkingStream())
        assert '"type": "thinking"' in body and "先谋篇" in body
        assert '"type": "chunk"' in body and "夜雨落在青瓦上" in body
        # 思考不混进正文 chunk
        import re

        chunks = re.findall(r'"type": "chunk", "text": "([^"]*)"', body)
        assert "".join(chunks) == "夜雨落在青瓦上。"
        assert "先谋篇" not in "".join(chunks)

    def test_guard_death_error_carries_kind_and_marker(self, monkeypatch):
        body = _router_sse(monkeypatch, _FakeGuardDeathStream())
        assert '"kind": "thinking_timeout"' in body
        assert '"thinking": true' in body
