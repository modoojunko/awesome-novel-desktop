"""c-modelconfig-gemini-go 单元账：vendor 身份链三模式＋OpenCode 身份头＋Gemini 思考换算。

覆盖 spec「供应商分组页签／供应商默认值预填／订阅入口与 Gemini 的调用适配」的
调用层行为（页签交互在前端套件 apiConfigForm.test.tsx）：
  - KNOWN_VENDORS 白名单放行三新键、检测链区分两个 Go 键（/v1 模式在前防遮蔽）
  - opencode_identity_headers：会话标识进程内稳定＋产品 UA；is_opencode_base 主机口径
  - 探针头（_build_probe 双格式）附头/不附头
  - 探针 payload（_generation_payload）与 AIClient 思考参数的 Gemini 契约换算（双路径同口径）
"""
from __future__ import annotations

import pytest

from api_configs import connection
from api_configs.schemas import KNOWN_VENDORS
from api_configs.vendor import (
    detect_vendor,
    gemini_effort,
    is_opencode_base,
    opencode_identity_headers,
    resolve_vendor,
)

# ── vendor 身份链：检测/白名单/顺序遮蔽 ──────────────────────────────────


def test_new_vendor_ids_in_whitelist():
    for v in ("gemini", "opencode-go-chat", "opencode-go-claude"):
        assert v in KNOWN_VENDORS


def test_opencode_go_candidates_cover_minimax_m31_flash():
    """拆书可直接选用的 MiniMax 模型 id 必须在候选清单里（官方清单 2026-10-22）。

    M3.1 Flash 走 Go·通用（OpenAI 格式）口，官方 id 带 -free 后缀；Go·Claude 系
    走 anthropic 口，登记的是 minimax-m3——两口各留各的，不混投（混投会探针失败）。
    """
    from api_configs.connection import VENDOR_MODEL_CANDIDATES as C

    assert "minimax-m3.1-flash-free" in C["opencode-go-chat"]
    assert "minimax-m3" in C["opencode-go-claude"]
    assert "minimax-m3.1-flash-free" not in C["opencode-go-claude"]


def test_detect_gemini_official_compat_base():
    vp = detect_vendor("https://generativelanguage.googleapis.com/v1beta/openai/")
    assert vp is not None and vp.vendor_id == "gemini"
    assert resolve_vendor("https://generativelanguage.googleapis.com/v1beta/openai/")[0] == "gemini"


def test_detect_opencode_two_keys_split_by_path_no_shadowing():
    # /v1 在前：chat URL 必须命中 chat 键（而非被无版本段模式遮蔽成 claude）
    assert resolve_vendor("https://opencode.ai/zen/go/v1")[0] == "opencode-go-chat"
    assert resolve_vendor("https://opencode.ai/zen/go")[0] == "opencode-go-claude"
    # zen 按量口（非 go）不认——落 openai-compat 兜底
    assert resolve_vendor("https://opencode.ai/zen/v1")[0] == "openai-compat"


# ── OpenCode 身份头 ──────────────────────────────────────────────────────


def test_is_opencode_base_host_scope():
    assert is_opencode_base("https://opencode.ai/zen/go/v1")
    assert is_opencode_base("https://api.opencode.ai/zen/go")
    assert not is_opencode_base("https://api.deepseek.com")
    assert not is_opencode_base("https://opencode.ai.evil.example/zen/go/v1")
    assert not is_opencode_base("")
    assert not is_opencode_base("not a url")


def test_identity_headers_session_stable_within_process_and_product_ua():
    h1 = opencode_identity_headers("sk-1", "https://opencode.ai/zen/go/v1")
    h2 = opencode_identity_headers("sk-1", "https://opencode.ai/zen/go/v1")
    assert h1["x-opencode-session"] == h2["x-opencode-session"]
    assert h1["x-opencode-session"]
    assert h1["User-Agent"].startswith("ai-novel/")
    # 不同配置 → 不同会话标识
    assert (
        opencode_identity_headers("sk-2", "https://opencode.ai/zen/go/v1")["x-opencode-session"]
        != h1["x-opencode-session"]
    )


# ── 探针头：生成/探针同口径（connection._build_probe 双格式） ─────────────


def test_build_probe_openai_opencode_includes_identity_headers():
    _, headers, _, fallback = connection._build_probe(
        "openai", "opencode-go-chat", "sk-1", "https://opencode.ai/zen/go/v1"
    )
    assert "x-opencode-session" in headers
    assert headers["User-Agent"].startswith("ai-novel/")
    # 降级探针同头（同一 dict 拷贝）
    assert fallback is not None and "x-opencode-session" in fallback[1]


def test_build_probe_anthropic_opencode_includes_identity_headers():
    _, headers, _, _ = connection._build_probe(
        "anthropic", "opencode-go-claude", "sk-1", "https://opencode.ai/zen/go"
    )
    assert "x-opencode-session" in headers
    assert headers["x-api-key"] == "sk-1"


def test_build_probe_non_opencode_no_identity_headers():
    _, headers, _, fallback = connection._build_probe(
        "openai", "deepseek", "sk-1", "https://api.deepseek.com"
    )
    assert "x-opencode-session" not in headers
    assert fallback is not None and "x-opencode-session" not in fallback[1]


# ── Gemini 思考换算：探针 payload 与 AIClient 双路径同口径 ────────────────


