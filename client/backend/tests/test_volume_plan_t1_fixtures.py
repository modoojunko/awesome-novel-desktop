"""volume-plan-ai — 提示词回归 T1（确定性 fixtures，进 CI 毫秒级）。

把 docs/volume-plan-prompt-experiment/out/ 的真模型原始输出当 fixtures，
直接打生产的解析/校验函数（_parse_json / _sanitize_plans / _sanitize_expand /
_report_groups），再配坏样本（带围栏 JSON／纯文本／三套同义／卷末空／1 套／
未知实体申报），断言行为不变。T2（真模型不变量）为手动/夜间 lane，不在此。

用法：
    cd client/backend
    python -m pytest tests/test_volume_plan_t1_fixtures.py -v
"""

import os

from volumes.ai_plan import (
    _entity_warnings,
    _parse_json,
    _report_groups,
    _sanitize_expand,
    _sanitize_plans,
)

_FIXTURES = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
    "docs",
    "volume-plan-prompt-experiment",
    "out",
)


def _read(name: str) -> str:
    with open(os.path.join(_FIXTURES, name), encoding="utf-8") as f:
        return f.read()


# ═══════════════ 好样本：真模型原始输出全部可解析、可兜底 ═══════════════


def test_fixture_check_outputs_parse_and_report():
    for name in ("check-1.txt", "check-2.txt"):
        parsed = _parse_json(_read(name))
        assert isinstance(parsed, dict), name
        report = _report_groups(parsed.get("groups"))
        assert report is not None, name
        assert len(report) >= 2, name
        for g in report:
            assert g["name"] and g["items"], name
            for it in g["items"]:
                assert it["status"] in ("ok", "warn", "none"), name


def test_fixture_expand_outputs_parse_and_sanitize():
    for name in ("expand-1.txt", "expand-2.txt"):
        parsed = _parse_json(_read(name))
        assert isinstance(parsed, dict), name
        draft = _sanitize_expand(parsed)
        assert draft is not None, name
        # 四问必须齐（fixtures 是旧 prompt 的真模型输出，带 goal——瘦身后 sanitize 不再
        # 要求也不再产出该键，故断言「三问在、goal 不在」）
        assert draft["summary"] and draft["conflict"] and draft["ending"], name
        assert "goal" not in draft, name
        assert 0 <= len(draft["checks"]) <= 3, name
        assert draft["chapter_target"] >= 0, name


def test_fixture_options_outputs_parse_and_sanitize():
    for name in ("options-1.txt", "options-2.txt"):
        parsed = _parse_json(_read(name))
        assert isinstance(parsed, dict), name
        result = _sanitize_plans(parsed)
        assert result is not None, name
        assert 2 <= len(result["plans"]) <= 3, name
        axes = [p["focus_axis"] for p in result["plans"]]
        assert len(axes) == len(set(axes)), name
        for p in result["plans"]:
            assert p["spine"] and p["ending"], name


# ═══════════════ 坏样本：解析/校验兜底逐条断言 ═══════════════


def test_bad_samples_rejected():
    # 带围栏的 JSON 仍可解析（```json 围栏剥除）
    fenced = "```json\n" + _read("expand-1.txt") + "\n```"
    assert _parse_json(fenced) is not None
    # 纯文本（无 JSON 对象）→ None
    assert _parse_json("三套方案如下：第一套……第二套……") is None
    # 1 套 → 整体失败（不足两套）
    one = {"plans": [{"spine": "唯一走向", "ending": "收", "focus_axis": "代价"}]}
    assert _sanitize_plans(one) is None
    # 三套同轴（同质）→ 同轴套丢弃后只剩 1 → 失败
    same = {
        "plans": [
            {"spine": f"走向{i}", "ending": "收", "focus_axis": "代价"}
            for i in range(3)
        ]
    }
    assert _sanitize_plans(same) is None
    # 卷末空 → 该套丢弃；只剩 1 套 < 2 → 整体失败（套数 2–3 硬规则）
    no_ending = {
        "plans": [
            {"spine": "走向一", "ending": "", "focus_axis": "代价"},
            {"spine": "走向二", "ending": "收", "focus_axis": "关系"},
        ]
    }
    assert _sanitize_plans(no_ending) is None
    # 展开缺「卷末结局」→ None（四件事必须齐）
    assert _sanitize_expand({"summary": "s", "conflict": "c", "goal": "g"}) is None
    # 体检组不足两组 → None
    assert _report_groups([{"name": "对主线", "items": [{"status": "ok", "text": "x"}]}]) is None


def test_unknown_entity_declaration_becomes_warning():
    known = {"林野", "旧贵族"}
    warnings = _entity_warnings(["林野", "夜行人"], ["夜巡议会"], known)
    assert any("夜行人" in w for w in warnings)
    assert any("夜巡议会" in w for w in warnings)
    assert len(warnings) == 2
    # 全部已知 → 无警告
    assert _entity_warnings(["林野"], [], known) == []
