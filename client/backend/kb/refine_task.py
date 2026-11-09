"""知识提炼任务（原型定稿 2026-11-08）：提炼＋关系梳理编排进任务清单。

原型拍板：单按钮「知识提炼」→ 确认弹窗 → 任务进任务清单后台执行（与拆书任务
同清单、类型章「知识提炼」）→ 任务详情页看执行过程时间线与结果账。

编排（一个任务干两件事，顺序单向）：
1. 归类进树 —— kb.refine.run_refine（其他 → 树／长新节点）
2. 梳理关系 —— kb.organize.run_organize（细化/矛盾/依赖）

存储＝raw DDL 建管＋ORM 镜像（models.kb.KbRefineTask，KbSummarizeRun 先例）：
镜像的唯一动机＝迁移引擎计划面认得这张表（build_plan 只认 Base.metadata，
纯 raw-DDL 表会被误标 table_retired 整段跳过）；schema 指纹代价已知
（mac-local-build 判例：同版本串试验期动 metadata 必踩 mismatch，装机按配方回填）。
状态机 queued→running→completed/failed。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from sqlalchemy import text as _t
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS kb_refine_tasks (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    genre TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    error TEXT NOT NULL DEFAULT '',
    current_step TEXT NOT NULL DEFAULT '',
    timeline_json TEXT NOT NULL DEFAULT '[]',
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_kb_refine_tasks_user ON kb_refine_tasks (user_id, created_at);
"""


async def ensure_ddl(db: AsyncSession) -> None:
    for stmt in filter(None, (x.strip() for x in _DDL.split(";"))):
        await db.execute(_t(stmt))
    await db.commit()


def _now() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def _row_dict(db: AsyncSession, task_id: str) -> dict | None:
    row = (await db.execute(_t("SELECT * FROM kb_refine_tasks WHERE id=:i"), {"i": task_id})).mappings().first()
    if row is None:
        return None
    d = dict(row)
    for k in ("timeline_json", "result_json"):
        try:
            d[k.removesuffix("_json")] = json.loads(d.pop(k) or ("[]" if k == "timeline_json" else "{}"))
        except ValueError:
            d[k.removesuffix("_json")] = [] if k == "timeline_json" else {}
    return d


async def create_task(db: AsyncSession, *, user_id: str, genre: str) -> tuple[dict | None, str]:
    """建任务（queued）；同题材已有未完成任务则拒（单飞）。返回 (任务, error)。"""
    await ensure_ddl(db)
    busy = (await db.execute(_t(
        "SELECT id FROM kb_refine_tasks WHERE user_id=:u AND genre=:g AND status IN ('queued','running') LIMIT 1"),
        {"u": user_id, "g": genre},
    )).scalar()
    if busy:
        return None, "该题材已有进行中的知识提炼任务"
    tid = uuid.uuid4().hex
    await db.execute(_t(
        "INSERT INTO kb_refine_tasks (id, user_id, genre, status) VALUES (:i, :u, :g, 'queued')"),
        {"i": tid, "u": user_id, "g": genre},
    )
    await db.commit()
    return await _row_dict(db, tid), ""


async def list_tasks(db: AsyncSession, *, user_id: str, limit: int = 50) -> list[dict]:
    await ensure_ddl(db)
    rows = (await db.execute(_t(
        "SELECT id FROM kb_refine_tasks WHERE user_id=:u ORDER BY created_at DESC LIMIT :n"),
        {"u": user_id, "n": limit},
    )).scalars().all()
    out = []
    for tid in rows:
        d = await _row_dict(db, tid)
        if d:
            out.append(d)
    return out


async def get_task(db: AsyncSession, *, user_id: str, task_id: str) -> dict | None:
    await ensure_ddl(db)
    d = await _row_dict(db, task_id)
    if d and d.get("user_id") != user_id:
        return None
    return d


async def delete_task(db: AsyncSession, *, user_id: str, task_id: str) -> str:
    await ensure_ddl(db)
    d = await _row_dict(db, task_id)
    if d is None or d.get("user_id") != user_id:
        return "任务不存在"
    if d.get("status") in ("queued", "running"):
        return "进行中的任务不能删"
    await db.execute(_t("DELETE FROM kb_refine_tasks WHERE id=:i"), {"i": task_id})
    await db.commit()
    return ""


async def _set(db: AsyncSession, task_id: str, **cols) -> None:
    sets = ", ".join(f"{k}=:{k}" for k in cols)
    cols["i"] = task_id
    cols["ua"] = _now()
    await db.execute(_t(f"UPDATE kb_refine_tasks SET {sets}, updated_at=:ua WHERE id=:i"), cols)
    await db.commit()


def _step(key: str, title: str, detail: str) -> dict:
    return {"key": key, "title": title, "detail": detail, "time": _now()}


