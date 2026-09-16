"""hooks 消费端真表语义回归（foreshadow-settings-v2 tasks 2.4）。

旧回归（KV 三数组结构错位 / introduced_in 短格式猜测）随 KV 通道退役一并了结：
- 注入只认 status==active（真表 novel_hooks），resolved/abandoned 永不注入；
- 「排除本章引入」按 introduced_chapter_id 与当前章 id 相等判断（章 id 精确匹配，
  替代 ref 字符串比较）；
- 展示编号 [H-####] 派生自 seq，优先级以「高/中/低」标注；
- 归档联动＝单条 UPDATE mentioned_in_chapter_id：status 不动、重复归档幂等。
"""

import asyncio
import os
import tempfile

from sqlalchemy import select

from archive.service import update_thread_state
from db import async_session
from filesystem.storage import get_storage
from models.chapter import Chapter
from models.hook import NovelHook
from models.project import Novel
from models.volume import Volume
from prompt.context import (
    active_hooks_for_chapter,
    filter_active_hooks,
    hook_view,
    render_hooks_block,
)
from settings.hooks_service import mark_hooks_mentioned


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _seed_book_with_chapters() -> tuple[str, str, list[str]]:
    """种一本书（root_path 指向临时目录）+ 一卷两章，返回 (root, novel_id, [ch1, ch2])。"""
    root = tempfile.mkdtemp(prefix="test_hooks_consumers_")
    slug = f"hkc-{os.path.basename(root)}"
    async with async_session() as session:
        session.add(Novel(
            user_id="hkc_user", name="伏笔消费书", slug=slug,
            root_path=root, source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(
            select(Novel).where(Novel.root_path == root)
        )).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        ids = []
        for no in (1, 2):
            ch = Chapter(
                project_id=proj.id, volume_id=vol.id, chapter_no=no,
                ref=f"vol-1-ch-{no}", title=f"第{no}章", status="outline",
            )
            session.add(ch)
            await session.flush()
            ids.append(ch.id)
        await session.commit()
        return root, proj.id, ids


async def _add_hook(novel_id: str, seq: int, **fields) -> str:
    async with async_session() as session:
        h = NovelHook(novel_id=novel_id, seq=seq, **fields)
        session.add(h)
        await session.commit()
        return h.id


# ── 注入过滤与渲染（prompt/context）──────────────────────────────────────


class TestActiveHookInjection:
    def test_active_hooks_injected_with_code_and_priority(self):
        async def _run():
            root, nid, _ch_ids = await _seed_book_with_chapters()
            await _add_hook(nid, 1, description="主角妹妹失踪的真相",
                            priority=1, type="mystery")
            await _add_hook(nid, 2, description="半张地图", priority=2, type="clue")
            hooks = await active_hooks_for_chapter(root, "vol-1-ch-1", nid)
            assert [h["code"] for h in hooks] == ["H-0001", "H-0002"]
            block = render_hooks_block(hooks)
            assert "## 当前悬而未决的伏笔" in block
            assert "[H-0001] 主角妹妹失踪的真相（优先级：高，类型：悬念）" in block
            assert "[H-0002] 半张地图（优先级：中，类型：线索）" in block

        _run_async(_run())

    def test_resolved_and_abandoned_never_injected(self):
        async def _run():
            root, nid, _ch_ids = await _seed_book_with_chapters()
            await _add_hook(nid, 1, description="已收束", status="resolved")
            await _add_hook(nid, 2, description="已废弃", status="abandoned")
            hooks = await active_hooks_for_chapter(root, "vol-1-ch-2", nid)
            assert hooks == []
            assert render_hooks_block(hooks) == ""

        _run_async(_run())

    def test_hook_introduced_in_current_chapter_excluded_by_id(self):
        """本章引入（introduced_chapter_id == 当前章 id）不注入；其他章引入照常。"""
        async def _run():
            root, nid, ch_ids = await _seed_book_with_chapters()
            await _add_hook(nid, 1, description="本章新埋的钩子",
                            introduced_chapter_id=ch_ids[0])
            await _add_hook(nid, 2, description="上一章引入",
                            introduced_chapter_id=ch_ids[1])
            await _add_hook(nid, 3, description="未定期（章留空）")
            hooks = await active_hooks_for_chapter(root, "vol-1-ch-1", nid)
            descs = [h["description"] for h in hooks]
            assert "本章新埋的钩子" not in descs
            assert "上一章引入" in descs
            assert "未定期（章留空）" in descs  # 未定引入章的伏笔照常注入

        _run_async(_run())

    def test_filter_caps_at_eight_and_orders_by_seq(self):
        rows = [
            type("H", (), {"seq": i, "status": "active", "description": f"伏笔{i}",
                           "introduced_chapter_id": None, "priority": 2, "type": ""})()
            for i in range(1, 13)
        ]
        kept = filter_active_hooks(rows, None)
        assert len(kept) == 8
        assert [h.seq for h in kept] == list(range(1, 9))

    def test_invalid_priority_dropped_not_crash(self):
        """非法 priority → 丢弃该标注而非静默吞错（spec prompt-crafting）。"""
        view = hook_view({"seq": 3, "description": "x", "priority": 99, "type": "bogus"})
        assert view["priority_label"] == ""
        block = render_hooks_block([view])
        assert "优先级" not in block
        assert "[H-0003] x（类型：bogus）" in block

    def test_no_novel_id_degrades_to_empty(self):
        assert _run_async(active_hooks_for_chapter("/tmp/whatever", "vol-1-ch-1", None)) == []


# ── 归档联动（archive → hooks_service.mark_hooks_mentioned）──────────────


class TestArchiveMentionedSync:
    def test_archive_marks_introduced_active_hooks(self):
        """归档第 1 章：引入于第 1 章的活跃伏笔 → mentioned 写入本章 id，status 仍 active。"""
        async def _run():
            _root, nid, ch_ids = await _seed_book_with_chapters()
            h1 = await _add_hook(nid, 1, description="第一章引入",
                                 introduced_chapter_id=ch_ids[0])
            await _add_hook(nid, 2, description="第二章引入", introduced_chapter_id=ch_ids[1])

            async with async_session() as session:
                await mark_hooks_mentioned(session, nid, ch_ids[0])
                await session.commit()

            async with async_session() as session:
                row = await session.get(NovelHook, h1)
                assert row.mentioned_chapter_id == ch_ids[0]
                assert row.status == "active"  # 状态枚举不被归档污染

        _run_async(_run())

    def test_archive_other_chapter_no_side_effect(self):
        """归档第 1 章不误伤引入于第 2 章的伏笔。"""
        async def _run():
            _root, nid, ch_ids = await _seed_book_with_chapters()
            h2 = await _add_hook(nid, 1, description="第二章引入",
                                 introduced_chapter_id=ch_ids[1])

            async with async_session() as session:
                await mark_hooks_mentioned(session, nid, ch_ids[0])
                await session.commit()

            async with async_session() as session:
                row = await session.get(NovelHook, h2)
                assert row.mentioned_chapter_id is None

        _run_async(_run())

    def test_repeated_archive_idempotent(self):
        """重复归档同一章：mentioned 值与 status 均不变。"""
        async def _run():
            _root, nid, ch_ids = await _seed_book_with_chapters()
            h1 = await _add_hook(nid, 1, description="第一章引入",
                                 introduced_chapter_id=ch_ids[0])
            for _ in range(2):
                async with async_session() as session:
                    await mark_hooks_mentioned(session, nid, ch_ids[0])
                    await session.commit()

            async with async_session() as session:
                row = await session.get(NovelHook, h1)
                assert row.mentioned_chapter_id == ch_ids[0]
                assert row.status == "active"
                assert row.resolved_chapter_id is None  # 收束记录不受归档影响

        _run_async(_run())

    def test_resolved_hook_not_marked(self):
        """归档只作用活跃伏笔；已收束条目的 mentioned 留痕不被归档改写。"""
        async def _run():
            _root, nid, ch_ids = await _seed_book_with_chapters()
            h = await _add_hook(nid, 1, description="已收束", status="resolved",
                                introduced_chapter_id=ch_ids[0])

            async with async_session() as session:
                await mark_hooks_mentioned(session, nid, ch_ids[0])
                await session.commit()

            async with async_session() as session:
                row = await session.get(NovelHook, h)
                assert row.mentioned_chapter_id is None

        _run_async(_run())


# ── 旧 KV 通道零残留（tasks 2.5）─────────────────────────────────────────


class TestKvChannelRetired:
    def test_injection_never_reads_hooks_yaml(self):
        """盘上残留 hooks.yaml（旧库文件）不再被注入消费。"""
        async def _run():
            root = tempfile.mkdtemp(prefix="test_hooks_consumers_kv_")
            await get_storage().write_yaml(
                root, "settings/hooks.yaml",
                {"active": [{"description": "KV 残留", "introduced_in": "1-1"}]},
            )
            assert await active_hooks_for_chapter(root, "vol-1-ch-2", None) == []

        _run_async(_run())

    def test_update_thread_state_no_longer_touches_hooks(self):
        """update_thread_state 只写 threads.yaml；hooks KV 读改写路径已退役。"""
        async def _run():
            root = tempfile.mkdtemp(prefix="test_hooks_consumers_thread_")
            await get_storage().write_yaml(
                root, "settings/hooks.yaml",
                {"active": [{"description": "x", "introduced_in": "1-1", "status": "pending"}]},
            )
            await update_thread_state(root, {"volume": 1, "chapter": 1, "thread": "主线"}, "摘要")
            data = await get_storage().read_yaml(root, "settings/hooks.yaml")
            assert data["active"][0]["status"] == "pending"  # 未被归档改写
            threads = await get_storage().read_yaml(root, "threads.yaml")
            assert threads["threads"]["主线"]["last_chapter"] == "vol-1-ch-1"

        _run_async(_run())
