"""题材定义注入写作链路测试（临时 root + 隔离临时 DB）。

覆盖 resolve_genre_context（缺 genre.yaml / genre_id 空 / 定义缺失 → None、
overrides 合并、prompt_injection_enabled 关闭）、build_genre_section 渲染内容、
整章写作路径（build_chapter_context+to_prompt）注入题材块 + 疲劳词合并，
以及定义缺失时的优雅降级（不报错、无题材块）。
分段路径（assembler）已退役（ai-prompt-crafting），仅保留整章口径。
"""

import asyncio
import os
import tempfile

import pytest

# ── Test environment (isolated temp DB + temp root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_genres_injection.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_genres_injection_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from db import Base, async_session, engine  # noqa: E402
from filesystem.storage import get_storage  # noqa: E402
from genres.service import (  # noqa: E402
    build_genre_section,
    create_genre,
    ensure_seed_genres,
    resolve_genre_context,
)
from write.chapter_writer import build_chapter_context  # noqa: E402

# ── Helpers ───────────────────────────────────────────────────────────────


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    _run_async(_create_tables())
    _run_async(ensure_seed_genres())
    yield


def _tmp_root() -> str:
    return tempfile.mkdtemp(prefix="test_genres_injection_root_")


async def _create_genre(gid: str):
    """服务层直接入库一个自定义题材（供 resolve/写作链路测试）。"""
    async with async_session() as s:
        await create_genre(
            s,
            {
                "id": gid,
                "name": "注入测试",
                "description": "测试题材说明",
                "category": "urban",
                "narratorRole": "贴近主角的第三人称",
                "typicalArc": "从平凡到成长",
                "taboos": ["忌一", "忌二"],
                "promptInjection": "[注入基调] 保持真实",
                "toneBlueprint": {
                    "defaultTone": "温暖",
                    "atmosphereOptions": ["默认氛围"],
                    "povOptions": ["第一人称"],
                    "techniqueTags": ["细节"],
                },
                "genreConfig": {
                    "fulfillmentTypes": ["成长"],
                    "chapterTypes": ["日常"],
                    "pacingRules": ["规则"],
                    "fatigueWords": ["默认疲劳词"],
                },
                "storyArcTemplates": [
                    {"id": "arc1", "name": "弧一", "description": "第一个弧", "beats": ["beat1"]},
                    {"id": "arc2", "name": "弧二", "description": "第二个弧", "beats": ["b1", "b2"]},
                ],
            },
        )


