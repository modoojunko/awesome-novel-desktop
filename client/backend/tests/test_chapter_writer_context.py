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
    """c-og-slim-v2 换源：前情取上章概要＋必须完成的变化＋章末落点。"""
    prev = {
        "outline": {"summary": "她夜探库房调包账册"},
        "memo": {
            "required_changes": ["主角与师父决裂"],
            "reader_expectation": {"detail": "想知道师父到底是谁"},
        },
        "ladder_exit": "拿到半张地图，连夜出门，更不安",
    }
    text, semantic = build_previous_context(prev)
    assert semantic is True
    assert "上章写的是：她夜探库房调包账册" in text
    assert "上章必须完成的改变" in text
    assert "上章章末落点" in text


def test_previous_context_fallback_when_outline_empty():
    # 上章章纲情绪字段全空 → 语义模式不可用，正文尾段由 previous_tail 承载
    text, semantic = build_previous_context({"prose": "正文。", "outline": {}})
    assert semantic is False
    assert text == ""


# ── 上章结尾原文（c-chapter-seam-hardcut）────────────────────────────────


def test_clip_tail_to_sentence_boundary():
    from write.chapter_writer import clip_tail_to_sentence_boundary

    # 未超限原样返回
    assert clip_tail_to_sentence_boundary("短句。", 100) == "短句。"
    # 超限回退句边界起头，不以残句开头
    long_text = "短。" * 40  # 120 字，窗口内必有边界
    out = clip_tail_to_sentence_boundary(long_text, 60)
    assert len(out) <= 60
    assert out.startswith("短。")
    assert not out.startswith(("，", "很", "得"))
    # 全篇无句边界的病态文本：宁残不空
    assert clip_tail_to_sentence_boundary("啊" * 300, 50) == "啊" * 50
    assert clip_tail_to_sentence_boundary("", 50) == ""


def test_clip_tail_paragraphs():
    from write.chapter_writer import clip_tail_paragraphs

    # 多段从末向前累加（10 字放不下三段 → 丢第一段）
    text = "第一段。\n第二段。\n第三段。"
    assert clip_tail_paragraphs(text, 10) == "第二段。\n第三段。"
    # 超长单段：段内回退句边界（扩窗保起头完整，上限 2×预算）
    huge = "开头一句。" + "长" * 120 + "结束。"
    out = clip_tail_paragraphs(huge, 60)
    assert out.endswith("结束。")
    assert out.startswith("长")
    assert len(out) <= 120
    assert clip_tail_paragraphs("", 100) == ""
    assert clip_tail_paragraphs(None, 100) == ""


def test_previous_tail_block_both_paths_and_absent():
    """两路同源：直写与素材包同款定位句；无尾块时两路与现状逐字一致。"""

    ctx = _rich_context()
    ctx.previous_tail = "枪口对着他，众人在等他放下刀。"
    material = ctx.material_markdown()
    user = ctx.to_user_material()
    assert "【上章结尾（原文）】" in material
    assert "## 上章结尾（原文）" in user
    # 两路定位句同款、尾文同字
    assert "本章第一段从这里直接接下去写" in material
    assert "本章第一段从这里直接接下去写" in user
    assert "枪口对着他，众人在等他放下刀。" in material
    assert "枪口对着他，众人在等他放下刀。" in user
    # 仲裁句只在语义前情在场时携带（_rich_context 有 previous_context）
    assert "以这段原文为准" in material and "以这段原文为准" in user
    # 无尾块：整块缺席
    ctx2 = _rich_context()
    assert "上章结尾（原文）" not in ctx2.material_markdown()
    assert "上章结尾（原文）" not in ctx2.to_user_material()
    # 恒定层不受素材影响：含/不含尾块两章的 system 段逐字节一致
    assert ctx.build_system_prompt() == ctx2.build_system_prompt()


