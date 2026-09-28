"""c-og-slim-v2 提示词侧契约：章纲块补齐与爽点中文标签。

三件事各自可单独回归：
- 素材包（material_markdown）含【章纲概要】块（此前缺，润色产物直接用于生成正文）；
- user 层素材（to_user_material）含「本章要撞的墙」与「本章在卷剧情里的位置」（此前只有素材包有）；
- 读者获得的类型渲染中文标签、不再输出英文枚举键，位置档不再进提示词。
"""

from write.chapter_writer import ChapterContext


def _ctx() -> ChapterContext:
    ctx = ChapterContext()
    ctx.novel_title = "渡口"
    ctx.chapter_outline = {"summary": "她夜探库房调包账册"}
    ctx.challenge = "旧档不对活人开放"
    ctx.plot_stage = "矛盾升级"
    ctx.word_target = 2000
    return ctx


class TestChapterOutlineBlockInBothPaths:
    def test_material_carries_summary_block(self):
        md = _ctx().material_markdown()
        assert "【章纲概要】她夜探库房调包账册" in md

    def test_material_carries_challenge_and_stage(self):
        md = _ctx().material_markdown()
        assert "【本章要撞的墙】旧档不对活人开放" in md
        assert "【本章在卷剧情里的位置】矛盾升级" in md

    def test_prompt_carries_challenge_and_stage(self):
        prompt = _ctx().to_user_material()
        assert "本章要撞的墙：旧档不对活人开放" in prompt
        assert "本章在卷剧情里的位置：矛盾升级" in prompt

    def test_empty_fields_absent_no_placeholder(self):
        empty = ChapterContext()
        for text in (empty.material_markdown(), empty.to_user_material()):
            assert "【章纲概要】" not in text
            assert "本章要撞的墙" not in text
            assert "本章在卷剧情里的位置" not in text
            assert "{}" not in text


class TestPayoffKindLabels:
    def _with_payoffs(self, payoffs) -> str:
        ctx = ChapterContext()
        ctx.micro_payoffs = payoffs
        return ctx.to_user_material()

    def test_kind_rendered_as_chinese_label(self):
        prompt = self._with_payoffs([{"kind": "clue", "description": "半块玉佩"}])
        assert "线索·半块玉佩" in prompt
        assert "clue" not in prompt

    def test_all_seven_kinds_have_labels(self):
        prompt = self._with_payoffs(
            [
                {"kind": "clue", "description": "甲"},
                {"kind": "reveal", "description": "乙"},
                {"kind": "twist", "description": "丙"},
                {"kind": "emotion", "description": "丁"},
                {"kind": "power", "description": "戊"},
                {"kind": "relation", "description": "己"},
                {"kind": "relief", "description": "庚"},
            ]
        )
        for label in ("线索", "真相揭示", "反转", "情绪共鸣", "实力成长", "关系进展", "压力释放"):
            assert f"{label}·" in prompt

    def test_unknown_kind_degrades_to_description_only(self):
        """未知类型（历史数据里的自由词）不产生悬空分隔符，也不吐英文。"""
        prompt = self._with_payoffs([{"kind": "反杀", "description": "守夜人认错人"}])
        assert "守夜人认错人" in prompt
        assert "·守夜人认错人" not in prompt

    def test_location_not_injected(self):
        """位置档已退役：前/中/后段不再进提示词（位置由剧情条目顺序表达）。"""
        prompt = self._with_payoffs(
            [{"kind": "clue", "description": "半块玉佩", "location": "中段"}]
        )
        assert "线索·半块玉佩" in prompt
        assert "中段" not in prompt
        line = next(l for l in prompt.splitlines() if "爽点设计" in l)
        assert line.endswith("线索·半块玉佩"), f"爽点行不应带位置或其他尾巴：{line}"