def _seed_writer(root: str):
    """最小 chapter_writer 文件结构。"""
    _run_async(get_storage().write_yaml(root, "story.yaml", {"synopsis": "一个故事"}))
    _run_async(get_storage().write_yaml(root, "settings/world-setting.yaml", {}))
    _run_async(
        get_storage().write_yaml(
            root,
            "settings/writing-style.yaml",
            {"role": "一位小说家", "core_principles": [], "possible_mistakes": []},
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


# ── resolve_genre_context 优雅降级 ───────────────────────────────────────


class TestResolveDegradation:
    def test_no_genre_yaml_returns_none(self):
        assert _run_async(resolve_genre_context(_tmp_root())) is None

    def test_empty_genre_id_returns_none(self):
        root = _tmp_root()
        _run_async(
            get_storage().write_yaml(root, "settings/genre.yaml", {"genre_id": ""})
        )
        assert _run_async(resolve_genre_context(root)) is None

    def test_unknown_genre_id_returns_none(self):
        root = _tmp_root()
        _run_async(
            get_storage().write_yaml(root, "settings/genre.yaml", {"genre_id": "not-in-db"})
        )
        assert _run_async(resolve_genre_context(root)) is None


# ── resolve_genre_context 合并逻辑 ───────────────────────────────────────


class TestResolveMerge:
    def test_overrides_win_over_defaults(self):
        _run_async(_create_genre("resolve-genre"))
        root = _tmp_root()
        _run_async(
            get_storage().write_yaml(
                root,
                "settings/genre.yaml",
                {
                    "genre_id": "resolve-genre",
                    "tone_overrides": {"atmosphere": "自定义氛围"},
                    "config_overrides": {"fatigue_words": ["自定义疲劳词"]},
                    "selected_arc_id": "arc2",
                    "prompt_injection_enabled": True,
                },
            )
        )
        ctx = _run_async(resolve_genre_context(root))
        assert ctx is not None
        assert ctx["name"] == "注入测试"
        # ADR-007：题材 ctx 不再携带基调/叙事者（归文风表单 tone）
        assert "atmosphere" not in ctx
        assert "pov" not in ctx
        assert "narrator_role" not in ctx
        # 6.0c 迁移：fatigue_words / chapter_types / pacing_rules 归 writing-style.yaml
        assert "fatigue_words" not in ctx
        assert "chapter_types" not in ctx
        assert "pacing_rules" not in ctx
        assert ctx["selected_arc"]["id"] == "arc2"
        assert ctx["selected_arc"]["beats"] == ["b1", "b2"]
        assert ctx["prompt_injection"] == "[注入基调] 保持真实"

    def test_prompt_injection_disabled_sets_none(self):
        _run_async(_create_genre("disable-genre"))
        root = _tmp_root()
        _run_async(
            get_storage().write_yaml(
                root,
                "settings/genre.yaml",
                {"genre_id": "disable-genre", "prompt_injection_enabled": False},
            )
        )
        ctx = _run_async(resolve_genre_context(root))
        assert ctx is not None
        assert ctx["prompt_injection"] is None


# ── build_genre_section 渲染 ─────────────────────────────────────────────


class TestBuildGenreSection:
    def test_renders_all_blocks(self):
        section = build_genre_section(
            {
                "name": "测试题材",
                "category": "urban",
                "description": "一段说明",
                "typical_arc": "典型弧",
                "taboos": ["忌一", "忌二"],
                # ADR-007：narrator_role/default_tone/atmosphere/pov/techniques
                # 已停用（归文风表单 tone）——传入也应被忽略
                "narrator_role": "叙事者",
                "default_tone": "温暖",
                "atmosphere": "温馨",
                "pov": "第一人称",
                "techniques": ["细节"],
                "prompt_injection": "[注入段]",
                "fulfillment_types": ["成长"],
                "selected_arc": {"name": "弧名", "description": "弧描述", "beats": ["b1", "b2"]},
            }
        )
        assert "## 题材设定" in section
        assert "题材：测试题材" in section
        assert "一段说明" in section
        assert "叙事者角色" not in section
        assert "默认基调" not in section
        assert "氛围" not in section
        assert "叙事视角" not in section
        assert "描写技法" not in section
        assert "题材禁忌：忌一；忌二" in section
        assert "[注入段]" in section
        assert "满足类型：成长" in section
        # 6.0c 迁移：章节类型/节奏规则不再由题材块渲染
        assert "章节类型" not in section
        assert "节奏规则" not in section
        assert "故事弧：弧名（弧描述）" in section
        assert "弧节拍：b1 → b2" in section

    def test_none_returns_empty(self):
        assert build_genre_section(None) == ""


# ── 整章路径 chapter_writer ─────────────────────────────────────────────


class TestChapterWriterInjection:
    def test_injects_genre_section_and_fatigue(self):
        _run_async(_create_genre("wr-genre"))
        root = _tmp_root()
        _seed_writer(root)
        # 疲劳词主源＝writing-style.yaml（6.0e 迁移）
        style = _run_async(
            get_storage().read_yaml(root, "settings/writing-style.yaml")
        )
        style["fatigue_words"] = ["默认疲劳词"]
        style["chapter_types"] = ["日常"]
        style["pacing_rules"] = ["规则"]
        _run_async(
            get_storage().write_yaml(root, "settings/writing-style.yaml", style)
        )
        _run_async(
            get_storage().write_yaml(root, "settings/genre.yaml", {"genre_id": "wr-genre"})
        )
        ctx = _run_async(build_chapter_context(root, "vol-1-ch-1", "测试小说"))
        assert "## 题材设定" in ctx.genre_section
        assert "题材：注入测试" in ctx.genre_section
        assert ctx.style_fatigue_words == ["默认疲劳词"]

        prompt = ctx.to_prompt()
        assert "## 题材设定" in prompt
        assert "禁止使用以下词汇：默认疲劳词" in prompt
        # 6.0c 迁移：章节类型/节奏规则随「## 叙事基调」注入
        assert "章节类型：日常" in prompt
        assert "节奏规则：规则" in prompt

    def test_degrades_gracefully_when_definition_missing(self):
        root = _tmp_root()
        _seed_writer(root)
        _run_async(
            get_storage().write_yaml(root, "settings/genre.yaml", {"genre_id": "unknown-id"})
        )
        ctx = _run_async(build_chapter_context(root, "vol-1-ch-1", "测试小说"))
        assert ctx.genre_section == ""
        assert ctx.style_fatigue_words == []
        assert "## 题材设定" not in ctx.to_prompt()
