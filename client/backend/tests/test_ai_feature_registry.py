"""端点 key 对拍守卫（tier-plan-four-tiers 1.5 立件；c-tier-gating-completion 重写为四向断言）。

扫描 C端 全部 FastAPI 路由：
① 凡挂 `ai_feature(key)` 标注的端点，key MUST 在门禁 key 全集内（= entitlement-defaults
   的 standard/pro/max/trial features 并集）——拼错 key、登记表删 key 端点没同步，这里先红；
② 已挂 key 的端点 MUST 同时挂**相称**的门——LLM 类 key 只认 `require_ai_access`；
   键自持端点（`KEYLESS_GATE_KEYS` 白名单：ai-detect/prompt-panel）才认
   `require_tier_access`——key 标注不得成为无门死标注、也不得错挂门型
  （曾实锤：POST /api/novels 挂 ai-plan 无门零行为，误导后来人补门误伤免费建书）；
③ 关键档位 key 各有至少一个真实端点消费点——挪 key/收门漏改端点，这里先红；
④ 扫描 MUST 穿透 starlette ≥1.6 的懒路由包装：旧实现顶层 `isinstance(route, APIRoute)`
   在 1.6 下恒扫到 0 条＝守卫空转恒绿，三个只读端点漏挂门与文风 key 挂错均由此漏网
  （c-tier-gating-completion 审计；本文件留有「枚举非空」断言防回潮）。

用法：cd client/backend && python -m pytest tests/test_ai_feature_registry.py -v
"""

import sys
from pathlib import Path

from fastapi.routing import APIRoute

# C端 app 装配（全部路由表）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth_local.service import STANDARD_FALLBACK  # noqa: E402
from main import app  # noqa: E402

# 关键档位 key：各须有 ≥1 个端点消费点（免费键不设——ai-model 等免费能力无端点门）
REQUIRED_CONSUMERS = (
    "ai-plan",
    "chapter-review",
    "settings-ai-fields",
    "style-suggest",
    "style-quant",
    "ai-generate",
    "prompt-panel",
    "ai-plot",
    "ai-polish",
    "ai-detect",
)


def _iter_api_routes(routes):
    """深度枚举：APIRoute 直命中；懒包装（starlette ≥1.6 _IncludedRouter 等形态）沿
    original_router 递归——duck-typing 不 import 私有名；starlette<1.6 顶层即
    APIRoute，双形态兼容。"""
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        else:
            orig = getattr(r, "original_router", None)
            if orig is not None:
                yield from _iter_api_routes(orig.routes)


# 允许挂「键自持门」的 key 白名单：端点用的是作者自持的第三方 Key，不需要写作大模型
# （`ai-detect`＝朱雀检测；`prompt-panel`＝提示词取数与编辑，2026-10-08 拍板）。
# 其余 key 一律要求 require_ai_access——防「LLM 端点错挂键自持门」凭空放行未配模型的作者。
KEYLESS_GATE_KEYS = ("ai-detect", "prompt-panel")


def _has_gate_named(dep, name: str) -> bool:
    """依赖树递归查指定函数名的门（门可挂端点参数或嵌套 Dependencies）。"""
    if getattr(dep.call, "__name__", "") == name:
        return True
    return any(_has_gate_named(d, name) for d in dep.dependencies)


def _has_key_gate(route) -> bool:
    """端点是否挂了与其 key 相称的门。

    两种门分工：`require_ai_access`（会员＋档位＋已配写作大模型 Key）为 LLM 类端点的
    唯一合法门；`require_tier_access`（会员＋档位）**仅** `KEYLESS_GATE_KEYS` 内的
    键自持端点可用——LLM 端点若只剩键自持门，等于把「未配模型」放行到深处才炸。
    """
    deps = route.dependant.dependencies
    if any(_has_gate_named(d, "require_ai_access") for d in deps):
        return True
    key = getattr(route.endpoint, "__ai_feature__", None)
    return key in KEYLESS_GATE_KEYS and any(
        _has_gate_named(d, "require_tier_access") for d in deps
    )


