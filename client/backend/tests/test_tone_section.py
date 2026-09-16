"""tone 块退役与归一断言（style-settings-v2 tasks 4.1）。

build_tone_section 退役恒返回空串；tone/possible_mistakes 信息经
normalize_style 拆并进三区（叙事身份/硬约束/描写手法），chapter_types
退役不再注入，ADR-007「题材不注入基调」口径不变。

Usage:
    cd client/backend
    python -m pytest tests/test_tone_section.py -v
"""

from settings.render import build_tone_section, style_section
from settings.style_model import normalize_style


class TestToneSectionRetired:
    def test_always_returns_empty(self):
        """退役占位：任何输入恒返回空串（含旧全量样式）。"""
        style = {
            "narrator_role": "第三人称限知",
            "tone": {"default_tone": "克制", "atmosphere": ["压抑"], "pov": ["第三人称"], "techniques": ["动作外化"]},
            "chapter_types": ["日常"],
            "pacing_rules": ["节奏规则"],
        }
        assert build_tone_section(style) == ""
        assert build_tone_section({}) == ""
        assert build_tone_section(None) == ""

    def test_chapter_types_not_rendered(self):
        """chapter_types 退役：不再以任何形式进提示词。"""
        style = normalize_style({"chapter_types": ["日常"], "pacing_rules": ["节奏规则"]})
        sec = style_section(style)
        assert "章节类型" not in sec
        assert "节奏规则" in sec  # pacing_rules 归一进硬约束（拍板：并入）


class TestLegacyMergedIntoThreeZones:
    def test_tone_info_lands_in_zones(self):
        style = normalize_style({
            "role": "冷静叙事者",
            "narrator_role": "第三人称限知",
            "tone": {"pov": ["全知片段每卷≤1次"], "techniques": ["动作外化"]},
            "possible_mistakes": ["心理活动不用他感到开头"],
        })
        sec = style_section(style)
        assert "第三人称限知" in sec
        assert "全知片段每卷≤1次" in sec
        assert "动作外化" in sec
        assert "心理活动不用他感到开头" in sec
