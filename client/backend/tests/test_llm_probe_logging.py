"""c-llm-call-log：连接探针／朱雀检测留痕行判据（llm.log 专项档）。

定诊本命（Gemini 401 案）：探针出网每请求一行——host＋path＋上游状态码＋耗时
＋结果分类；Key / 正文 / URL query 永不落行。脚本桩同 test_api_format 的
fake_http 惯例（monkeypatch httpx.AsyncClient）。
"""

import asyncio
import logging
from typing import ClassVar

import httpx
import pytest

from api_configs import connection as conn_mod
from zhuque import client as zhuque_mod
from zhuque.client import ZhuqueUpstreamError


def _run_async(coro):
    return asyncio.run(coro)


class _FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body
        self.headers = {"content-type": "application/json"}

    def json(self):
        if self._body is None:
            raise ValueError("non-json body")
        return self._body


class _FakeAsyncClient:
    script: ClassVar[list] = []
    calls: ClassVar[list] = []

    def __init__(self, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        return self._next(("GET", url, headers))

    async def post(self, url, headers=None, json=None):
        return self._next(("POST", url, headers, json))

    def _next(self, call):
        type(self).calls.append(call)
        entry = type(self).script.pop(0)
        if isinstance(entry, Exception):
            raise entry
        return entry


@pytest.fixture
def fake_http(monkeypatch):
    _FakeAsyncClient.script = []
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(
        conn_mod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(**kw)
    )
    return _FakeAsyncClient


@pytest.fixture
def zhuque_http(monkeypatch):
    _FakeAsyncClient.script = []
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(
        zhuque_mod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(**kw)
    )
    monkeypatch.setenv("ZHUQUE_API_BASE", "https://gw.example.com")
    return _FakeAsyncClient


@pytest.fixture()
def cap_probe(caplog):
    caplog.set_level(logging.INFO, logger="llm_probe")
    return caplog


@pytest.fixture()
def cap_zhuque(caplog):
    caplog.set_level(logging.INFO, logger="zhuque.client")
    return caplog


def _probe_lines(cap):
    return [r for r in cap.records if r.name == "llm_probe"]


def _zhuque_lines(cap):
    return [r for r in cap.records if r.name == "zhuque.client"]


# ── 连接探针（test_connection / fetch_models）────────────────────────────────


def test_fetch_models_401_logs_auth_error_line(fake_http, cap_probe):
    """Gemini 401 案本命：Key 失焦探针 401 必须自己留一行——host＋status＋result。"""
    fake_http.script = [
        _FakeResp(401, {"error": {"message": "API key not valid. Please pass a valid API key."}})
    ]
    out = _run_async(conn_mod.fetch_models(
        vendor_id="custom", api_key="sk-SECRET-KEY-000",
        base_url="https://relay.example.com/v1", api_format="openai",
    ))
    assert out["status"] == "auth_error"
    records = _probe_lines(cap_probe)
    assert len(records) == 1, "一个出网请求恰一行留痕"
    line = records[0].getMessage()
    assert "kind=models_list" in line
    assert "vendor=custom" in line and "format=openai" in line
    assert "host=relay.example.com" in line and "path=/v1/models" in line
    assert "status=401" in line and "result=auth_error" in line
    assert records[0].levelno == logging.WARNING, "失败行升 WARNING"
    # 隐私红线：Key 在请求头里，永不落行
    assert "sk-SECRET-KEY-000" not in line
    assert "sk-SECRET-KEY-000" not in cap_probe.text


def test_test_connection_401_logs_line(fake_http, cap_probe):
    fake_http.script = [_FakeResp(401, {"error": {"message": "invalid"}})]
    out = _run_async(conn_mod.test_connection(
        vendor_id="custom", api_key="sk-SECRET",
        base_url="https://relay.example.com/v1",
    ))
    assert out["status"] == "auth_error"
    line = _probe_lines(cap_probe)[-1].getMessage()
    assert "status=401" in line and "result=auth_error" in line
    assert "sk-SECRET" not in line


def test_models_timeout_logs_line(fake_http, cap_probe):
    fake_http.script = [httpx.ConnectTimeout("connect timed out")]
    out = _run_async(conn_mod.test_connection(
        vendor_id="custom", api_key="sk",
        base_url="https://slow.example.com/v1",
    ))
    assert out["status"] == "timeout"
    line = _probe_lines(cap_probe)[-1].getMessage()
    assert "status=0" in line and "result=timeout" in line
    assert "host=slow.example.com" in line


def test_happy_path_logs_models_and_generation_lines(fake_http, cap_probe):
    """openai 全通：models 行＋生成探针行各一条，均 INFO result=ok。"""
    fake_http.script = [
        _FakeResp(200, {"data": [{"id": "m-1"}]}),
        _FakeResp(200, {"choices": [{"message": {"content": "你好！"}}]}),
    ]
    out = _run_async(conn_mod.test_connection(
        vendor_id="custom", api_key="sk", base_url="https://api.example.com/v1",
        preferred_model="m-1",
    ))
    assert out["ok"] is True
    records = _probe_lines(cap_probe)
    assert len(records) == 2
    models_line = records[0].getMessage()
    assert "kind=models_list" in models_line and "status=200" in models_line
    assert "result=ok" in models_line
    gen_line = records[1].getMessage()
    assert "kind=generation_probe" in gen_line and "model=m-1" in gen_line
    assert "path=/v1/chat/completions" in gen_line and "result=ok" in gen_line
    assert records[1].levelno == logging.INFO


def test_generation_probe_empty_reply_warns(fake_http, cap_probe):
    """200 但回复为空：探针判失败，行记 result=unknown（WARNING）。"""
    fake_http.script = [
        _FakeResp(200, {"data": [{"id": "m-1"}]}),
        _FakeResp(200, {"choices": [{"message": {"content": ""}}]}),
    ]
    out = _run_async(conn_mod.test_connection(
        vendor_id="custom", api_key="sk", base_url="https://api.example.com/v1",
    ))
    assert out["ok"] is False
    records = _probe_lines(cap_probe)
    line = records[-1].getMessage()
    assert "kind=generation_probe" in line and "result=unknown" in line
    assert records[-1].levelno == logging.WARNING


def test_anthropic_fallback_probe_lines(fake_http, cap_probe):
    """anthropic 404 降级：models 行如实记 not_found，降级探针 401 行 auth_error。"""
    fake_http.script = [
        _FakeResp(404, {"error": {"message": "not found"}}),
        _FakeResp(401, {"error": {"message": "invalid x-api-key"}}),
    ]
    out = _run_async(conn_mod.test_connection(
        vendor_id="glm", api_key="sk",
        base_url="https://open.bigmodel.cn/api/anthropic", api_format="anthropic",
    ))
    assert out["status"] == "auth_error"
    records = _probe_lines(cap_probe)
    assert len(records) == 2
    models_line = records[0].getMessage()
    assert "kind=models_list" in models_line and "status=404" in models_line
    assert "result=not_found" in models_line, "请求级事实：404 就是 404"
    gen_line = records[1].getMessage()
    assert "kind=generation_probe" in gen_line and "status=401" in gen_line
    assert "result=auth_error" in gen_line and "vendor=glm" in gen_line


def test_probe_url_query_never_logged(fake_http, cap_probe):
    """query 可能含 Key（某些网关 ?key= 传钥）——path 只取路径段，query 永不落行。"""
    fake_http.script = [_FakeResp(401, {"error": {"message": "bad"}})]
    _run_async(conn_mod.fetch_models(
        vendor_id="custom", api_key="sk",
        base_url="https://gw.example.com/v1?key=AIzaQUERY-SECRET",
        api_format="openai",
    ))
    text = cap_probe.text
    assert "AIzaQUERY-SECRET" not in text
    assert "key=" not in text


def test_malformed_base_url_never_breaks_probe(fake_http, cap_probe):
    """评审 P2：未闭合 `[` 等畸形 URL httpx 接受并真实连接失败——探针须仍返回
    友好 network_error（不得从 except 处理器里二次抛 ValueError 500 化），
    留痕行 host/path 兜底 -。"""
    fake_http.script = [httpx.ConnectError("connection failed")]
    out = _run_async(conn_mod.test_connection(
        vendor_id="custom", api_key="sk", base_url="http://[",
    ))
    assert out["status"] == "network_error"
    line = _probe_lines(cap_probe)[-1].getMessage()
    assert "host=-" in line and "path=-" in line
    assert "result=network_error" in line


def test_ollama_probe_logs_native_format(fake_http, cap_probe):
    """评审 P3：ollama 探测走原生 /api/tags（_build_probe 特例），format 记 -
    而非误记入参缺省 openai。"""
    fake_http.script = [_FakeResp(200, {"models": [{"name": "llama3"}]})]
    out = _run_async(conn_mod.test_connection(
        vendor_id="ollama", api_key="", base_url="http://localhost:11434",
    ))
    assert out["ok"] is True
    line = _probe_lines(cap_probe)[-1].getMessage()
    assert "vendor=ollama" in line and "path=/api/tags" in line
    assert "format=-" in line


# ── 朱雀检测（zhuque.client.classify）────────────────────────────────────────


def test_zhuque_ok_logs_line_with_chars_only(zhuque_http, cap_zhuque):
    text = "这是整章正文绝密内容SECRET-CHAPTER"
    zhuque_http.script = [_FakeResp(200, {"status": "success", "labels": []})]
    out = _run_async(zhuque_mod.classify(text, "zk-SECRET-KEY"))
    assert out["status"] == "success"
    records = _zhuque_lines(cap_zhuque)
    assert len(records) == 1, "classify 每次调用恰一行留痕"
    line = records[0].getMessage()
    assert "kind=zhuque_classify" in line and "vendor=zhuque" in line
    assert "host=gw.example.com" in line and "status=200" in line
    assert f"chars={len(text)}" in line and "result=ok" in line
    assert records[0].levelno == logging.INFO
    # 隐私红线：正文只记字符数
    assert "SECRET-CHAPTER" not in line and "SECRET-CHAPTER" not in cap_zhuque.text
    assert "zk-SECRET-KEY" not in line


def test_zhuque_401_logs_auth_error(zhuque_http, cap_zhuque):
    zhuque_http.script = [_FakeResp(401, {"error": {"message": "bad key"}})]
    with pytest.raises(ZhuqueUpstreamError) as ei:
        _run_async(zhuque_mod.classify("正文", "zk-SECRET"))
    assert ei.value.status == 401
    line = _zhuque_lines(cap_zhuque)[-1]
    assert "status=401" in line.getMessage() and "result=auth_error" in line.getMessage()
    assert line.levelno == logging.WARNING


def test_zhuque_timeout_logs_line(zhuque_http, cap_zhuque):
    zhuque_http.script = [httpx.ReadTimeout("read timed out")]
    with pytest.raises(ZhuqueUpstreamError) as ei:
        _run_async(zhuque_mod.classify("正文", "zk"))
    assert ei.value.status == 0
    line = _zhuque_lines(cap_zhuque)[-1].getMessage()
    assert "status=0" in line and "result=timeout" in line


def test_zhuque_non_json_200_controlled_and_logged(zhuque_http, cap_zhuque):
    """200 但体非 JSON：受控上抛 ZhuqueUpstreamError（不再裸抛 JSONDecodeError）
    且恰一行 result=bad_response——「每次调用恰一行」的边界。"""
    zhuque_http.script = [_FakeResp(200, None)]
    with pytest.raises(ZhuqueUpstreamError) as ei:
        _run_async(zhuque_mod.classify("正文", "zk"))
    assert "无法解析" in ei.value.message
    records = _zhuque_lines(cap_zhuque)
    assert len(records) == 1
    assert "result=bad_response" in records[0].getMessage()
    assert "status=200" in records[0].getMessage()
