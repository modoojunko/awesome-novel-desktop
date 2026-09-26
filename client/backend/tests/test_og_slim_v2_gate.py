"""c-og-slim-v2 门控：章纲必填由四项降为两项。

退役的「预期策略」「段落规划」在正文组装链里没有任何消费点（不进粗组兜底、
不进润色素材包），继续当必填门槛只会卡作者。
"""

from workflow.gates import gate_chapter_ready


def _chapter(memo=None, emotional=None) -> dict:
    return {
        "memo": memo if memo is not None else {},
        "emotional_design": emotional if emotional is not None else {},
    }


class TestChapterReadyGate:
    def test_two_required_items_pass(self):
        data = _chapter(
            memo={"required_changes": ["账册被调包"]},
            emotional={"primary_mood": "紧张"},
        )
        result = gate_chapter_ready(data)
        assert result.valid is True
        assert result.warnings == []

    def test_retired_fields_are_not_required(self):
        """预期策略/段落规划留空不再拦——VACUOUS 断言用「缺项清单不含它们」表达。"""
        result = gate_chapter_ready(_chapter())
        assert result.valid is False
        assert result.warnings == ["必须完成的变化", "主情绪"]
        assert "预期策略" not in result.warnings
        assert "段落规划" not in result.warnings

    def test_missing_changes_blocks(self):
        result = gate_chapter_ready(_chapter(emotional={"primary_mood": "紧张"}))
        assert result.valid is False
        assert result.warnings == ["必须完成的变化"]

    def test_missing_mood_blocks(self):
        result = gate_chapter_ready(
            _chapter(memo={"required_changes": ["账册被调包"]})
        )
        assert result.valid is False
        assert result.warnings == ["主情绪"]

    def test_gate_is_hard_block(self):
        assert gate_chapter_ready(_chapter()).hard_block is True
