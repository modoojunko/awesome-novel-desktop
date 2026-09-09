"""叙事基调「## 叙事基调」块注入测试（ADR-007 题材/文风分离）。

覆盖：build_tone_section 纯函数渲染（narrator_role + tone{default_tone,
atmosphere, pov, techniques}，dict/list 双态，全空不注入）；整章写作路径
（build_chapter_context+to_prompt）注入该块；题材定义（toneBlueprint）
不再向提示词注入基调——只有文风表单的 tone 生效。
分段路径（assembler）已退役（ai-prompt-crafting），仅保留整章口径。
"""

import asyncio
import tempfile

from filesystem.storage import get_storage
from settings.render import build_tone_section
from write.chapter_writer import build_chapter_context


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _tmp_root() -> str:
    return tempfile.mkdtemp(prefix="test_tone_section_")


def _seed_writer(root: str, style: dict):
    """最小 chapter_writer 文件结构 + 指定 writing-style。"""
    _run_async(get_storage().write_yaml(root, "story.yaml", {"synopsis": "一个故事"}))
    _run_async(get_storage().write_yaml(root, "settings/world-setting.yaml", {}))
    _run_async(
        get_storage().write_yaml(
            root,
            "settings/writing-style.yaml",
            {"role": "一位小说家", "core_principles": [], "possible_mistakes": [], **style},
        )
    )
    _run_async(
        get_storage().write_yaml(
            root,
            "settings/anti-ai.yaml",
            {"fatigue_words_zh": {}, "structural_tic_patterns": []},
        )
    )
    _run_async(get_storage().write_yaml(root, "settings/hooks.yaml", {"active": []}))
    _run_async(
        get_storage().write_yaml(
            root,
            "chapters/vol-1-ch-1.yaml",
            {
                "volume": 1,
                "chapter": 1,
                "title": "第一章",
                "outline": {"summary": "s", "characters": []},
                "segments": [],
            },
        )
    )
    _run_async(get_storage().write_yaml(root, "volumes/vol-1.yaml", {"summary": ""}))


FULL_STYLE = {
    "narrator_role": "贴近主角的第三人称",
    "tone": {
        "default_tone": "克制",
        "atmosphere": ["压抑", "烟火气"],
        "pov": ["第三人称有限视角"],
        "techniques": ["动作外化情绪"],
    },
}


# ── build_tone_section 纯函数 ────────────────────────────────────────────


class TestBuildToneSection:
    def test_full_style_renders_all_lines(self):
        section = build_tone_section(FULL_STYLE)
        assert section.startswith("## 叙事基调")
        assert "叙事者角色：贴近主角的第三人称" in section
        assert "默认基调：克制" in section
        assert "氛围：压抑、烟火气" in section
        assert "叙事视角：第三人称有限视角" in section
        assert "描写技法：动作外化情绪" in section

    def test_tone_without_narrator(self):
        section = build_tone_section(
            {"tone": {"default_tone": "悬疑", "atmosphere": ["暗流"]}}
        )
        assert "叙事者角色" not in section
        assert "默认基调：悬疑" in section
        assert "氛围：暗流" in section

    def test_string_values_rendered_as_single(self):
        """tone 值为字符串（存量/AI 单值）时也渲染，不崩（双态容忍）。"""
        section = build_tone_section(
            {
                "tone": {
                    "default_tone": "温暖",
                    "atmosphere": "轻松",
                    "pov": "第一人称",
                }
            }
        )
        assert "氛围：轻松" in section
        assert "叙事视角：第一人称" in section

    def test_empty_style_returns_empty(self):
        assert build_tone_section({}) == ""
        assert build_tone_section(None) == ""

    def test_tone_missing_but_narrator_present(self):
        section = build_tone_section({"narrator_role": "全知叙述者"})
        assert section == "## 叙事基调\n叙事者角色：全知叙述者"

    def test_empty_tone_dict_returns_empty(self):
        assert build_tone_section({"tone": {}}) == ""

    def test_chapter_types_and_pacing_rules_rendered(self):
        """6.0c 迁移：章节类型/节奏规则随叙事基调块注入。"""
        section = build_tone_section(
            {"chapter_types": ["日常", "冲突"], "pacing_rules": ["每 3 章一次小高潮"]}
        )
        assert "章节类型：日常、冲突" in section
        assert "节奏规则：每 3 章一次小高潮" in section

    def test_extras_alone_still_emit_block(self):
        """只有迁移项、无 tone/narrator 时也要出块（不能被全空守卫吞掉）。"""
        section = build_tone_section({"chapter_types": ["日常"]})
        assert section == "## 叙事基调\n章节类型：日常"


# ── 整章路径 chapter_writer ─────────────────────────────────────────────


class TestChapterWriterToneInjection:
    def test_injects_tone_block_from_style(self):
        root = _tmp_root()
        _seed_writer(root, FULL_STYLE)
        ctx = _run_async(build_chapter_context(root, "vol-1-ch-1", "测试小说"))
        prompt = ctx.to_prompt()
        assert "## 叙事基调" in prompt
        assert "叙事者角色：贴近主角的第三人称" in prompt
        assert "描写技法：动作外化情绪" in prompt

    def test_no_tone_means_no_block(self):
        root = _tmp_root()
        _seed_writer(root, {})
        ctx = _run_async(build_chapter_context(root, "vol-1-ch-1", "测试小说"))
        assert "## 叙事基调" not in ctx.to_prompt()


# ── 题材不再注入基调（ADR-007）──────────────────────────────────────────


class TestGenreDoesNotInjectTone:
    def test_genre_tone_blueprint_ignored_without_style_tone(self):
        """题材定义带 toneBlueprint 但文风无 tone → 提示词无「## 叙事基调」块。"""
        root = _tmp_root()
        _seed_writer(root, {})
        # genre.yaml 指定了题材 id，但该 id 在库中不存在 → resolve 优雅降级，
        # 且即使题材定义携带 toneBlueprint，也不应注入基调。
        _run_async(
            get_storage().write_yaml(
                root, "settings/genre.yaml", {"genre_id": "tone-ignored-genre"}
            )
        )
        ctx = _run_async(build_chapter_context(root, "vol-1-ch-1", "测试小说"))
        assert "## 题材设定" not in ctx.to_prompt()
        assert "## 叙事基调" not in ctx.to_prompt()
