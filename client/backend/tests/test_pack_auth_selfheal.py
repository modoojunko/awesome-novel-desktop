"""c-pack-auth-selfheal：静默自愈不得沿用过期令牌 ＋ 401 语义分离 ＋ 换钥不降档。

覆盖：
- token_expired：有效/过期/缺 exp/非 JWT/畸形 payload/边界（exp==now）
- 静默自愈臂：过期+exchange 成功（落盘＋触发同步钩子）／过期+不可达（现态保留）／
  有效令牌不换新／过期+配对终局失败（清凭据全集＋pairing_broken）／
  限流与网关 401 均按可重试态不清凭据
- call_server_api：HTTP 401 → code 401（JSON/非 JSON 体），200 照旧透传，5xx HTML 仍 -1
- prompt_pack.sync_once：换钥 401 → 终态 failed/auth，不降档重试

用法：cd client/backend && python -m pytest tests/test_pack_auth_selfheal.py -v
"""
import asyncio
import base64
import json
import os
import tempfile
import time
from pathlib import Path
from typing import ClassVar

_tmp_db = tempfile.NamedTemporaryFile(suffix="_selfheal.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_selfheal_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")

_REFRESH = {"tier": "pro", "expires_at": "2030-01-01",
            "entitlement": {"v": 1, "features": [], "limits": {"max_projects": None}}}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


_JWT_HEAD = _b64(b'{"alg":"HS256","typ":"JWT"}')


def _jwt(payload: dict) -> str:
    """测试用 JWT（客户端只解 payload 不验签——签名段给占位即可）。"""
    return f"{_JWT_HEAD}.{_b64(json.dumps(payload).encode())}.sig"


def _valid_token() -> str:
    return _jwt({"sub": "u", "username": "u", "exp": time.time() + 3600})


def _expired_token() -> str:
    return _jwt({"sub": "u", "username": "u", "exp": time.time() - 3600})


def _write_cfg(**overrides) -> dict:
    _service.CONFIG_FILE = _CFG_PATH
    cfg = {"pc_hash": "selfheal-hash", "device_secret": "s3cret", "tier": "none", "expires_at": ""}
    cfg.update(overrides)
    _service.save_local_config(cfg)
    return cfg


def _read_cfg() -> dict:
    return json.loads(Path(_service.CONFIG_FILE).read_text(encoding="utf-8"))


def _run(coro):
    return asyncio.run(coro)


def _patch_call(monkeypatch, responses: dict, calls: list | None = None):
    async def fake_call(endpoint, method="GET", params=None, json_body=None, with_token=False):
        if calls is not None:
            calls.append((endpoint, method, json_body))
        return responses[endpoint]

    monkeypatch.setattr(_service, "call_server_api", fake_call)

    async def fake_ensure(username):
        return None

    monkeypatch.setattr(_service, "_ensure_local_user", fake_ensure)


# ── 1. token_expired ─────────────────────────────────────────────────────────

class TestTokenExpired:
    def test_future_exp_is_valid(self):
        assert _service.token_expired(_valid_token()) is False

    def test_past_exp_is_expired(self):
        assert _service.token_expired(_expired_token()) is True

    def test_boundary_exp_now_is_expired(self):
        tok = _jwt({"sub": "u", "exp": 1000})
        assert _service.token_expired(tok, now=1000.0) is True
        assert _service.token_expired(tok, now=999.0) is False

    def test_missing_exp_is_expired(self):
        assert _service.token_expired(_jwt({"sub": "u"})) is True

    def test_non_jwt_is_expired(self):
        assert _service.token_expired("local-tok") is True
        assert _service.token_expired("") is True

    def test_malformed_payload_is_expired(self):
        assert _service.token_expired(f"{_b64(b'x')}.%%%not-base64%%%.sig") is True


# ── 2. 静默自愈臂 ────────────────────────────────────────────────────────────

