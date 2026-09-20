"""迁入免登端点（db-generation PR1 → 异步化）：candidates / preview / start / status / dismiss。

specs：迁入端点全家免登录（复用 loginless-data-exit 防护面：回环中间件已在
main.py 注册本前缀）；与导出/下载 job_runner 跨 kind 单飞互斥；dismiss 与
完成态绑定候选身份指纹（回滚编辑后 mtime 变化→重新提示合并）。

异步化（2026-09-20 评审实施）：start 立即返回初始快照（不再 600s 同步等待）；
引擎进度经 job_runner.phase/set_job 上报（stage/tables_done/tables_total）；
status 透传 job_runner.status()（含 running/report/progress 字段）；
完成记录 _record_completion 在线程体内执行（run_thread 包装保证 state=done）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import DATA_ROOT
from db_lifecycle import scan_migration_candidates
from schema_version import SCHEMA_VERSION

router = APIRouter(prefix="/api/backup/db-migration", tags=["db-migration"])


class StartBody(BaseModel):
    source_filename: str


def _active_db_path() -> Path:
    from config import DATABASE_URL

    return Path(DATABASE_URL.split("///")[-1])


def _app_meta_value(key: str) -> str | None:
    import sqlite3

    db = _active_db_path()
    if not db.exists():
        return None
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        con.close()


@router.get("/candidates")
async def candidates():
    """候选列表＋隔离件只读展示＋提示抑制状态（登录前可调——登录页计数行同源）。"""
    root = Path(DATA_ROOT)
    items = scan_migration_candidates(root, SCHEMA_VERSION)
    done = _app_meta_value("migration.last")
    done_stamp = ""
    if done:
        try:
            done_stamp = json.loads(done).get("source_stamp", "")
        except json.JSONDecodeError:
            pass
    dismissed_stamp = _app_meta_value("migration.dismissed") or ""
    for it in items:
        p = root / it["filename"]
        it["stamp"] = f"{it['filename']}:{it['mtime']}:{it['size_bytes']}"
        it["suppressed"] = it["stamp"] in (done_stamp, dismissed_stamp)
    quarantined = [
        {"filename": f.name, "size_bytes": f.stat().st_size}
        for f in sorted(root.glob("novel*.corrupt-*"))
        if f.is_file() and not f.name.endswith(("-wal", "-shm"))
    ]
    return {"code": 0, "data": {"candidates": items, "quarantined": quarantined,
                                "schema_version": SCHEMA_VERSION}}


@router.post("/preview")
async def preview(body: StartBody):
    """第 3 步计划的只读预演（与 result 同构 v:1）。"""
    from migration.engine import precheck

    pc = precheck(Path(DATA_ROOT), body.source_filename, _active_db_path())
    if not pc["ok"]:
        if pc["reason"] == "pre_adr_generation":
            return {"code": 1, "data": {
                "reason": "pre_adr_generation",
                "message": "这份旧版数据的设定存于旧版文件格式，请改用「备份包导入」找回。",
            }}
        raise HTTPException(422, {"message": _precheck_msg(pc["reason"])})
    import shutil
    import tempfile

    src = Path(DATA_ROOT) / body.source_filename
    tmpdir = tempfile.mkdtemp(prefix="mig-preview-")
    staged = Path(tmpdir) / body.source_filename
    try:
        shutil.copy2(src, staged)
        for suf in ("-wal", "-shm"):
            side = Path(str(src) + suf)
            if side.exists():
                shutil.copy2(side, str(staged) + suf)
        import sqlite3 as _sq

        con = _sq.connect(str(staged))
        try:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            con.close()
        from migration.engine import build_plan

        plan = build_plan(staged)
        plan["source"] = body.source_filename
        try:
            con2 = _sq.connect(f"file:{staged}?mode=ro", uri=True)
            try:
                plan["book_count_source"] = con2.execute(
                    "SELECT COUNT(*) FROM novels").fetchone()[0]
            finally:
                con2.close()
        except _sq.Error:
            plan["book_count_source"] = None
        return {"code": 0, "data": plan}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@router.post("/start")
async def start(body: StartBody):
    """异步启动迁入（立即返回初始快照；进度经 status 轮询）。"""
    import job_runner
    from job_runner import running_kind

    rk = running_kind()
    if rk:
        label = {"backup": "备份", "single": "导出", "download": "下载"}.get(rk, rk)
        raise HTTPException(409, {"message": f"已有{label}任务在进行中", "running_kind": rk})
    from migration.engine import precheck

    pc = precheck(Path(DATA_ROOT), body.source_filename, _active_db_path())
    if not pc["ok"]:
        raise HTTPException(422, {"message": _precheck_msg(pc["reason"])})

    def _run(payload: dict, user_id: str) -> None:
        """线程体：engine 跑完→写 report→记完成→run_thread 兜 state=done。

        进度回调→set_job（遵守 job_runner「只经 set() 整值替换」纪律）；
        report_progress 收 dict 事件 {stage, tables_total, tables_done, table, rows_inserted}。
        必须 run_thread 包装（与 backup/export._run_backup_thread 同款）——否则
        state 永远停在 running，单飞槽卡死到重启（2026-09-20 评审 P0 修复）。
        """
        import asyncio

        from job_runner import run_thread
        from migration.engine import run_migration

        def _on_progress(event: dict) -> None:
            job_runner.set_job(progress=event)

        def _body() -> None:
            report = run_migration(
                Path(DATA_ROOT), body.source_filename, _active_db_path(),
                report_progress=_on_progress,
            )
            job_runner.set_job(report=report)
            if report.get("status") == "ok":
                asyncio.run(_record_completion(body.source_filename, report))

        run_thread(_body)

    started = job_runner.start("migration", _run, "local",
                               target=body.source_filename,
                               report=None, progress=None)
    if started is None:
        raise HTTPException(409, {"message": "已有任务在进行中", "running_kind": running_kind()})
    return {"code": 0, "data": started}


@router.get("/status")
async def status():
    """透传 job_runner.status()——前端轮询 progress/report/state 三个字段。"""
    import job_runner

    return {"code": 0, "data": job_runner.status()}


class DismissBody(BaseModel):
    filename: str


@router.post("/dismiss")
async def dismiss(body: DismissBody):
    """「保留旧文件，不再提醒」——dismiss 键绑候选身份指纹（新数据自动重开）。"""
    p = Path(DATA_ROOT) / body.filename
    if not p.exists():
        return {"code": 1, "msg": "文件不存在"}
    stamp = f"{body.filename}:{int(p.stat().st_mtime)}:{p.stat().st_size}"
    await _set_app_meta("migration.dismissed", stamp)
    return {"code": 0}


def _precheck_msg(reason: str) -> str:
    return {
        "source_missing": "旧库文件不存在，请重新检测",
        "source_is_active_db": "不能迁移当前正在使用的库",
        "disk_full": "磁盘空间不足（需约旧数据体积两倍），请先清理后重试",
        "source_unreadable": "旧库文件无法读取",
    }.get(reason, reason)


async def _set_app_meta(key: str, value: str) -> None:
    from sqlalchemy import text

    from db import async_session

    async with async_session() as session:
        await session.execute(
            text("INSERT INTO app_meta (key, value) VALUES (:k, :v) "
                 "ON CONFLICT(key) DO UPDATE SET value=:v"),
            {"k": key, "v": value},
        )
        await session.commit()


async def _record_completion(source_filename: str, report: dict) -> None:
    src = Path(DATA_ROOT) / source_filename
    stamp = f"{source_filename}:{int(src.stat().st_mtime)}:{src.stat().st_size}"
    payload = {"source_filename": source_filename, "source_stamp": stamp,
               "finished_at": datetime.now(timezone.utc).isoformat(), "report": report}
    await _set_app_meta("migration.last", json.dumps(payload, ensure_ascii=False))
    await _set_app_meta("migration.dismissed", "")
