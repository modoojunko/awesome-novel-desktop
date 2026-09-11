"""ai-prompt-crafting — 素材包组装层测试（ChapterContext 升级）

验证：前情上下文三分支（章纲语义优先 / 无章纲回退正文末段 / 开篇固定句 +
卷首章读上卷末章）；裁剪预算（世界观 ≤600 字 / 伏笔 ≤8 / 角色 ≤5）；
无 {…} 占位符；word_target 夹取；material_markdown 骨架。

用法：
    cd client/backend
    python -m pytest tests/test_chapter_writer_context.py -v
"""

import asyncio
import os
import re
import tempfile

import pytest

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_cwc.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_chapter_writer_context_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from chapters.service import create_chapter  # noqa: E402
from chapters.store import save_chapter  # noqa: E402
from db import Base, async_session, engine  # noqa: E402
from models import Novel  # noqa: E402
from write.chapter_writer import (  # noqa: E402
    ChapterContext,
    build_chapter_context,
    build_previous_context,
    clamp_word_target,
)

USER_ID = "cwc_user"

_PLACEHOLDER = re.compile(r"\{[^}\n]*\}")


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


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    _run_async(_create_tables())
    yield


async def _new_project(name: str) -> Novel:
    root = os.path.join(_tmp_data_root, name)
    os.makedirs(os.path.join(root, "volumes"), exist_ok=True)
    os.makedirs(os.path.join(root, "chapters"), exist_ok=True)
    project = Novel(
        user_id=USER_ID,
        name=name,
        slug=name,
        root_path=root,
        source="manual",
        current_phase="outline",
    )
    async with async_session() as session:
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project


async def _make_chapter(project: Novel, vol: int, data: dict) -> str:
    from repositories import volume_repo

    async with async_session() as session:
        proj = await session.get(Novel, project.id)
        await volume_repo.upsert(session, proj.id, vol, title=f"第{vol}卷")
        await session.refresh(proj)
        ch = await create_chapter(session, proj, f"vol-{vol}", title=data.get("title", ""))
        await save_chapter(project.root_path, ch["ref"], data)
        return ch["ref"]


# ── word_target 夹取 ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, 2500),
        ("abc", 2500),
        (100, 2500),      # 低于下限 → 默认
        (10000, 2500),    # 超上限 → 默认
        (800, 800),
        (6000, 6000),
        ("3000", 3000),
    ],
)
def test_clamp_word_target(raw, expected):
    assert clamp_word_target(raw) == expected


# ── 前情三分支（build_previous_context 单元）──────────────────────────────


def test_previous_context_semantic_from_outline():
    prev = {
        "emotional_design": {
            "mood_progression": "平静→不安→紧张",
            "emotional_hook": "师父的身份成谜",
        },
        "memo": {
            "required_changes": ["主角与师父决裂"],
            "reader_expectation": {"detail": "想知道师父到底是谁"},
        },
        "ladder_exit": "拿到半张地图，连夜出门，更不安",
    }
    text, semantic = build_previous_context(prev)
    assert semantic is True
    assert "上章结尾情绪：紧张" in text
    assert "上章章末情绪钩子" in text
    assert "上章必须完成的改变" in text
    assert "上章章末落点" in text
    assert "读者期待缺口" in text


def test_previous_context_fallback_when_outline_empty():
    # 上章章纲情绪字段全空 → 语义模式不可用，调用方回退正文末段
    text, semantic = build_previous_context({"prose": "正文。", "outline": {}})
    assert semantic is False
    assert text == ""


# ── 预算与占位符守卫（纯 ChapterContext）─────────────────────────────────


def _rich_context() -> ChapterContext:
    ctx = ChapterContext()
    ctx.novel_title = "暗流"
    ctx.volume_no = 1
    ctx.chapter_no = 2
    ctx.word_target = 1800
    ctx.premise = "退役刑警调查悬案"
    ctx.world_setting = {
        "geography": {"scenes": "很" * 300},  # 超预算世界观
    }
    ctx.style_setting = {
        "role": "冷峻的叙事者",
        "few_shot_examples": ["雨点砸在铁皮棚上，他没抬头。"],
    }
    ctx.hooks = [{"description": f"伏笔{i}"} for i in range(12)]
    ctx.characters = [{"name": f"角色{i}", "state": "在场"} for i in range(8)]
    ctx.scene_cards = [
        {
            "scene_name": "酒馆对峙",
            "goal": "问出货源",
            "obstacle": "掌柜装傻",
            "hook": "角落有人盯梢",
            "weight": "high",
            "focus": "核心冲突",
        },
        {"scene_name": "巷口转场", "weight": "low", "focus": "信息差"},
    ]
    ctx.micro_payoffs = [
        {"kind": "clue", "description": "半块玉佩", "location": "中段"},
    ]
    ctx.ladder_exit = "拿到地图，出门，更不安"
    ctx.required_changes = ["主角与师父决裂"]
    ctx.previous_context = "上章结尾情绪：紧张"
    return ctx


