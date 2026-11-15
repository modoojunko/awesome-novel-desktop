"""原生 function calling 通道契约（c-agent-harness tasks 3）。

- chat_stream(tools=…)：tools 下发供应商；流内 delta.tool_calls 按 index 聚合，
  收口产独立 StreamEvent(tool_calls=…)（arguments 已解析；坏 JSON 保留 args_raw）
- supports_native_tools：openai 协议＋vendor 白名单（glm/openai）→True；
  anthropic 协议/未知 vendor →False；env ASSISTANT_HARNESS 强制覆盖
- chat() 非流式：响应带 tool_calls → meta["tool_calls"]（返回类型 str 不变）
"""

import asyncio

import ai_client as ai_client_module
from ai_client import AIClient

TOOL_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "read_chapter",
            "description": "读一章",
            "parameters": {
                "type": "object",
                "properties": {"chapter_ref": {"type": "string"}},
                "required": ["chapter_ref"],
            },
        },
    }
]


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _delta(content=None, reasoning=None, tool_calls=None):
    d = type("D", (), {})()
    d.content = content
    d.reasoning_content = reasoning
    d.tool_calls = tool_calls
    return d


def _tool_call_delta(index, id_="", name="", args=""):
    fn = type("F", (), {})()
    fn.name = name or None
    fn.arguments = args or None
    tc = type("T", (), {})()
    tc.index = index
    tc.id = id_ or None
    tc.function = fn
    return tc


def _chunk(delta, finish_reason=None, usage=None):
    choice = type("C", (), {})()
    choice.delta = delta
    choice.finish_reason = finish_reason
    return type("Chunk", (), {"choices": [choice], "usage": usage})()


class _StreamRecorder:
    """记录 create() kwargs，按剧本吐 chunk 流。"""

    def __init__(self, chunks):
        self.chunks = chunks
        self.kwargs: dict = {}

    async def _create(self, **kwargs):
        self.kwargs = kwargs

        async def _gen():
            for c in self.chunks:
                yield c

        return _gen()


class _FakeStreamOpenAI:
    def __init__(self, **kwargs):
        self.recorder: _StreamRecorder | None = None

        class _Completions:
            async def create(self, **kw):  # instance-bound via closure
                return await self.recorder._create(**kw)

        self._completions = _Completions()
        self.chat = type("Chat", (), {"completions": self._completions})()

    def set_script(self, recorder):
        self.recorder = recorder
        self._completions.create = lambda **kw: recorder._create(**kw)


def _make_client(monkeypatch, chunks):
    fake = _FakeStreamOpenAI()
    recorder = _StreamRecorder(chunks)
    fake.set_script(recorder)
    monkeypatch.setattr(ai_client_module, "AsyncOpenAI", lambda **kw: fake)
    c = AIClient(api_key="sk-x", base_url="https://x/v1", model="m", vendor="glm")
    return c, recorder


def test_chat_stream_passes_tools_and_aggregates(monkeypatch):
    chunks = [
        _chunk(_delta(reasoning="想一想")),
        _chunk(_delta(tool_calls=[_tool_call_delta(0, id_="call_1", name="read_chapter")])),
        _chunk(_delta(tool_calls=[_tool_call_delta(0, args='{"chapter_')])),
        _chunk(_delta(tool_calls=[_tool_call_delta(0, args='ref": "vol-1-ch-7"}')])),
        _chunk(_delta(), finish_reason="tool_calls"),
    ]
    c, rec = _make_client(monkeypatch, chunks)
    events = _run_async(
        _collect(
            c.chat_stream(model="m", system="", messages=[{"role": "user", "content": "x"}],
                          tools=TOOL_SPEC)
        )
    )
    assert rec.kwargs.get("tools") == TOOL_SPEC
    tc_events = [e for e in events if e.tool_calls]
    assert len(tc_events) == 1
    call = tc_events[0].tool_calls[0]
    assert call["id"] == "call_1"
    assert call["name"] == "read_chapter"
    assert call["arguments"] == {"chapter_ref": "vol-1-ch-7"}
    done = next(e for e in events if e.is_done)
    assert done.finish_reason == "tool_calls"
    # 思考与工具调用并行流出（spike 口径）
    assert any(e.thinking for e in events)


