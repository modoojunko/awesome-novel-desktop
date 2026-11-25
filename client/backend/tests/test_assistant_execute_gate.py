"""执行门测试（c-writing-agent-tier）。

口径：写类工具先过 assistant-execute（标准起），无权回升级 gate 事件；
读类/产卡类不在此门；兜底表按档含键、旧快照隐式放行按标准档。
"""

from types import SimpleNamespace

import assistant.router as router_mod
from auth_local.deps import _LEGACY_IMPLICIT_FEATURES, _TIER_RANK
from auth_local.service import STANDARD_FALLBACK


def test_write_tool_gated_when_not_granted(monkeypatch):
    calls = []

    def fake_granted(feature=None):
        calls.append(feature)
        return False

    monkeypatch.setattr(router_mod, "ai_access_granted", fake_granted)
    ev = router_mod.execute_gate_event(
        SimpleNamespace(kind="write", requires_feature="assistant-execute")
    )
    assert ev is not None
    assert ev["type"] == "gate"
    assert ev["feature"] == "assistant-execute"
    assert ev["tier_required"] == "standard"
    assert ev["approved"] is False
    assert calls == ["assistant-execute"]


def test_write_tool_passes_when_granted(monkeypatch):
    monkeypatch.setattr(router_mod, "ai_access_granted", lambda feature=None: True)
    tool = SimpleNamespace(kind="write", requires_feature="assistant-execute")
    assert router_mod.execute_gate_event(tool) is None


def test_read_and_card_tools_untouched(monkeypatch):
    monkeypatch.setattr(router_mod, "ai_access_granted", lambda feature=None: False)
    for kind in ("read", "card"):
        assert router_mod.execute_gate_event(SimpleNamespace(kind=kind, requires_feature="")) is None


def test_registry_declares_execute_for_all_write_tools():
    from assistant.tools import TOOL_REGISTRY

    write_tools = [t for t in TOOL_REGISTRY if t.kind == "write"]
    assert write_tools, "注册表无写类工具——基准坏了"
    for t in write_tools:
        assert t.requires_feature == "assistant-execute", t.name
    for t in TOOL_REGISTRY:
        if t.kind != "write":
            assert t.requires_feature == "", t.name


def test_fallback_member_tiers_include_key():
    for tier in ("standard", "pro", "max", "trial"):
        assert "assistant-execute" in STANDARD_FALLBACK[tier]["features"], tier
    for tier in ("none", "free"):
        assert "assistant-execute" not in STANDARD_FALLBACK[tier]["features"], tier


def test_legacy_implicit_allows_pro():
    # 三档会员：assistant-execute 标准免费不再发放，隐式放行最低 PRO。
    assert _LEGACY_IMPLICIT_FEATURES["assistant-execute"] == _TIER_RANK["pro"]
