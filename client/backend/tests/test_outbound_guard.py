# tests/test_outbound_guard.py
"""outbound_guard 单源校验：fake-ip 放行矩阵＋旧语义逐字保持（c-proxy-fakeip-compat）。

四条 CDN/更新链路的守卫收敛到这里；本文件是策略主靶（resolve 注入，无需 stub DNS），
调用方接线的行为保持由各自既有测试文件把守（_validate_outbound 全绿＝逐字保持）。
"""
import socket

import pytest

import outbound_guard as og

_TRUSTED = frozenset({"www.awesomenovel.com"})
_MAIN = "https://www.awesomenovel.com/prompts/latest.json"


def _infos(*ips: str) -> list:
    return [(2, 1, 6, "", (ip, 443)) for ip in ips]


# ── classify_infos：verdict 判定矩阵 ────────────────────────────────────────


def test_全公网_ok():
    assert og.classify_infos(_infos("106.55.209.168", "106.55.209.169")) == "ok"


def test_全fakeip_fakeip():
    assert og.classify_infos(_infos("198.18.0.1", "198.19.255.254")) == "fakeip"


def test_混合_公网fakeip_blocked():
    assert og.classify_infos(_infos("106.55.209.168", "198.18.0.1")) == "blocked"


def test_私网_blocked():
    assert og.classify_infos(_infos("192.168.1.5")) == "blocked"


def test_环回_blocked():
    assert og.classify_infos(_infos("127.0.0.1")) == "blocked"


def test_畸形IP_blocked():
    assert og.classify_infos(_infos("not-an-ip")) == "blocked"


def test_空解析_blocked():
    assert og.classify_infos([]) == "blocked"


# ── validate_outbound：目标段＋解析段 ───────────────────────────────────────


def test_https可信域fakeip解析_放行():
    ok, verdict = og.validate_outbound(
        _MAIN, _TRUSTED, resolve=lambda h: _infos("198.18.0.7"))
    assert ok is True and verdict == "fakeip"


def test_https可信域公网解析_放行ok():
    ok, verdict = og.validate_outbound(
        _MAIN, _TRUSTED, resolve=lambda h: _infos("106.55.209.168"))
    assert ok is True and verdict == "ok"


def test_混合解析_拒绝():
    ok, verdict = og.validate_outbound(
        _MAIN, _TRUSTED, resolve=lambda h: _infos("198.18.0.7", "192.168.1.5"))
    assert ok is False and verdict == "blocked"


def test_私网解析_拒绝():
    ok, verdict = og.validate_outbound(
        _MAIN, _TRUSTED, resolve=lambda h: _infos("192.168.1.5"))
    assert ok is False and verdict == "blocked"


def test_非可信域_拒绝():
    ok, verdict = og.validate_outbound(
        "https://evil.example.com/x.json", _TRUSTED,
        resolve=lambda h: _infos("106.55.209.168"))
    assert ok is False and verdict == "blocked"


def test_http_拒绝():
    ok, verdict = og.validate_outbound(
        "http://www.awesomenovel.com/prompts/latest.json", _TRUSTED,
        resolve=lambda h: _infos("106.55.209.168"))
    assert ok is False and verdict == "blocked"


def test_trusted_required_空集拒绝():
    """kb tree 语义：可信域空集直接拒（allowlist 缺失＝不猜）。"""
    ok, verdict = og.validate_outbound(
        _MAIN, frozenset(), resolve=lambda h: _infos("106.55.209.168"))
    assert ok is False and verdict == "blocked"


def test_trusted空集_非required_放行():
    """kb baseline 语义：可信域空集放行（开发态）。"""
    ok, verdict = og.validate_outbound(
        _MAIN, frozenset(), trusted_required=False,
        resolve=lambda h: _infos("106.55.209.168"))
    assert ok is True and verdict == "ok"


def test_IP字面量私网_拒绝():
    ok, verdict = og.validate_outbound(
        "https://192.168.1.5/x.json", _TRUSTED,
        resolve=lambda h: _infos("192.168.1.5"))
    assert ok is False and verdict == "blocked"


def test_IP字面量公网_放行():
    ok, verdict = og.validate_outbound(
        "https://106.55.209.168/x.json", frozenset({"106.55.209.168"}),
        resolve=lambda h: _infos("106.55.209.168"))
    assert ok is True and verdict == "ok"


def test_开发环回http_逃生口():
    """kb 开发逃生口逐字保持：可信域空集（开发态）＋http+环回宿主放行，
    且跳过解析段公网闸。"""
    ok, verdict = og.validate_outbound(
        "http://127.0.0.1:8800/knowledge/baseline/latest.json", frozenset(),
        allow_dev_loopback=True, trusted_required=False,
        resolve=lambda h: _infos("127.0.0.1"))
    assert ok is True and verdict == "ok"


def test_开发环回_非逃生口仍拒():
    ok, verdict = og.validate_outbound(
        "http://127.0.0.1:8800/x.json", _TRUSTED,
        resolve=lambda h: _infos("127.0.0.1"))
    assert ok is False and verdict == "blocked"


def test_环回宿主https_逃生口跳过解析闸():
    """kb 逃生口＝宿主白名单维度：可信域含环回宿主时环回解析放行（旧语义）。"""
    ok, verdict = og.validate_outbound(
        "https://localhost/x.json", frozenset({"localhost"}),
        allow_dev_loopback=True, resolve=lambda h: _infos("127.0.0.1"))
    assert ok is True and verdict == "ok"


def test_DNS失败_blocked():
    def _boom(hostname):
        raise OSError("dns down")

    ok, verdict = og.validate_outbound(_MAIN, _TRUSTED, resolve=_boom)
    assert ok is False and verdict == "blocked"


def test_真实socket解析被stub感知():
    """测试桩面契约：默认 resolve 走 socket.getaddrinfo（与旧 _validate_outbound
    的 monkeypatch 形态一致——桩 socket 模块即生效）。"""
    real = socket.getaddrinfo
    try:
        socket.getaddrinfo = lambda *a, **k: _infos("198.18.0.9")
        ok, verdict = og.validate_outbound(_MAIN, _TRUSTED)
        assert ok is True and verdict == "fakeip"
    finally:
        socket.getaddrinfo = real


# ── fake-ip 段本身（对拍 198.18.0.0/15 判定）──────────────────────────────


@pytest.mark.parametrize("ip", ["198.18.0.0", "198.18.255.255", "198.19.0.0", "198.19.255.255"])
def test_fakeip段边界(ip):
    assert og.classify_infos(_infos(ip)) == "fakeip"


@pytest.mark.parametrize("ip", ["198.17.255.255", "198.20.0.0"])
def test_段外_非fakeip(ip):
    # 段外公网地址判 ok；段外保留段判 blocked
    import ipaddress
    if ipaddress.ip_address(ip).is_global:
        assert og.classify_infos(_infos(ip)) == "ok"
    else:
        assert og.classify_infos(_infos(ip)) == "blocked"
