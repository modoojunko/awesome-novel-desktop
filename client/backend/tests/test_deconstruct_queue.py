"""拆书队列与启动 sweep（c-deconstruct-book 1.4）——直调 dispatcher 函数（pytest 不触发 lifespan）。

- sweep：running 无线程→failed(interrupted)；queued 缺源→need_reupload；有源 queued 保留；
- _pick_next：FIFO 按 (queue_seq, created_at) 抢占（queued→running 单句 UPDATE）；
- cancel 走 status 列（service 层置列，worker 段边界重读）。
"""

import asyncio
import os
import tempfile

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix="_deq.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_deq_")

from db import Base, async_session, engine  # noqa: E402
from models.deconstruct import DeconstructJob  # noqa: E402

_UID = "deq-user"


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module", autouse=True)
def _db():
    _run(_ensure_tables())
    # 全量跑时与 api 测试共享同一临时库（env 按收集序被覆盖）：清场保 FIFO 断言确定性
    from sqlalchemy import select

    async def _clean():
        async with async_session() as s:
            for t in (await s.scalars(select(DeconstructJob))).all():
                await s.delete(t)
            await s.commit()

    _run(_clean())
    yield


async def _ensure_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _mk_task(task_id: str, status: str, *, with_source: bool = True, seq: int | None = None) -> None:
    async def _go():
        async with async_session() as s:
            seq_val = seq
            if seq_val is None:
                from deconstruct.service import next_queue_seq

                seq_val = await next_queue_seq(s)
            task = DeconstructJob(
                id=task_id,
                user_id=_UID,
                status=status,
                queue_seq=seq_val,
                book_name=f"书{task_id}",
                source_path=(
                    os.path.join(tempfile.gettempdir(), f"deq-src-{task_id}.txt")
                    if with_source
                    else ""
                ),
            )
            s.add(task)
            await s.commit()

    _run(_go())
    if with_source:
        with open(os.path.join(tempfile.gettempdir(), f"deq-src-{task_id}.txt"), "w") as f:
            f.write("第1章 试\n正文。\n")


def _del_task(task_id: str) -> None:
    async def _go():
        async with async_session() as s:
            t = await s.get(DeconstructJob, task_id)
            if t:
                await s.delete(t)
                await s.commit()

    _run(_go())


def test_sweep_marks_running_interrupted():
    _mk_task("sw-run", "running")
    from deconstruct.pipeline import startup_sweep

    _run(startup_sweep())

    async def _read():
        async with async_session() as s:
            t = await s.get(DeconstructJob, "sw-run")
            return t.status

    assert _run(_read()) == "failed"
    _del_task("sw-run")


def test_sweep_marks_queued_missing_source_need_reupload():
    _mk_task("sw-nosrc", "queued", with_source=False, seq=90)
    from deconstruct.pipeline import startup_sweep

    _run(startup_sweep())

    async def _read():
        async with async_session() as s:
            t = await s.get(DeconstructJob, "sw-nosrc")
            return t.status

    assert _run(_read()) == "need_reupload"
    _del_task("sw-nosrc")


def test_pick_next_fifo_and_claim():
    _mk_task("fifo-b", "queued", seq=2)
    _mk_task("fifo-a", "queued", seq=1)
    _mk_task("fifo-c", "queued", seq=3)
    from deconstruct.dispatcher import _pick_next

    first = _run(_pick_next())
    assert first == "fifo-a"

    async def _read():
        async with async_session() as s:
            a = await s.get(DeconstructJob, "fifo-a")
            b = await s.get(DeconstructJob, "fifo-b")
            return a.status, b.status

    a_status, b_status = _run(_read())
    assert a_status == "running"  # 被抢占
    assert b_status == "queued"  # 其余保持排队
    for tid in ("fifo-a", "fifo-b", "fifo-c"):
        _del_task(tid)


def test_cancel_via_status_column():
    _mk_task("cx-1", "running")
    from deconstruct.service import get_task

    async def _cancel():
        async with async_session() as s:
            t = await get_task(s, "cx-1", _UID)
            t.status = "cancelled"
            await s.commit()
            return t.status

    assert _run(_cancel()) == "cancelled"
    _del_task("cx-1")
