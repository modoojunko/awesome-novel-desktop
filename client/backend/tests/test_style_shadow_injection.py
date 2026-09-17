"""文风影子 → 量化基线段覆盖注入（chapter-style-shadow）。"""
from settings.render import quant_section


def _quant():
    return {
        "confidence": 80,
        "baseline": {
            "narrative": {"value": "第三人称限知", "tolerance": 10},
            "rhythm": {"value": "场景配比 40/30/20/10", "tolerance": 10},
            "syntax": {"value": "短句为主", "tolerance": 10},
            "lexicon": {"value": "白描", "tolerance": 10},
            "emotion": {"value": "克制的情绪外化", "tolerance": 10},
            "dialogue_verb": {"value": "动词驱动", "tolerance": 10},
        },
    }


def test_shadow_rows_override_baseline_lines():
    quant = _quant()
    shadow = {
        "syntax": {"value": "更短的句子，动词开场", "reason": "打斗章节奏"},
        "emotion": {"value": "外化再加一档", "reason": "高潮章"},
    }
    out = quant_section(quant, shadow)
    assert "更短的句子，动词开场" in out
    assert "本章覆盖：打斗章节奏" in out
    assert "外化再加一档" in out
    # 未覆盖行保持基线渲染
    assert "约 白描" in out
    # 无影子行保持「约 X（±tol%）」
    assert "约 第三人称限知" in out


def test_no_shadow_keeps_baseline_render():
    out = quant_section(_quant(), {})
    assert "约 白描" in out
    assert "本章覆盖" not in out


def test_shadow_for_unknown_row_is_ignored():
    out = quant_section(_quant(), {"unknown_dim": {"value": "x", "reason": "y"}})
    assert "unknown_dim" not in out
    assert "x" not in out.replace("约 白描", "")
