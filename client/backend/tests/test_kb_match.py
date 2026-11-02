"""写法块选择器测试（c-kb-write-block 批A）：信号归类/短名单/配额预算/零命中/确定性。"""

import asyncio
import json
import uuid

import pytest
from sqlalchemy import select as sel

from db import async_session
from kb.match import select_block
from models.chapter import Chapter, ChapterCharacter
from models.kb import KbEntry, KbPref
from models.project import Novel
from models.user import User
from models.volume import Volume
from write.write_block import extract_signals


def _run(coro):
    return asyncio.run(coro)


async def _seed_library(uid: str, entries: list[dict]) -> None:
    """直接播种条目＋物化标签（走 kb create_entry 闸门口径）。"""
    from kb.service import create_entry

    async with async_session() as db:
        for e in entries:
            entry, _gate, error = await create_entry(
                db,
                user_id=uid,
                genre=e.get("genre", ""),
                concept=e["concept"],
                title=e.get("title", ""),
                payload=e["payload"],
                instruction=e.get("instruction", ""),
                when_json=e.get("when"),
                src_kind="manual",
            )
            assert entry is not None, f"seed failed: {error}"


async def _seed_book(uid: str, *, summary="", mood="", stage="", items=None, chars=None) -> tuple[str, str]:
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="选块"))
        novel = Novel(
            user_id=uid, name="选块书", slug=f"m{uuid.uuid4().hex[:8]}",
            root_path=f"./data/m{uuid.uuid4().hex[:8]}", source="manual", current_phase="write",
        )
        db.add(novel)
        await db.flush()
        vol = Volume(project_id=novel.id, volume_no=1, title="第一卷")
        db.add(vol)
        await db.flush()
        ch = Chapter(
            project_id=novel.id, volume_id=vol.id, chapter_no=1, ref="vol-1-ch-1",
            title="第一章", summary=summary, primary_mood=mood or None,
            plot_stage=stage or None,
            plot_items=json.dumps(items or [], ensure_ascii=False),
        )
        db.add(ch)
        await db.flush()
        for i, name in enumerate(chars or []):
            db.add(ChapterCharacter(chapter_id=ch.id, sort_order=i, character_name=name))
        await db.commit()
        return novel.id, "vol-1-ch-1"


@pytest.fixture
def lib_uid():
    return f"m{uuid.uuid4().hex[:8]}"


def test_信号抽取_命中与不硬猜(lib_uid):
    uid = lib_uid

    async def _go():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            novel = Novel(
                user_id=uid, name="信", slug=f"s{uuid.uuid4().hex[:8]}",
                root_path="./data/x", source="manual", current_phase="write",
            )
            db.add(novel)
            await db.flush()
            vol = Volume(project_id=novel.id, volume_no=1, title="卷")
            db.add(vol)
            await db.flush()
            db.add(Chapter(
                project_id=novel.id, volume_id=vol.id, chapter_no=3, ref="c3",
                title="决战", summary="与老祖决战，两败俱伤", primary_mood="紧张压抑",
                plot_stage="卷末收束", plot_items=json.dumps(["夜里偷袭敌营"], ensure_ascii=False),
            ))
            await db.flush()
            db.add(ChapterCharacter(chapter_id=(await db.execute(
                sel(Chapter.id).where(Chapter.ref == "c3"))).scalar_one(), sort_order=0, character_name="沈青崖"))
            db.add(Chapter(
                project_id=novel.id, volume_id=vol.id, chapter_no=4, ref="c4",
                title="闲章", summary="整理行囊，闲话家常",
            ))
            await db.commit()
            return novel.id

    nid = _run(_go())

    async def _signals(ref):
        async with async_session() as db:
            return await extract_signals(db, novel_id=nid, chapter_ref=ref, genre="玄幻")

    s1 = _run(_signals("c3"))
    assert s1.scene == "打斗"          # 概要「决战」→ 打斗（包含式别名）
    assert s1.emotion == "冷"          # primary_mood「紧张压抑」直接归类
    assert s1.chapter_pos == "卷末"    # plot_stage 映射
    assert s1.characters == ["沈青崖"]

    s2 = _run(_signals("c4"))
    assert s2.scene == "文戏"          # 概要「闲话家常」→ 文戏（命中即归类，不硬猜）
    assert s2.emotion == ""            # 不硬猜
    assert s2.chapter_pos == ""        # plot_stage 空 → 空

    async def _clean(uid=uid):
        async with async_session() as db:
            from sqlalchemy import delete as _del

            for m in (ChapterCharacter, Chapter, Volume, Novel, User):
                await db.execute(_del(m).where(True) if m is User else _del(m))
            await db.commit()
    # 不清了——共享库按 uid 天然隔离，避免误删他测试数据


