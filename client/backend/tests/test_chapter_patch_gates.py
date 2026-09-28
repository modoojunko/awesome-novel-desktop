"""章 PUT 缺键守卫（c-og-chapter-put-patch-gates）：部分键保存不得抹掉未带字段。

背景（2026-09-28 演示栈事故）：此前除 plot_items 外全字段族「缺键即清」，任何
部分键 PUT（旁路写入/瘦身底座合并）都会把未带字段抹空——用户的挑战/章末落点/
必须完成的变化×5 被一次整表回传清空。本文件钉死新合同：
- family 键缺失 / None / 形状非 dict、顶层标量缺键或 None → 保持现值；
  （None 按缺键处理与 plot_items 守卫同口径；显式清空走空串/[]）
- 显式值落值；显式空串/[] 清空；
- prose 缺键 → 正文与派生元数据（word_count/has_prose/outline_status）保持现值；
- plot_items 守卫不变（test_plot_items_save.py 另有覆盖）。

用法：
    cd client/backend
    python -m pytest tests/test_chapter_patch_gates.py -v
"""

import asyncio
import os
import tempfile

_tmp_db = tempfile.NamedTemporaryFile(suffix="_patch_gates.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_patch_gates_")

import pytest  # noqa: E402

from conftest import seed_chapter_db  # noqa: E402
from db import Base, engine  # noqa: E402

_FULL = {
    "volume": 1,
    "chapter": 1,
    "title": "第一章",
    "outline": {"summary": "主角来到边境城邦。", "characters": ["林野", "阿蓟"]},
    "memo": {
        "payoff_plan": {"must_resolve": ["旧刀的来历"], "must_hold": ["幕后主使身份"]},
        "required_changes": ["林野从流民变成守夜人"],
        "prohibitions": ["不出现现代词汇"],
    },
    "emotional_design": {"primary_mood": "紧张"},
    "ladder_exit": "枪口对着他，局面未定。",
    "challenge": "守夜人举枪要清掉他。",
    "plot_stage": "冲突初现",
    "micro_payoffs": [{"kind": "clue", "description": "咬痕的秘密露了一角"}],
    "prose": "煤气灯在雾里发脏黄的光。",
    "word_target": 2500,
}

# 种子后的期望快照（键名 → 装配层取值路径见 _collect）
_SEED_EXPECT = {
    "summary": "主角来到边境城邦。",
    "characters": ["林野", "阿蓟"],
    "mood": "紧张",
    "ladder": "枪口对着他，局面未定。",
    "challenge": "守夜人举枪要清掉他。",
    "stage": "冲突初现",
    "changes": ["林野从流民变成守夜人"],
    "prohibitions": ["不出现现代词汇"],
    "must_resolve": ["旧刀的来历"],
    "must_hold": ["幕后主使身份"],
    "micro": [{"kind": "clue", "description": "咬痕的秘密露了一角"}],
    "prose": "煤气灯在雾里发脏黄的光。",
    "word_target": 2500,
}


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _ensure_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _seed(root: str) -> None:
    _run(seed_chapter_db(root, dict(_FULL)))


async def _load(root: str, ref: str = "vol-1-ch-1") -> dict:
    from chapters.store import load_chapter

    return await load_chapter(root, ref)


def _collect(d: dict) -> dict:
    """装配层章 JSON → 平铺期望键（装配对空值省键，取值带默认）。"""
    return {
        "summary": (d.get("outline") or {}).get("summary", ""),
        "characters": (d.get("outline") or {}).get("characters", []),
        "mood": (d.get("emotional_design") or {}).get("primary_mood", ""),
        "ladder": d.get("ladder_exit", ""),
        "challenge": d.get("challenge", ""),
        "stage": d.get("plot_stage", ""),
        "changes": ((d.get("memo") or {}).get("required_changes") or []),
        "prohibitions": ((d.get("memo") or {}).get("prohibitions") or []),
        "must_resolve": (((d.get("memo") or {}).get("payoff_plan") or {}).get("must_resolve") or []),
        "must_hold": (((d.get("memo") or {}).get("payoff_plan") or {}).get("must_hold") or []),
        "micro": d.get("micro_payoffs", []),
        "prose": d.get("prose", ""),
        "word_target": d.get("word_target"),
    }


