"""备份导出/恢复导入路由（c-novel-export-roundtrip）。

PR0：旧版数据检测（legacy-db/status——c-db-per-version 起数据源改为候选扫描）。
PR1：备份导出任务化（目录选择+后端直写+真进度）+ 配置包掩码预览。
包导入端点随 PR2 落地。
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_local.middleware import get_current_user, get_user_or_local
from config import DATA_ROOT
from db import get_db
from db_lifecycle import scan_migration_candidates
from schema_version import app_version

# 持有自己的 APIRouter，由 main.py 显式 include（与 account/devices 同款）。
router = APIRouter(prefix="/api/backup", tags=["backup"])


def _scan_prior_libraries(data_root: Path) -> list[dict]:
    """本机旧版数据盘点（最新的在前）。

    c-db-per-version：数据源改由**候选扫描**供给——「升级即整库留档」的 `.legacy-*`
    机制已退役，该端点此前恒 `present:false`（死面）。载荷键保持不变，登录页计数行
    与设置徽标消费方零改动。
    """
    from config import DATABASE_URL

    active = Path(DATABASE_URL.split("///")[-1])
    items = []
    for it in scan_migration_candidates(data_root, app_version(), active):
        items.append({
            "filename": it["filename"],
            "size_bytes": it["size_bytes"],
            "archived_at": it["mtime"],
            "book_count": it["book_count"],
            "unreadable": it["unreadable"],
        })
    return items


@router.get("/legacy-db/status")
async def legacy_db_status():
    """首启检测/设置徽标/登录页计数行数据源（loginless-data-exit：免登——
    登录页升级卡与找回向导都要在登录前读它；只读旧文件，无敏感载荷）。"""
    root = Path(DATA_ROOT)
    archives = _scan_prior_libraries(root)
    latest = archives[0] if archives else None
    return {"code": 0, "data": {
        "present": bool(archives),
        "filename": latest["filename"] if latest else None,
        "book_count": latest["book_count"] if latest else None,
        "size_bytes": latest["size_bytes"] if latest else None,
        "archived_at": latest["archived_at"] if latest else None,
        "all": archives,
    }}


# ── PR1 · 备份导出（目录选择 + 后端直写 + 真进度） ────────────────────────────


class ExportStartBody(BaseModel):
    kind: str  # backup | single
    target_dir: str | None = None      # kind=backup：保存目录
    target_file: str | None = None     # kind=single：完整文件路径
    book_id: str | None = None         # kind=single：书 id
    include_config: bool = True        # kind=backup：是否同时产配置包


class ImportParseBody(BaseModel):
    paths: list[str]                   # 恢复包文件路径（资产包/配置包，至少一个）


class ImportPersistBody(BaseModel):
    paths: list[str]
    include_config: bool = True        # 是否恢复配置包


def _mask_config_block(cfg: dict | None) -> dict | None:
    """预览脱敏：配置块的密钥一律 *** 不回传前端。"""
    if not cfg:
        return cfg
    import copy

    out = copy.deepcopy(cfg)
    if isinstance(out.get("user"), dict) and "api_key" in out["user"]:
        out["user"]["api_key"] = "***"
    for c in out.get("api_configs") or []:
        if "api_key" in c:
            c["api_key"] = "***"
    return out


def _guard_target_outside_data_root(*candidate: str | None) -> None:
    """导出目标路径守卫（loginless-data-exit）：拒绝落在 DATA_ROOT 内——
    防「导出写文件」路径直指 novel.db / config.json（免登态尤其必须）。
    读 config.DATA_ROOT 实时值（模块级 from-import 会固化，测试 monkeypatch 失真）。"""
    import config as _config

    root = Path(_config.DATA_ROOT).resolve()
    for c in candidate:
        if not c:
            continue
        p = Path(c)
        # 显式路径前缀判定 + resolve 后包含判定双保险（相对路径/.. 穿越都兜住）
        try:
            rp = p.resolve()
        except OSError:
            rp = p
        if rp == root or root in rp.parents:
            raise HTTPException(422, "保存位置不能选在应用数据目录内，请换个文件夹")


@router.post("/export/start")
async def export_start(
    body: ExportStartBody,
    user: dict = Depends(get_user_or_local),
    db=Depends(get_db),
):
    from backup import export as export_mod

    # loginless-data-exit：免登态（user["id"] is None）整库无主化、强制不含
    # 配置包（配置含 api_key 明文——永不免登）；登录态语义不变
    loginless = user["id"] is None
    include_config = False if loginless else body.include_config
    _guard_target_outside_data_root(body.target_dir, body.target_file)

    if body.kind == "backup":
        if not body.target_dir:
            raise HTTPException(422, "缺少保存目录")
        started = export_mod.start_backup_job(
            target_dir=body.target_dir,
            user_id=user["id"],
            include_config=include_config,
        )
    elif body.kind == "single":
        if not (body.target_file and body.book_id):
            raise HTTPException(422, "缺少保存路径或作品")
        started = export_mod.start_single_job(
            target_file=body.target_file,
            user_id=user["id"],
            book_id=body.book_id,
        )
    else:
        raise HTTPException(422, f"未知导出类型：{body.kind}")
    if started is None:
        # 单飞是全局的（备份/单书/下载互斥，job_runner 单源）；409 带 running_kind
        # 让前端说人话（「已有备份在进行」/「已有下载在进行」）。
        from job_runner import running_kind

        kind = running_kind()
        label = {"backup": "备份", "single": "导出", "download": "下载"}.get(kind or "", "导出")
        raise HTTPException(
            409, detail={"message": f"已有{label}任务在进行中", "running_kind": kind}
        )
    return {"code": 0, "data": started}


@router.get("/export/status")
async def export_status(user: dict = Depends(get_user_or_local)):
    from backup import export as export_mod

    return {"code": 0, "data": export_mod.job_status()}


@router.get("/export/config/preview")
async def export_config_preview(user: dict = Depends(get_current_user), db=Depends(get_db)):
    from backup import export as export_mod

    return {"code": 0, "data": await export_mod.config_preview(db, user["id"])}


@router.post("/import/parse")
async def import_parse(
    body: ImportParseBody,
    user: dict = Depends(get_current_user),
):
    """恢复预览：解析包归并出作品块+配置块（密钥脱敏）+warnings，供确认弹层。"""
    import zipfile

    from backup.importer import parse_package

    if not body.paths:
        raise HTTPException(422, "缺少恢复包路径")
    try:
        info = parse_package(body.paths)
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise HTTPException(422, f"备份包无法识别：{e}")
    if not info["books"] and not info["config"]:
        raise HTTPException(422, "无法识别的备份包（未找到作品或配置内容）")
    return {
        "code": 0,
        "data": {
            "books": info["books"],
            "config": _mask_config_block(info["config"]),
            "warnings": info["warnings"],
            "schema_version": info["schema_version"],
        },
    }


@router.post("/import/persist")
async def import_persist(
    body: ImportPersistBody,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """恢复落库：逐书原子（单书 SAVEPOINT 全成全败）+ 配置恢复 + 智能挂回。"""
    import zipfile

    from backup.importer import persist_package

    if not body.paths:
        raise HTTPException(422, "缺少恢复包路径")
    try:
        summary = await persist_package(
            db, user["id"], body.paths, include_config=body.include_config
        )
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise HTTPException(422, f"恢复失败：{e}")
    return {"code": 0, "data": summary}
