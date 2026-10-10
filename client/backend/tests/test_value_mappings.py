"""值域降级映射查询 API 单测（c-legacy-drill-gate）。

初始登记表为空——「一切未声明＝禁降级」就是现行门禁口径：引擎（降级回迁在
c-carry-degrade-remigrate 落地）拿到 None MUST NOT 改值。这里的用例同时钉住
第一笔映射落地后的三级查询语义。
"""

from __future__ import annotations

from migration.value_mappings import ValueRule, lookup_degradation


def test_empty_registry_means_no_degradation():
    """现行口径：登记表为空，任何查询都是 None（禁降级，拒收按行损失上报）。"""
    assert lookup_degradation("chapters", "status", "writing_v2") is None


def test_lookup_three_tiers(monkeypatch):
    """三级语义：精确命中 > 保守默认 > 未声明条目 None。"""
    from migration import value_mappings as vm

    monkeypatch.setattr(vm, "VALUE_MAPPINGS", {
        ("chapters", "status"): ValueRule(
            mapping={"writing_v2": "draft", "writing_v1": "draft"}, default="draft"),
        ("novels", "phase"): ValueRule(mapping={}),  # 有条目、无映射、无默认
    })
    assert lookup_degradation("chapters", "status", "writing_v2") == "draft"  # 精确
    assert lookup_degradation("chapters", "status", "没登记过的旧值") == "draft"  # 默认
    assert lookup_degradation("novels", "phase", "旧值") is None  # 无默认＝禁降级
    assert lookup_degradation("chapters", "title", "writing_v2") is None  # 列未声明


def test_null_and_empty_pass_through():
    """None/空串不构成拒收面，直通 None（引擎不应对它们做降级改写）。"""
    assert lookup_degradation("chapters", "status", None) is None
    assert lookup_degradation("chapters", "status", "") is None
