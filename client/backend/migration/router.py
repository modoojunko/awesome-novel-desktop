"""迁入免登端点（db-generation PR1）：candidates / preview / start / status / dismiss。

specs：迁入端点全家免登录（复用 loginless-data-exit 防护面：回环中间件已在
main.py 注册本前缀）；与导出/下载 job_runner 跨 kind 单飞互斥；dismiss 与
完成态绑定候选身份指纹（回滚编辑后 mtime 变化→重新提示合并）。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import DATA_ROOT
from db_lifecycle import scan_migration_candidates
from schema_version import SCHEMA_VERSION

router = APIRouter(prefix="/api/backup/db-migration", tags=["db-migration"])

# 轻量任务态（单进程内存即可——迁入是阻塞向导的独占操作，不跨重启续传；
# 重启后 status 查询回落 idle，向导重开走 candidates 重新检测）
_last_report: dict | None = None
_running = False


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
    # 抑制：完成记录或 dismissed 的身份指纹命中（filename+mtime+size）
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
    # 隔离件（只读可见，不进候选）
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
        # 世代门禁：明示走资产包通道（specs：不进行级迁入）
        if pc["reason"] == "pre_adr_generation":
            return {"code": 1, "data": {
                "reason": "pre_adr_generation",
                "message": "这份旧版数据的设定存于旧版文件格式，请改用「备份包导入」找回。",
            }}
        raise HTTPException(422, {"message": _precheck_msg(pc["reason"])})
    # 拷贝到暂存做 preview（源零接触；与执行同码路——同构保证）
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
        # 书计数
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
    """同步执行迁入（单飞：running 期间重复调用 409）。"""
    global _last_report, _running
    from job_runner import running_kind

    rk = running_kind()
    if rk:
        label = {"backup": "备份", "single": "导出", "download": "下载"}.get(rk, rk)
        raise HTTPException(409, {"message": f"已有{label}任务在进行中", "running_kind": rk})
    from migration.engine import precheck

    pc = precheck(Path(DATA_ROOT), body.source_filename, _active_db_path())
    if not pc["ok"]:
        raise HTTPException(422, {"message": _precheck_msg(pc["reason"])})
    # job_runner 单飞（kind=migration）：与 backup/single/download 双向互斥；
    # 完成态经 job 负载带回（state=done + report），进度经 phase 上报
    import job_runner

    def _run(payload: dict, user_id: str) -> None:
        from migration.engine import run_migration

        report = run_migration(Path(DATA_ROOT), body.source_filename,
                               _active_db_path())
        job_runner.set_job(report=report)

    started = job_runner.start("migration", _run, "local",
                               target=body.source_filename,
                               report=None)
    if started is None:
        raise HTTPException(409, {"message": "已有任务在进行中", "running_kind": running_kind()})
    # 等待完成（迁入是向导独占操作——前端进度轮询 status）
    import time

    deadline = time.time() + 600
    while time.time() < deadline:
        snap = job_runner.status()
        if snap.get("state") in ("done", "error"):
            break
        await asyncio.sleep(0.3)
    snap = job_runner.status()
    report = snap.get("report") or {"status": "error", "reason": "no_report"}
    _last_report = report
    _running = False
    if report.get("status") == "ok":
        await _record_completion(body.source_filename, report)
    return {"code": 0, "data": report}


@router.get("/status")
async def status():
    return {"code": 0, "data": {"running": _running, "last_report": _last_report}}


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
    await _set_app_meta("migration.dismissed", "")  # 完成即清 dismiss
