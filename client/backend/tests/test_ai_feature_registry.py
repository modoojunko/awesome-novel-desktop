"""端点 key 对拍守卫（tier-plan-four-tiers 1.5 立件；c-tier-gating-completion 重写为四向断言）。

扫描 C端 全部 FastAPI 路由：
① 凡挂 `ai_feature(key)` 标注的端点，key MUST 在门禁 key 全集内（= entitlement-defaults
   的 standard/pro/max/trial features 并集）——拼错 key、登记表删 key 端点没同步，这里先红；
② 已挂 key 的端点 MUST 同时挂 `require_ai_access`——key 标注不得成为无门死标注
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


def _has_ai_gate(dep) -> bool:
    """依赖树递归查 require_ai_access（门可挂端点参数或嵌套 Dependencies）。"""
    if getattr(dep.call, "__name__", "") == "require_ai_access":
        return True
    return any(_has_ai_gate(d) for d in dep.dependencies)


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


def test_decorated_endpoint_must_have_gate():
    """挂 key 而无 require_ai_access＝死标注（免费档直通），在此先红。"""
    offenders = []
    for route in _decorated_endpoints():
        if not any(_has_ai_gate(d) for d in route.dependant.dependencies):
            offenders.append(f"{route.path} -> {route.endpoint.__ai_feature__}")
    assert not offenders, f"挂 key 未挂门（补 require_ai_access 或删标注）: {offenders}"


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
