"""agent 模式写法块测试（c-agent-dialog-prose 批D）：挑选条目直接组装/重试复用/零命中无块。

上下文隔离铁律的组装面在这层钉死：块内容只来自 kb_picks 解析结果，
与规则选择器（章纲信号）零关系。
"""

import asyncio
import tempfile
import uuid

from sqlalchemy import select as sel

from db import async_session
from kb.service import create_entry
from models.chapter import Chapter
from models.kb import KbMatchRun
from models.project import Novel
from models.user import User
from models.volume import Volume
from write.write_block import build_block_from_picks, resolve_pick_entries


def _run(coro):
    return asyncio.run(coro)


async def _seed(with_entries: bool = True):
    uid = f"ag{uuid.uuid4().hex[:8]}"
    root = tempfile.mkdtemp(prefix=f"ag_{uid}_")
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="agent块"))
        novel = Novel(
            user_id=uid, name="agent块书", slug=uuid.uuid4().hex[:12],
            root_path=root, source="manual", current_phase="write",
        )
        db.add(novel)
        await db.flush()
        vol = Volume(project_id=novel.id, volume_no=1, title="卷")
        db.add(vol)
        await db.flush()
        db.add(Chapter(
            project_id=novel.id, volume_id=vol.id, chapter_no=1, ref="vol-1-ch-1",
            title="第一章", summary="林野用体温计试探血族弱点", primary_mood="疑",
            plot_stage="冲突初现",
        ))
        ids: list[str] = []
        if with_entries:
            id_a = (await create_entry(
                db, user_id=uid, genre="", concept="手法",
                title="体温计反转", payload={"instruction": "体温计反转：物件反应递减泄底，物件推进。", "scene": "日常"},
                instruction="体温计反转：物件反应递减泄底，物件推进。",
            ))[0].id
            id_b = (await create_entry(
                db, user_id=uid, genre="", concept="文笔",
                title="以物写情", payload={"slot": "craft", "craft": "以物写情：情绪落在物件上，不直陈。", "name": "以物写情"},
                instruction="以物写情：情绪落在物件上，不直陈。",
            ))[0].id
            ids = [id_a, id_b]
        await db.commit()
        return uid, novel.id, ids


async def _call(novel_id: str, uid: str, picks, prompt="【本章剧情走向】体温计试探"):
    async with async_session() as db:
        return await build_block_from_picks(
            db, novel_id=novel_id, chapter_ref="vol-1-ch-1", user_id=uid,
            picks=picks, prompt=prompt,
        )


def test_挑选条目直接组装_保序_选择器零参与():
    _uid, novel_id, ids = _run(_seed())
    # 倒序传：块内顺序必须跟 agent 挑选顺序（文笔在前），而非规则打分序
    picks = [
        {"entry_id": ids[1], "reason": "落点用物件收"},
        {"entry_id": ids[0], "reason": "章纲已安排物件试探桥段"},
    ]
    block, run_id, listing = _run(_call(novel_id, _uid, picks))
    assert block is not None and run_id is not None
    assert "【本章写法指引】" in block
    assert block.index("以物写情") < block.index("体温计反转")  # 保挑选顺序
    assert "今昔对比" not in block  # 未挑选的条目绝不出现
    assert [it["entry_id"] for it in listing] == ids[::-1]
    assert listing[0]["reason"] == "落点用物件收"
    # run 落 selector=agent＋brief_json 审计
    async def _run_row():
        async with async_session() as db:
            return (
                await db.execute(sel(KbMatchRun).where(KbMatchRun.id == run_id))
            ).scalar_one()
    row = _run(_run_row())
    assert row.selector == "agent"
    assert ids[1] in row.brief_json


def test_重试同挑选同提示词_复用同run字节一致():
    _uid, novel_id, ids = _run(_seed())
    picks = [{"entry_id": ids[0], "reason": "物件桥段"}, {"entry_id": ids[1]}]
    first = _run(_call(novel_id, _uid, picks))
    second = _run(_call(novel_id, _uid, picks))
    assert first[1] == second[1]
    assert first[0] == second[0]  # 逐字节一致
    async def _count():
        async with async_session() as db:
            return len((
                await db.execute(sel(KbMatchRun).where(KbMatchRun.novel_id == novel_id))
            ).scalars().all())
    assert _run(_count()) == 1


def test_提示词变了_重选新run():
    _uid, novel_id, ids = _run(_seed())
    picks = [{"entry_id": ids[0]}]
    first = _run(_call(novel_id, _uid, picks, prompt="提示词A"))
    second = _run(_call(novel_id, _uid, picks, prompt="提示词B"))
    assert first[1] != second[1]


def test_空picks_零命中无块():
    _uid, novel_id, _ids = _run(_seed())
    assert _run(_call(novel_id, _uid, [])) == (None, None, None)


def test_无效id全部剔除_零有效无块():
    _uid, novel_id, _ids = _run(_seed())
    picks = [{"entry_id": "ghost-1"}, {"entry_id": "ghost-2"}]
    assert _run(_call(novel_id, _uid, picks)) == (None, None, None)


def test_混合有效无效_只注有效():
    _uid, novel_id, ids = _run(_seed())
    picks = [{"entry_id": ids[0], "reason": "物件桥段"}, {"entry_id": "ghost-9"}]
    block, _run_id, listing = _run(_call(novel_id, _uid, picks))
    assert block is not None
    assert "体温计反转" in block
    assert [it["entry_id"] for it in listing] == [ids[0]]


def test_resolve_pick_entries_无效清单与clause():
    _uid, novel_id, ids = _run(_seed())

    async def _go():
        async with async_session() as db:
            return await resolve_pick_entries(
                db, novel_id=novel_id, user_id=_uid,
                picks=[(ids[0], "物件桥段"), ("ghost-1", "")],
            )
    resolved, invalid = _run(_go())
    assert [r[2] for r in resolved] == ["手法"]
    assert invalid == ["ghost-1"]
    assert resolved[0][1] == "物件桥段"