async def _row_derived(root: str) -> dict:
    """直查行：word_count/has_prose/outline_status/status（装配层不吐派生元数据）。"""
    from sqlalchemy import select

    from db import async_session
    from models.chapter import Chapter
    from models.project import Novel

    async with async_session() as session:
        row = (await session.scalars(
            select(Chapter)
            .join(Novel, Novel.id == Chapter.project_id)
            .where(Novel.root_path == root, Chapter.ref == "vol-1-ch-1")
        )).one()
        return {
            "word_count": row.word_count,
            "has_prose": row.has_prose,
            "outline_status": row.outline_status,
            "status": row.status,
        }


# ── 核心合同：部分键 PUT 只动带了的键 ───────────────────────────────────────


def test_partial_put_preserves_everything_not_sent():
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="patch_one_key_")
    _seed(root)
    from chapters.store import save_chapter

    _run(save_chapter(root, "vol-1-ch-1", {"challenge": "换了墙"}))
    got = _collect(_run(_load(root)))
    assert got == {**_SEED_EXPECT, "challenge": "换了墙"}


@pytest.mark.parametrize("payload,patched", [
    ({"challenge": "x"}, {"challenge": "x"}),
    ({"emotional_design": {"primary_mood": "平静"}}, {"mood": "平静"}),
    ({"outline": {"characters": ["甲", "乙"]}}, {"characters": ["甲", "乙"]}),
    ({"memo": {"prohibitions": ["禁A"]}}, {"prohibitions": ["禁A"]}),
    ({"micro_payoffs": [{"kind": "reveal", "description": "真相"}]},
     {"micro": [{"kind": "reveal", "description": "真相"}]}),
    ({"ladder_exit": "新落点"}, {"ladder": "新落点"}),
    ({"word_target": 3000}, {"word_target": 3000}),
    ({"plot_stage": "高潮爆发"}, {"stage": "高潮爆发"}),
    ({"memo": {"required_changes": ["新变化"]}}, {"changes": ["新变化"]}),
    ({"memo": {"payoff_plan": {"must_resolve": ["新回收"], "must_hold": []}}},
     {"must_resolve": ["新回收"], "must_hold": []}),
])
def test_single_field_patch_never_touches_siblings(payload, patched):
    """任意单字段 patch 后：本键落值，其余字段全部原样。"""
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="patch_single_")
    _seed(root)
    from chapters.store import save_chapter

    _run(save_chapter(root, "vol-1-ch-1", payload))
    got = _collect(_run(_load(root)))
    assert got == {**_SEED_EXPECT, **patched}


# ── 缺键 / None / 脏形状 ────────────────────────────────────────────────────


def test_missing_family_keys_and_bad_shapes_keep_values():
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="patch_shapes_")
    _seed(root)
    from chapters.store import save_chapter

    for payload in (
        {"emotional_design": None},
        {"emotional_design": "脏形状"},
        {"outline": None},
        {"outline": "脏形状"},
        {"memo": None},
        {"memo": "脏形状"},
        {"ladder_exit": None, "challenge": None, "plot_stage": None},
    ):
        _run(save_chapter(root, "vol-1-ch-1", payload))
        assert _collect(_run(_load(root))) == _SEED_EXPECT, payload


def test_explicit_values_and_empties_still_write():
    """显式值落值；显式空串/[] 清空——守卫不改变「想清就能清」。"""
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="patch_explicit_")
    _seed(root)
    from chapters.store import save_chapter

    _run(save_chapter(root, "vol-1-ch-1", {"emotional_design": {"primary_mood": ""}}))
    got = _collect(_run(_load(root)))
    assert got == {**_SEED_EXPECT, "mood": ""}

    _run(save_chapter(root, "vol-1-ch-1", {"ladder_exit": ""}))
    got = _collect(_run(_load(root)))
    assert got == {**_SEED_EXPECT, "mood": "", "ladder": ""}

    _run(save_chapter(root, "vol-1-ch-1", {
        "memo": {
            "required_changes": [], "prohibitions": [],
            "payoff_plan": {"must_resolve": [], "must_hold": []},
        },
    }))
    got = _collect(_run(_load(root)))
    assert got == {**_SEED_EXPECT, "mood": "", "ladder": "",
                   "changes": [], "prohibitions": [], "must_resolve": [], "must_hold": []}

    _run(save_chapter(root, "vol-1-ch-1", {"micro_payoffs": []}))
    got = _collect(_run(_load(root)))
    assert got["micro"] == []