class TestSilentSelfheal:
    def test_expired_token_exchanged_and_persisted(self, monkeypatch):
        """过期令牌 + 配对有效 → exchange 换新落盘，包同步钩子触发（自愈闭环）。"""
        _write_cfg(token=_expired_token(), username="u", tier="max")
        calls: list = []
        fired: list = []
        monkeypatch.setattr("prompt_pack.sync.maybe_after_auth", lambda: fired.append(1))
        _patch_call(monkeypatch, {
            "check-auth": {"code": 0, "data": dict(_REFRESH)},
            "pair/exchange": {"code": 0, "data": {"token": "fresh-tok", "username": "u", **_REFRESH}},
        }, calls)
        r = _run(_service.browser_auth(silent=True))
        assert r["code"] == 0 and r["data"]["token"] == "fresh-tok"
        body = next(j for e, m, j in calls if e == "pair/exchange")
        assert body == {"pc_hash": "selfheal-hash", "device_secret": "s3cret"}
        assert _read_cfg()["token"] == "fresh-tok"
        assert fired, "自愈成功必须触发包同步钩子"

    def test_valid_token_skips_exchange(self, monkeypatch):
        """有效令牌不发起 pair/exchange（避免无谓轮换）。"""
        tok = _valid_token()
        _write_cfg(token=tok, username="u")
        calls: list = []
        _patch_call(monkeypatch, {
            "check-auth": {"code": 0, "data": dict(_REFRESH)},
            "pair/exchange": {"code": 0, "data": {}},
        }, calls)
        r = _run(_service.browser_auth(silent=True))
        assert r["code"] == 0 and r["data"]["token"] == tok
        assert all(e != "pair/exchange" for e, _, _ in calls)

    def test_exchange_unreachable_keeps_stale_token(self, monkeypatch):
        """过期令牌 + S 端不可达 → 现态原样保留（可重试态，不清凭据）。"""
        stale = _expired_token()
        _write_cfg(token=stale, username="u", tier="max")
        _patch_call(monkeypatch, {
            "check-auth": {"code": 0, "data": dict(_REFRESH)},
            "pair/exchange": {"code": -1, "msg": "S端 不可达"},
        })
        r = _run(_service.browser_auth(silent=True))
        assert r["code"] == -1
        cfg = _read_cfg()
        assert cfg["token"] == stale and cfg["tier"] == "max"

    def test_exchange_401_envelope_is_retryable(self, monkeypatch):
        """网关 401 透传（call_server_api code=401）→ 与不可达同口径：现态保留。"""
        stale = _expired_token()
        _write_cfg(token=stale, username="u", tier="max")
        _patch_call(monkeypatch, {
            "check-auth": {"code": 0, "data": dict(_REFRESH)},
            "pair/exchange": {"code": 401, "msg": "无效的令牌"},
        })
        r = _run(_service.browser_auth(silent=True))
        assert r["code"] == -1
        assert _read_cfg()["token"] == stale

    def test_pairing_failure_with_dead_token_clears_full_set(self, monkeypatch):
        """配对终局失败 + 本地令牌已死 → 清凭据全集 + pairing_broken 独立标志。"""
        _write_cfg(token=_expired_token(), username="writer", tier="yearly",
                   expires_at="2027-01-01", last_login_at="2026-10-01T00:00:00+00:00",
                   entitlement_fetched_at="2026-10-01T00:00:00+00:00",
                   entitlement={"v": 1, "features": ["x"]}, tier_catalog={"v": 1},
                   deletion_pending=True)
        _patch_call(monkeypatch, {
            "check-auth": {"code": 0, "data": dict(_REFRESH)},
            "pair/exchange": {"code": 1, "msg": "配对失败，请在桌面端重新发起授权"},
        })
        r = _run(_service.browser_auth(silent=True))
        assert r["code"] == 1 and r["data"]["pairing_broken"] is True
        assert "重新登录" in r["data"]["message"] and "不受影响" in r["data"]["message"]
        cfg = _read_cfg()
        for k in ("token", "username", "expires_at", "last_login_at", "entitlement_fetched_at"):
            assert cfg[k] == "", f"{k} 必须清空"
        assert cfg["tier"] == "none"
        assert cfg["entitlement"] is None and cfg["tier_catalog"] is None
        assert cfg["deletion_pending"] is False
        # 非登录字段不动：设备标识与配对密语保留
        assert cfg["device_secret"] == "s3cret" and cfg["pc_hash"] == "selfheal-hash"

    def test_rate_limited_with_dead_token_keeps_credentials(self, monkeypatch):
        """限流（code 2）是可重试态不是终局失败：死令牌也 MUST NOT 清凭据。"""
        stale = _expired_token()
        _write_cfg(token=stale, username="u", tier="max")
        _patch_call(monkeypatch, {
            "check-auth": {"code": 0, "data": dict(_REFRESH)},
            "pair/exchange": {"code": 2, "msg": "请求过于频繁，请稍后再试"},
        })
        r = _run(_service.browser_auth(silent=True))
        assert r["code"] == 1
        assert r["data"].get("pairing_broken") is not True
        assert _read_cfg()["token"] == stale


# ── 3. call_server_api HTTP 401 透传 ─────────────────────────────────────────

class _StatusResp:
    def __init__(self, payload: dict | None, status: int):
        self._payload = payload
        self.status_code = status

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("non-json body")
        return self._payload


class _StatusClient:
    resp: ClassVar[_StatusResp | None] = None
    calls: ClassVar[list[str]] = []

    def __init__(self, *, timeout=None):  # noqa: ARG002 — 与 httpx 签名对齐
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _dispatch(self, url: str):
        type(self).calls.append(url)
        return type(self).resp

    async def get(self, url, params=None, headers=None):  # noqa: ARG002
        return await self._dispatch(url)

    async def post(self, url, json=None, headers=None):  # noqa: ARG002
        return await self._dispatch(url)


def _wire_http(monkeypatch, resp: _StatusResp) -> None:
    _StatusClient.calls = []
    _StatusClient.resp = resp
    monkeypatch.setattr(_service.httpx, "AsyncClient", _StatusClient)
    monkeypatch.setattr(_service, "_get_server_api", lambda: "https://s.example.com/api")
    monkeypatch.setattr(_service, "_get_server_api_fallback", lambda: "")


class TestCallServerApi401:
    def _post(self) -> dict:
        return _run(_service.call_server_api(
            "prompt-pack/key", method="POST", json_body={}, with_token=True))

    def test_http401_json_body_maps_to_401(self, monkeypatch):
        """S 端 401 的 envelope code（-1「无效的令牌」）以 HTTP status 为准 → 401。"""
        _wire_http(monkeypatch, _StatusResp({"code": -1, "msg": "无效的令牌"}, 401))
        assert self._post() == {"code": 401, "msg": "无效的令牌"}

    def test_http401_nonjson_body_maps_to_401(self, monkeypatch):
        """网关形态 401 非 JSON 体同样归 401，不再塌缩成 -1。"""
        _wire_http(monkeypatch, _StatusResp(None, 401))
        r = self._post()
        assert r["code"] == 401 and r["msg"]

    def test_http200_json_passthrough_unchanged(self, monkeypatch):
        _wire_http(monkeypatch, _StatusResp({"code": 0, "data": {"x": 1}}, 200))
        assert self._post() == {"code": 0, "data": {"x": 1}}

    def test_http503_html_still_minus1(self, monkeypatch):
        """网关冷启动 5xx HTML 维持既有「不可达」语义。"""
        _wire_http(monkeypatch, _StatusResp(None, 503))
        r = self._post()
        assert r["code"] == -1 and "503" in r["msg"]
