"""备份导出/恢复导入路由（c-novel-export-roundtrip）。

PR0：旧库留档检测（legacy-db/status）。
PR1：备份导出任务化（目录选择+后端直写+真进度）+ 配置包掩码预览。
包导入端点随 PR2 落地。
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_local.middleware import get_current_user
from config import DATA_ROOT
from db import get_db
from legacy_archive import inspect_library

# 持有自己的 APIRouter，由 main.py 显式 include（与 account/devices 同款）。
router = APIRouter(prefix="/api/backup", tags=["backup"])


def _scan_legacy_archives(data_root: Path) -> list[dict]:
    """枚举 novel.legacy-*.db 留档，最新在前；逐个只读体检。"""
    items = []
    for f in sorted(data_root.glob("novel.db.legacy-*"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = f.stat()
        info = inspect_library(f)
        items.append({
            "filename": f.name,
            "size_bytes": stat.st_size,
            "archived_at": int(stat.st_mtime),
            "book_count": info.get("book_count"),
            "unreadable": info.get("unreadable", False),
        })
    return items


@router.get("/legacy-db/status")
async def legacy_db_status(user: dict = Depends(get_current_user)):
    """首启检测/设置徽标数据源（quiet：前端对 401/失败自行降级，不弹提示）。"""
    root = Path(DATA_ROOT)
    archives = _scan_legacy_archives(root)
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


@router.post("/export/start")
async def export_start(
    body: ExportStartBody,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    from backup import export as export_mod

    if body.kind == "backup":
        if not body.target_dir:
            raise HTTPException(422, "缺少保存目录")
        started = export_mod.start_backup_job(
            target_dir=body.target_dir,
            user_id=user["id"],
            include_config=body.include_config,
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
async def export_status(user: dict = Depends(get_current_user)):
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
