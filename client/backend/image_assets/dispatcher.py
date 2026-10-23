"""图像生成独立 dispatcher（c-image-generation）。

与拆书 dispatcher 同形态：daemon 线程自带事件循环、条件 UPDATE 抢任务、空闲轮询。
刻意不碰 ``job_runner``——图像生成不能锁死备份/下载的全局单飞槽。
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading

from db import async_session

log = logging.getLogger(__name__)

_POLL_SECONDS = 2.0
_started = False
_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop = threading.Event()


def start_dispatcher() -> None:
    global _started, _thread
    if os.environ.get("IMAGE_DISPATCHER_OFF") == "1":
        return
    with _lock:
        if _started:
            return
        _started = True
        _thread = threading.Thread(target=_thread_main, name="image-dispatcher", daemon=True)
        _thread.start()


def stop_dispatcher() -> None:
    """测试出口：停掉常驻轮询，防止共享测试库上的 queued 任务被后台抢跑。"""
    _stop.set()


def _thread_main() -> None:
    try:
        asyncio.run(_loop())
    except Exception:  # noqa: BLE001 — 常驻线程兜底留痕
        log.exception("event=image_dispatcher_crash")


async def _loop() -> None:
    from image_assets.generation import run_job, startup_sweep

    try:
        await startup_sweep()
    except Exception:  # noqa: BLE001 — sweep 失败不挡调度
        log.exception("event=image_sweep_failed")
    while not _stop.is_set():
        job_id = None
        try:
            job_id = await _pick_next()
        except Exception:  # noqa: BLE001
            log.exception("event=image_pick_failed")
        if job_id:
            try:
                await run_job(job_id)
            except Exception:  # noqa: BLE001 — run_job 自收敛终态；防线程蒸发
                log.exception("event=image_run_crash job=%s", job_id)
                await _mark_failed(job_id)
            continue
        await asyncio.sleep(_POLL_SECONDS)


async def _pick_next() -> str | None:
    from image_assets.generation import claim_job, list_queued_ids

    for job_id in await list_queued_ids():
        if await claim_job(job_id):
            return job_id
    return None


async def _mark_failed(job_id: str) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import update

    from models.image_asset import ImageJob

    async with async_session() as db:
        await db.execute(
            update(ImageJob)
            .where(ImageJob.id == job_id, ImageJob.status == "running")
            .values(
                status="failed",
                error_kind="interrupted",
                error_message="生成任务异常中断，可重试",
                finished_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        await db.commit()
