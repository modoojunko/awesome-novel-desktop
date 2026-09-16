"""量化参数端点（style-settings-v2 tasks 3.1/3.2）。

- GET  /settings/style-quant        全文（无则 {}；免费可见空态所需）
- PUT  /settings/style-quant        仅受理 locks（行级锁定切换；数值忽略）
- GET  /settings/style-samples      样本两路（novel-samples/ 文件＋已归档章节）＋区间判定

注册顺序必须先于 settings/router.py 的 GET /settings/{type} 兜底（main.py，
characters/hooks 先例）。style-quant 键仿 threads：route_relative_path 专用键，
不进 PATH_TO_KEY——通用 /settings/{type} 天然拒绝该类型。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import get_current_user
from db import get_db
from filesystem.paths import STYLE_QUANT_PATH
from filesystem.storage import get_storage
from models.archive import Archive
from models.chapter import Chapter
from novels.service import get_novel
from settings import style_quant_model as qm

router = APIRouter(prefix="/api/novels/{project_id}/settings", tags=["style-quant"])


async def _load_quant(root_path: str) -> dict:
    return qm.quant_doc(await get_storage().read_yaml(root_path, STYLE_QUANT_PATH) or {})


@router.get("/style-quant")
async def get_style_quant(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    return await _load_quant(project.root_path)


@router.put("/style-quant")
async def put_style_quant(
    project_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """唯一前端写路径：行级锁定切换。基线数值字段服务端只写——body 里的
    baseline/details/confidence 一律忽略（评审 P0：防表单整卡回踩只读基线）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    doc = await _load_quant(project.root_path)
    locks = body.get("locks") if isinstance(body, dict) else None
    if locks is not None:
        if not isinstance(locks, dict):
            raise HTTPException(400, "只支持锁定切换：body 传 {locks: {行名: bool}}")
        doc = qm.apply_locks(doc, locks)
    # locks 缺省＝无操作成功（基线数值等字段一律忽略——服务端只写，评审 P0）
    await get_storage().write_yaml(project.root_path, STYLE_QUANT_PATH, doc)
    return doc


@router.get("/style-samples")
async def list_style_samples(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """蒸馏样本两路：novel-samples/ 目录文件＋已归档章节；合计字数＋区间判定。

    字数＝去空白字符数（与疲劳词统计口径一致）。文件名做穿越校验：
    只认目录直下 .md/.txt，任何 .. / 子目录条目跳过。
    """
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    files: list[dict] = []
    samples_dir = os.path.join(project.root_path, "novel-samples")
    if os.path.isdir(samples_dir):
        for name in sorted(os.listdir(samples_dir)):
            if not name.lower().endswith((".md", ".txt")):
                continue
            safe = os.path.realpath(os.path.join(samples_dir, name))
            if os.path.dirname(safe) != os.path.realpath(samples_dir) or not os.path.isfile(safe):
                continue
            try:
                with open(safe, encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue
            chars = len("".join(text.split()))
            if chars:
                files.append({"name": name, "chars": chars})

    chapters: list[dict] = []
    rows = await db.execute(
        select(Archive)
        .join(Chapter, Chapter.id == Archive.chapter_id)
        .where(Chapter.project_id == project.id)
        .order_by(Archive.archived_at.asc())
    )
    for a in rows.scalars():
        chars = len("".join((a.content or "").split()))
        if chars:
            chapters.append({"id": a.chapter_id, "label": a.title or "已归档章节", "chars": chars})

    total = sum(f["chars"] for f in files) + sum(c["chars"] for c in chapters)
    in_range = qm.SAMPLE_MIN <= total <= qm.SAMPLE_MAX
    hint = ""
    if total < qm.SAMPLE_MIN:
        hint = f"样本合计 {total} 字，少于 {qm.SAMPLE_MIN} 字统计噪声大——再补一些你认可的文章"
    elif total > qm.SAMPLE_MAX:
        hint = f"样本合计 {total} 字，超过 {qm.SAMPLE_MAX} 字——挑最有代表性的几章"
    return {
        "files": files,
        "chapters": chapters,
        "total": total,
        "min": qm.SAMPLE_MIN,
        "max": qm.SAMPLE_MAX,
        "in_range": in_range,
        "hint": hint,
    }
