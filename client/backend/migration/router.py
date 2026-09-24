"""迁入免登端点（c-db-per-version）：candidates / preview / start / status / dismiss
＋ retention / cleanup。

specs：迁入端点全家免登录（复用 loginless-data-exit 防护面：回环中间件已在
main.py 注册本前缀）；与导出/下载 job_runner 跨 kind 单飞互斥；dismiss 与
完成态绑定候选身份指纹（回滚编辑后三件套 max(mtime)/体积变化→重新提示合并）。

本版改动（c-db-per-version）：
- 候选载荷改版本语义（`version`/`kind`/`legacy_generation`/`recommended`＋顶层
  `current_version`），退役 `generation`/`schema_version`；
- 活跃库按**路径**排除、白名单形状枚举、`recommended` 后端单源；
- 新增 retention/cleanup：**只允许删「本次成功带回且搬运完整」的件**（`migration.last`
  ＋ history 完整性字段，c-db-version-hardening），默认保留最近 2 份，
  路径校验收口在 `db_lifecycle.delete_candidate`；
- dismiss 补路径校验（原实现直接 `DATA_ROOT / filename`）。
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import DATA_ROOT
from db_lifecycle import (
    clean_stale_staging,
    deletable_candidates,
    delete_candidate,
    list_quarantined,
    scan_migration_candidates,
)
from schema_version import app_version, candidate_stamp

router = APIRouter(prefix="/api/backup/db-migration", tags=["db-migration"])

# 旧库留存：带回多少份之后才允许清理（不自动删；用户动作才删）
RETENTION_KEEP = 2
HISTORY_KEY = "migration.history"
HISTORY_LIMIT = 20


class StartBody(BaseModel):
    source_filename: str


class DismissBody(BaseModel):
    filename: str


class CleanupBody(BaseModel):
    filenames: list[str]


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


def _migrated_stamps() -> set[str]:
    """可删白名单：仅「本次成功带回且搬运完整」的源（c-db-version-hardening）。

    规格口径（db-generation）：仅 `migration.last.source_stamp` 可删，且含整表跳过/
    FK 违规的搬运 SHALL NOT 出现清理入口。history 条目缺完整性字段（老数据）或
    book_count 对不上时保守排除——少删优于误删。
    """
    last_raw = _app_meta_value("migration.last")
    if not last_raw:
        return set()
    try:
        last = json.loads(last_raw)
    except json.JSONDecodeError:
        return set()
    if not isinstance(last, dict):
        return set()
    stamp = str(last.get("source_stamp") or "")
    if not stamp:
        return set()
    for entry in _history_entries():
        if entry.get("source_stamp") != stamp:
            continue
        if entry.get("tables_skipped") != 0 or entry.get("fk_violations") != 0:
            return set()
        src = entry.get("book_count_source")
        mig = entry.get("book_count_migrated")
        if src is not None and mig is not None and src != mig:
            return set()
        return {stamp}
    return set()


def _history_entries() -> list[dict]:
    """migration.history 条目（非 list/坏 JSON 一律空表）。"""
    raw = _app_meta_value(HISTORY_KEY)
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [it for it in items if isinstance(it, dict)] if isinstance(items, list) else []


def _validated_source(filename: str) -> Path:
    """start/preview 入参走与 dismiss/cleanup 同源的白名单校验
    （c-backend-infra-hygiene）：这两条路径会读文件、复制并 ATTACH，
    MUST NOT 未过校验即操作。不合法 → 400 可读拒绝。"""
    from db_lifecycle import validate_candidate_filename

    p = validate_candidate_filename(Path(DATA_ROOT), filename, _active_db_path())
    if p is None or not p.exists():
        raise HTTPException(400, "文件名不合法或不在数据目录内")
    return p


@router.get("/candidates")
async def candidates():
    """候选列表＋隔离件只读展示＋提示抑制状态（登录前可调——登录页计数行同源）。"""
    root = Path(DATA_ROOT)
    items = scan_migration_candidates(root, app_version(), _active_db_path())
    done_stamp = ""
    done = _app_meta_value("migration.last")
    if done:
        try:
            done_stamp = json.loads(done).get("source_stamp", "")
        except json.JSONDecodeError:
            pass
    dismissed_stamp = _app_meta_value("migration.dismissed") or ""
    for it in items:
        it["suppressed"] = it["stamp"] in (done_stamp, dismissed_stamp)
    return {"code": 0, "data": {"candidates": items, "quarantined": list_quarantined(root),
                                "current_version": app_version()}}


@router.get("/retention")
async def retention():
    """待删清单：仅**本次成功带回且搬运完整**的件（无用户动作永不删）。"""
    root = Path(DATA_ROOT)
    # keep 保留窗口随白名单收窄（c-db-version-hardening）失去意义：可删集至多一项，
    # 再套 keep=2 会把唯一可删项也保住＝清理功能死亡。置 0，保留窗口由白名单本身承载。
    items = deletable_candidates(root, _migrated_stamps(), keep=0,
                                 active_db_path=_active_db_path())
    return {"code": 0, "data": {"items": items, "keep": 0}}


@router.post("/cleanup")
async def cleanup(body: CleanupBody):
    """删除用户勾选的旧库（服务端再次收口：只认待删清单内的名字）。"""
    root = Path(DATA_ROOT)
    allowed = {it["filename"] for it in deletable_candidates(
        root, _migrated_stamps(), keep=0, active_db_path=_active_db_path())}
    deleted: list[str] = []
    refused: list[str] = []
    for name in body.filenames:
        if name not in allowed:
            refused.append(name)
            continue
        (deleted if delete_candidate(root, name, _active_db_path()) else refused).append(name)
    return {"code": 0, "data": {"deleted": deleted, "refused": refused}}


@router.post("/preview")
async def preview(body: StartBody):
    """第 3 步计划的只读预演（与 result 同构 v:1）。"""
    import shutil
    import tempfile

    from db_lifecycle import copy_sidecars, prepare_staged
    from migration.engine import build_plan, precheck

    _validated_source(body.source_filename)
    pc = precheck(Path(DATA_ROOT), body.source_filename, _active_db_path())
    if not pc["ok"]:
        if pc["reason"] in ("pre_adr_generation", "pre_rename_generation"):
            return {"code": 1, "data": {
                "reason": pc["reason"],
                "message": "这份旧版数据是更早的版本写下的格式，请改用「备份包导入」带回作品。",
            }}
        raise HTTPException(422, {"message": _precheck_msg(pc["reason"])})

    src = Path(DATA_ROOT) / body.source_filename
    tmpdir = tempfile.mkdtemp(prefix="mig-preview-")
    staged = Path(tmpdir) / body.source_filename
    try:
        copy_sidecars(src, staged)
        prepare_staged(staged)
        plan = build_plan(staged)
        plan["source"] = body.source_filename
        plan["source_version"] = pc.get("source_version")
        plan["legacy_generation"] = pc.get("legacy_generation")
        try:
            import sqlite3 as _sq

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

    _validated_source(body.source_filename)
    pc = precheck(Path(DATA_ROOT), body.source_filename, _active_db_path())
    if not pc["ok"]:
        raise HTTPException(422, {"message": _precheck_msg(pc["reason"])})

    def _run(payload: dict, user_id: str) -> None:
        """线程体：engine 跑完→写 report→记完成→run_thread 兜 state=done。

        进度回调→set_job（遵守 job_runner「只经 set() 整值替换」纪律）；
        report_progress 收 dict 事件 {stage, tables_total, tables_done, table, rows_inserted}。
        必须 run_thread 包装（与 backup/export._run_backup_thread 同款）——否则
        state 永远停在 running，单飞槽卡死到重启。
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