async def execute_task(task_id: str, *, user_id: str, genre: str) -> None:
    """后台执行体（自带会话）：归类进树 → 梳理关系 → 落时间线与结果账。"""
    from db import async_session
    from kb.organize import run_organize
    from kb.refine import run_refine

    try:
        async with async_session() as db:
            await ensure_ddl(db)
            timeline: list[dict] = [_step("read", "读「其他」原始材料", f"题材「{genre}」待提炼材料")]
            await _set(db, task_id, status="running", current_step="读「其他」原始材料", timeline_json=json.dumps(timeline, ensure_ascii=False))

            staged = await db.execute(_t(
                "SELECT COUNT(*) FROM kb_knowledge_instances i JOIN kb_entries e ON e.id=i.knowledge_id "
                "WHERE e.user_id=:u AND e.genre=:g AND e.concept='' AND e.origin='summary' AND e.title='其他'"),
                {"u": user_id, "g": genre},
            )
            n_staged = staged.scalar() or 0
            timeline[-1]["detail"] = f"取到 {n_staged} 条待提炼材料"
            await _set(db, task_id, timeline_json=json.dumps(timeline, ensure_ascii=False))

            # ── 1. 归类进树 ──
            await _set(db, task_id, current_step="归类进树")
            refine_summary, refine_err = (await _run(db, run_refine, user_id=user_id, genre=genre))
            if refine_err == "running":
                refine_err = "上一轮提炼尚未结束"
            if refine_summary is None:
                timeline.append(_step("classify", "归类进树", f"失败：{refine_err}"))
                await _set(db, task_id, status="failed", error=f"refine: {refine_err}",
                           timeline_json=json.dumps(timeline, ensure_ascii=False))
                return
            timeline.append(_step("classify", "归类进树",
                                  f"{refine_summary['moved']} 条挂进知识点；撑不起的留守「其他」"))
            await _set(db, task_id, timeline_json=json.dumps(timeline, ensure_ascii=False))

            # ── 2. 长出新知识点 ──
            created = refine_summary["nodes_created"]
            detail = refine_summary.get("details") or {}
            new_nodes = detail.get("new_nodes") or []
            if created:
                names = "、".join(n.get("title", "") for n in new_nodes[:3])
                await _set(db, task_id, current_step=f"长出新知识点（{names}）")
            timeline.append(_step("grow", "长出新知识点",
                                  f"AI 提案 {created} 个，已自动挂树" if created else "这一轮没有提案新知识点"))
            await _set(db, task_id, timeline_json=json.dumps(timeline, ensure_ascii=False))

            # ── 3. 梳理关系 ──
            await _set(db, task_id, current_step="梳理关系")
            run, org_err = await _run(db, run_organize, user_id=user_id, genre=genre, trigger="refine_task")
            relations = run.relations_added if run is not None and not org_err else 0
            if org_err and org_err != "running":
                logger.warning("event=kb.refine_task.organize_fail err=%s", org_err)
            timeline.append(_step("relate", "梳理关系", f"找出 {relations} 条关系（细化/矛盾/依赖）"))
            await _set(db, task_id, timeline_json=json.dumps(timeline, ensure_ascii=False))

            # ── 完成 ──
            kept = refine_summary["kept"]
            timeline.append(_step("done", "完成", f"{kept} 条材料撑不起知识，留守「其他」"))
            result = {
                "staged": refine_summary["staged"],
                "moved": refine_summary["moved"],
                "nodes_created": created,
                "relations": relations,
                "kept": kept,
                "details": detail,
                "organize_error": org_err or "",
            }
            await _set(db, task_id, status="completed", current_step="已完成",
                       timeline_json=json.dumps(timeline, ensure_ascii=False),
                       result_json=json.dumps(result, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 — 任务失败落账不炸进程
        logger.warning("event=kb.refine_task.fail task=%s err=%s", task_id, exc, exc_info=True)
        try:
            async with async_session() as db:
                await ensure_ddl(db)
                await _set(db, task_id, status="failed", error=str(exc)[:200])
        except Exception:  # noqa: BLE001 — 落账失败仅记日志（任务体已失败，无可恢复动作）
            logger.warning("event=kb.refine_task.finalize_fail task=%s", task_id)


async def _run(db: AsyncSession, fn, **kwargs):
    """提炼/整理都在自会话里跑（调用方会话只管任务账）。"""
    return await fn(db, **kwargs)


# 进程内持有执行体引用——asyncio 对裸 task 只持弱引用（官方文档明示可能被 GC
# 中途消失），丢引用＝任务无声蒸发且行状态卡 running（评审 P1）
_RUNNING: set[asyncio.Task] = set()


def schedule(task_id: str, *, user_id: str, genre: str) -> None:
    """投递后台执行（FastAPI 事件循环内调用）。"""
    task = asyncio.get_event_loop().create_task(execute_task(task_id, user_id=user_id, genre=genre))
    _RUNNING.add(task)
    task.add_done_callback(_RUNNING.discard)


async def sweep_stale_on_boot() -> int:
    """启动回收：queued/running 全部落 failed（应用重启＝执行体必死，asyncio
    task 不跨进程）。不回收则该题材永久 409 锁死（评审 P1）。"""
    from db import async_session

    n = 0
    async with async_session() as db:
        await ensure_ddl(db)
        rows = (await db.execute(_t(
            "SELECT id FROM kb_refine_tasks WHERE status IN ('queued','running')"
        ))).scalars().all()
        for tid in rows:
            await _set(db, tid, status="failed", current_step="",
                       error="应用重启中断，材料原样留在「其他」；重新提炼即可")
            n += 1
    return n
