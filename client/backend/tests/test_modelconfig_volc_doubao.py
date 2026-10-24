"""c-modelconfig-volc-doubao 单元账：方舟厂商身份链＋豆包候选＋思考形态钉。

覆盖 spec「供应商分组页签／供应商默认值预填／接口格式为配置的一级字段」的
调用层行为（页签/预填交互在前端套件）：
  - KNOWN_VENDORS 白名单放行 doubao；检测链认 ark.<region>.volces.com（cn-beijing
    精确模式在前、异 region 兜底在后），非 ark 的 volces 域不误收
  - VENDOR_MODEL_CANDIDATES 豆包条目：完整版本 id 纪律（数据面裸名 404 实测）
  - 探针 payload（_generation_payload）与 AIClient 思考参数（_thinking_params）：
    app 默认 openai 形态在方舟三形态实测 200（enabled+low／disabled／enabled+max），
    零 vendor 适配；**钉**「关思考形态 SHALL NOT 带 reasoning_effort」——方舟禁组合
    disabled+档位（400 Invalid combination，2026-10-24 探针实锤），防未来回归把
    档位漏进关思考形态
"""
from __future__ import annotations

from api_configs import connection
from api_configs.schemas import KNOWN_VENDORS
from api_configs.vendor import resolve_vendor

# ── vendor 身份链：白名单／检测 ──────────────────────────────────────────


def test_doubao_in_whitelist():
    assert "doubao" in KNOWN_VENDORS


def test_detect_doubao_registered_region_and_other_regions():
    assert resolve_vendor("https://ark.cn-beijing.volces.com/api/v3")[0] == "doubao"
    assert resolve_vendor("https://ark.cn-beijing.volces.com/api/v3/chat/completions")[0] == "doubao"
    # 未登记 region 的同族主机：识别归 doubao（仅展示名，预填值不登记）
    assert resolve_vendor("https://ark.ap-southeast-1.volces.com/api/v3")[0] == "doubao"


def test_detect_non_ark_volces_not_doubao():
    # 非 ark 子域的 volces 主机不收（识别落 openai-compat 兜底）
    assert resolve_vendor("https://www.volces.com/api/v3")[0] == "openai-compat"
    assert resolve_vendor("https://evil-ark.volces.com/api/v3")[0] == "openai-compat"
    # 前缀伪装（ark 在路径而非主机）不收
    assert resolve_vendor("https://example.com/ark.cn-beijing.volces.com")[0] == "openai-compat"


def test_doubao_candidates_are_full_version_ids():
    """数据面裸名 404 实测（2026-10-24）——候选一律完整版本 id（name+primary_version）。"""
    cands = connection.VENDOR_MODEL_CANDIDATES["doubao"]
    assert cands[0] == "doubao-seed-2-1-lite-260915"
    assert len(cands) == 3
    for cid in cands:
        assert cid.rsplit("-", 1)[-1].isdigit() and len(cid.rsplit("-", 1)[-1]) == 6
        # 裸名（剥版本段）不得出现在候选里
        assert cid.rsplit("-", 1)[0] not in cands


# ── 思考形态：零适配＋禁组合钉 ───────────────────────────────────────────


def test_probe_payload_doubao_default_openai_shapes():
    """探针三形态（方舟 2026-10-24 真弹 200 实证的原样形态）。"""
    on_low = connection._generation_payload(
        "doubao-seed-2-1-lite-260915", thinking_enabled=True, thinking_effort="low",
        vendor_id="doubao",
    )
    assert on_low["thinking"] == {"type": "enabled"}
    assert on_low["reasoning_effort"] == "low"
    assert on_low["max_tokens"] == connection._PROBE_MAX_TOKENS_THINKING
    on_max = connection._generation_payload(
        "doubao-seed-2-1-lite-260915", thinking_enabled=True, thinking_effort="max",
        vendor_id="doubao",
    )
    assert on_max["reasoning_effort"] == "max"  # 方舟认 max 档，零换算
    off = connection._generation_payload(
        "doubao-seed-2-1-lite-260915", thinking_enabled=False, vendor_id="doubao"
    )
    assert off["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in off  # 禁组合钉：disabled 与档位同传方舟 400
    assert off["max_tokens"] == connection._PROBE_MAX_TOKENS


def test_ai_client_thinking_params_doubao_default_path():
    from ai_client import AIClient

    c = AIClient.__new__(AIClient)  # 直装实例（与既有测试同款，绕开 SDK 构造）
    c._vendor = "doubao"
    c._base_url = "https://ark.cn-beijing.volces.com/api/v3"
    c._thinking_enabled = True
    c._thinking_effort = "low"
    assert c._thinking_params() == {"thinking": {"type": "enabled"}, "reasoning_effort": "low"}
    c._thinking_enabled = False
    assert c._thinking_params() == {"thinking": {"type": "disabled"}}
    # 显式 disabled（判定类路径）同口径：不带档位
    assert c._explicit_thinking_params({"type": "disabled"}) == {"thinking": {"type": "disabled"}}
    # 显式 thinking 形态原样透传（拼档位只在配置驱动路径 _thinking_params）
    assert c._explicit_thinking_params({"type": "enabled"}) == {"thinking": {"type": "enabled"}}