def test_配额与排除_role槽(lib_uid):
    uid = lib_uid
    novel_id, ref = _run(_seed_book(uid, summary="两军对垒激烈交锋", mood="热血", stage="高潮爆发", chars=["沈青崖"]))

    entries = []
    for i in range(8):  # 8 条手法：全章适用 → 配额 6
        entries.append({
            "concept": "手法", "genre": "玄幻", "title": f"手法{i}",
            "payload": {"instruction": f"打斗第{i}条：收招要快。", "scene": "打斗"},
            "instruction": f"打斗第{i}条：收招要快。",
            "when": None,
        })
    # role 槽场景条目：书级恒定，不得进块
    entries.append({
        "concept": "文风", "genre": "玄幻", "title": "叙述身份",
        "payload": {"slot": "role", "role": "冷峻旁白"},
        "instruction": "冷峻旁白的声音", "when": {"scene": "打斗"},
    })
    # tone 场景条目：进块
    entries.append({
        "concept": "文风", "genre": "玄幻", "title": "打斗基调",
        "payload": {"slot": "tone", "text": "打斗要短促"},
        "instruction": "打斗要短促", "when": {"scene": "打斗"},
    })
    _run(_seed_library(uid, entries))

    async def _select():
        async with async_session() as db:
            signals = await extract_signals(db, novel_id=novel_id, chapter_ref=ref, genre="玄幻")
            return await select_block(db, user_id=uid, signals=signals, genre="玄幻")
    selr = _run(_select())
    assert selr is not None
    tech = [i for i in selr.items if i.entry.concept == "手法"]
    style = [i for i in selr.items if i.entry.concept != "手法"]
    assert len(tech) == 6                      # 手法配额
    assert len(style) == 1                     # role 被排除，tone 进
    assert style[0].entry.title == "打斗基调"
    assert not any("旁白" in i.entry.instruction for i in selr.items)


def test_条件不命中不选_无场面线索只出兜底(lib_uid):
    uid = lib_uid
    novel_id, ref = _run(_seed_book(uid, summary="整理行囊，闲话家常"))  # 无场面信号

    entries = [
        # 场面限定手法（打斗）：本章无场面信号 → 条件不命中 → 不出
        {"concept": "手法", "genre": "玄幻", "title": "打斗专用",
         "payload": {"instruction": "交手时先让三招。", "scene": "打斗"},
         "instruction": "交手时先让三招。", "when": {"scene": "打斗"}},
        # 无条件手法：全章适用兜底 → 出
        {"concept": "手法", "genre": "玄幻", "title": "通用手法",
         "payload": {"instruction": "对话不要每次都把话说完。"},
         "instruction": "对话不要每次都把话说完。"},
    ]
    # 无条件手法 payload 需带 scene？手法 payload scene 必填（TechniquePayload scene 必填）
    entries[1]["payload"] = {"instruction": "对话不要每次都把话说完。", "scene": "日常"}
    _run(_seed_library(uid, entries))

    async def _select():
        async with async_session() as db:
            signals = await extract_signals(db, novel_id=novel_id, chapter_ref=ref, genre="玄幻")
            return await select_block(db, user_id=uid, signals=signals, genre="玄幻")
    selr = _run(_select())
    assert selr is not None, "selection None; entries seeded above"
    titles = {i.entry.title for i in selr.items}
    assert "打斗专用" not in titles     # 条件不命中不出
    assert "通用手法" in titles         # 全章适用手法兜底出
    # 无 when 的文笔 rule＝基线快照成员（scope=base），不进写法块


