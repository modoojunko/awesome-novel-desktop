"""迁入引擎（db-generation）：六步＋预检。preview 与 result 同构（v:1）。"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import models  # noqa: F401 —— 注册全表（Base.metadata 依赖副作用 import）
from config import (
    DATA_ROOT,  # noqa: F401 —— 测试经 monkeypatch(engine, "DATA_ROOT") 注入数据目录
)
from db import Base
from db_lifecycle import (
    copy_sidecars,
    inspect_schema,
    migration_probe,
    prepare_staged,
    snapshot_signature,
    version_stamp_payload,
)
from schema_version import parse_db_filename

logger = logging.getLogger("uvicorn.error")

# 迁移排除表：app_meta（旧 schema_id 污染新戳；migration.* 是新库私产）
EXCLUDED_TABLES = {"app_meta"}

# 预置种子表清单（c-lossless-upgrade D4）：＝启动期 ensure_seed_* 播种的全部
# 出厂字典表。这些表在搬运路径按「源行胜出」处理（用户编辑优先于新版出厂文案）；
# 将来新增播种表 MUST 同批登记进本清单（specs：预置题材源行胜出）。
SEED_TABLES = ("genres", "genre_vocab")

# 世代门禁：库内含盘上 yaml 世代特征（自存储 ADR 前设定在文件系统）→ 行级
# 迁入会丢设定（specs R5 宁少勿错——引导资产包通道）。探测：novels.root_path
# 下的 settings 目录有 yaml 且库内无对应承载表（settings 键迁库后的形态）。
LEGACY_YAML_MARKER = "settings/genre.yaml"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── 「完整达成」单源判定（c-lossless-upgrade D8）────────────────────────────
# 三处消费共用：候选/常驻行的抑制与继续提醒（router）、清理白名单（router）、
# 演练对拍（upgrade_drill）。契约＝吃搬运 report dict（migration.last 内嵌完整
# report）；history 侧（计数形态）经 completeness_from_history 适配后消费。


def is_complete_report(report: dict | None) -> bool:
    """完整达成＝无整表跳过 ∧ 无 FK 违规 ∧ 源/迁入书数一致 ∧ 状态 ok。

    None/缺字段一律 False（宁保守：不完整者继续提醒、不进清理白名单）。
    """
    if not isinstance(report, dict):
        return False
    if report.get("status") != "ok":
        return False
    skipped = report.get("tables_skipped")
    if isinstance(skipped, list) and skipped:
        return False
    fk = report.get("fk_violations")
    if isinstance(fk, list) and fk:
        return False
    src = report.get("book_count_source")
    mig = report.get("book_count_migrated")
    return not (src is not None and mig is not None and src != mig)


def completeness_from_history(entry: dict) -> dict:
    """history 条目（计数形态）→ report dict 适配器（老数据走同一条判定）。

    字段**缺失**（老格式）按不完整处理——少删优于误删（沿用既有保守语义）；
    书数两缺一时不在适配器里判（is_complete_report 对缺计数容忍，同旧口径）。
    """
    skipped = entry.get("tables_skipped")
    fk = entry.get("fk_violations")
    return {
        "status": "ok",
        "tables_skipped": [] if skipped == 0 else [{"table": "history"}],
        "fk_violations": [] if fk == 0 else [{"table": "history"}],
        "book_count_source": entry.get("book_count_source"),
        "book_count_migrated": entry.get("book_count_migrated"),
    }



def _sqlite_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)


def _sqlite_rw(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), timeout=10)
    con.execute("PRAGMA foreign_keys=OFF")  # 迁移纪律：FK OFF，违规行事后报告
    return con


# ── 第 0 步：预检 ──────────────────────────────────────────────────────────


def _reencrypt_dead_ciphertexts(tgt: sqlite3.Connection,
                                src_con: sqlite3.Connection,
                                data_root: Path) -> int:
    """密钥转接（c-lossless-upgrade D3）：修「目标钥匙解不开」的 api_configs 行。

    候选源钥依次为：①源库 app_meta.fernet_key 行（src_con＝只读 work 副本，
    app_meta 表在副本内完整——EXCLUDED_TABLES 只影响 INSERT 计划）；②数据目录
    旧 `.fernet_key` 文件（按本次搬运的 data_root 解析，不依赖 import 期常量）。
    源钥内容非法按「不可得」降级（构造失败即跳过，不使搬运失败）。
    只碰目标钥匙解不开的行（幂等；可解行永不触碰，目标原生密文不受影响）；
    目标钥匙经 api_configs.crypto 取（init_crypto 已在 lifespan 先行；Fernet
    无共享可变态，本后台线程使用安全）。返回搬后目标库不可解 enc: 行数
    （含目标库既有死文——只报事实不断言成因）。
    """
    from cryptography.fernet import Fernet, InvalidToken

    from api_configs import crypto as _crypto

    def _load(raw) -> Fernet | None:
        try:
            return Fernet(raw)
        except Exception:  # noqa: BLE001 —— 非法钥＝不可得，降级
            return None

    source_keys: list[Fernet] = []
    try:
        row = src_con.execute(
            "SELECT value FROM app_meta WHERE key = 'fernet_key'"
        ).fetchone()
        if row:
            fk = _load(str(row[0]).strip().encode("ascii", "ignore"))
            if fk is not None:
                source_keys.append(fk)
    except sqlite3.Error:
        pass
    try:
        legacy = (Path(data_root) / ".fernet_key")
        if legacy.is_file():
            fk = _load(legacy.read_bytes().strip())
            if fk is not None:
                source_keys.append(fk)
    except OSError:
        pass

    def _decrypt(f: Fernet, token: str) -> str | None:
        try:
            return f.decrypt(token.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError):
            return None

    rows = tgt.execute(
        "SELECT rowid, api_key FROM main.api_configs WHERE api_key LIKE 'enc:%'"
    ).fetchall()
    dead = 0
    for rowid, stored in rows:
        token = stored[4:]
        if _decrypt(_crypto._get_fernet(), token) is not None:
            continue  # 目标钥匙可解——原生或已转接，永不触碰
        plaintext = next(
            (pt for pt in (_decrypt(f, token) for f in source_keys) if pt is not None),
            None,
        )
        if plaintext is None:
            dead += 1
            continue
        new_stored = _crypto.encrypt_api_key(plaintext)
        tgt.execute(
            "UPDATE main.api_configs SET api_key = ? WHERE rowid = ?",
            (new_stored, rowid),
        )
    return dead


def precheck(data_root: Path, source_filename: str, active_db_path: Path) -> dict:
    """磁盘与安全预检（specs 第 0 步）。返回 {"ok": bool, "reason": str?}。"""
    src = data_root / source_filename
    if not src.exists():
        return {"ok": False, "reason": "source_missing"}
    if src.resolve() == active_db_path.resolve():
        return {"ok": False, "reason": "source_is_active_db"}
    size = src.stat().st_size + sum(
        (Path(str(src) + s).stat().st_size if Path(str(src) + s).exists() else 0)
        for s in ("-wal", "-shm")
    )
    try:
        free = shutil.disk_usage(data_root).free
    except OSError:
        free = 0
    if free < size * 2:
        return {"ok": False, "reason": "disk_full"}
    # 体检与引擎同口径（一次暂存口径：WAL 库不在源目录留痕迹）
    probe = migration_probe(src)
    if probe["unreadable"]:
        return {"ok": False, "reason": "source_unreadable"}
    # 版本门禁：ADR 前世代（设定在盘上 yaml）不进行级迁入——按 schema 体检判定，
    # 不依赖文件名（版本命名轴换代后这一条天然可留）
    parsed = parse_db_filename(source_filename)
    label = {"source_version": parsed.version, "legacy_generation": parsed.generation}
    if "novels" not in set(probe.get("tables") or []) and "projects" in set(probe.get("tables") or []):
        # 「novel 正名」之前的世代：业务数据挂在 projects/项目外键下，行级搬运行列交集
        # 与表名都对不上 → 搬过去会是「成功但 0 本书」。响亮引走资产包通道（宁少勿错）。
        return {"ok": False, "reason": "pre_rename_generation", **label}
    if _is_pre_adr_generation(data_root, probe):
        return {"ok": False, "reason": "pre_adr_generation", **label}
    return {"ok": True, **label}


def _is_pre_adr_generation(data_root: Path, probe: dict) -> bool:
    """探测 ADR 前世代：库内无 settings 承载表（project_settings）而盘上
    root_path 存在 settings yaml（含 genre.yaml 标记）。

    判定只用 `migration_probe` 的读取结果（不在源上另开连接：WAL 库的只读连接会
    改写 `-shm` 字节）。
    """
    tables = set(probe.get("tables") or [])
    if "project_settings" in tables:
        return False  # 设定已入库（ADR 后）
    if "novels" not in tables:
        return False
    base = Path(data_root).parent  # root_path 相对 DATA_ROOT 父目录解析
    for r in probe.get("novels_roots") or []:
        if r and (base / r / LEGACY_YAML_MARKER).exists():
            return True
    return False


# ── 列交集计划（preview 引擎共享） ────────────────────────────────────────


def _neutral_literal(col) -> str | None:
    """缺失列的中性填充字面量（SQL 直插不经 ORM——Python default 不生效，
    DDL 无 server_default 的 NOT NULL 列必须显式补字面量，否则整行被
    INSERT OR IGNORE 静默吞）。按类型给中性值：数字/布尔 0、字符串空串；
    未知类型返回 None（调用方整表跳过）。"""
    t = str(col.type).upper()
    if any(k in t for k in ("INT", "BIGINT", "BOOLEAN", "BOOL", "REAL", "FLOAT", "NUMERIC", "DECIMAL")):
        return "0"
    if any(k in t for k in ("VARCHAR", "TEXT", "CHAR", "STRING")):
        return "''"
    return None


def build_plan(staged: Path) -> dict:
    """第 3 步：列交集计划（对已整备副本）。返回 v:1 报告的计划段。"""
    src_schema = inspect_schema(staged)
    if src_schema is None:
        return {"error": "source_schema_unreadable"}
    plan: list[dict] = []
    skipped: list[dict] = []
    backfills: list[dict] = []
    meta = {t.name: t for t in Base.metadata.tables.values()}
    for tname in sorted(set(src_schema) & set(meta) - EXCLUDED_TABLES):
        src_cols = src_schema[tname]
        tgt_cols = [c.name for c in meta[tname].columns]
        inter = [c for c in tgt_cols if c in src_cols]
        skipped_src = [c for c in src_cols if c not in tgt_cols]
        missing_tgt = [c for c in tgt_cols if c not in src_cols]
        # 可迁性：目标存在 NOT NULL 无 server_default 无自增的缺失列 → 整表跳过
        # （Python 侧 default 不经 ORM 不生效——SQL 直插必须显式给值，否则
        # INSERT OR IGNORE 静默吞整行：total_archives 事故根因）
        blocker = []
        entry_backfill: dict[str, str] = {}
        for c in meta[tname].columns:
            if c.name in missing_tgt:
                # NOT NULL 且无 server_default → SQL 直插必须显式给值。
                # 注意：server_default=func.now() 是 SQLAlchemy 的函数引用，
                # create_all 生成的 DDL 里有 DEFAULT CURRENT_TIMESTAMP——但源库
                # 没有 created_at 列时 INSERT SELECT 不会用到该 DEFAULT（显式列
                # 清单里没它就行）。真正要 backfill 的是 DDL 里没 DEFAULT 的
                # NOT NULL 列（如 total_archives）。
                if not c.nullable and c.server_default is None:
                    lit = _neutral_literal(c)
                    if lit is None:
                        blocker.append(c.name)
                    else:
                        entry_backfill[c.name] = lit
                elif not c.nullable and c.server_default is not None:
                    # 有 server_default 的 NOT NULL 列：不显式给值——INSERT
                    # SELECT 的列清单里不包含它，DDL DEFAULT 会自动填。
                    # 但 created_at 的 server_default=func.now() 在 create_all
                    # DDL 里是 DEFAULT CURRENT_TIMESTAMP——不进列清单即可。
                    pass
        entry = {
            "table": tname,
            "columns": inter,
            # select 可用列＝交集∩源实有（源缺列处由 backfill 字面量供值）
            "select_columns": [c for c in inter if c in src_cols],
            "rows_source": None,  # 执行时填
            "rows_inserted": None,
            "skipped_source_cols": skipped_src,
            "missing_target_cols": missing_tgt,
            "backfill": entry_backfill,
        }
        if blocker:
            skipped.append({"table": tname, "reason": "notnull_nodefault",
                            "columns": blocker})
        else:
            plan.append(entry)
    for tname in sorted(set(src_schema) - set(meta)):
        skipped.append({"table": tname, "reason": "table_retired",
                        "columns": src_schema[tname]})
    # dead_keys/complete 是搬后结果——preview 恒 None（同构＝字段集合一致，不造数）
    return {"v": 1, "tables": plan, "tables_skipped": skipped, "backfills": backfills,
            "dead_keys": None, "complete": None, "planned_at": _now_iso()}


# ── 执行（六步） ──────────────────────────────────────────────────────────


def run_migration(data_root: Path, source_filename: str, active_db_path: Path,
                  report_progress=None) -> dict:
    """完整迁入。任何异常下源文件零接触；目标库写入由 OR IGNORE 幂等。

    report_progress 回调收 dict 事件（内部契约 v1，唯一消费方 router._run）：
    {"stage": "copy"|"prepare"|"plan"|"transfer"|"verify",
     "tables_total": N, "tables_done": k, "table": t, "rows_inserted": r}
    """
    data_root = Path(data_root)
    src = data_root / source_filename
    stamp = datetime.now(UTC).replace(tzinfo=None).strftime("%Y%m%d-%H%M%S")
    staging = data_root / "migration-staging" / stamp
    work_dir: Path | None = None  # 早退路径（precheck/拷贝失败）时 finally 不误清
    report = {"v": 1, "source": source_filename, "at": _now_iso(),
              "tables": [], "tables_skipped": [], "fk_violations": [],
              "dead_keys": 0, "complete": None,
              # source＝源库书数；migrated＝**本次真正带回**的书数（目标已有书时不得虚高）；
              # target_after＝合并后目标库总数（诊断用）
              "book_count_source": None, "book_count_migrated": None,
              "book_count_target_after": None,
              "status": "ok", "notes": []}

    def _emit(stage: str, **kw) -> None:
        if report_progress:
            report_progress({"stage": stage, **kw})

    try:
        # 0 预检
        pc = precheck(data_root, source_filename, active_db_path)
        if not pc["ok"]:
            report["status"] = "precheck_failed"
            report["reason"] = pc["reason"]
            return report
        report["source_version"] = pc.get("source_version")
        report["legacy_generation"] = pc.get("legacy_generation")

        # 1 暂存拷贝（源零接触；不拷 -shm）＋一致性守卫：拷贝窗口内源被写（旧版本
        #    应用还在跑，自动 checkpoint 与拷贝交错）→ 重试一次，仍变化即拒绝——
        #    否则会「成功但少若干次提交」地静默搬入陈旧快照
        _emit("copy")
        staging.mkdir(parents=True, exist_ok=True)
        staged = staging / source_filename
        for attempt in (1, 2):
            before = snapshot_signature(src)
            copy_sidecars(src, staged)
            if snapshot_signature(src) == before:
                break
            if attempt == 2:
                report["status"] = "source_busy"
                report["reason"] = "source_busy"
                report["notes"].append("旧版本应用可能仍在运行，请关闭后重试")
                return report
            time.sleep(0.3)

        # 2 副本整备：可写打开（按需重建 -shm）→ checkpoint 收编 WAL → integrity
        _emit("prepare")
        if not prepare_staged(staged):
            report["status"] = "source_corrupt"
            return report
        for suf in ("-wal", "-shm"):
            side = Path(str(staged) + suf)
            if side.exists():
                side.unlink()  # checkpoint 后边车可清（副本域内）

        # 2.5 搬运用**容器本地**副本（c-db-version-hardening）：数据目录在 docker
        # 部署下是 bind mount，macOS VirtioFS 等共享挂载对刚拷贝文件的 ATTACH
        # 加锁会随机 disk I/O error。落到本地临时目录再 ATTACH；staging 里的
        # 副本仍是清理/审计口径，本地副本用完即删。
        work_dir = Path(tempfile.mkdtemp(prefix="mig-work-"))
        work = work_dir / staged.name
        shutil.copy2(staged, work)

        # 3 计划
        _emit("plan")
        plan = build_plan(staged)
        if plan.get("error"):
            report["status"] = "source_corrupt"
            return report
        report["tables_skipped"] = plan["tables_skipped"]
        tables_total = len(plan["tables"])
        tables_done = 0

        # 4 搬运：ATTACH ro 副本 → 目标（FK OFF 逐表 OR IGNORE）
        tgt = _sqlite_rw(active_db_path)
        src_con = _sqlite_ro(work)
        try:
            # ATTACH 传普通路径：file: URI 仅在连接以 uri=True 打开时才被解析
            # 字面量转义（c-backend-infra-hygiene）：sqlite3 不支持 ATTACH 参数绑定，
            # 白名单形状已排除引号，转义为纵深防御
            staged_sql = str(work).replace("'", "''")
            tgt.execute(f"ATTACH DATABASE '{staged_sql}' AS mig_src")
            for entry in plan["tables"]:
                t = entry["table"]
                cols = list(entry["columns"])
                selects = [f'"{c}"' for c in cols]
                # 缺失 NOT NULL 列补中性字面量（SQL 直插不经 ORM——Python
                # default 不生效，DDL 无 DEFAULT 的 NOT NULL 必须显式给值，
                # 否则 INSERT OR IGNORE 静默吞整行）
                for cname, lit in (entry.get("backfill") or {}).items():
                    cols.append(cname)
                    selects.append(lit)
                cl = ",".join(f'"{c}"' for c in cols)
                sl = ",".join(selects)
                rows_src = tgt.execute(f"SELECT COUNT(*) FROM mig_src.\"{t}\"").fetchone()[0]
                cur = tgt.execute(
                    f'INSERT OR IGNORE INTO main."{t}" ({cl}) SELECT {sl} FROM mig_src."{t}"'
                )
                entry["rows_source"] = rows_src
                entry["rows_inserted"] = max(cur.rowcount, 0)
                report["tables"].append(entry)
                tables_done += 1
                _emit("transfer", tables_total=tables_total, tables_done=tables_done,
                      table=t, rows_inserted=entry["rows_inserted"])
            # 4.5 预置种子表源行胜出（c-lossless-upgrade D4）：清单钉死＝ensure_seed_*
            # 播种表（新增播种表须同批登记 SEED_TABLES）。用户对预置项的编辑优先于
            # 新版出厂文案。实现＝UPDATE 交集列（两表 PK 均为 id）：**不做 DELETE+重插**
            # ——源行常缺目标 NOT NULL 无默认列，重插会被 OR IGNORE 静默吞掉整行
            # （测试实锤）；UPDATE 只写源实有列，目标独有列（含新版新增预置行）原样保留，
            # 源独有行由上方正常搬运路径带 backfill 插入。
            for seed_table in SEED_TABLES:
                if seed_table not in {e["table"] for e in plan["tables"]}:
                    continue
                cols = next(e["columns"] for e in plan["tables"]
                            if e["table"] == seed_table)
                set_cols = [c for c in cols if c != "id"]
                if not set_cols:
                    continue
                assignments = ", ".join(
                    f'"{c}" = (SELECT s."{c}" FROM mig_src."{seed_table}" s '
                    f'WHERE s.id = main."{seed_table}".id)' for c in set_cols)
                tgt.execute(
                    f'UPDATE main."{seed_table}" SET {assignments} '
                    f'WHERE id IN (SELECT id FROM mig_src."{seed_table}")'
                )

            # 4.6 密钥转接（c-lossless-upgrade D3）：只修「目标钥匙解不开」的行——
            # 依次用源库钥匙行（staged 副本 app_meta 可读：EXCLUDED_TABLES 只影响
            # INSERT 计划，不影响 ATTACH 读取）与数据目录旧钥匙文件（按本次搬运的
            # data_root 解析，不依赖 import 期常量）解密，成功者按目标钥匙重加密
            # 原地改写；两把皆解不开则保持原样，dead_keys 只报事实不断言成因。
            # 仅本次 api_configs 有迁入行时执行（幂等：可解行永不触碰）。
            if any(e["table"] == "api_configs" and e.get("rows_inserted")
                   for e in report["tables"]):
                try:
                    report["dead_keys"] = _reencrypt_dead_ciphertexts(
                        tgt, src_con, data_root)
                except Exception:  # noqa: BLE001 —— 转接失败不阻断迁入（沿用死文统计的容错口径）
                    logger.warning("migration: 密钥转接失败（按不转接处理）", exc_info=True)

            # 5 核对：FK 违规只报不删 + 书计数
            _emit("verify", tables_total=tables_total, tables_done=tables_done)
            for row in tgt.execute("PRAGMA foreign_key_check"):
                report["fk_violations"].append({"table": row[0], "rowid": row[1],
                                                "parent": row[2]})
            book_src = src_con.execute(
                "SELECT COUNT(*) FROM novels").fetchone()[0] \
                if _has_table(src_con, "novels") else 0
            book_tgt = tgt.execute("SELECT COUNT(*) FROM main.novels").fetchone()[0] \
                if _has_table(tgt, "main.novels") else 0
            report["book_count_source"] = book_src
            report["book_count_target_after"] = book_tgt
            # migrated＝本次真正写入；books 表被跳过（NOT NULL 阻塞等）时**只能是 0**——
            # 回退成目标总数会把「什么都没带过来」报成「带回了一堆」（检视 P2）
            inserted = next((e.get("rows_inserted") for e in report["tables"]
                             if e["table"] == "novels"), None)
            report["book_count_migrated"] = inserted or 0
            # 库自证来源：把本机版本与组件快照写进目标库（app_meta 不随行搬运）
            if _has_table(tgt, "main.app_meta"):
                for k, v in version_stamp_payload().items():
                    tgt.execute(
                        "INSERT INTO main.app_meta (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (k, v),
                    )
            # dead_keys 口径（c-lossless-upgrade）：搬后目标库全部不可解 enc: 行数
            # （含目标库既有死文）——文案只报事实；运行期由「密文无法解密」的
            # 503 no_key 引导承接。转接未执行（api_configs 无迁入行）时保持初值 0。
            if report.get("dead_keys"):
                report["notes"].append(
                    f"{report['dead_keys']} 条配置的 API Key 按当前加密钥匙不可解"
                    "——请在「模型配置」重新粘贴保存"
                )
            tgt.commit()
        finally:
            try:
                tgt.execute("DETACH DATABASE mig_src")
            except sqlite3.Error:
                pass
            tgt.close()
            src_con.close()


        report["complete"] = is_complete_report(report)

    except Exception:
        logger.exception("migration failed: %s", source_filename)
        report["status"] = "error"
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)
    return report


def _has_table(con: sqlite3.Connection, name: str) -> bool:
    q = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
    parts = name.split(".")
    tbl = parts[-1].strip('"')
    row = con.execute(q, (tbl,)).fetchone()
    return row is not None