def test_validate_polished_prompt_tail_anchor():
    from write.chapter_writer import validate_polished_prompt

    base = (
        "## 任务指示\n字数不少。\n## 前情上下文\n前情要点。\n"
        "## 章纲概要\n概要。\n红线：无。\n质感：细节。爽点设计：线索·玉佩。\n"
    )
    ctx = ChapterContext()
    ctx.chapter_outline = {"summary": "概要"}
    ctx.micro_payoffs = [{"kind": "clue", "description": "玉佩"}]
    # 无尾块：不要求上章结尾锚
    assert validate_polished_prompt(base, ctx) == []
    # 有尾块：缺锚判不合格，补齐后合格
    ctx.previous_tail = "枪口对着他。"
    assert "上章结尾" in validate_polished_prompt(base, ctx)
    with_tail = base + "## 上章结尾（原文）\n枪口对着他。"
    assert validate_polished_prompt(with_tail, ctx) == []
    # 回退态：语义前情缺席 → 前情锚不触发、上章结尾锚照常触发
    ctx_fb = ChapterContext()
    ctx_fb.previous_tail = "枪口对着他。"
    no_prev = "## 任务指示\n字数不少。\n红线：无。\n质感：细节。"
    assert validate_polished_prompt(no_prev, ctx_fb) == ["上章结尾"]


# ── 预算与占位符守卫（纯 ChapterContext）─────────────────────────────────


def _rich_context() -> ChapterContext:
    ctx = ChapterContext()
    ctx.novel_title = "暗流"
    ctx.volume_no = 1
    ctx.chapter_no = 2
    ctx.word_target = 1800
    ctx.premise = "退役刑警调查悬案"
    ctx.world_setting = {
        "stage": "很" * 300,  # 段落吃满预算
        "extra": [{"key": f"名目{i}", "value": "容" * 180} for i in range(4)],
    }
    ctx.style_setting = {
        "role": "冷峻的叙事者",
        "few_shot_examples": ["雨点砸在铁皮棚上，他没抬头。"],
    }
    ctx.hooks = [{"description": f"伏笔{i}"} for i in range(12)]
    ctx.characters = [{"name": f"角色{i}", "state": "在场"} for i in range(8)]
    ctx.chapter_outline = {"summary": "她夜探库房调包账册", "characters": ["角色0"]}
    ctx.challenge = "旧档堆不对活人开放"
    ctx.plot_stage = "矛盾升级"
    ctx.plot_items = ["她翻墙进了库房", "灯下的账册是假的"]
    ctx.micro_payoffs = [
        {"kind": "clue", "description": "半块玉佩"},
    ]
    ctx.ladder_exit = "拿到地图，出门，更不安"
    ctx.required_changes = ["主角与师父决裂"]
    ctx.previous_context = "上章结尾情绪：紧张"
    return ctx


def test_budgets_world_hooks_characters():
    """c-write-prompt-layering：写正文恒定层世界块改全量注入——不裁剪、无「从略」；
    伏笔 ≤8 上限留在 user 层（伏笔8 在、伏笔11 不在）。"""
    ctx = _rich_context()
    system = ctx.build_system_prompt()
    assert "从略" not in system, "恒定层世界块全量注入，SHALL NOT 显式从略"
    assert "…" * 50 not in system
    assert "名目3" in system  # 4 条 extra 全量在场（旧 600 预算下必被从略）
    user = ctx.to_user_material()
    assert "伏笔7" in user
    assert "伏笔11" not in user


def test_red_lines_carry_all_constraints_verbatim():
    """铁律免死金牌（D4）：10 条铁律逐条完整进红线区，世界块不含铁律。"""
    ctx = _rich_context()
    ctx.world_setting = {
        "stage": "云梁界修仙世界",
        "constraints": [
            {"key": f"铁律{i}", "value": "死者不可复生，灵根不可后天再造"} for i in range(10)
        ],
    }
    system = ctx.build_system_prompt()
    # 世界铁律区（c-write-prompt-layering 上收恒定层）：10 条全量在场且完整
    for i in range(10):
        assert f"世界铁律·铁律{i}：死者不可复生，灵根不可后天再造" in system
    # 世界块不含铁律（铁律独立成节）
    block = next(
        (l for l in system.splitlines() if l.startswith("世界观：")), ""
    )
    if block:
        block_idx = system.index(block)
        block_end = system.find("\n##", block_idx)
        world_block = system[block_idx:block_end if block_end > 0 else len(system)]
        assert "世界铁律" not in world_block
    # user 层章级红线 SHALL NOT 再携带世界铁律
    assert "世界铁律·铁律0" not in ctx.to_user_material()