def test_gemini_effort_mapping():
    assert gemini_effort("low") == "low"
    assert gemini_effort("high") == "high"
    assert gemini_effort("max") == "high"  # Gemini 契约无 max 档
    assert gemini_effort("") == "low"


def test_probe_payload_gemini_on_maps_effort_and_drops_thinking_key():
    p = connection._generation_payload(
        "gemini-2.5-pro", thinking_enabled=True, thinking_effort="max", vendor_id="gemini"
    )
    assert p["reasoning_effort"] == "high"
    assert "thinking" not in p


def test_probe_payload_gemini_off_is_reasoning_none():
    p = connection._generation_payload(
        "gemini-2.5-pro", thinking_enabled=False, thinking_effort="low", vendor_id="gemini"
    )
    assert p["reasoning_effort"] == "none"
    assert "thinking" not in p


def test_probe_payload_non_gemini_unchanged_glm_contract():
    p = connection._generation_payload(
        "glm-5.3", thinking_enabled=True, thinking_effort="max", vendor_id="glm"
    )
    assert p["thinking"] == {"type": "enabled"}
    assert p["reasoning_effort"] == "max"
    p2 = connection._generation_payload("glm-5.3", thinking_enabled=False, vendor_id="glm")
    assert p2["thinking"] == {"type": "disabled"}


def test_ai_client_thinking_params_gemini_contract():
    from ai_client import AIClient

    c = AIClient.__new__(AIClient)  # 直装实例（与既有测试同款，绕开 SDK 构造）
    c._vendor = "gemini"
    c._base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
    c._thinking_enabled = True
    c._thinking_effort = "max"
    assert c._thinking_params() == {"reasoning_effort": "high"}
    c._thinking_enabled = False
    assert c._thinking_params() == {"reasoning_effort": "none"}
    # 显式 disabled（判定类路径）同口径
    assert c._explicit_thinking_params({"type": "disabled"}) == {"reasoning_effort": "none"}


def test_probe_payload_claude_adaptive_shapes():
    # zen claude 上游真机实证：开＝adaptive 裸形态（budget/reasoning_effort 均多余输入）；
    # 关＝disabled 形态可用
    on = connection._generation_payload(
        "claude-haiku-5-5", thinking_enabled=True, thinking_effort="high",
        vendor_id="opencode-go-claude",
    )
    assert on["thinking"] == {"type": "adaptive"}
    assert "reasoning_effort" not in on
    assert on["max_tokens"] == 3072  # 评审 P3 硬化：adaptive 耗量自决，探针预算放大防判空
    off = connection._generation_payload(
        "claude-haiku-5-5", thinking_enabled=False, vendor_id="opencode-go-claude"
    )
    assert off["thinking"] == {"type": "disabled"}


def test_ai_client_thinking_params_claude_adaptive():
    from ai_client import AIClient

    c = AIClient.__new__(AIClient)
    c._vendor = "opencode-go-claude"
    c._base_url = "https://opencode.ai/zen/go"
    c._thinking_enabled = True
    c._thinking_effort = "max"
    assert c._thinking_params() == {"thinking": {"type": "adaptive"}}
    c._thinking_enabled = False
    assert c._thinking_params() == {"thinking": {"type": "disabled"}}
    # 显式 disabled / enabled 形态同口径
    assert c._explicit_thinking_params({"type": "disabled"}) == {"thinking": {"type": "disabled"}}
    assert c._explicit_thinking_params({"type": "enabled"}) == {"thinking": {"type": "adaptive"}}


def test_ai_client_thinking_params_non_gemini_untouched():
    from ai_client import AIClient

    c = AIClient.__new__(AIClient)
    c._vendor = "glm"
    c._base_url = "https://open.bigmodel.cn/api/paas/v4"
    c._thinking_enabled = False
    c._thinking_effort = "low"
    assert c._thinking_params() == {"thinking": {"type": "disabled"}}


def _capture_openai_kwargs(monkeypatch):
    """conftest 的 openai 替身不记 kwargs——用记录替身抓 `_init_client` 实际下发值。"""
    import ai_client

    captured: dict = {}

    class RecordingAsyncOpenAI:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(ai_client, "AsyncOpenAI", RecordingAsyncOpenAI)
    return captured


def test_init_client_opencode_attaches_default_headers(monkeypatch):
    from ai_client import AIClient

    captured = _capture_openai_kwargs(monkeypatch)
    AIClient(
        api_key="sk-1",
        base_url="https://opencode.ai/zen/go/v1",
        api_format="openai",
        vendor="opencode-go-chat",
    )
    headers = captured.get("default_headers") or {}
    assert any(k.lower() == "x-opencode-session" for k in headers)
    assert any(
        k.lower() == "user-agent" and str(v).startswith("ai-novel/") for k, v in headers.items()
    )


def test_init_client_non_opencode_no_session_header(monkeypatch):
    from ai_client import AIClient

    captured = _capture_openai_kwargs(monkeypatch)
    AIClient(api_key="sk-1", base_url="https://api.deepseek.com", api_format="openai")
    headers = captured.get("default_headers") or {}
    assert not any(k.lower() == "x-opencode-session" for k in headers)


@pytest.mark.parametrize(
    ("base", "expected"),
    [
        ("https://opencode.ai/zen/go/v1", "opencode-go-chat"),
        ("https://opencode.ai/zen/go", "opencode-go-claude"),
    ],
)
def test_resolve_vendor_display_names(base: str, expected: str):
    vendor_id, display, _protocol = resolve_vendor(base)
    assert vendor_id == expected
    assert display