def test_memo_subkey_gate_replaces_only_named_list():
    """memo 在场但只带 required_changes：changes 整表替换，prohibitions/payoff 保持。"""
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="patch_memo_")
    _seed(root)
    from chapters.store import save_chapter

    _run(save_chapter(root, "vol-1-ch-1", {"memo": {"required_changes": ["新变化一", "新变化二"]}}))
    got = _collect(_run(_load(root)))
    assert got == {**_SEED_EXPECT, "changes": ["新变化一", "新变化二"]}


def test_outline_subkey_gate_replaces_only_named():
    """outline 在场但只带 characters：角色整表替换，summary 保持。"""
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="patch_outline_")
    _seed(root)
    from chapters.store import save_chapter

    _run(save_chapter(root, "vol-1-ch-1", {"outline": {"characters": ["银铎"]}}))
    got = _collect(_run(_load(root)))
    assert got == {**_SEED_EXPECT, "characters": ["银铎"]}


# ── prose 与派生元数据 ──────────────────────────────────────────────────────


def test_prose_missing_keeps_text_and_derived_metadata():
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="patch_prose_")
    _seed(root)
    from chapters.store import save_chapter

    seed_meta = _run(_row_derived(root))
    assert seed_meta["has_prose"] is True
    assert seed_meta["word_count"] == len("煤气灯在雾里发脏黄的光。")

    _run(save_chapter(root, "vol-1-ch-1", {"challenge": "只改挑战"}))
    d = _run(_load(root))
    assert d["prose"] == "煤气灯在雾里发脏黄的光。"
    meta = _run(_row_derived(root))
    assert meta["word_count"] == seed_meta["word_count"]
    assert meta["has_prose"] is True
    assert meta["outline_status"] == seed_meta["outline_status"]
    assert meta["status"] == seed_meta["status"]

    # 显式 prose 落值：替换并重算派生
    _run(save_chapter(root, "vol-1-ch-1", {"prose": "新的一段。", "status": "confirmed"}))
    d = _run(_load(root))
    assert d["prose"] == "新的一段。"
    meta = _run(_row_derived(root))
    assert meta["word_count"] == len("新的一段。")
    assert meta["has_prose"] is True
    assert meta["outline_status"] == "confirmed"
    assert meta["status"] == "confirmed"
    assert d["challenge"] == "只改挑战"  # 同时其余字段保持


# ── 版本快照触发面 ──────────────────────────────────────────────────────────


def test_no_version_snapshot_on_partial_put_without_content_change():
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="patch_snapshot_")
    _seed(root)
    from sqlalchemy import select

    from chapters.store import save_chapter
    from db import async_session
    from models.chapter import Chapter, ChapterVersion
    from models.project import Novel

    async def _version_count() -> int:
        async with async_session() as session:
            ch = (await session.scalars(
                select(Chapter)
                .join(Novel, Novel.id == Chapter.project_id)
                .where(Novel.root_path == root, Chapter.ref == "vol-1-ch-1")
            )).one()
            return len((await session.scalars(
                select(ChapterVersion).where(ChapterVersion.chapter_id == ch.id)
            )).all())

    baseline = _run(_version_count())  # 种子本身带 prose → 已有 1 条
    assert baseline == 1

    _run(save_chapter(root, "vol-1-ch-1", {"challenge": "又换了墙"}))
    assert _run(_version_count()) == baseline  # 无 prose/summary 变化 → 不写快照

    _run(save_chapter(root, "vol-1-ch-1", {"outline": {"summary": "新概要。"}}))
    assert _run(_version_count()) == baseline + 1  # summary 实质变化才写
