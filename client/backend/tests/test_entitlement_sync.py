"""权益快照同步测试（c-s-entitlement-sync）

覆盖：
- 3.1 browser_auth(silent) 快照写入/清除
- 3.2 FALLBACK 名单含 pro/max、无 MEMBER_TIERS 残留（grep 由 CI/检视承担）
- 3.3 check_permission 优先级链全分支（快照自证/兜底/过期先于快照/trial 收紧）
- 3.4 ensure_entitlement_snapshot 重同步 + 节流
- 3.5 verify_session 透传 entitlement/entitlement_degraded
- 3.6 STANDARD_FALLBACK 与 docs/contracts/entitlement-defaults.json 对拍

用法：cd client/backend && python -m pytest tests/test_entitlement_sync.py -v
"""
import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

# ── Test environment (isolated temp config/DB，沿 test_ai_member_gate 套路) ──
_tmp_db = tempfile.NamedTemporaryFile(suffix="_ent_sync.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_ent_sync_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")
_AI_FEATURES = ["settings-ai-fields", "outline-advanced-fields",
                "ai-generate", "prompt-panel", "ai-model"]
_MEMBER_SNAP = {"v": 1, "features": _AI_FEATURES,
                "limits": {"max_projects": None}}


def _write_cfg(**overrides):
    _service.CONFIG_FILE = _CFG_PATH
    cfg = {"pc_hash": "ent-sync-test-hash", "tier": "none", "expires_at": ""}
    cfg.update(overrides)
    _service.save_local_config(cfg)
    return cfg


def _future(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


def _past(days: int = 1) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).date().isoformat()


# ── 3.2 FALLBACK 名单 ────────────────────────────────────────────────────────

def test_fallback_tiers_include_normalized_names():
    for t in ("trial", "pro", "max", "monthly", "quarterly", "yearly", "lifetime"):
        assert t in _service.FALLBACK_MEMBER_TIERS


# ── 3.3 check_permission 优先级链 ────────────────────────────────────────────

class TestCheckPermissionChain:
    def test_pro_with_member_snapshot_unlocks(self):
        _write_cfg(tier="pro", expires_at=_future(), entitlement=dict(_MEMBER_SNAP))
        perm = _service.check_permission()
        assert perm["allowed"] is True
        assert perm["is_member"] is True
        assert perm["project_limit"] is None
        assert perm["entitlement_degraded"] is False
        assert perm["entitlement"] == _MEMBER_SNAP

    def test_pro_without_snapshot_falls_back_member(self):
        """老 S端 无快照：档位名单兜底 → 会员不限（本次事故的补丁）。"""
        _write_cfg(tier="pro", expires_at=_future())
        perm = _service.check_permission()
        assert perm["is_member"] is True
        assert perm["project_limit"] is None
        assert perm["entitlement_degraded"] is False

    def test_expired_takes_precedence_over_snapshot(self):
        """过期先于快照：到期会员即使快照仍为会员内容也降免费基线。"""
        _write_cfg(tier="pro", expires_at=_past(), entitlement=dict(_MEMBER_SNAP))
        perm = _service.check_permission()
        assert perm["allowed"] is False
        assert perm["expired"] is True
        assert perm["is_member"] is False
        assert perm["project_limit"] == 1

    def test_trial_without_expiry_tightened_in_production(self):
        _write_cfg(tier="trial", expires_at="")
        perm = _service.check_permission()
        assert perm["allowed"] is False
        assert perm["is_member"] is False
        assert perm["project_limit"] == 1

    def test_trial_without_expiry_legacy_env_kept(self, monkeypatch):
        monkeypatch.setenv("ENTITLEMENT_LEGACY_TRIAL", "1")
        _write_cfg(tier="trial", expires_at="")
        perm = _service.check_permission()
        assert perm["is_member"] is True
        assert perm["project_limit"] is None

    def test_none_tier_stays_free_even_with_snapshot(self):
        """免费档位先于快照：none + 会员快照仍按免费（档位是身份底线）。"""
        _write_cfg(tier="none", entitlement=dict(_MEMBER_SNAP))
        perm = _service.check_permission()
        assert perm["is_member"] is False
        assert perm["project_limit"] == 1

    def test_incomplete_snapshot_uses_standard_fallback_degraded(self):
        """快照缺 max_projects（Q3）：按档位标准兜底 + degraded 标志。"""
        _write_cfg(tier="pro", expires_at=_future(),
                   entitlement={"v": 1, "features": _AI_FEATURES, "limits": {}})
        perm = _service.check_permission()
        assert perm["is_member"] is True
        assert perm["project_limit"] is None
        assert perm["entitlement_degraded"] is True

    def test_contradictory_snapshot_self_evident(self):
        """矛盾输入（tier=pro 快照=免费基线）：快照自证，白名单不翻案。"""
        _write_cfg(tier="pro", expires_at=_future(),
                   entitlement={"v": 1, "features": [], "limits": {"max_projects": 1}})
        perm = _service.check_permission()
        assert perm["is_member"] is False
        assert perm["project_limit"] == 1

    def test_deletion_pending_free_baseline(self):
        _write_cfg(tier="pro", expires_at=_future(), deletion_pending=True,
                   entitlement=dict(_MEMBER_SNAP))
        perm = _service.check_permission()
        assert perm["allowed"] is False
        assert perm["is_member"] is False
        assert perm["reason"] == "deletion_pending"


# ── 3.1 browser_auth(silent) 快照写入/清除 ──────────────────────────────────

