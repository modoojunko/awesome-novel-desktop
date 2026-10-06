"""版本快照每章上限（MAX_VERSIONS_PER_CHAPTER = 50，chapter_versions 表）

编辑器 1.5s 防抖自动保存每次内容变更都会写一份快照，不设上限会随写作
时长线性膨胀。本测试直接打 store.save_chapter（所有写路径的快照唯一入口：
/prose 自动保存、全量 PUT、restore、AI 写作；章族入库后从 engine 委托进来）。

用法：
    cd client/backend
    python -m pytest tests/test_version_snapshot_cap.py -v
"""

import os
import threading
import time as _time
import types

import pytest
from sqlalchemy import select

from workflow import engine
from workflow.engine import MAX_VERSIONS_PER_CHAPTER, save_chapter


def _fake_clock(monkeypatch):
    """每次调用 +1s：保证 version 毫秒时间戳唯一（同毫秒撞唯一键）。

    **只换 `chapters.store` 的时钟，不动全局 `time.time`**（2026-10-06 CI 实锤）：
    全局替换会被同进程的其它线程偷走 tick——`prompt_pack` 的同步 daemon 线程
    （sync.py `_set_state(updated_at=time.time())`）在长套件后段仍可能活动，CI 上
    版本号因此漂到 +61s/+62s（本用例两连红、本地恒绿——本地该线程已停）。锚到唯一
    消费点（store 的快照时间戳）后，断言值与进程里别的时间消费者彻底解耦。
    """
    tick = [1_700_000_000.0]

    def _now():
        tick[0] += 1.0
        return tick[0]

    from chapters import store as _store

    monkeypatch.setattr(_store, "time", types.SimpleNamespace(time=_now))
    return tick


async def _seed_chapter_row(root: str):
    """章族入库：save_chapter 要求章行在场，先种 Novel/Volume/Chapter。"""
    from db import Base, async_session
    from db import engine as db_engine
    from models import Novel
    from models.volume import Volume
    from repositories import chapter_repo

    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        proj = Novel(
            user_id="snap_user", name="snap小说",
            slug=f"snap-{os.path.basename(root)}",
            root_path=root, source="manual", current_phase="write",
        )
        session.add(proj)
        await session.flush()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        await chapter_repo.upsert(
            session, proj.id, vol.id, chapter_no=1, ref="vol-1-ch-1", title="第1章"
        )
        await session.commit()


async def _versions(root: str) -> list[int]:
    from db import async_session
    from models.chapter import Chapter, ChapterVersion
    from models.project import Novel

    async with async_session() as session:
        stmt = (
            select(ChapterVersion.version)
            .join(Chapter, Chapter.id == ChapterVersion.chapter_id)
            .join(Novel, Novel.id == Chapter.project_id)
            .where(Novel.root_path == root, Chapter.ref == "vol-1-ch-1")
            .order_by(ChapterVersion.version.asc())
        )
        return [v for v in (await session.scalars(stmt)).all()]


async def _save_n(root: str, n: int):
    """初始建章 + n 次内容变更保存。"""
    await _seed_chapter_row(root)
    chapter = {"volume": 1, "chapter": 1, "title": "第1章", "prose": ""}
    for i in range(n):
        chapter = {**chapter, "prose": f"第 {i} 版正文" + "字" * 100}
        await save_chapter(root, "vol-1-ch-1", chapter)


class TestVersionSnapshotCap:
    @pytest.mark.asyncio
    async def test_cap_keeps_latest_50(self, tmp_path, monkeypatch):
        _fake_clock(monkeypatch)
        root = str(tmp_path)

        # 60 次变更 → 无上限应产生 60 份快照，上限后只剩最近 50 份
        await _save_n(root, 60)

        versions = await _versions(root)
        assert len(versions) == MAX_VERSIONS_PER_CHAPTER
        # 最旧的 10 份（第 0-9 次变更）被清掉，最新一份在场
        assert versions[0] != 1_700_000_001_000  # 第一次变更的时间戳已被删
        assert versions[-1] == 1_700_000_060_000  # 第 60 次变更（tick 起始 +60s）

    @pytest.mark.asyncio
    async def test_cap_immune_to_other_time_consumers(self, tmp_path, monkeypatch):
        """回归钉子（2026-10-06 CI 两连红）：别的线程消费全局 time.time() 不得影响版本号。

        旧写法（monkeypatch 全局 time.time）下，同进程任何别的时间消费者都会偷走
        tick——实锤者＝prompt_pack 同步 daemon 线程的 `_set_state(updated_at=...)`，
        致 CI 端版本号漂到 +61s/+62s 而本地恒绿。本用例开着「小偷线程」跑同一路径：
        旧写法必红、锚到 chapters.store 后必绿。
        """
        _fake_clock(monkeypatch)
        stop = threading.Event()

        def _thief():
            while not stop.is_set():
                _time.time()  # 模拟同步线程的 updated_at 时间戳
                _time.sleep(0.001)

        t = threading.Thread(target=_thief, daemon=True)
        t.start()
        try:
            root = str(tmp_path)
            await _save_n(root, 60)
            versions = await _versions(root)
            assert versions[-1] == 1_700_000_060_000, (
                "版本号被同进程别的时间消费者带偏——假时钟必须只锚 chapters.store")
        finally:
            stop.set()
            t.join(timeout=1)

    @pytest.mark.asyncio
    async def test_under_cap_keeps_all(self, tmp_path, monkeypatch):
        _fake_clock(monkeypatch)
        root = str(tmp_path)

        await _save_n(root, 10)
        assert len(await _versions(root)) == 10

    @pytest.mark.asyncio
    async def test_unchanged_content_no_snapshot(self, tmp_path, monkeypatch):
        _fake_clock(monkeypatch)
        root = str(tmp_path)

        await _seed_chapter_row(root)
        chapter = {"volume": 1, "chapter": 1, "title": "第1章", "prose": "同样内容"}
        await save_chapter(root, "vol-1-ch-1", chapter)
        # 建章后首写：空 → 有内容，产生 1 份快照
        assert len(await _versions(root)) == 1
        # 内容未变 → 不产生新快照
        await save_chapter(root, "vol-1-ch-1", {**chapter})
        assert len(await _versions(root)) == 1

    def test_cap_constant(self):
        # 契约：上限值稳定（前端版本列表依赖后端有界返回）
        assert MAX_VERSIONS_PER_CHAPTER == 50
        assert callable(engine.save_chapter)
