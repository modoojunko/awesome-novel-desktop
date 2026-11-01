"""写法块注入测试（c-kb-write-block B6）：未启用零变化/run 复用/续写带同块/停用无块/零命中。"""

import asyncio
import uuid

from sqlalchemy import select as sel

from db import async_session
from kb.service import create_entry
from models.chapter import Chapter
from models.kb import (
    KbBookBinding,
    KbLibrary,
    KbMatchRun,
)
from models.project import Novel
from models.user import User
from models.volume import Volume
from write.write_block import prepare_write_block


def _run(coro):
    return asyncio.run(coro)


async def _seed(with_entries: bool, bind: bool = True):
    uid = f"wb{uuid.uuid4().hex[:8]}"
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="写法块"))
        novel = Novel(
            user_id=uid, name="写法块书", slug=uuid.uuid4().hex[:12],
            root_path=f"./data/{uuid.uuid4().hex[:12]}", source="manual", current_phase="write",
        )
        db.add(novel)
        await db.flush()
        vol = Volume(project_id=novel.id, volume_no=1, title="卷")
        db.add(vol)
        await db.flush()
        ch = Chapter(
            project_id=novel.id, volume_id=vol.id, chapter_no=1, ref="vol-1-ch-1",
            title="第一章", summary="与老祖正面交锋，硬撼对方底牌", primary_mood="燃",
            plot_stage="高潮爆发",
        )
        db.add(ch)
        if with_entries:
            for i in range(3):
                entry, _g, err = await create_entry(
                    db, user_id=uid, genre="", concept="手法",
                    title=f"招式{i}", payload={"instruction": f"交锋第{i}式：先守后攻。", "scene": "打斗"},
                    instruction=f"交锋第{i}式：先守后攻。",
                )
                assert entry is not None, str(err)
        if bind:
            if with_entries:
                # create_entry 已自动建 auto 手法库（批3 修复后 enabled=True）——复用它
                lib = (await db.execute(
                    sel(KbLibrary).where(KbLibrary.user_id == uid, KbLibrary.concept == "手法")
                )).scalars().first()
            else:
                # 空库测试：无条目不触发 auto 建库，手动落一张空 auto 库
                lib = KbLibrary(
                    user_id=uid, genre="", concept="手法", name="手法库",
                    rule_kind="auto", enabled=True,
                )
                db.add(lib)
                await db.flush()
            assert lib is not None
            db.add(KbBookBinding(novel_id=novel.id, library_id=lib.id, enabled=True))
        await db.commit()
        return uid, novel.id


def test_未启用库_零变化():
    uid, novel_id = _run(_seed(with_entries=True, bind=False))
    async def _go():
        async with async_session() as db:
            return await prepare_write_block(db, novel_id=novel_id, chapter_ref="vol-1-ch-1", user_id=uid)
    assert _run(_go()) == (None, None, None)


def test_启用后选块落run_重试复用字节一致():
    uid, novel_id = _run(_seed(with_entries=True, bind=True))

    async def _go():
        async with async_session() as db:
            return await prepare_write_block(db, novel_id=novel_id, chapter_ref="vol-1-ch-1", user_id=uid)
    first = _run(_go())
    assert first[0] is not None and first[1] is not None
    assert "【本章写法指引】" in first[0]
    assert "红线与契约优先" in first[0]
    assert len(first[2]) == 3  # 清单三条

    second = _run(_go())
    assert second[0] == first[0]           # 逐字节一致
    assert second[1] == first[1]           # 复用同 run

    async def _run_count():
        async with async_session() as db:
            return len((await db.execute(
                sel(KbMatchRun).where(KbMatchRun.novel_id == novel_id)
            )).scalars().all())
    assert _run(_run_count()) == 1         # 没有第二条 run


def test_续写按章节复用():
    uid, novel_id = _run(_seed(with_entries=True, bind=True))
    async def _go(**kw):
        async with async_session() as db:
            return await prepare_write_block(db, novel_id=novel_id, chapter_ref="vol-1-ch-1", user_id=uid, **kw)
    first = _run(_go())
    refill = _run(_go(refill=True))
    assert refill[0] == first[0] and refill[1] == first[1]


def test_停用后无块_不注入旧run():
    uid, novel_id = _run(_seed(with_entries=True, bind=True))
    async def _go():
        async with async_session() as db:
            return await prepare_write_block(db, novel_id=novel_id, chapter_ref="vol-1-ch-1", user_id=uid)
    assert _run(_go())[0] is not None

    async def _unbind():
        async with async_session() as db:
            b = (await db.execute(
                sel(KbBookBinding).where(KbBookBinding.novel_id == novel_id)
            )).scalars().first()
            b.enabled = False
            await db.commit()
    _run(_unbind())
    assert _run(_go()) == (None, None, None)  # 停用后无块，不注入旧 run


def test_零命中不出块不留run():
    uid, novel_id = _run(_seed(with_entries=False, bind=True))  # 绑定空库
    async def _go():
        async with async_session() as db:
            return await prepare_write_block(db, novel_id=novel_id, chapter_ref="vol-1-ch-1", user_id=uid)
    assert _run(_go()) == (None, None, None)

    async def _run_count():
        async with async_session() as db:
            return len((await db.execute(
                sel(KbMatchRun).where(KbMatchRun.novel_id == novel_id)
            )).scalars().all())
    assert _run(_run_count()) == 0  # 零命中不留 run
