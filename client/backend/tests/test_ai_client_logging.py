"""backend-logging：AI 调用链留痕判据（openspec/changes/c-backend-daily-logging 2.4）。

成功 INFO 行（operation/model/host/耗时/tokens/ok）；失败 WARNING 行带归一化分类
＋attempt 序号；日志不含 api_key、不含正文全文。
"""

import logging
import time
from types import SimpleNamespace

import httpx
import pytest

import ai_client
from ai_client import AIClient, AITimeoutError


def _make_openai_client() -> AIClient:
    """绕过 __init__（不建真 SDK 客户端），直装 openai 形态的假 provider。"""
    c = AIClient.__new__(AIClient)
    c._provider = "openai"
    c._model = "test-model"
    c._base_url = "https://api.example.com/v1"
    c._temp_supported = True
    return c


def _fake_response(text: str = "OK", tokens_in: int = 11, tokens_out: int = 7):
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=tokens_in, completion_tokens=tokens_out),
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
    )


@pytest.fixture()
def cap_ai(caplog):
    caplog.set_level(logging.INFO, logger="ai_client")
    return caplog


def test_success_logs_info_line_with_tokens(cap_ai, daily_file_log):
    c = _make_openai_client()

    async def _create(**kw):
        return _fake_response()

    c._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )
    import asyncio

    usage: dict = {}
    out = asyncio.run(
        c.chat(
            model="haiku", system="sys", messages=[{"role": "user", "content": "SECRET-NOVEL-TEXT"}],
            usage=usage, operation="unit_op",
        )
    )
    assert out == "OK"
    assert usage["tokens_in"] == 11 and usage["tokens_out"] == 7, "usage 回填语义不受影响"
    line = [r.getMessage() for r in cap_ai.records if r.name == "ai_client"][-1]
    assert "event=ai_call" in line
    assert "op=unit_op" in line and "model=test-model" in line and "host=api.example.com" in line
    assert "tokens_in=11" in line and "tokens_out=7" in line and "result=ok" in line
    # 双断言之文件侧：同一行落按天文件
    file_text = (daily_file_log / "app.log").read_text(encoding="utf-8")
    assert "op=unit_op" in file_text and "result=ok" in file_text
    # 隐私红线：正文全文不落日志
    assert "SECRET-NOVEL-TEXT" not in cap_ai.text
    assert "SECRET-NOVEL-TEXT" not in file_text


def test_timeout_failure_logs_warning_with_class(cap_ai):
    c = _make_openai_client()

    async def _boom(**kw):
        raise httpx.TimeoutException("connect timeout")

    c._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_boom))
    )
    import asyncio

    with pytest.raises(AITimeoutError):
        asyncio.run(
            c.chat(
                model="haiku", system="s", messages=[{"role": "user", "content": "x"}],
                operation="unit_op_fail",
            )
        )
    line = [r.getMessage() for r in cap_ai.records if r.name == "ai_client"][-1]
    assert "result=timeout" in line, line
    assert "op=unit_op_fail" in line and "attempt=1" in line
    assert "SECRET" not in line  # 无正文


def test_log_call_attempt_field_and_truncation(cap_ai):
    c = _make_openai_client()
    start = time.perf_counter()
    c._log_call("unit_op2", "m", start, error=ValueError("模型未返回文本内容（返回块：['thinking']）"), attempt=2)
    line = [r.getMessage() for r in cap_ai.records if r.name == "ai_client"][-1]
    assert "attempt=2" in line and "result=empty_response" in line


def test_normalize_upstream_reject_classified(cap_ai):
    """AIRequestError（404/405 归一）分类＝upstream_reject。"""
    err = ai_client.AIRequestError("模型服务拒绝了请求（HTTP 405）")
    assert ai_client._classify_error(err) == "upstream_reject"
    assert ai_client._classify_error(AITimeoutError("x")) == "timeout"
    assert ai_client._classify_error(ValueError("模型未返回文本内容")) == "empty_response"


def test_stream_success_logs_final_line(cap_ai):
    """流式：done 事件前落一行 ok（tokens 来自流末 usage）。"""
    import asyncio

    c = _make_openai_client()

    class _FakeStream:
        def __init__(self):
            self._i = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            self._i += 1
            if self._i == 1:
                return SimpleNamespace(
                    usage=None,
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="片段"))],
                )
            if self._i == 2:
                return SimpleNamespace(
                    usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3),
                    choices=[],
                )
            raise StopAsyncIteration

    async def _create(**kw):
        return _FakeStream()

    c._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )

    async def _consume():
        events = []
        async for ev in c.chat_stream(
            model="haiku", system="s", messages=[{"role": "user", "content": "x"}],
            operation="unit_stream",
        ):
            events.append(ev)
        return events

    events = asyncio.run(_consume())
    assert events[-1].is_done and events[-1].tokens == 3
    lines = [r.getMessage() for r in cap_ai.records if r.name == "ai_client"]
    assert any("op=unit_stream" in m and "result=ok" in m and "tokens_out=3" in m for m in lines), lines


def test_stream_midway_failure_logs_warning(cap_ai):
    import asyncio

    c = _make_openai_client()

    class _DeadStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise httpx.TimeoutException("read timed out")

    async def _create(**kw):
        return _DeadStream()

    c._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )

    async def _consume():
        async for _ev in c.chat_stream(
            model="haiku", system="s", messages=[{"role": "user", "content": "x"}],
            operation="unit_stream_fail",
        ):
            pass

    with pytest.raises(AITimeoutError):
        asyncio.run(_consume())
    lines = [r.getMessage() for r in cap_ai.records if r.name == "ai_client"]
    assert any("op=unit_stream_fail" in m and "result=timeout" in m for m in lines), lines