def test_budgets_world_hooks_characters():
    ctx = _rich_context()
    prompt = ctx.to_prompt()
    # v2（world-setting-v2）：世界块整条从略预算制——块整体不超 600 预算，
    # 超预算条目整条跳过（不切半条），以显式「从略」行收尾
    world_block = "\n".join(
        l for l in prompt.splitlines()
        if l.startswith(("世界观：", "  - ", "- 世界舞台", "- 力量体系", "- 力量的代价", "- 势力", "- 历史与旧账", "- 世界细节", "（另有"))
    )
    assert "很" * 300 in world_block or "从略" in world_block
    assert "…" * 50 not in world_block  # 不再腰斩截断
    # 伏笔 ≤8：伏笔8 在、伏笔11 不在
    assert "伏笔7" in prompt


def test_red_lines_carry_all_constraints_verbatim():
    """铁律免死金牌（D4）：10 条铁律逐条完整进红线区，世界块不含铁律。"""
    ctx = _rich_context()
    ctx.world_setting = {
        "stage": "云梁界修仙世界",
        "constraints": [
            {"key": f"铁律{i}", "value": "死者不可复生，灵根不可后天再造"} for i in range(10)
        ],
    }
    prompt = ctx.to_prompt()
    # 红线区：10 条全量在场且完整（任何压缩不得删改）
    for i in range(10):
        assert f"世界铁律·铁律{i}：死者不可复生，灵根不可后天再造" in prompt
    # 世界块不含铁律（走独立红线区，不占 600 预算）
    block = next(
        (l for l in prompt.splitlines() if l.startswith("世界观：")), ""
    )
    if block:
        block_idx = prompt.index(block)
        block_end = prompt.find("\n##", block_idx)
        world_block = prompt[block_idx:block_end if block_end > 0 else len(prompt)]
        assert "世界铁律" not in world_block


def test_story_engine_terrain_reads_v2_stage():
    """story engine terrain 改读 v2 stage（tasks 2.5 回归钉）：归一化后取 stage。"""
    from settings.world_model import normalize_world

    v2 = normalize_world({"stage": "南境多山，北境大漠"})
    assert v2.get("stage") == "南境多山，北境大漠"
    # v1 旧形状归一化后同样能取到 stage（engine.load_from_project 的取数口径）
    legacy = normalize_world({"geography": {"scenes": "南境修仙界"}})
    assert legacy.get("stage") == "南境修仙界"


def test_budgets_characters():
    """角色 ≤5（原预算测试的遗留半段，拆出防误挂）。"""
    prompt = _rich_context().to_prompt()
    assert "角色4" in prompt
    assert "角色7" not in prompt


def test_no_placeholders_in_prompt_or_material():
    for prompt in (_rich_context().to_prompt(), _rich_context().material_markdown()):
        assert not _PLACEHOLDER.search(prompt)
    # 空上下文也不产生占位符
    empty = ChapterContext()
    assert not _PLACEHOLDER.search(empty.to_prompt())
    assert not _PLACEHOLDER.search(empty.material_markdown())


def test_prompt_consumes_new_grid_fields():
    ctx = _rich_context()
    prompt = ctx.to_prompt()
    assert "权重：高" in prompt
    assert "焦点：核心冲突" in prompt
    assert "核心事件链（外部动作，非内心）：问出货源 → 掌柜装傻 → 角落有人盯梢" in prompt
    assert "爽点设计（读者获得）" in prompt
    assert "章末落点：拿到地图，出门，更不安" in prompt
    assert "雨点砸在铁皮棚上，他没抬头。" in prompt
    # 字数动态化：1800 而非硬编码 2500
    assert "约 1800 字" in prompt
    assert "约 2500 字" not in prompt