async def _collect(aiter):
    out = []
    async for ev in aiter:
        out.append(ev)
    return out


def test_chat_stream_bad_json_keeps_args_raw(monkeypatch):
    chunks = [
        _chunk(_delta(tool_calls=[_tool_call_delta(0, id_="c2", name="read_chapter", args='{"chapter_ref": ')])),
        _chunk(_delta(), finish_reason="tool_calls"),
    ]
    c, _rec = _make_client(monkeypatch, chunks)
    events = _run_async(
        _collect(c.chat_stream(model="m", system="", messages=[], tools=TOOL_SPEC))
    )
    call = next(e for e in events if e.tool_calls).tool_calls[0]
    assert call["arguments"] is None
    assert call["args_raw"] == '{"chapter_ref": '


def test_chat_stream_without_tools_no_tool_call_event(monkeypatch):
    chunks = [
        _chunk(_delta(content="正文")), 
        _chunk(_delta(), finish_reason="stop"),
    ]
    c, rec = _make_client(monkeypatch, chunks)
    events = _run_async(
        _collect(c.chat_stream(model="m", system="", messages=[]))
    )
    assert rec.kwargs.get("tools") is None
    assert not [e for e in events if e.tool_calls]
    assert any(e.text == "正文" for e in events)


def test_supports_native_tools_matrix(monkeypatch):
    c = AIClient(api_key="k", base_url="https://x/v1", model="m", vendor="glm")
    assert c.supports_native_tools() is True
    c2 = AIClient(api_key="k", base_url="https://x/v1", model="m", vendor="不认识的家伙")
    assert c2.supports_native_tools() is False
    c3 = AIClient(api_key="k", base_url="https://x/anthropic", model="m",
                  api_format="anthropic", vendor="glm")
    assert c3.supports_native_tools() is False
    monkeypatch.setenv("ASSISTANT_HARNESS", "text")
    assert c.supports_native_tools() is False
    monkeypatch.setenv("ASSISTANT_HARNESS", "native")
    assert c3.supports_native_tools() is True


def test_chat_nonstream_tool_calls_into_meta():
    """非流式出口：响应带 tool_calls → meta 填充；返回类型 str 不变。"""
    import ai_client as mod

    tc = _tool_call_delta(0, id_="c9", name="read_progress")
    tc.id = "c9"
    tc.function.name = "read_progress"
    tc.function.arguments = "{}"
    msg = type("M", (), {"content": "", "tool_calls": [tc]})()
    choice = type("C", (), {"message": msg})()
    usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 2})()
    response = type("R", (), {"choices": [choice], "usage": usage})()

    class _Recorder2:
        def __init__(self) -> None:
            self.kwargs: dict = {}

        async def _create(self, **kwargs):
            self.kwargs = kwargs
            return response

    rec = _Recorder2()

    class _FakeNonStream:
        def __init__(self, **kw):
            self.recorder = rec

            class _Completions:
                async def create(self, **kw2):
                    return await rec._create(**kw2)

            self.chat = type("Chat", (), {"completions": _Completions()})()

    c = mod.AIClient.__new__(mod.AIClient)
    # 手工装最小依赖面：openai 分支路径所需属性
    c._provider = "openai"
    c._vendor = "glm"
    c._model = "m"
    c._guarded = lambda x: x
    c._log_call = lambda *a, **k: None
    c._client = _FakeNonStream()
    c.resolve = lambda name: name
    c._openai_thinking_extra = lambda kw: {}
    meta: dict = {}
    out = _run_async(
        c.chat(model="m", system="", messages=[{"role": "user", "content": "x"}],
               tools=[t for t in TOOL_SPEC], meta=meta)
    )
    assert out == ""
    assert rec.kwargs.get("tools") == TOOL_SPEC
    assert meta["tool_calls"][0]["name"] == "read_progress"
    assert meta["tool_calls"][0]["arguments"] == {}
