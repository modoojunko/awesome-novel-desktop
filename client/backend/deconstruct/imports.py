"""建书阶段（c-deconstruct-import-async）——整段后台执行、单飞、可取消、可重试、可收敛。

状态机（`DeconstructJob.status`）：`completed` → `importing` → `imported` / `import_failed`。

载荷（`dims_json.import`；管线 `_state_json` 保留未知顶键，建书发生在终态之后不会再被覆盖）::

    {run_id, items, step, started_at, finished_at, draft_book_id,
     warnings, error: {message, kind, retryable}, attempts: [...]}

纪律（评审整改的落点，改动前先读 design.md D1/D3/D4/D5）：

- **status 是唯一生命周期事实源**；`run_id` 是「这一次建书」的身份。取消＝把 status 写回
  `completed`；执行体在阶段边界比对 status+run_id，不符即清理自己的 draft 后退出——绝不写
  终态（否则会把用户刚点的取消吞掉，也会误伤重建的新一轮）。
- **单飞**：DB 侧靠受理时的条件抢占（`completed|import_failed → importing`）；进程内再用
  一个按事件循环懒创建的 `asyncio.Lock` 排队（测试/多 loop 不会串）。
- **半成品清理**：`draft_book_id` 在受理时预分配并随抢占同事务落库，因此任何时刻被杀，
  `startup_sweep` 都有指针可清；清理＝软删（`Novel.status='deleted'`），与既有删书同口径。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import update

from db import async_session
from models.deconstruct import DeconstructJob

log = logging.getLogger(__name__)

# 执行体注册表（防重复调度 + 关停时能取消；Python 只弱引用 task，必须自持）
_inflight: dict[str, asyncio.Task] = {}
_stop_events: dict[str, asyncio.Event] = {}
_lock: asyncio.Lock | None = None
_lock_loop: object | None = None

IMPORT_STEPS = ("waiting", "refine", "writing", "done")
RETRYABLE_KINDS = frozenset({"interrupted", "stalled", "storage_busy", "error"})


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _parse(dims_json: str | None) -> dict:
    try:
        raw = json.loads(dims_json or "{}")
    except ValueError:
        return {}
    return raw if isinstance(raw, dict) else {}


def read_state(task: DeconstructJob | None) -> dict:
    """任务的建书载荷（无则空 dict）。"""
    if task is None:
        return {}
    imp = _parse(task.dims_json).get("import")
    return imp if isinstance(imp, dict) else {}


def normalize_items(raw: object) -> list[str]:
    """勾选归一：白名单 + 去重保序。

    空/非法返回 `[]`（＝请求未带勾选）——此时执行体按旧口径回落任务勾选维度，
    与前端始终显式带 8 项的行为互不干扰。
    """
    from deconstruct.apply import IMPORT_ITEM_KEYS

    picked = {str(x) for x in raw} if isinstance(raw, list) else set()
    return [k for k in IMPORT_ITEM_KEYS if k in picked]


def view(state: dict) -> dict:
    """下发视图：不含内部自由字段之外的东西，错误只给可读面。"""
    err = state.get("error") if isinstance(state.get("error"), dict) else {}
    return {
        "run_id": str(state.get("run_id") or ""),
        "items": list(state.get("items") or []),
        "step": str(state.get("step") or ""),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "warnings": [str(w) for w in (state.get("warnings") or [])][:50],
        "error": {
            "message": str(err.get("message") or ""),
            "kind": str(err.get("kind") or ""),
            "retryable": bool(err.get("retryable", True)),
        },
        "attempts": list(state.get("attempts") or [])[-5:],
    }


async def state_of(task_id: str) -> dict:
    """独立 session 读载荷（请求 session 可能持有旧实例；claim 后必须用这个）。"""
    return read_state(await _load(task_id))


async def _load(task_id: str) -> DeconstructJob | None:
    async with async_session() as session:
        return await session.get(DeconstructJob, task_id)


async def _patch(task_id: str, patch: dict, *, run_id: str | None = None) -> bool:
    """改写 `dims_json.import`（保留其它顶键）。

    `run_id` 非空时做代际校验：载荷里的 run_id 变了就整体丢弃这次写（返回 False）——
    这是「取消后立刻重建」的反例序列（design D5）的落点。
    """
    async with async_session() as session:
        row = await session.get(DeconstructJob, task_id)
        if row is None:
            return False
        state = _parse(row.dims_json)
        imp = state.get("import") if isinstance(state.get("import"), dict) else {}
        if run_id is not None and str(imp.get("run_id") or "") != run_id:
            return False
        imp.update(patch)
        state["import"] = imp
        row.dims_json = json.dumps(state, ensure_ascii=False)
        await session.commit()
        return True


async def claim(task_id: str, items: list[str], seed_warnings: list[str] | None = None) -> str | None:
    """受理：`completed|import_failed → importing` 条件抢占，同时落 run_id/items/draft_book_id。

    返回本次 run_id；抢占失败（状态不符）返回 None。draft_book_id 在这里就生成并落库——
    预分配 id 是为了「建书行已创建、还没回填 id」这段崩溃窗口里 sweep 仍有指针可清
    （design D4：不要改成建完再回填）。
    """
    run_id = uuid.uuid4().hex
    draft = str(uuid.uuid4())
    now = _now().isoformat()
    async with async_session() as session:
        res = await session.execute(
            update(DeconstructJob)
            .where(
                DeconstructJob.id == task_id,
                DeconstructJob.status.in_(("completed", "import_failed")),
            )
            .values(status="importing")
        )
        if res.rowcount == 0:
            await session.rollback()
            return None
        row = await session.get(DeconstructJob, task_id)
        state = _parse(row.dims_json)
        prev = state.get("import") if isinstance(state.get("import"), dict) else {}
        attempts = list(prev.get("attempts") or [])[-19:]
        state["import"] = {
            "run_id": run_id,
            "items": list(items),
            "step": "waiting",
            "started_at": now,
            "finished_at": None,
            "draft_book_id": draft,
            "warnings": list(seed_warnings or []),
            "attempts": attempts,
        }
        row.dims_json = json.dumps(state, ensure_ascii=False)
        row.book_id = None  # 幂等键只在写入全部成功后落（design D4）
        await session.commit()
    return run_id


async def cancel(task_id: str) -> bool:
    """取消：`importing → completed`（状态即取消载体）+ 掐断在途调用 + 清理半成品。"""
    async with async_session() as session:
        res = await session.execute(
            update(DeconstructJob)
            .where(DeconstructJob.id == task_id, DeconstructJob.status == "importing")
            .values(status="completed")
        )
        if res.rowcount == 0:
            await session.rollback()
            return False
        await session.commit()
    ev = _stop_events.get(task_id)
    if ev is not None:
        ev.set()
    task = _inflight.get(task_id)
    if task is not None and not task.done():
        task.cancel()  # 加速：执行体自己在阶段边界/竞速里收场，状态由本函数写定
    return True


async def soft_delete_book(book_id: str | None) -> None:
    """软删半成品（与既有删书同口径，不碰子表；设计里已登记这笔债）。"""
    if not book_id:
        return
    from models.project import Novel

    async with async_session() as session:
        row = await session.get(Novel, book_id)
        if row is not None and row.status != "deleted":
            row.status = "deleted"
            await session.commit()


async def _cancelled(task_id: str, run_id: str) -> bool:
    async with async_session() as session:
        row = await session.get(DeconstructJob, task_id)
        if row is None or row.status != "importing":
            return True
        return str(read_state(row).get("run_id") or "") != run_id


def _lock_for_loop() -> asyncio.Lock:
    """按事件循环懒创建单飞锁（测试的多 loop / TestClient 不会串死锁）。"""
    global _lock, _lock_loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # 无运行循环（不应发生，兜底给临时锁）
        return asyncio.Lock()
    if _lock is None or _lock_loop is not loop:
        _lock = asyncio.Lock()
        _lock_loop = loop
    return _lock


def start(task_id: str) -> None:
    """受理后立即起执行体（不进拆书 FIFO：建书 20 余秒，排在 30 分钟拆书之后不可接受）。"""
    if os.environ.get("IMPORT_RUNNER_OFF") == "1":
        # 测试开关（照 DECONSTRUCT_DISPATCHER_OFF 口径）：执行体由用例显式驱动，
        # 后台 task 不得抢跑，否则同一任务会被跑两遍（会出现两本书）。
        return
    running = _inflight.get(task_id)
    if running is not None and not running.done():
        return
    task = asyncio.create_task(run(task_id), name=f"deconstruct-import:{task_id}")
    _inflight[task_id] = task
    task.add_done_callback(lambda t: _on_done(task_id, t))


def _on_done(task_id: str, task: asyncio.Task) -> None:
    _inflight.pop(task_id, None)
    _stop_events.pop(task_id, None)
    if task.cancelled():
        log.info("event=deconstruct_import_cancelled task=%s", task_id)
        return
    err = task.exception()
    if err is not None:  # 逃逸异常不写终态就白跑：至少落日志（状态由 run 内部兜底）
        log.exception("event=deconstruct_import_crash task=%s", task_id, exc_info=err)


def _classify(exc: BaseException) -> dict:
    """失败分诊：可重试 vs 不可重试（design D1/D6）。"""
    from sqlalchemy.exc import OperationalError

    text = str(exc)
    if isinstance(exc, OperationalError):
        low = text.lower()
        if "locked" in low or "disk i/o" in low or "database is locked" in low:
            return {"message": "写入设定时存储忙（数据库被占用）", "kind": "storage_busy", "retryable": True}
    if isinstance(exc, TimeoutError):
        return {"message": "建书超时未完成", "kind": "stalled", "retryable": True}
    if "书架已满" in text or "上限" in text:
        return {"message": text, "kind": "quota", "retryable": False}
    return {"message": text or "建书失败", "kind": "error", "retryable": True}


async def _fail(task_id: str, run_id: str, draft: str | None, exc: BaseException) -> None:
    """失败收尾：**先**写终态再清理（顺序反了会卡在 importing，design D4）。"""
    err = _classify(exc)
    patched = await _patch(
        task_id,
        {"step": "", "error": err, "finished_at": _now().isoformat()},
        run_id=run_id,
    )
    if not patched:
        return  # 已被取消/被新一轮抢占：连终态都不该写
    async with async_session() as session:
        res = await session.execute(
            update(DeconstructJob)
            .where(DeconstructJob.id == task_id, DeconstructJob.status == "importing")
            .values(status="import_failed", book_id=None)
        )
        await session.commit()
        if res.rowcount == 0:
            return
    await soft_delete_book(draft)
    log.warning("event=deconstruct_import_failed task=%s kind=%s", task_id, err["kind"])


async def _succeed(task_id: str, run_id: str, draft: str | None, result: dict, warnings: list[str]) -> None:
    """成功收尾：一次写入 book_id + status=imported + 载荷；被取消则清理半成品。"""
    async with async_session() as session:
        row = await session.get(DeconstructJob, task_id)
        state = _parse(row.dims_json) if row is not None else {}
        imp = state.get("import") if isinstance(state.get("import"), dict) else {}
        if row is None or row.status != "importing" or str(imp.get("run_id") or "") != run_id:
            # 收尾前发现已取消/被新一轮接管：本次的半成品必须清掉（不写终态）
            await session.rollback()
            await soft_delete_book(draft)
            return
        row.book_id = str(result.get("book_id") or "")
        row.status = "imported"
        imp.pop("error", None)
        imp["step"] = "done"
        imp["finished_at"] = _now().isoformat()
        imp["warnings"] = [*(imp.get("warnings") or []), *warnings]
        attempts = list(imp.get("attempts") or [])
        attempts.append({"at": imp["finished_at"], "result": "ok"})
        imp["attempts"] = attempts[-20:]
        state["import"] = imp
        row.dims_json = json.dumps(state, ensure_ascii=False)
        await session.commit()


async def run(task_id: str) -> None:
    """执行体：整段建书（精炼 → 写入 → 收尾），全程可取消、异常必落终态。"""
    from deconstruct import apply

    st = await _load(task_id)
    if st is None:
        return
    state = read_state(st)
    run_id = str(state.get("run_id") or "")
    items = list(state.get("items") or []) or None
    draft = str(state.get("draft_book_id") or "") or None
    if not run_id or st.status != "importing":
        return

    stop_event = asyncio.Event()
    _stop_events[task_id] = stop_event
    lock = _lock_for_loop()
    if lock.locked():
        await _patch(task_id, {"step": "waiting"}, run_id=run_id)

    async def _on_step(step: str) -> None:
        await _patch(task_id, {"step": step}, run_id=run_id)

    async def _is_cancelled() -> bool:
        return await _cancelled(task_id, run_id)

    try:
        async with lock:
            if await _is_cancelled():
                await soft_delete_book(draft)
                return
            async with async_session() as db:
                task = await db.get(DeconstructJob, task_id)
                if task is None or task.status != "importing":
                    await soft_delete_book(draft)
                    return
                # 写入前二次校验额度：受理时查过一次，但精炼这段时间里用户可能又建了一本
                # （评审 P1-7）。必须在建书行之前拦，否则会多出一本超额的可见书。
                from auth_local.deps import project_quota_reject

                reject = await project_quota_reject(db, task.user_id)
                if reject:
                    raise RuntimeError(reject)
                result, warnings = await apply.import_book(
                    db,
                    task,
                    task.user_id,
                    items,
                    book_id=draft,
                    on_step=_on_step,
                    is_cancelled=_is_cancelled,
                    stop_event=stop_event,
                )
        await _succeed(task_id, run_id, draft, result, warnings)
    except apply.ImportCancelled:
        await soft_delete_book(draft)
    except asyncio.CancelledError:
        # 桌面壳关停/用户取消：用独立短事务把终态写掉，不留永久的「建书中」
        with contextlib.suppress(BaseException):
            await asyncio.shield(_fail(task_id, run_id, draft, TimeoutError("建书被中断")))
        raise
    except BaseException as exc:  # noqa: BLE001 — 后台执行体：任何异常都必须落终态
        with contextlib.suppress(BaseException):
            await asyncio.shield(_fail(task_id, run_id, draft, exc))
    finally:
        _stop_events.pop(task_id, None)


async def sweep() -> None:
    """启动收敛：残留的 importing → import_failed(interrupted)，并清理半成品。

    与 `pipeline.startup_sweep` 同批调用；对遗留 draft 的重试清理是幂等的。
    """
    from sqlalchemy import select

    async with async_session() as session:
        rows = (
            await session.scalars(
                select(DeconstructJob).where(DeconstructJob.status == "importing")
            )
        ).all()
        drafts: list[str] = []
        for row in rows:
            imp = read_state(row)
            draft = str(imp.get("draft_book_id") or "")
            if draft:
                drafts.append(draft)
            imp["error"] = {
                "message": "应用退出导致建书中断，可重试",
                "kind": "interrupted",
                "retryable": True,
            }
            imp["step"] = ""
            imp["finished_at"] = _now().isoformat()
            state = _parse(row.dims_json)
            state["import"] = imp
            row.dims_json = json.dumps(state, ensure_ascii=False)
            row.status = "import_failed"
            row.book_id = None
        if rows:
            await session.commit()
    for draft in drafts:
        await soft_delete_book(draft)
    if rows:
        log.info("event=deconstruct_import_swept count=%s", len(rows))


async def stale_inflight() -> list[str]:
    """视图侧陈旧兜底用：仍在 importing 的任务 id（供上层判 started_at 是否过界）。"""
    from sqlalchemy import select

    async with async_session() as session:
        return list(
            (
                await session.scalars(
                    select(DeconstructJob.id).where(DeconstructJob.status == "importing")
                )
            ).all()
        )