def test_story_engine_terrain_reads_v2_stage():
    """story engine terrain 改读 v2 stage（tasks 2.5 回归钉）：归一化后取 stage。"""
    from settings.world_model import normalize_world

    v2 = normalize_world({"stage": "南境多山，北境大漠"})
    assert v2.get("stage") == "南境多山，北境大漠"
    # v1 旧形状归一化后同样能取到 stage（engine.load_from_project 的取数口径）
    legacy = normalize_world({"geography": {"scenes": "南境修仙界"}})
    assert legacy.get("stage") == "南境修仙界"


def test_characters_full_roster_no_cap():
    """c-ai-material-audit：在场者不再封 5 人——第 6 个起也必须在提示词里（旧实现里"根本不存在"）。"""
    prompt = _rich_context().to_user_material()
    assert "角色4" in prompt
    assert "角色7" in prompt  # 旧断言「角色7 不在」＝5 人上限，已退役


def test_no_placeholders_in_prompt_or_material():
    for text in (
        _rich_context().to_user_material(),
        _rich_context().build_system_prompt(),
        _rich_context().material_markdown(),
    ):
        assert not _PLACEHOLDER.search(text)
    # 空上下文也不产生占位符
    empty = ChapterContext()
    assert not _PLACEHOLDER.search(empty.to_user_material())
    assert not _PLACEHOLDER.search(empty.build_system_prompt())
    assert not _PLACEHOLDER.search(empty.material_markdown())


def test_prompt_consumes_surviving_fields():
    """c-og-slim-v2：user 层消费留存格子（章纲概要/挑战/阶段/剧情条目/爽点/落点）。"""
    ctx = _rich_context()
    prompt = ctx.to_user_material()
    assert "章纲：她夜探库房调包账册" in prompt
    assert "本章要撞的墙：旧档堆不对活人开放" in prompt
    assert "本章在卷剧情里的位置：矛盾升级" in prompt
    assert "- 她翻墙进了库房" in prompt  # 剧情条目块
    assert "爽点设计（读者获得）：线索·半块玉佩" in prompt
    assert "章末落点：拿到地图，出门，更不安" in prompt
    # 文风例句随恒定层上收 system（c-write-prompt-layering 归属表）
    assert "雨点砸在铁皮棚上，他没抬头。" in ctx.build_system_prompt()
    # 退役面：场景原材料/权重/关键情节点一律不进提示词
    assert "场景原材料" not in prompt
    assert "权重：" not in prompt
    assert "关键情节点" not in prompt
    # 字数动态化：1800 而非硬编码 2500
    assert "写故事至少 1800 字" in prompt
    assert "写故事至少 2500 字" not in prompt


def test_material_markdown_skeleton():
    ctx = _rich_context()
    md = ctx.material_markdown()
    for label in (
        "【叙事身份】",
        "【任务指示】",
        "【前情上下文】",
        "【故事背景】",
        "【章纲概要】",
        "【本章要撞的墙】",
        "【本章在卷剧情里的位置】",
        "【角色初始状态】",
        "【活跃伏笔】",
        "【约束红线（最高优先级，任何压缩不得删改）】",
        "【文风例句（案例段原料）】",
    ):
        assert label in md
    # 场景原材料块随场景卡退役（c-og-slim-v2）
    assert "【场景原材料】" not in md
    assert "字数要求：写故事至少 1800 字" in md
    assert "扩写策略" in md
    # 「叙事完整性优先」逃生门与超限压缩策略退役（字数只设下限，可多不可少）
    assert "叙事完整性优先" not in md
    assert "压缩策略" not in md