class TestBrowserAuthSnapshot:
    def test_code0_saves_entitlement(self, monkeypatch):
        _write_cfg()

        async def fake_call(endpoint, params=None, json_body=None):
            assert endpoint == "check-auth"
            return {"code": 0, "data": {"token": "tok", "username": "u",
                                        "tier": "pro", "expires_at": "2126-01-01T00:00:00",
                                        "entitlement": dict(_MEMBER_SNAP)}}

        async def fake_ensure(username):
            return None

        monkeypatch.setattr(_service, "call_server_api", fake_call)
        monkeypatch.setattr(_service, "_ensure_local_user", fake_ensure)
        r = asyncio.run(_service.browser_auth(silent=True))
        assert r["code"] == 0
        cfg = _service.get_local_config()
        assert cfg["entitlement"]["features"] == _AI_FEATURES
        assert cfg["entitlement_fetched_at"]

    def test_code1_clears_entitlement(self, monkeypatch):
        _write_cfg(token="tok", tier="pro", expires_at=_future(),
                   entitlement=dict(_MEMBER_SNAP), entitlement_fetched_at="x")

        async def fake_call(endpoint, params=None, json_body=None):
            return {"code": 1, "data": {"deleted": False}}

        monkeypatch.setattr(_service, "call_server_api", fake_call)
        r = asyncio.run(_service.browser_auth(silent=True))
        assert r["code"] == 1
        cfg = _service.get_local_config()
        assert cfg["entitlement"] is None
        assert cfg["token"] == ""
        assert cfg["tier"] == "none"


# ── 3.4 ensure_entitlement_snapshot（重同步 + 节流）─────────────────────────

class TestEnsureEntitlementSnapshot:
    def setup_method(self):
        _service._LAST_ENT_RESYNC["t"] = 0.0

    def test_complete_snapshot_no_resync(self, monkeypatch):
        _write_cfg(entitlement=dict(_MEMBER_SNAP))
        calls = []

        async def fake_browser_auth(silent=False):
            calls.append(silent)
            return {"code": 0}

        monkeypatch.setattr(_service, "browser_auth", fake_browser_auth)
        asyncio.run(_service.ensure_entitlement_snapshot())
        assert calls == []

    def test_incomplete_snapshot_resyncs_once(self, monkeypatch):
        _write_cfg(tier="pro", entitlement={"v": 1, "features": _AI_FEATURES, "limits": {}})
        calls = []

        async def fake_browser_auth(silent=False):
            calls.append(silent)
            return {"code": 0}

        monkeypatch.setattr(_service, "browser_auth", fake_browser_auth)
        asyncio.run(_service.ensure_entitlement_snapshot())
        asyncio.run(_service.ensure_entitlement_snapshot())  # 60s 节流：第二次不再打
        assert calls == [True]

    def test_no_snapshot_no_resync(self, monkeypatch):
        _write_cfg(tier="pro")
        calls = []

        async def fake_browser_auth(silent=False):
            calls.append(silent)
            return {"code": 0}

        monkeypatch.setattr(_service, "browser_auth", fake_browser_auth)
        asyncio.run(_service.ensure_entitlement_snapshot())
        assert calls == []  # 无快照属分支 4，不触发重同步


# ── 3.5 verify_session 透传 ──────────────────────────────────────────────────

class TestVerifySessionPassthrough:
    def _login(self, **extra):
        _write_cfg(token="tok", username="u", tier="pro", expires_at=_future(),
                   last_login_at=datetime.now(UTC).isoformat(), **extra)

    def test_verify_carries_entitlement(self):
        self._login(entitlement=dict(_MEMBER_SNAP))
        r = asyncio.run(_service.verify_session())
        assert r["valid"] is True
        assert r["entitlement"] == _MEMBER_SNAP
        assert r["entitlement_degraded"] is False

    def test_verify_degraded_flag(self):
        self._login(entitlement={"v": 1, "features": _AI_FEATURES, "limits": {}},
                    entitlement_fetched_at="2026-09-07T06:00:00+00:00")
        r = asyncio.run(_service.verify_session())
        assert r["entitlement_degraded"] is True
        assert "entitlement" not in r  # 不完整快照不透传原文，只给标志
        assert r["entitlement_fetched_at"] == "2026-09-07T06:00:00+00:00"  # 详情三要素

    def test_verify_without_snapshot_omits_field(self):
        self._login()
        r = asyncio.run(_service.verify_session())
        assert "entitlement" not in r
        assert "entitlement_fetched_at" not in r
        assert r["entitlement_degraded"] is False


# ── 3.6 STANDARD_FALLBACK × 共享 JSON 对拍 ──────────────────────────────────

def test_standard_fallback_matches_shared_contract():
    contract_path = (Path(__file__).resolve().parents[3]
                     / "docs" / "contracts" / "entitlement-defaults.json")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    for tier_key, cfg_doc in contract["tiers"].items():
        fb = _service.STANDARD_FALLBACK[tier_key]
        assert fb["features"] == cfg_doc["features"], f"{tier_key} features 漂移"
        assert fb["limits"] == cfg_doc["limits"], f"{tier_key} limits 漂移"
    # 别名档位归位：legacy 名按归一化档取标准
    assert _service.standard_fallback_for("monthly") == _service.STANDARD_FALLBACK["pro"]
    assert _service.standard_fallback_for("lifetime") == _service.STANDARD_FALLBACK["pro"]
    assert _service.standard_fallback_for("unknown-tier") == _service.STANDARD_FALLBACK["none"]
