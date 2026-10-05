"""端点 key ∈ 词汇表对拍（tier-plan-four-tiers tasks 1.5，新机械件）。

扫描 C端 全部 FastAPI 路由：凡挂 `ai_feature(key)` 标注的端点，其 key MUST 在
STANDARD_FALLBACK 派生的门禁 key 全集内（= entitlement-defaults.json 的
standard/pro/max features 并集）。把「端点→key」这处无保护漂移变成 CI 保护：
拼错 key、登记表删了 key 但端点没同步，这里先红。

用法：cd client/backend && python -m pytest tests/test_ai_feature_registry.py -v
"""

from pathlib import Path
import sys

from fastapi.routing import APIRoute

# C端 app 装配（全部路由表）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth_local.service import STANDARD_FALLBACK  # noqa: E402
from main import app  # noqa: E402


def _gate_keys() -> set[str]:
    """门禁 key 全集：标准/PRO/MAX 兜底行 features 并集（免费行恒空）。"""
    keys: set[str] = set()
    for tier in ("standard", "pro", "max", "trial"):
        keys.update(STANDARD_FALLBACK.get(tier, {}).get("features", []))
    return keys


def _decorated_endpoints():
    for route in app.routes:
        if isinstance(route, APIRoute) and getattr(route.endpoint, "__ai_feature__", None):
            yield route


def test_registry_has_gate_keys():
    """兜底表本身必须含门禁 key 全集（空集=镜像坏了，对拍失效）。"""
    assert _gate_keys(), "STANDARD_FALLBACK 未含任何门禁 key——对拍基准坏了"


def test_every_decorated_endpoint_key_in_vocabulary():
    """凡挂 ai_feature 的端点，key MUST ∈ 词汇表（兜底并集）。"""
    vocab = _gate_keys()
    offenders = []
    for route in _decorated_endpoints():
        key = route.endpoint.__ai_feature__
        if key not in vocab:
            offenders.append(f"{route.path} -> {key}")
    assert not offenders, f"端点 key 不在词汇表（先登记 specs 再挂门）: {offenders}"


def test_decorated_endpoints_exist_or_pending():
    """B3 前允许 0 挂点（本件是回归网，不是进度闸）；一旦有挂点即受 1.5 约束。

    本测试固化「扫描器真的在扫」：app.routes 非空即可。
    """
    assert len(app.routes) > 0