# ── 前情三分支（build_chapter_context 集成）──────────────────────────────


def test_build_context_semantic_previous():
    """ch-2 且上章章纲有留存字段 → 语义前情＋上章结尾原文尾块两路并存。"""

    async def _run():
        project = await _new_project("cwc_sem")
        await _make_chapter(
            project,
            1,
            {
                "title": "第一章",
                "prose": "第一章的正文内容。\n结尾停在枪口对着他。",
                "outline": {"summary": "她在码头截住船家"},
                "ladder_exit": "主角决定查到底，焦虑升级",
            },
        )
        ref2 = await _make_chapter(project, 1, {"title": "第二章"})
        ctx = await build_chapter_context(project.root_path, ref2, "暗流")
        assert ctx.previous_context_semantic is True
        assert "上章写的是：她在码头截住船家" in ctx.previous_context
        assert "上章章末落点" in ctx.previous_context
        assert "主角决定查到底" in ctx.previous_context
        # 语义模式不把上章正文混进前情段（原文由尾块另路承载）
        assert "第一章的正文内容" not in ctx.previous_context
        assert ctx.previous_chapter_recap == ""
        # c-chapter-seam-hardcut：尾块承载上章正文结尾（文本级衔接）
        assert ctx.previous_tail != ""
        assert "结尾停在枪口对着他。" in ctx.previous_tail
        material = ctx.material_markdown()
        user = ctx.to_user_material()
        assert "【上章结尾（原文）】" in material
        assert "## 上章结尾（原文）" in user
        assert "以这段原文为准" in material and "以这段原文为准" in user

    _run_async(_run())


def test_build_context_fallback_to_prev_prose_tail():
    """上章章纲全空但正文存在 → 回退块化：无语义前情段，尾块承载正文末段。"""

    async def _run():
        project = await _new_project("cwc_fb")
        tail = "结尾处的最后一句。" * 60  # >800 字，验证裁剪
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
        # 回退块化：硬截摘要退役，正文尾段由 previous_tail 承载
        assert ctx.previous_context == ""
        assert ctx.previous_context_semantic is False
        assert ctx.previous_chapter_recap == ""
        assert len(ctx.previous_tail) <= 800
        assert ctx.previous_tail.endswith("结尾处的最后一句。")
        assert "开头。主角推门" not in ctx.previous_tail
        # 尾块在场，且回退态定位句不带仲裁句（无章末落点摘要可仲裁）
        user = ctx.to_user_material()
        assert "## 上章结尾（原文）" in user
        assert "以这段原文为准" not in user
        material = ctx.material_markdown()
        assert "【上章结尾（原文）】" in material

    _run_async(_run())


def test_build_context_first_chapter_fixed_sentence():
    """全书第一章（vol-1-ch-1）→ 开篇固定句。"""

    async def _run():
        project = await _new_project("cwc_ch1")
        ref1 = await _make_chapter(project, 1, {"title": "第一章"})
        ctx = await build_chapter_context(project.root_path, ref1, "暗流")
        assert ctx.previous_context == "无前置章节，开篇直接切入角色当下行动，禁止大段世界观背景介绍。"
        assert ctx.previous_context_semantic is True
        # c-chapter-seam-hardcut：首章无尾块，章首接点铁律自然不触发
        assert ctx.previous_tail == ""
        assert "上章结尾（原文）" not in ctx.to_user_material()

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
                "outline": {"summary": "卷一收官：她拿回族谱"},
                "ladder_exit": "卷一末章落点",
            },
        )
        ref_v2 = await _make_chapter(project, 2, {"title": "2-1"})
        ctx = await build_chapter_context(project.root_path, ref_v2, "暗流")
        assert ctx.volume_no == 2
        assert ctx.previous_context_semantic is True
        assert "她拿回族谱" in ctx.previous_context
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
        assert "写故事至少 1800 字" in ctx.to_user_material()

    _run_async(_run())