def _gate_keys() -> set[str]:
    """门禁 key 全集：标准/PRO/MAX/trial 兜底行 features 并集（免费行恒空）。"""
    keys: set[str] = set()
    for tier in ("standard", "pro", "max", "trial"):
        keys.update(STANDARD_FALLBACK.get(tier, {}).get("features", []))
    return keys


def _decorated_endpoints():
    for route in _iter_api_routes(app.routes):
        if getattr(route.endpoint, "__ai_feature__", None):
            yield route


def test_registry_has_gate_keys():
    """兜底表本身必须含门禁 key 全集（空集=镜像坏了，对拍失效）。"""
    assert _gate_keys(), "STANDARD_FALLBACK 未含任何门禁 key——对拍基准坏了"


def test_scanner_sees_decorated_endpoints():
    """守卫不是空转：懒路由包装下旧式顶层遍历扫到 0 条（曾恒绿漏网），walker 必须枚举到。"""
    decorated = list(_decorated_endpoints())
    assert len(decorated) > 0, (
        "扫描器枚举到 0 个挂 key 端点——路由表遍历未穿透懒路由包装，守卫空转"
    )


def test_every_decorated_endpoint_key_in_vocabulary():
    """凡挂 ai_feature 的端点，key MUST ∈ 词汇表（兜底并集）。"""
    vocab = _gate_keys()
    offenders = []
    for route in _decorated_endpoints():
        key = route.endpoint.__ai_feature__
        if key not in vocab:
            offenders.append(f"{route.path} -> {key}")
    assert not offenders, f"端点 key 不在词汇表（先登记 specs 再挂门）: {offenders}"


def test_keyless_gate_keys_are_known_vocabulary():
    """键自持门白名单本身必须非空且 ∈ 词汇表（白名单写坏＝守卫对 LLM 端点放水）。"""
    assert KEYLESS_GATE_KEYS, "键自持门白名单为空——守卫退化成「任何门都算」"
    unknown = [k for k in KEYLESS_GATE_KEYS if k not in _gate_keys()]
    assert not unknown, f"白名单 key 不在门禁词汇表: {unknown}"


def test_decorated_endpoint_must_have_matching_gate():
    """挂 key 而无相称的门＝死标注/错门（免费档直通 或 未配模型放行到深处），在此先红。

    相称＝「LLM 类 key → `require_ai_access`」；只有 `KEYLESS_GATE_KEYS` 内的键自持
    端点才允许 `require_tier_access`（防错配：生成类端点错挂键自持门，等于把「未配
    写作大模型」的作者放行到业务深处才炸——正是 c-zhuque-config-keyless 修的同类）。
    """
    offenders = []
    for route in _decorated_endpoints():
        if not _has_key_gate(route):
            key = route.endpoint.__ai_feature__
            offenders.append(f"{route.path} -> {key}")
    assert not offenders, (
        "挂 key 未挂相称的门（LLM 类 key 补 require_ai_access；键自持端点用 "
        f"require_tier_access 且 key 须 ∈ {list(KEYLESS_GATE_KEYS)}）: {offenders}"
    )


def test_required_keys_have_consumers():
    """关键档位 key 消费点非空（挪 key/删端点漏改，这里先红）。"""
    counts: dict[str, int] = {}
    for route in _decorated_endpoints():
        key = route.endpoint.__ai_feature__
        counts[key] = counts.get(key, 0) + 1
    missing = [k for k in REQUIRED_CONSUMERS if counts.get(k, 0) == 0]
    assert not missing, f"关键档位 key 无任何端点消费点: {missing}"


def test_decorated_endpoints_exist_or_pending():
    """app 装配自检（路由表非空——本件是回归网，不是进度闸）。"""
    assert len(app.routes) > 0
