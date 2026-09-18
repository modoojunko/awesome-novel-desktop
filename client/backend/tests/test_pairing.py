"""设备配对挑战-应答（s-security-hardening）——C端 本机后端契约。

覆盖：
- device_secret 首启自生成 + challenge=SHA-256（密语绝不上 URL）
- 静默链路：S端 轮询无 token（硬切）→ 本机有令牌则保留刷新 / 无令牌走 pair/exchange
- exchange 失败（密钥不符/限流/S端 不可达）不清本地凭据、给出可重试/重授权信号

用法：cd client/backend && python -m pytest tests/test_pairing.py -v
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

_tmp_db = tempfile.NamedTemporaryFile(suffix="_pairing.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_pairing_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")

_REFRESH = {"tier": "pro", "expires_at": "2030-01-01", "entitlement": {"v": 1, "features": [], "limits": {"max_projects": None}}}


def _write_cfg(**overrides) -> dict:
    _service.CONFIG_FILE = _CFG_PATH
    cfg = {"pc_hash": "pairing-test-hash", "tier": "none", "expires_at": ""}
    cfg.update(overrides)
    _service.save_local_config(cfg)
    return cfg


def _run(coro):
    return asyncio.run(coro)


def _patch_call(monkeypatch, responses: dict, calls: list | None = None):
    async def fake_call(endpoint, method="GET", params=None, json_body=None):
        if calls is not None:
            calls.append((endpoint, method, params, json_body))
        return responses[endpoint]

    monkeypatch.setattr(_service, "call_server_api", fake_call)

    async def fake_ensure(username):
        return None

    monkeypatch.setattr(_service, "_ensure_local_user", fake_ensure)


# ── 1. device_secret 自举 ────────────────────────────────────────────────────

class TestDeviceSecretBootstrap:
    def test_first_load_generates_secret(self, monkeypatch):
        monkeypatch.setattr(_service, "CONFIG_FILE", _CFG_PATH)
        if os.path.exists(_CFG_PATH):
            os.unlink(_CFG_PATH)
        cfg = _service.load_or_create_config()
        assert len(cfg["device_secret"]) >= 40  # token_urlsafe(32) ≈ 43 字符
        # 幂等：再次加载不换密语（换了会使已授权设备的挑战失配）
        cfg2 = _service.load_or_create_config()
        assert cfg2["device_secret"] == cfg["device_secret"]

    def test_challenge_is_sha256_of_secret(self):
        import hashlib

        assert _service.device_challenge("abc") == hashlib.sha256(b"abc").hexdigest()

    def test_auth_url_carries_challenge_not_secret(self):
        url = _service._build_auth_url("https://www.example.com/api", "h1", "PC", "prof",
                                       challenge="c" * 64)
        assert f"challenge={'c' * 64}" in url
        assert "device_secret" not in url


# ── 2. 静默链路（硬切后的令牌获取）─────────────────────────────────────────

class TestSilentPairing:
    def test_poll_without_token_exchanges_and_returns_token(self, monkeypatch):
        """首装/掉登录：轮询无 token → 本机密钥换 token → 对前端仍回 code 0 + token。"""
        _write_cfg(pc_hash="ph1", device_secret="s3cret", token="", username="")
        calls: list = []
        _patch_call(monkeypatch, {
            "check-auth": {"code": 0, "data": dict(_REFRESH)},  # S端 硬切：无 token 字段
            "pair/exchange": {"code": 0, "data": {"token": "tok-1", "username": "u", **_REFRESH}},
        }, calls)
        result = _run(_service.browser_auth(silent=True))
        assert result["code"] == 0 and result["data"]["token"] == "tok-1"
        assert any(e == "pair/exchange" and m == "POST" for e, m, _, _ in calls)
        body = next(json_body for e, m, _, json_body in calls if e == "pair/exchange")
        assert body == {"pc_hash": "ph1", "device_secret": "s3cret"}

    def test_poll_without_token_keeps_local_token_when_present(self, monkeypatch):
        """本地已有令牌：轮询仅刷套餐数据，不得覆盖/清空本地令牌。"""
        _write_cfg(pc_hash="ph2", device_secret="s3cret", token="local-tok", username="u")
        _patch_call(monkeypatch, {
            "check-auth": {"code": 0, "data": dict(_REFRESH)},
            "pair/exchange": {"code": 1, "msg": "配对失败"},  # 不应被调用
        })
        result = _run(_service.browser_auth(silent=True))
        assert result["code"] == 0 and result["data"]["token"] == "local-tok"
        cfg = json.loads(Path(_service.CONFIG_FILE).read_text(encoding="utf-8"))
        assert cfg["token"] == "local-tok"
        assert cfg["tier"] == "pro"  # 套餐数据照常刷新

    def test_exchange_rejection_keeps_credentials(self, monkeypatch):
        """配对被拒（密钥不符/未升级）：MUST NOT 清凭据，给出重新授权信号。"""
        _write_cfg(pc_hash="ph3", device_secret="s3cret", token="", username="")
        _patch_call(monkeypatch, {
            "check-auth": {"code": 0, "data": dict(_REFRESH)},
            "pair/exchange": {"code": 1, "msg": "配对失败，请在桌面端重新发起授权"},
        })
        result = _run(_service.browser_auth(silent=True))
        assert result["code"] == 1
        assert "重新登录" in result["data"]["message"] or "重新授权" in result["data"]["message"]
        cfg = json.loads(Path(_service.CONFIG_FILE).read_text(encoding="utf-8"))
        assert cfg.get("device_secret") == "s3cret"  # 凭据/密语原样保留

    def test_exchange_rate_limited_is_retryable(self, monkeypatch):
        """429/网关失败（无业务 code）按可重试处理：不清凭据，向下游报网络态。"""
        _write_cfg(pc_hash="ph4", device_secret="s3cret", token="", username="")
        _patch_call(monkeypatch, {
            "check-auth": {"code": 0, "data": dict(_REFRESH)},
            "pair/exchange": {"code": 2, "msg": "请求过于频繁，请稍后再试"},
        })
        result = _run(_service.browser_auth(silent=True))
        assert result["code"] == 1  # 未授权完成；凭据仍在，可重试
        cfg = json.loads(Path(_service.CONFIG_FILE).read_text(encoding="utf-8"))
        assert cfg.get("device_secret") == "s3cret"

    def test_exchange_server_unreachable_reports_minus1(self, monkeypatch):
        _write_cfg(pc_hash="ph5", device_secret="s3cret", token="", username="")
        _patch_call(monkeypatch, {
            "check-auth": {"code": 0, "data": dict(_REFRESH)},
            "pair/exchange": {"code": -1, "msg": "S端 不可达"},
        })
        result = _run(_service.browser_auth(silent=True))
        assert result["code"] == -1

    def test_poll_with_token_unchanged(self, monkeypatch):
        """S端 仍回 token（兼容形态）时行为不变——回归钉。"""
        _write_cfg(pc_hash="ph6", device_secret="s3cret", token="", username="")
        _patch_call(monkeypatch, {
            "check-auth": {"code": 0, "data": {"token": "tok-legacy", "username": "u", **_REFRESH}},
        })
        result = _run(_service.browser_auth(silent=True))
        assert result["code"] == 0 and result["data"]["token"] == "tok-legacy"
