"""call_server_api 主/兜底基址切换 — 单测。

线上统一域名解析偶发抖动时，S端 调用要能自动切直连兜底地址，
终端用户零操作。关键行为：
- 主基址网络失败 → 兜底成功
- 双基址全失败 → 保留旧版错误语义（code=-1 / 网络超时|网络错误: …）
- 主基址正常 → 不发兜底请求
- 基址去重：兜底与主相同（或仅斜杠差异）时只打一次
"""

import asyncio
from typing import ClassVar

import httpx
import pytest

from auth_local import service as svc


class _FakeResp:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """按 host 分流：host 含 'down' 的请求一律抛 RequestError，其余返回 200。"""

    calls: ClassVar[list[str]] = []

    def __init__(self, *, timeout=None):  # noqa: ARG002 — 与 httpx 签名对齐
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _dispatch(self, url: str):
        self.calls.append(url)
        if "down" in url.split("/")[2]:
            raise httpx.RequestError("boom", request=httpx.Request("GET", url))
        return _FakeResp({"code": 0, "data": {"base": url}})

    # headers=None：镜像真 httpx.AsyncClient 签名（换钥 with_token 会传
    # Authorization——c-prompt-pack-client；真客户端本就接受该参数）
    async def get(self, url, params=None, headers=None):  # noqa: ARG002
        return await self._dispatch(url)

    async def post(self, url, json=None, headers=None):  # noqa: ARG002
        return await self._dispatch(url)


class _AlwaysFailClient(_FakeAsyncClient):
    async def _dispatch(self, url: str):
        self.calls.append(url)
        raise httpx.RequestError("x", request=httpx.Request("GET", url))


@pytest.fixture(autouse=True)
def _fake_client(monkeypatch):
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(svc.httpx, "AsyncClient", _FakeAsyncClient)


def _run() -> dict:
    return asyncio.run(svc.call_server_api("check-auth", params={"pc_hash": "x"}))


def test_primary_down_falls_back(monkeypatch):
    monkeypatch.setattr(svc, "_get_server_api", lambda: "https://primary-down.example.com/api")
    monkeypatch.setattr(
        svc, "_get_server_api_fallback", lambda: "https://backup-ok.example.com/api"
    )
    r = _run()
    assert r["code"] == 0 and "backup-ok" in r["data"]["base"]
    assert len(_FakeAsyncClient.calls) == 2 and "primary-down" in _FakeAsyncClient.calls[0]


def test_primary_ok_skips_fallback(monkeypatch):
    monkeypatch.setattr(svc, "_get_server_api", lambda: "https://primary-ok.example.com/api")
    monkeypatch.setattr(
        svc, "_get_server_api_fallback", lambda: "https://backup-ok.example.com/api"
    )
    r = _run()
    assert r["code"] == 0 and "primary-ok" in r["data"]["base"]
    assert len(_FakeAsyncClient.calls) == 1


def test_both_fail_keeps_legacy_error(monkeypatch):
    monkeypatch.setattr(svc.httpx, "AsyncClient", _AlwaysFailClient)
    monkeypatch.setattr(svc, "_get_server_api", lambda: "https://a-down.example.com/api")
    monkeypatch.setattr(svc, "_get_server_api_fallback", lambda: "https://b-down.example.com/api")
    r = _run()
    assert r["code"] == -1 and r["msg"].startswith("网络错误")


def test_duplicate_base_called_once(monkeypatch):
    monkeypatch.setattr(svc, "_get_server_api", lambda: "https://same.example.com/api")
    monkeypatch.setattr(svc, "_get_server_api_fallback", lambda: "https://same.example.com/api/")
    r = _run()
    assert len(_FakeAsyncClient.calls) == 1 and r["code"] == 0


def test_empty_fallback_keeps_single_base(monkeypatch):
    """未配置兜底（老部署形态）→ 行为同旧版单基址，只打一次。"""
    monkeypatch.setattr(svc, "_get_server_api", lambda: "https://only-up.example.com/api")
    monkeypatch.setattr(svc, "_get_server_api_fallback", lambda: "")
    r = _run()
    assert len(_FakeAsyncClient.calls) == 1 and r["code"] == 0


def test_fallback_reader_reads_env_chain(monkeypatch):
    """_get_server_api_fallback 取值链：config.json → SERVER_API_FALLBACK → 空串归一化。"""
    monkeypatch.delenv("SERVER_API_FALLBACK", raising=False)
    monkeypatch.delenv("AI_NOVEL_SERVER_API_FALLBACK", raising=False)
    monkeypatch.setattr(svc, "get_local_config", lambda: {"server_api_fallback": "https://cfg.example.com"})
    assert svc._get_server_api_fallback() == "https://cfg.example.com/api"

    monkeypatch.setattr(svc, "get_local_config", dict)
    monkeypatch.setenv("SERVER_API_FALLBACK", "https://env.example.com")
    assert svc._get_server_api_fallback() == "https://env.example.com/api"

    monkeypatch.delenv("SERVER_API_FALLBACK")
    assert svc._get_server_api_fallback() == ""