def test_零命中返回None_空库(lib_uid):
    uid = lib_uid
    novel_id, ref = _run(_seed_book(uid, summary="两军交锋"))
    async def _select():
        async with async_session() as db:
            signals = await extract_signals(db, novel_id=novel_id, chapter_ref=ref, genre="玄幻")
            return await select_block(db, user_id=uid, signals=signals, genre="玄幻")
    assert _run(_select()) is None  # 空库


def test_确定性_同输入同选集(lib_uid):
    uid = lib_uid
    novel_id, ref = _run(_seed_book(uid, summary="正面交锋", mood="燃", stage="高潮爆发"))
    entries = [
        {"concept": "手法", "genre": "玄幻", "title": f"招式{i}",
         "payload": {"instruction": f"第{i}式：见招拆招。", "scene": "打斗"},
         "instruction": f"第{i}式：见招拆招。"}
        for i in range(5)
    ]
    _run(_seed_library(uid, entries))

    async def _select():
        async with async_session() as db:
            signals = await extract_signals(db, novel_id=novel_id, chapter_ref=ref, genre="玄幻")
            selr = await select_block(db, user_id=uid, signals=signals, genre="玄幻")
            return [(i.entry.id, round(i.score, 6)) for i in selr.items] if selr else None
    a = _run(_select())
    b = _run(_select())
    assert a is not None and a == b


def test_有用率回写影响排序(lib_uid):
    uid = lib_uid
    novel_id, ref = _run(_seed_book(uid, summary="正面交锋", mood="燃"))
    entries = [
        {"concept": "手法", "genre": "玄幻", "title": f"招式{i}",
         "payload": {"instruction": f"第{i}式：借力打力。", "scene": "打斗"},
         "instruction": f"第{i}式：借力打力。"}
        for i in range(4)
    ]
    _run(_seed_library(uid, entries))

    async def _ids_and_mark(entry_pos: int):
        async with async_session() as db:
            rows = (await db.execute(sel(KbEntry).where(KbEntry.user_id == uid).order_by(KbEntry.id))).scalars().all()
            target = rows[entry_pos]
            db.add(KbPref(user_id=uid, entry_id=target.id, weight=0.2, drop_count=5, adopt_count=1))
            await db.commit()
            return [r.id for r in rows]

    before = _run(_ids_and_mark(0))  # 标记第一条「没用」×5
    async def _select_order():
        async with async_session() as db:
            signals = await extract_signals(db, novel_id=novel_id, chapter_ref=ref, genre="玄幻")
            selr = await select_block(db, user_id=uid, signals=signals, genre="玄幻")
            return [i.entry.id for i in selr.items]
    after = _run(_select_order())
    assert before[0] not in after[:2]  # 被标没用后跌出前列


def test_账号路径跨题材不入选(lib_uid):
    """账号级存量路径（无书副本、走绑定的老书）：题材过滤必须仍在——
    其他题材的全章适用条目录不得混进本书写法块（P1 回归钉）。"""
    uid = lib_uid
    novel_id, ref = _run(_seed_book(uid, summary="正面交锋", mood="燃"))
    entries = [
        {"concept": "手法", "genre": "玄幻", "title": "玄幻全章手法",
         "payload": {"instruction": "玄幻打法：先让三招。", "scene": "打斗"},
         "instruction": "玄幻打法：先让三招。"},
        {"concept": "手法", "genre": "悬疑", "title": "悬疑全章手法",
         "payload": {"instruction": "悬疑打法：先抛钩子。", "scene": "打斗"},
         "instruction": "悬疑打法：先抛钩子。"},
        {"concept": "手法", "genre": "", "title": "通用全章手法",
         "payload": {"instruction": "通用打法：对话别说完。", "scene": "打斗"},
         "instruction": "通用打法：对话别说完。"},
    ]
    _run(_seed_library(uid, entries))

    async def _titles():
        async with async_session() as db:
            signals = await extract_signals(db, novel_id=novel_id, chapter_ref=ref, genre="玄幻")
            selr = await select_block(db, user_id=uid, signals=signals, genre="玄幻")
            return [i.entry.title for i in selr.items] if selr else []

    titles = _run(_titles())
    assert "玄幻全章手法" in titles and "通用全章手法" in titles
    assert "悬疑全章手法" not in titles  # 跨题材不得混入
