"""回调验签背压（s-security-hardening 9.1）：独立桶/SIGNTEST 豁免/不可信只告警/白名单。"""
from __future__ import annotations

import pytest

from app.interfaces.web_api import notify as notify_mod
from app.main import app


class _FailGateway:
    def callback(self, headers, body):
        return None  # 恒验签失败


class _CaptureNotify:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, title: str, markdown: str = "") -> bool:
        self.sent.append((title, markdown))
        return True


@pytest.fixture
def backend(client, monkeypatch):
    """恒验签失败的网关 + 告警捕获 + 背压状态清零。"""
    notify_mod._reset_backpressure()
    monkeypatch.setattr(app.state, "payment_gateway", _FailGateway())
    cap = _CaptureNotify()
    monkeypatch.setattr(app.state, "notify_service", cap)
    return cap


def _post(client, ip: str | None = None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post("/api/pay/notify", content=b"junk", headers=headers)


def test_trusted_source_blocks_after_threshold(client, backend, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    codes = [_post(client, ip="9.9.9.9").status_code for _ in range(10)]
    assert all(c == 401 for c in codes), codes  # 阈值内逐次 401（微信可重试语义）
    assert _post(client, ip="9.9.9.9").status_code == 429  # 超阈 → 暂封
    assert any("验签连续失败" in t for t, _ in backend.sent)  # 达阈值告警


def test_untrusted_source_alerts_without_blocking(client, backend, monkeypatch):
    """默认（来源不可信）：只告警不阻断——真微信回调始终能进验签流程。"""
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    for _ in range(15):
        r = _post(client)
        assert r.status_code == 401  # 永远 401，不出现 429
    assert backend.sent and "验签连续失败" in backend.sent[0][0]


def test_signtest_exempt_from_backpressure(client, backend):
    """微信例行探测（SIGNTEST）：拒绝但不计数——连续探测不触发背压。"""
    codes = [client.post("/api/pay/notify", content=b"junk",
                         headers={"Wechatpay-Signature": "WECHATPAY/SIGNTEST/abc"}).status_code
             for _ in range(15)]
    assert all(c == 401 for c in codes)
    assert backend.sent == []  # 探测也不告警


def test_allowlist_enforced_when_configured(client, backend, monkeypatch):
    monkeypatch.setattr(notify_mod.settings, "WXPAY_NOTIFY_ALLOWLIST", "9.9.9.9")
    r = _post(client, ip="6.6.6.6")
    assert r.status_code == 403
    assert backend.sent == []  # 名单外不告警


def test_allowlist_off_by_default(client, backend, monkeypatch):
    monkeypatch.setattr(notify_mod.settings, "WXPAY_NOTIFY_ALLOWLIST", "")
    r = _post(client, ip="6.6.6.6")
    assert r.status_code == 401  # 未配置 → 一律进验签流程（行为不变）


def test_bad_allowlist_config_rejected_at_startup():
    """白名单解析失败 → 启动门禁拒绝（fail-fast，不静默失效）。"""
    import copy

    from app.config import settings

    original = settings.WXPAY_NOTIFY_ALLOWLIST
    try:
        settings.WXPAY_NOTIFY_ALLOWLIST = "10.0.0.0/8, not-a-net"
        errs = settings.startup_config_errors()
        assert any("WXPAY_NOTIFY_ALLOWLIST" in e for e in errs)
    finally:
        settings.WXPAY_NOTIFY_ALLOWLIST = original
        _ = copy


def test_backpressure_uses_independent_bucket(client, backend, monkeypatch):
    """背压与登录限流互不串桶：登录次数不影响回调判定。"""
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    for _ in range(5):
        client.post("/api/web/login", json={"username": "x", "password": "y"})
    r = _post(client, ip="9.9.9.9")
    assert r.status_code == 401  # 登录限流不影响回调计数
