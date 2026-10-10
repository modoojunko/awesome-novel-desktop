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
import logging
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import DATA_ROOT
from db_lifecycle import (
    candidate_manifest,
    clean_stale_staging,
    deletable_candidates,
    delete_candidate,
    list_quarantined,
    scan_migration_candidates,
)
from migration.engine import completeness_from_history, is_complete_report
from schema_version import app_version, candidate_stamp, candidate_stamp_legacy

# c-upgrade-log：无损升级全链具名 logger——upgrade.log 专项档＋双写 app.log。
logger = logging.getLogger("migration")

router = APIRouter(prefix="/api/backup/db-migration", tags=["db-migration"])

# 旧库留存：带回多少份之后才允许清理（不自动删；用户动作才删）
RETENTION_KEEP = 2
HISTORY_KEY = "migration.history"
HISTORY_LIMIT = 20
# 「稍后带」抑制键（c-lossless-upgrade）：值＝被「本版不再提醒」的候选 stamp。
# 与旧 migration.dismissed 的区别：dismissed 是永久静默（退役口径），snoozed 绑
# 当前库——下一版建新库时键天然不存在＝自动重开；搬完（migration.last 完整达成）
# 亦由 _record_completion 清除。旧 dismissed 键不再参与抑制（存量用户不被永久静默）。
SNOOZE_KEY = "migration.snoozed"


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
    # 完整性单源判定（c-lossless-upgrade D8）：migration.last 内嵌完整 report 时
    # 直接判；老数据（无 report）经 history 适配器归一后走同一条判定。
    report = last.get("report") if isinstance(last.get("report"), dict) else None
    if report is not None:
        complete = is_complete_report(report)
    else:
        complete = any(
            entry.get("source_stamp") == stamp
            and is_complete_report(completeness_from_history(entry))
            for entry in _history_entries()
        )
    if not complete:
        return set()
    # c-carry-modal-reshow 兼容：升级前的完成记录可能编着 -shm 分量（读者会改写、
    # 恒漂移）。现行文件按两种形态对拍，任一命中（＝数据件未变）即换发现行指纹，
    # 让白名单与现行扫描同键；都不命中＝文件已变，保守退回原串（对不上任何扫描
    # 项＝不可删，少删优于误删）。
    fname = str(last.get("source_filename") or "")
    if fname:
        src = Path(DATA_ROOT) / fname
        if src.exists():
            current = {candidate_stamp(fname, src), candidate_stamp_legacy(fname, src)}
            if stamp in current:
                return {candidate_stamp(fname, src)}
    return {stamp}


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
    MUST NOT 未过校验即操作。不合法 → 400 可读拒绝。
    allow_sentinel=True：哨兵候选在迁入白名单内（v0.30.1 真机判例
    c-sentinel-carry-gate——cleanup 的非哨兵规则不得上扩到迁入链）。"""
    from db_lifecycle import validate_candidate_filename

    p = validate_candidate_filename(Path(DATA_ROOT), filename, _active_db_path(),
                                    allow_sentinel=True)
    if p is None or not p.exists():
        logger.warning("event=migration_source_rejected source=%s reason=invalid_filename",
                       filename)
        raise HTTPException(400, "文件名不合法或不在数据目录内")
    return p


@router.get("/candidates")
async def candidates():
    """候选列表＋隔离件只读展示＋提示抑制状态（登录前可调——登录页计数行同源）。"""
    root = Path(DATA_ROOT)
    items = scan_migration_candidates(root, app_version(), _active_db_path())
    done_stamp = ""
    done_complete = False
    done_partial = False
    done = _app_meta_value("migration.last")
    if done:
        try:
            last = json.loads(done)
            done_stamp = last.get("source_stamp", "")
            report = last.get("report") if isinstance(last.get("report"), dict) else None
            done_complete = is_complete_report(report)
            # 部分迁移态（c-carry-degrade-remigrate）：有完成记录且搬运「成功跑完」
            # 但完整性未达标——前端据此不再自动重弹完整告知卡（提醒行承接）。
            # status!=ok 的搬运不写完成记录，天然不进这里。
            done_partial = (report is not None and report.get("status") == "ok"
                            and not done_complete)
        except json.JSONDecodeError:
            pass
    snoozed_stamp = _app_meta_value(SNOOZE_KEY) or ""
    # 呈现状态三字段（c-lossless-upgrade / c-carry-degrade-remigrate）：carried＝
    # 已带回（完整才算）；carried_partial＝曾带回但不完整（不自动重弹整卡）；
    # suppressed＝被「本版不再提醒」抑制（snoozed 绑 stamp；不完整 last 永不抑制）。
    # 对拍按双形态：现行指纹（数据件）或旧三件套指纹（c-carry-modal-reshow——升级前
    # 写入的记录可能编着 -shm 分量）任一命中即同一源；数据件变了两者都不命中。
    for it in items:
        stamps = {it["stamp"], it.get("stamp_legacy") or it["stamp"]}
        it["carried"] = done_complete and done_stamp in stamps
        it["carried_partial"] = (not it["carried"]) and done_partial \
            and done_stamp in stamps
        it["suppressed"] = it["carried"] or snoozed_stamp in stamps
        # 只读清单只挂 recommended（免登端点返回面收敛；密钥永不返回）
        if it.get("recommended") and not it["unreadable"]:
            it["manifest"] = candidate_manifest(root / it["filename"])
    return {"code": 0, "data": {"candidates": items, "quarantined": list_quarantined(root),
                                "current_version": app_version()}}


@router.get("/gaps")
async def gaps(filename: str):
    """缺口清单（c-carry-degrade-remigrate）：「旧版有、这一版没有」的实名内容。

    只读免登（candidates 同防护面）：白名单校验 → WAL 源走暂存读取（零接触）→
    按在场判定缺书（源书 id 对拍目标）与缺配置（名称对拍）。密钥红线同 manifest
    （不返回任何密钥材料）。任何读取失败按空清单降级——清单 SHALL NOT 阻塞迁移。
    """
    try:
        src = _validated_source(filename)
    except HTTPException:
        return {"code": 0, "data": {"books": [], "books_total": 0,
                                    "configs": [], "configs_total": 0}}
    staged = _staged_copy(src)
    if staged is None:
        return {"code": 0, "data": {"books": [], "books_total": 0,
                                    "configs": [], "configs_total": 0}}
    try:
        con = sqlite3.connect(f"file:{staged}?mode=ro", uri=True, timeout=5)
        try:
            try:
                src_books = con.execute(
                    "SELECT n.id, n.name, COALESCE((SELECT SUM(c.word_count) FROM chapters c"
                    " WHERE c.novel_id = n.id), 0) FROM novels n ORDER BY n.created_at, n.name"
                ).fetchall()
            except sqlite3.Error:
                # 老库 chapters 无 word_count 列：降级为书名清单（words=0），
                # 与 candidate_manifest 同口径（清单失败不阻塞）
                src_books = con.execute(
                    "SELECT n.id, n.name, 0 FROM novels n ORDER BY n.created_at, n.name"
                ).fetchall()
            try:
                src_cfgs = [r[0] for r in con.execute(
                    "SELECT name FROM api_configs ORDER BY created_at, name")]
            except sqlite3.Error:
                src_cfgs = []
        finally:
            con.close()
        active = _active_db_path()
        tgt = sqlite3.connect(f"file:{active}?mode=ro", uri=True, timeout=5) \
            if active.exists() else None
        try:
            tgt_book_ids = {r[0] for r in tgt.execute("SELECT id FROM novels")} \
                if tgt else set()
            try:
                tgt_cfgs = {r[0] for r in tgt.execute("SELECT name FROM api_configs")} \
                    if tgt else set()
            except sqlite3.Error:
                tgt_cfgs = set()
        finally:
            if tgt is not None:
                tgt.close()
        books = [{"name": str(name), "words": int(w or 0)}
                 for bid, name, w in src_books if bid not in tgt_book_ids]
        configs = [str(c) for c in src_cfgs if c not in tgt_cfgs]
        return {"code": 0, "data": {"books": books, "books_total": len(books),
                                    "configs": configs, "configs_total": len(configs)}}
    except sqlite3.Error:
        return {"code": 0, "data": {"books": [], "books_total": 0,
                                    "configs": [], "configs_total": 0}}
    finally:
        shutil.rmtree(staged.parent, ignore_errors=True)


def _staged_copy(src: Path) -> Path | None:
    """源库零接触暂存副本（candidate_manifest 同口径）：WAL 库 checkpoint 后可读。"""
    try:
        from db_lifecycle import _is_wal_mode, copy_sidecars, prepare_staged
    except ImportError:  # pragma: no cover — 同包内导入失败即降级
        return None
    tmpdir = tempfile.mkdtemp(prefix="mig-gaps-")
    staged = Path(tmpdir) / src.name
    copy_sidecars(src, staged)
    if not prepare_staged(staged):
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None
    if not _is_wal_mode(src):
        # 非 WAL 源无需整备副本，直读即可——但保留暂存形态统一出口
        pass
    return staged


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
    logger.info("event=migration_cleanup deleted=%s refused=%s", deleted, refused)
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
        logger.warning("event=migration_precheck_rejected source=%s reason=%s entry=preview",
                       body.source_filename, pc["reason"])
        if pc["reason"] in ("pre_adr_generation", "pre_rename_generation"):
            return {"code": 1, "data": {
                "reason": pc["reason"],
                "message": "这份旧版数据是更早的版本写下的格式，请改用「备份包导入」恢复作品。",
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
        if plan.get("error"):
            logger.warning("event=migration_preview_failed source=%s error=%s",
                           body.source_filename, plan["error"])
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
        plan["manifest"] = candidate_manifest(staged)
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
        logger.warning("event=migration_start_rejected source=%s reason=job_busy running_kind=%s",
                       body.source_filename, rk)
        raise HTTPException(409, {"message": f"已有{label}任务在进行中", "running_kind": rk})
    from migration.engine import precheck

    _validated_source(body.source_filename)
    pc = precheck(Path(DATA_ROOT), body.source_filename, _active_db_path())
    if not pc["ok"]:
        logger.warning("event=migration_precheck_rejected source=%s reason=%s entry=start",
                       body.source_filename, pc["reason"])
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
            # c-upgrade-log：run_thread 兜底只把 str(e) 吞进 state=error、零落日志
            # ——堆栈必须在重抛前经 migration logger 落双档，否则无法定位。
            try:
                report = run_migration(
                    Path(DATA_ROOT), body.source_filename, _active_db_path(),
                    report_progress=_on_progress,
                )
                job_runner.set_job(report=report)
                if report.get("status") == "ok":
                    asyncio.run(_record_completion(body.source_filename, report))
            except Exception:
                logger.exception("event=migration_job_error source=%s", body.source_filename)
                raise

        run_thread(_body)

    started = job_runner.start("migration", _run, "local",
                               target=body.source_filename,
                               report=None, progress=None)
    if started is None:
        logger.warning("event=migration_start_rejected source=%s reason=job_busy running_kind=%s",
                       body.source_filename, running_kind())
        raise HTTPException(409, {"message": "已有任务在进行中", "running_kind": running_kind()})
    return {"code": 0, "data": started}


@router.get("/status")
async def status():
    """透传 job_runner.status()——前端轮询 progress/report/state 三个字段。"""
    import job_runner

    return {"code": 0, "data": job_runner.status()}


@router.post("/dismiss")
async def dismiss(body: DismissBody):
    """「本版不再提醒」（稍后带）——snoozed 键绑候选身份指纹（源数据变化自动重开）。

    旧 `migration.dismissed`（永久静默）语义退役：本端点自 c-lossless-upgrade 起
    改写 SNOOZE_KEY；旧键不再被读取抑制（存量用户不被永久静默）。
    """
    from db_lifecycle import validate_candidate_filename

    # allow_sentinel：哨兵候选可 snooze（c-sentinel-carry-gate——迁入链放行哨兵）
    p = validate_candidate_filename(Path(DATA_ROOT), body.filename, _active_db_path(),
                                    allow_sentinel=True)
    if p is None or not p.exists():
        return {"code": 1, "msg": "文件不存在"}
    await _set_app_meta(SNOOZE_KEY, candidate_stamp(body.filename, p))
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
        "pre_rename_generation": "这份旧版数据是更早的版本写下的格式，请改用「备份包导入」恢复作品",
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
    await _set_app_meta(SNOOZE_KEY, "")
    await _set_app_meta("migration.dismissed", "")  # 旧键清废（不再参与抑制）
    # 完成行以持久化成功为前提（评审 P2）：migration.last 写库失败时此行不落——
    # upgrade.log 不得在没写进完成记录时谎报已完成。
    logger.info("event=migration_completed source=%s stamp=%s source_version=%s books=%s",
                source_filename, stamp, report.get("source_version"),
                report.get("book_count_migrated"))
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
        # 完整性字段（c-db-version-hardening）：cleanup 白名单据此拒绝半途搬运的源；
        # present＝源书在场数（c-carry-retry-complete——完整判定按在场不按本次插入）
        "book_count_source": report.get("book_count_source"),
        "book_count_present": report.get("book_count_present"),
        "tables_skipped": len(skipped) if isinstance(skipped, list) else skipped,
        "fk_violations": len(fk) if isinstance(fk, list) else fk,
    })
    await _set_app_meta(HISTORY_KEY, json.dumps(history[-HISTORY_LIMIT:], ensure_ascii=False))