@router.post("/dismiss")
async def dismiss(body: DismissBody):
    """「保留旧文件，不再提醒」——dismiss 键绑候选身份指纹（新数据自动重开）。"""
    from db_lifecycle import validate_candidate_filename

    p = validate_candidate_filename(Path(DATA_ROOT), body.filename, _active_db_path())
    if p is None or not p.exists():
        return {"code": 1, "msg": "文件不存在"}
    await _set_app_meta("migration.dismissed", candidate_stamp(body.filename, p))
    return {"code": 0}


@router.post("/staging-sweep")
async def staging_sweep():
    """清理 `migration-staging/*` 残留（硬杀/断电遗留；启动期同源调用）。"""
    return {"code": 0, "data": {"removed": clean_stale_staging(Path(DATA_ROOT))}}


def _precheck_msg(reason: str) -> str:
    return {
        "source_missing": "旧库文件不存在，请重新检测",
        "source_is_active_db": "不能迁移当前正在使用的库",
        "disk_full": "磁盘空间不足（需约旧数据体积两倍），请先清理后重试",
        "source_unreadable": "旧库文件无法读取",
        "source_busy": "旧版数据正在被另一个程序写入，请先关闭旧版本应用再试",
        "pre_rename_generation": "这份旧版数据是更早的版本写下的格式，请改用「备份包导入」带回作品",
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
    """完成记录：`migration.last`（幂等/重开判定）＋`migration.history`（cleanup 白名单）。"""
    src = Path(DATA_ROOT) / source_filename
    stamp = candidate_stamp(source_filename, src)
    payload = {"source_filename": source_filename, "source_stamp": stamp,
               "source_version": report.get("source_version"),
               "legacy_generation": report.get("legacy_generation"),
               "book_count_migrated": report.get("book_count_migrated"),
               "finished_at": datetime.now(UTC).isoformat(), "report": report}
    await _set_app_meta("migration.last", json.dumps(payload, ensure_ascii=False))
    await _set_app_meta("migration.dismissed", "")
    raw = _app_meta_value(HISTORY_KEY)
    history: list[dict] = []
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                history = [it for it in loaded if isinstance(it, dict)]
        except json.JSONDecodeError:
            history = []
    history = [it for it in history if it.get("source_stamp") != stamp]
    skipped = report.get("tables_skipped") or report.get("skipped") or []
    fk = report.get("fk_violations") or []
    history.append({
        **{k: payload[k] for k in
           ("source_filename", "source_stamp", "source_version",
            "legacy_generation", "book_count_migrated", "finished_at")},
        # 完整性字段（c-db-version-hardening）：cleanup 白名单据此拒绝半途搬运的源
        "book_count_source": report.get("book_count_source"),
        "tables_skipped": len(skipped) if isinstance(skipped, list) else skipped,
        "fk_violations": len(fk) if isinstance(fk, list) else fk,
    })
    await _set_app_meta(HISTORY_KEY, json.dumps(history[-HISTORY_LIMIT:], ensure_ascii=False))