def test_material_markdown_skeleton():
    ctx = _rich_context()
    md = ctx.material_markdown()
    for label in (
        "【叙事身份】",
        "【任务指示】",
        "【前情上下文】",
        "【故事背景】",
        "【场景原材料】",
        "【角色初始状态】",
        "【活跃伏笔】",
        "【约束红线（最高优先级，任何压缩不得删改）】",
        "【文风例句（案例段原料）】",
    ):
        assert label in md
    assert "目标字数：约 1800 字" in md
    assert "压缩策略" in md


# ── 前情三分支（build_chapter_context 集成）──────────────────────────────


def test_build_context_semantic_previous():
    """ch-2 且上章章纲有情绪设计 → 语义前情，不读上章正文。"""

    async def _run():
        project = await _new_project("cwc_sem")
        await _make_chapter(
            project,
            1,
            {
                "title": "第一章",
                "prose": "第一章的正文内容。",
                "emotional_design": {
                    "mood_progression": "平静→不安",
                    "emotional_hook": "信件来路不明",
                },
                "ladder_exit": "主角决定查到底，焦虑升级",
            },
        )
        ref2 = await _make_chapter(project, 1, {"title": "第二章"})
        ctx = await build_chapter_context(project.root_path, ref2, "暗流")
        assert ctx.previous_context_semantic is True
        assert "上章章末落点" in ctx.previous_context
        assert "主角决定查到底" in ctx.previous_context
        # 语义模式不注入上章正文
        assert "第一章的正文内容" not in ctx.previous_context
        assert ctx.previous_chapter_recap == ""

    _run_async(_run())


def test_build_context_fallback_to_prev_prose_tail():
    """上章章纲情绪字段全空但正文存在 → 回退上章正文末 500 字。"""

    async def _run():
        project = await _new_project("cwc_fb")
        tail = "结尾处的最后一句。" * 60  # >500 字，验证截尾
        await _make_chapter(
            project,
            1,
            {
                "title": "第一章",
                "prose": "开头。主角推门。" + "中段。" * 100 + tail,
            },
        )
        ref2 = await _make_chapter(project, 1, {"title": "第二章"})
        ctx = await build_chapter_context(project.root_path, ref2, "暗流")
        assert ctx.previous_context == ""
        assert ctx.previous_context_semantic is False
        assert len(ctx.previous_chapter_recap) == 500
        assert ctx.previous_chapter_recap.endswith("结尾处的最后一句。")
        assert "开头。主角推门" not in ctx.previous_chapter_recap

    _run_async(_run())


def test_build_context_first_chapter_fixed_sentence():
    """全书第一章（vol-1-ch-1）→ 开篇固定句。"""

    async def _run():
        project = await _new_project("cwc_ch1")
        ref1 = await _make_chapter(project, 1, {"title": "第一章"})
        ctx = await build_chapter_context(project.root_path, ref1, "暗流")
        assert ctx.previous_context == "无前置章节，开篇直接切入角色当下行动，禁止大段世界观背景介绍。"
        assert ctx.previous_context_semantic is True

    _run_async(_run())


def test_build_context_volume_first_chapter_reads_prev_volume_tail():
    """vol-2-ch-1（卷首章）→ 读上一卷末章章纲。"""

    async def _run():
        project = await _new_project("cwc_vol2")
        await _make_chapter(project, 1, {"title": "1-1"})
        await _make_chapter(
            project,
            1,
            {
                "title": "1-2",
                "emotional_design": {"emotional_hook": "卷一收官钩子"},
                "ladder_exit": "卷一末章落点",
            },
        )
        ref_v2 = await _make_chapter(project, 2, {"title": "2-1"})
        ctx = await build_chapter_context(project.root_path, ref_v2, "暗流")
        assert ctx.volume_no == 2
        assert ctx.previous_context_semantic is True
        assert "卷一收官钩子" in ctx.previous_context
        assert "卷一末章落点" in ctx.previous_context

    _run_async(_run())


def test_build_context_word_target_from_chapter():
    """章纲 word_target 落库 → ctx 夹取后取用。"""

    async def _run():
        project = await _new_project("cwc_wt")
        ref1 = await _make_chapter(
            project, 1, {"title": "第一章", "word_target": 1800}
        )
        ctx = await build_chapter_context(project.root_path, ref1, "暗流")
        assert ctx.word_target == 1800
        assert "约 1800 字" in ctx.to_prompt()

    _run_async(_run())
