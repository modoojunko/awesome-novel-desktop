"""限流绕过回归（s-security-hardening P0-B）。

实测漏洞（修复前）：`/api/web/login` 第 31 次 429，而剥 `/api` 前缀形态 `/web/login`
35 次全 200——归一化中间件在限流**内侧**，而生产网关转发过来的正是剥前缀形态
（同款绕行也可用于 /authorize）。等于唯一的口令防爆破防线不存在。

本文件锁三件事：①两形态同桶计数（执行序=归一化先于限流）；②敏感清单覆盖全部凭据入口；
③来源键信任开关（TRUSTED_PROXY_HOPS 默认 0，取右起可信跳，最左段可伪造不得采信）。
"""
from __future__ import annotations

import pytest

from app.interfaces.middleware import (
    RateLimitMiddleware,
    _client_key,
    _trusted_proxy_hops,
)


@pytest.fixture
def clear_bucket(client):
    """清空进程内限流桶：全量会话共享同一个 TestClient/中间件栈，桶跨用例累积。

    只影响限流状态，不改 LIMIT/清单——各用例自设阈值前先清桶，避免互相干扰。
    """
    node = getattr(client.app, "middleware_stack", None)
    found = False
    while node is not None:
        if isinstance(node, RateLimitMiddleware):
            node._history.clear()
            found = True
            break
        node = getattr(node, "app", None)
    assert found, "未在中间件栈中找到 RateLimitMiddleware"
    return node


class _FakeRequest:
    """_client_key 的最小替身（只用 client.host 与 headers）。"""

    def __init__(self, peer: str = "1.2.3.4", xff: str = ""):
        self.client = type("_C", (), {"host": peer})()
        self.headers = {"x-forwarded-for": xff} if xff else {}


# ══════════════════════════════════════════════════════════════════
# ① 剥前缀形态与带前缀形态同桶（执行序回归钉）
# ══════════════════════════════════════════════════════════════════

def test_stripped_prefix_form_shares_bucket_with_prefixed(client, monkeypatch, clear_bucket):
    """带前缀形态打满阈值后，剥前缀形态必须同样 429（修复前为 200=完全绕过）。"""
    monkeypatch.setattr(RateLimitMiddleware, "LIMIT", 3)
    payload = {"username": "nobody", "password": "wrong"}

    for _ in range(3):
        assert client.post("/api/web/login", json=payload).status_code == 200

    # 剥 /api 前缀形态（网关转发形态）→ 同桶 → 已超阈
    assert client.post("/web/login", json=payload).status_code == 429
    # 带前缀形态同样被拒（桶已满，两形态语义一致）
    assert client.post("/api/web/login", json=payload).status_code == 429


def test_authorize_stripped_prefix_also_covered(client, monkeypatch, clear_bucket):
    """C端 设备授权入口同样两形态同桶（/authorize 剥前缀曾同款可绕）。"""
    monkeypatch.setattr(RateLimitMiddleware, "LIMIT", 2)
    payload = {"username": "nobody", "password": "wrong", "pc_hash": "pc-x"}

    assert client.post("/api/authorize", json=payload).status_code == 200
    assert client.post("/api/authorize", json=payload).status_code == 200
    assert client.post("/authorize", json=payload).status_code == 429


# ══════════════════════════════════════════════════════════════════
# ② 清单覆盖与无死条目
# ══════════════════════════════════════════════════════════════════

# 人工对拍表：新增凭据校验端点时必须同步进 SENSITIVE_PATHS（本清单=评审用清单）
_CREDENTIAL_POST_ROUTES = (
    "/api/web/login",
    "/api/web/register",
    "/api/authorize",
    "/api/reset_password",
    "/api/user/password",
    "/api/user/deletion",
    "/api/user/deletion/revoke",
)


def test_credential_routes_are_rate_limited():
    missing = [p for p in _CREDENTIAL_POST_ROUTES if p not in RateLimitMiddleware.SENSITIVE_PATHS]
    assert not missing, f"凭据校验端点未纳限流清单：{missing}"


def test_no_dead_entries_in_sensitive_paths():
    """清单里不得有拼错/不存在的路径（pair/exchange 属任务 6.2 待落地，先白名单）。"""
    from app.main import _collect_api_paths, app

    known = _collect_api_paths(app.routes)
    dead = RateLimitMiddleware.SENSITIVE_PATHS - known
    assert not dead, f"清单含不存在路径：{dead}"


# ══════════════════════════════════════════════════════════════════
# ③ 来源键：默认不信任 XFF，可信跳数取右端
# ══════════════════════════════════════════════════════════════════

def test_hops_default_zero_ignores_xff(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    assert _trusted_proxy_hops() == 0
    # 默认下 XFF 完全不参与键计算（客户端可伪造该头，取它=把桶交给攻击者）
    assert _client_key(_FakeRequest(peer="1.2.3.4", xff="6.6.6.6, 9.9.9.9")) == "1.2.3.4"


@pytest.mark.parametrize("raw", ["", "  ", "abc", "0", "-2"])
def test_hops_invalid_falls_back_to_zero(monkeypatch, raw):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", raw)
    assert _trusted_proxy_hops() == 0


def test_hops_one_takes_rightmost_hop_ignoring_spoofed_left(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    # 反代追加语义：最左=客户端自带（可伪造），右端=可信代理注入 → 取右端
    assert _client_key(_FakeRequest(peer="10.0.0.1", xff="6.6.6.6, 9.9.9.9")) == "9.9.9.9"
    # 伪造最左段不改变键（换头也换不了桶）
    assert _client_key(_FakeRequest(peer="10.0.0.1", xff="7.7.7.7, 9.9.9.9")) == "9.9.9.9"


def test_hops_two_takes_second_from_right(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
    assert _client_key(_FakeRequest(peer="10.0.0.1", xff="8.8.8.8, 9.9.9.9")) == "8.8.8.8"


def test_hops_insufficient_chain_falls_back_to_peer(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "3")
    assert _client_key(_FakeRequest(peer="10.0.0.1", xff="9.9.9.9")) == "10.0.0.1"


def test_hops_strips_port_and_brackets(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    assert _client_key(_FakeRequest(peer="10.0.0.1", xff="9.9.9.9:5678")) == "9.9.9.9"
    assert _client_key(_FakeRequest(peer="10.0.0.1", xff="[2001:db8::1]")) == "2001:db8::1"
