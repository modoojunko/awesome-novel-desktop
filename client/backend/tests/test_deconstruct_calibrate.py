"""校准工具纯函数测试（c-deconstruct-knowledge 批A A5）：对表指标/输出解析。

大模型调用部分不进测试（开发期工具需真 Key，python -m deconstruct.calibrate 手跑）。"""

from deconstruct.calibrate import _parse_scene, compare_labels


def test_对表_命中率与混淆对():
    labeled = [
        ("c1", "打斗"), ("c2", "打斗"), ("c3", "对峙"),
        ("c4", "文戏"), ("c5", "文戏"),
    ]
    predicted = [
        ("c1", "打斗"), ("c2", "对峙"), ("c3", "对峙"),
        ("c4", "文戏"), ("c5", "打斗"),
    ]
    r = compare_labels(labeled, predicted)
    assert r["hits"] == 3 and r["total"] == 5
    assert r["overall_hit_rate"] == 60.0
    assert r["per_type"]["打斗"] == {"total": 2, "hit": 1}
    assert r["confusion"]["打斗→对峙"] == 1
    assert r["confusion"]["文戏→打斗"] == 1


def test_对表_空列表不除零():
    r = compare_labels([], [])
    assert r["overall_hit_rate"] == 0.0 and r["total"] == 0


def test_模型输出解析_容错():
    valid = {"打斗", "文戏", "开篇", "转折", "收尾", "对峙", "日常"}
    assert _parse_scene('{"scene": "打斗"}', valid) == "打斗"
    assert _parse_scene('前缀噪声\n{"scene": "文戏"}\n后缀', valid) == "文戏"
    assert _parse_scene("模型输出了非法类型", valid) == ""      # 非法场面不计
    assert _parse_scene("没有 JSON", valid) == ""              # 无 JSON 不炸
