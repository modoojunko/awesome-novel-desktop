"""Tests for ChapterContext builder."""

from settings.style_model import normalize_style
from write.chapter_writer import ChapterContext


class TestChapterContext:
    def test_empty_context_returns_valid_prompt(self):
        ctx = ChapterContext()
        prompt = ctx.to_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 50
        assert "## 角色定位" in prompt
        assert "## 原则与禁忌" in prompt
        assert "## 故事背景" in prompt
        assert "## 写作要求" in prompt

    def test_with_premise(self):
        ctx = ChapterContext()
        ctx.premise = "一个退役刑警调查悬案的故事"
        ctx.novel_title = "暗流"
        prompt = ctx.to_prompt()
        assert "暗流" in prompt
        assert "退役刑警" in prompt

    def test_with_world_setting(self):
        ctx = ChapterContext()
        ctx.world_setting = {
            "geography": {"scenes": "潮湿的南方城市"},
            "politics": {"rule": "军阀割据"},
            "rules": {"world": "没有超自然力量"},
        }
        prompt = ctx.to_prompt()
        assert "潮湿的南方城市" in prompt

    def test_with_style_settings(self):
        """style-settings-v2：三区文风段（身份→红线→手法），tone/mistakes 块退役。"""
        ctx = ChapterContext()
        ctx.style_setting = normalize_style({
            "role": "冷峻的叙事者",
            "core_principles": ["简洁", "有力"],
            "possible_mistakes": ["不要滥用形容词"],
            "depiction_techniques": {"action": "快速剪辑"},
        })
        prompt = ctx.to_prompt()
        assert "冷峻的叙事者" in prompt
        assert "快速剪辑" in prompt
        assert "简洁" in prompt and "有力" in prompt
        assert "叙事基调" not in prompt
        assert "文风常见错误" not in prompt

    def test_with_template_dict_structure(self):
        """模板盘文件 dict 结构（分类分组）不崩溃、内容进提示词（ADR-006 双态）。"""
        ctx = ChapterContext()
        ctx.style_setting = normalize_style({
            "core_principles": {
                "global_rules": ["规则一"],
                "natural_expression": ["原则二"],
            },
            "possible_mistakes": ["错误一", "错误二"],
        })
        prompt = ctx.to_prompt()
        assert "规则一" in prompt
        assert "原则二" in prompt
        assert "错误一" in prompt

    def test_with_list_depiction_techniques(self):
        """模板 list 结构（{name/description/example}）也能渲染（ADR-006 双态）。"""
        ctx = ChapterContext()
        ctx.style_setting = normalize_style({
            "depiction_techniques": [
                {"name": "动作描写", "description": "通过身体动作展示情感"},
                {"name": "微表情捕捉", "description": "通过细微表情变化展示内心"},
            ]
        })
        prompt = ctx.to_prompt()
        assert "动作描写：通过身体动作展示情感" in prompt
        assert "微表情捕捉：通过细微表情变化展示内心" in prompt

    def test_with_string_list_depiction_techniques(self):
        """前端表单归一保存的纯字符串列表也能渲染（ADR-006 双态）。"""
        ctx = ChapterContext()
        ctx.style_setting = normalize_style({
            "depiction_techniques": ["动作描写：通过动作展示情感", "对话展示：贴近真人"]
        })
        prompt = ctx.to_prompt()
        assert "动作描写：通过动作展示情感" in prompt
        assert "对话展示：贴近真人" in prompt

    def test_with_hooks(self):
        ctx = ChapterContext()
        ctx.hooks = [{"description": "神秘信件"}, {"description": "失踪的钥匙"}]
        prompt = ctx.to_prompt()
        assert "神秘信件" in prompt

    def test_with_characters(self):
        ctx = ChapterContext()
        ctx.characters = [
            {"name": "张三", "state": "正在调查"},
            {"name": "李四", "state": "隐藏身份"},
        ]
        prompt = ctx.to_prompt()
        assert "张三" in prompt

    def test_flatten_fatigue_words(self):
        ctx = ChapterContext()
        result = ctx._flatten_fatigue_words(
            {"副词": ["突然", "忽然"], "语气词": ["嗯", "啊"]}
        )
        assert len(result) == 4
        assert "突然" in result

    def test_with_previous_chapter_recap(self):
        ctx = ChapterContext()
        ctx.previous_chapter_recap = "上一章结尾，张三推开了那扇门。"
        prompt = ctx.to_prompt()
        assert "上一章结尾" in prompt
