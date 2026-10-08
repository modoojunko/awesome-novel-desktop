# backend/tests/test_http_client.py
"""出网 HTTP 客户端工厂三分支回归（c-httpx-socks-fallback，spec outbound-http-client）。

分支口径见 design D5：走代理分支断言 mounts/transport 确为 SOCKS 代理传输（可辨别，
非「非 500」——三条出网链路的既有错误路径都把代理失败收敛为非 500，与降级直连不可
区分）；降级分支断言 trust_env=False 重建＋留痕无凭据；守恒分支干净 env 直连不变。
"""

import logging

import httpcore
import httpx
import pytest

from http_client import build_async_client, build_sync_client

_SOCKS_WITH_CREDS = "socks5://user:pass@127.0.0.1:59999"  # 端口未监听即可：构造期不连网

_PROXY_ENV_NAMES = (
    "HTTP_PROXY", "http_proxy",
    "HTTPS_PROXY", "https_proxy",
    "ALL_PROXY", "all_proxy",
)


def _isolate_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _PROXY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_async_socks_env_builds_socks_transport(monkeypatch):
    """走代理分支：env SOCKS 代理下所建 client 确系 SOCKS 代理传输、未降级。"""
    _isolate_proxy_env(monkeypatch)
    monkeypatch.setenv("ALL_PROXY", _SOCKS_WITH_CREDS)
    client = build_async_client(timeout=1)
    assert client._trust_env is True
    (transport,) = client._mounts.values()  # 单一环境代理 → 单 mounts 条目
    assert isinstance(transport._pool, httpcore.AsyncSOCKSProxy)


def test_sync_socks_env_builds_socks_transport(monkeypatch):
    _isolate_proxy_env(monkeypatch)
    monkeypatch.setenv("ALL_PROXY", _SOCKS_WITH_CREDS)
    with build_sync_client(timeout=1) as client:
        assert client._trust_env is True
        (transport,) = client._mounts.values()
        assert isinstance(transport._pool, httpcore.SOCKSProxy)


def test_async_degrades_to_direct_on_construction_error(monkeypatch, caplog):
    """降级分支：首笔构造 ImportError → trust_env=False 直连重建＋留痕无凭据。"""
    _isolate_proxy_env(monkeypatch)
    monkeypatch.setenv("ALL_PROXY", _SOCKS_WITH_CREDS)
    real = httpx.AsyncClient
    calls: list[dict] = []

    def flaky(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise ImportError(
                "Using SOCKS proxy, but the 'socksio' package is not installed."
            )
        return real(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", flaky)  # 模块属性 patch——工厂晚绑定可拦截
    with caplog.at_level(logging.WARNING, logger="http_client"):
        client = build_async_client(timeout=1, transport=None)

    assert client._trust_env is False  # 降级直连
    assert not client._mounts  # 无任何代理 mounts
    assert calls[0] == {"timeout": 1, "transport": None}  # 首笔 kwargs 全透传
    assert calls[1]["trust_env"] is False  # 重建仅覆写代理感知
    assert calls[1]["timeout"] == 1

    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "outbound_client_degrade" in joined
    assert "user:pass" not in joined  # 凭据绝不进日志（spec 降级留痕 MUST NOT）
    assert "socks5://127.0.0.1:59999" in joined  # 形态可诊断：scheme＋host:port


def test_sync_degrades_to_direct_on_construction_error(monkeypatch, caplog):
    _isolate_proxy_env(monkeypatch)
    monkeypatch.setenv("ALL_PROXY", _SOCKS_WITH_CREDS)
    real = httpx.Client
    calls: list[dict] = []

    def flaky(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise ImportError("Using SOCKS proxy, but the 'socksio' package is not installed.")
        return real(**kwargs)

    monkeypatch.setattr(httpx, "Client", flaky)
    client = build_sync_client(timeout=1)
    try:
        with caplog.at_level(logging.WARNING, logger="http_client"):
            assert client._trust_env is False
    finally:
        client.close()
    assert calls[1]["trust_env"] is False
    assert any("outbound_client_degrade" in r.getMessage() for r in caplog.records)


def test_clean_env_keeps_direct_behavior(monkeypatch, caplog):
    """守恒分支：无代理配置时不降级、无 mounts、零降级日志（spec 行为不变）。"""
    _isolate_proxy_env(monkeypatch)
    with caplog.at_level(logging.WARNING, logger="http_client"):
        client = build_async_client(timeout=1)
    assert client._trust_env is True
    assert not client._mounts
    assert not [r for r in caplog.records if "outbound_client_degrade" in r.getMessage()]
