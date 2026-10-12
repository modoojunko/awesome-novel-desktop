"""拆书串行 dispatcher（c-deconstruct-book 1.4）——常驻 daemon 线程自带事件循环。

- 进程内单例守卫（打包态单 uvicorn worker 仍防重复启动）；
- 启动 sweep：running 且无线程→failed(interrupted)；queued 缺源→need_reupload；
- FIFO 取 queued 最小 (queue_seq, created_at) 逐个串行执行；空闲 2s 轮询；
- pytest 不触发 lifespan：sweep/取任务逻辑拆为可直调函数（pipeline.startup_sweep / list_queued_ids）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading

from db import async_session

log = logging.getLogger(__name__)

_POLL_SECONDS = 2.0
_started = False
_lock = threading.Lock()
_thread: threading.Thread | None = None


def start_dispatcher() -> None:
    global _started, _thread
    if os.environ.get("DECONSTRUCT_DISPATCHER_OFF") == "1":
        return  # 测试开关：TestClient lifespan 不起真轮询线程（评审 P2-12）
    with _lock:
        if _started:
            return
        _started = True
        _thread = threading.Thread(target=_thread_main, name="deconstruct-dispatcher", daemon=True)
        _thread.start()


def _thread_main() -> None:
    try:
        asyncio.run(_loop())
    except Exception:  # noqa: BLE001 — 常驻线程兜底留痕（重启 sweep 会收敛状态）
        log.exception("event=deconstruct_dispatcher_crash")


async def _loop() -> None:
    from deconstruct.pipeline import run_task, startup_sweep

    try:
        await startup_sweep()
    except Exception:  # noqa: BLE001 — sweep 失败不阻调度
        log.exception("event=deconstruct_sweep_failed")
    while True:
        try:
            task_id = await _pick_next()
        except Exception:  # noqa: BLE001 — DB 抖动等下轮重试
            log.exception("event=deconstruct_pick_failed")
            task_id = None
        if task_id:
            try:
                await run_task(task_id)
            except Exception:  # noqa: BLE001 — run_task 自兜底终态；此处防线程蒸发
                log.exception("event=deconstruct_run_crash task=%s", task_id)
                await _mark_failed(task_id)
            continue
        await asyncio.sleep(_POLL_SECONDS)


async def _pick_next() -> str | None:
    from deconstruct.pipeline import list_queued_ids

    ids = await list_queued_ids()
    for task_id in ids:
        # 源文件缺失（如 staging 被清）→ 置需重传，跳过（sweep 的补充防线）
        if not await _source_exists(task_id):
            await _mark_need_reupload(task_id)
            continue
        if await _claim(task_id):
            return task_id
    return None


async def _source_exists(task_id: str) -> bool:
    async with async_session() as session:
        from models.deconstruct import DeconstructJob

        task = await session.get(DeconstructJob, task_id)
        return bool(task and task.source_path and os.path.exists(task.source_path))


async def _claim(task_id: str) -> bool:
    """queued→running 单句 UPDATE 抢占（WHERE status='queued' 防并发双跑）。"""
    from sqlalchemy import update

    from models.deconstruct import DeconstructJob

    async with async_session() as session:
        result = await session.execute(
            update(DeconstructJob)
            .where(DeconstructJob.id == task_id, DeconstructJob.status == "queued")
            .values(status="running")
        )
        await session.commit()
        return result.rowcount > 0


async def _mark_need_reupload(task_id: str) -> None:
    from sqlalchemy import update

    from models.deconstruct import DeconstructJob

    async with async_session() as session:
        await session.execute(
            update(DeconstructJob)
            .where(DeconstructJob.id == task_id, DeconstructJob.status == "queued")
            .values(status="need_reupload")
        )
        await session.commit()


async def _mark_failed(task_id: str) -> None:
    from datetime import UTC, datetime

    from models.deconstruct import DeconstructJob

    async with async_session() as session:
        task = await session.get(DeconstructJob, task_id)
        if task is None:
            return
        task.status = "failed"
        task.error_json = json.dumps({"message": "任务执行异常中断，可续拆", "kind": "interrupted"}, ensure_ascii=False)
        task.finished_at = datetime.now(UTC).replace(tzinfo=None)
        await session.commit()
