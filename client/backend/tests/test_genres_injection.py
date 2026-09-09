"""题材定义注入写作链路测试（临时 root + 隔离临时 DB）。

D19 关系化后：题材唯一来源＝`novel_genre` + 关联表（`project_settings('genre')`
KV 行已废弃）。覆盖：
- `resolve_genre_context`：无 novel_id / 五字段全空 → None（优雅降级）
- `build_genre_section`：只渲染五字段
- 整章写作路径（build_chapter_context + to_prompt）注入题材块 + 疲劳词合并
  （疲劳词主源＝writing-style.yaml）
"""

import asyncio
import os
import tempfile
import uuid

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_genres_injection.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_genres_injection_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from db import Base, async_session, engine  # noqa: E402
from filesystem.storage import get_storage  # noqa: E402
from genres.novel_genre_service import (  # noqa: E402
    ensure_seed_genre_vocab,
    put_novel_genre,
)
from genres.service import build_genre_section, resolve_genre_context  # noqa: E402
from models.project import Novel  # noqa: E402
from write.chapter_writer import build_chapter_context  # noqa: E402

USER_ID = "genre_injection_user"


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
    _run_async(ensure_seed_genre_vocab())
    yield


def _tmp_root() -> str:
    return tempfile.mkdtemp(prefix="test_genres_injection_root_")


async def _new_novel(root: str) -> str:
    async with async_session() as session:
        novel = Novel(
            user_id=USER_ID,
            name=f"注入-{uuid.uuid4().hex[:6]}",
            slug=f"inj-{uuid.uuid4().hex[:6]}",
            root_path=root,
        )
        session.add(novel)
        await session.commit()
        await session.refresh(novel)
        return novel.id


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
    def test_no_novel_id_returns_none(self):
        assert _run_async(resolve_genre_context(_tmp_root())) is None

    def test_empty_genre_returns_none(self):
        root = _tmp_root()
        nid = _run_async(_new_novel(root))
        assert _run_async(resolve_genre_context(root, nid)) is None


# ── build_genre_section 渲染 ─────────────────────────────────────────────


class TestBuildGenreSection:
    def test_renders_five_fields(self):
        section = build_genre_section(
            {
                "core_promise": "以弱破强的痛快",
                "promise_note": "读者要看弱者用脑子翻盘",
                "cost_ratio": 7,
                "track": "从被赶出家门到掌控全城",
                "forbidden": ["禁天降外援"],
                "battlefield": ["抢资源"],
                # 旧契约键传入也应被忽略（KV 路径已退役）
                "name": "测试题材",
                "taboos": ["忌一"],
                "prompt_injection": "[注入段]",
                "selected_arc": {"name": "弧名"},
            }
        )
        assert "## 题材设定" in section
        assert "核心承诺：以弱破强的痛快" in section
        assert "读者预期：读者要看弱者用脑子翻盘" in section
        assert "吃苦指数：7" in section
        assert "剧情轨道：从被赶出家门到掌控全城" in section
        assert "绝对禁止：禁天降外援" in section
        assert "主线战场：抢资源" in section
        # 旧契约键不再渲染
        assert "测试题材" not in section
        assert "[注入段]" not in section
        assert "故事弧" not in section

    def test_none_returns_empty(self):
        assert build_genre_section(None) == ""


# ── 整章路径 chapter_writer ─────────────────────────────────────────────


class TestChapterWriterInjection:
    def test_injects_genre_section_and_fatigue(self):
        root = _tmp_root()
        _seed_writer(root)
        nid = _run_async(_new_novel(root))
        _run_async(_put(nid))

        # 疲劳词主源＝writing-style.yaml（6.0e 迁移）
        style = _run_async(get_storage().read_yaml(root, "settings/writing-style.yaml"))
        style["fatigue_words"] = ["默认疲劳词"]
        style["chapter_types"] = ["日常"]
        style["pacing_rules"] = ["规则"]
        _run_async(get_storage().write_yaml(root, "settings/writing-style.yaml", style))

        ctx = _run_async(build_chapter_context(root, "vol-1-ch-1", "测试小说", nid))
        assert "## 题材设定" in ctx.genre_section
        assert "核心承诺：以弱破强的痛快" in ctx.genre_section
        assert ctx.style_fatigue_words == ["默认疲劳词"]

        prompt = ctx.to_prompt()
        assert "## 题材设定" in prompt
        assert "禁止使用以下词汇：默认疲劳词" in prompt
        assert "章节类型：日常" in prompt
        assert "节奏规则：规则" in prompt

    def test_degrades_gracefully_when_genre_empty(self):
        root = _tmp_root()
        _seed_writer(root)
        nid = _run_async(_new_novel(root))
        ctx = _run_async(build_chapter_context(root, "vol-1-ch-1", "测试小说", nid))
        assert ctx.genre_section == ""
        assert ctx.style_fatigue_words == []
        assert "## 题材设定" not in ctx.to_prompt()


async def _put(novel_id: str) -> None:
    async with async_session() as session:
        await put_novel_genre(
            session,
            novel_id,
            {
                "core_promise": "以弱破强的痛快",
                "promise_note": "读者要看弱者用脑子翻盘",
                "cost_ratio": 7,
                "track": "从被赶出家门到掌控全城",
                "forbidden_list": [{"tagId": "forbidden:no-deus-ex-machina"}],
                "battlefield": ["battlefield:resources"],
            },
        )
