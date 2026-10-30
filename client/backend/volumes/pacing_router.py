"""卷节奏端点（c-volume-pacing）。

- GET  /api/novels/{project_id}/pacing/presets        六套预设＋书级默认＋题材建议
- PUT  /api/novels/{project_id}/pacing/book-default   书级默认（套路键＋每段几章）
- GET  /api/novels/{project_id}/volumes/{ref}/pacing  卷配置＋展示预填＋段表
- PUT  /api/novels/{project_id}/volumes/{ref}/pacing  保存卷配置（归一后落列）

拍位注入不在本文件——消费方（拆章/剧情/推演/正文/体检）各自调 volumes/pacing.py
的查询函数。路径避开 /volumes/{ref} 单段命名空间（/pacing/* 独立前缀，无次序
耦合）。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import get_current_user
from db import get_db
from filesystem.storage import get_storage
from models.volume import Volume
from novels.service import get_novel
from settings import book_prefs_model as bm
from volumes import pacing as pc

router = APIRouter(prefix="/api/novels/{project_id}", tags=["volume-pacing"])


async def _get_volume_row(db: AsyncSession, project_id: str, ref: str) -> Volume | None:
    """按 /volumes/{ref} 同口径解析 ref（容 vol-N），返回 ORM 行供读写列。"""
    try:
        vol_no = int(ref.replace("vol-", "").removesuffix(".yaml"))
    except ValueError:
        return None
    return (
        await db.execute(
            select(Volume).where(
                Volume.project_id == project_id, Volume.volume_no == vol_no
            )
        )
    ).scalar_one_or_none()


def _parse_pacing(vol) -> dict | None:
    """卷列 JSON → 归一配置；脏值一律按未配置（不抛错，不阻塞读）。"""
    if not vol or not vol.pacing_json:
        return None
    try:
        return pc.normalize_pacing_config(json.loads(vol.pacing_json))
    except (ValueError, TypeError):
        return None


async def _book_default(doc: dict) -> dict | None:
    return pc.book_pacing_default(doc)


async def _theme_of(project) -> tuple[str, str]:
    """题材口径与设定页同源：大类/子类都在 story.yaml（genre/sub_genre 键）。"""
    try:
        story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    except Exception:  # noqa: BLE001 — 读不到按未设兜底
        story = {}
    return str(story.get("genre") or ""), str(story.get("sub_genre") or "")


@router.get("/pacing/presets")
async def get_pacing_presets(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """六套预设全文＋书级默认现值＋题材建议（设定页块与卷页签共用一次取数）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    theme, sub = await _theme_of(project)
    from filesystem.paths import BOOK_PREFS_PATH

    prefs = await get_storage().read_yaml(project.root_path, BOOK_PREFS_PATH)
    book_default = pc.book_pacing_default(prefs)
    suggested = pc.preset_for_genre(theme, sub)
    return {
        "presets": list(pc.PACING_PRESETS.values()),
        "default_key": pc.DEFAULT_PRESET_KEY,
        "book_default": book_default,
        "suggested_key": suggested,
        "theme": theme,
        "sub_genre": sub,
    }


@router.put("/pacing/book-default")
async def put_pacing_book_default(
    project_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """书级默认（套路键＋每段几章）：题材设定页「全书默认节奏」块的写路径。

    与 book-prefs 同一 KV 文件——直接复用其读写（pacing 字段的校验在
    book_prefs_router 已实现，这里按同款规则受理成对字段）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    if not isinstance(body, dict):
        raise HTTPException(400, "全书默认节奏需为对象")
    preset = str(body.get("preset") or "")
    if preset not in pc.PACING_PRESETS:
        raise HTTPException(400, "未知的剧情套路")
    try:
        steps_len = int(body.get("steps_len"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "一段剧情讲几章需为整数") from exc
    if not pc.LEN_MIN <= steps_len <= pc.LEN_MAX:
        raise HTTPException(400, f"一段剧情讲几章需在 {pc.LEN_MIN}-{pc.LEN_MAX} 之间")

    from filesystem.paths import BOOK_PREFS_PATH

    doc = await get_storage().read_yaml(project.root_path, BOOK_PREFS_PATH) or {}
    doc[bm.PACING_PRESET_FIELD] = preset
    doc[bm.PACING_STEPS_LEN_FIELD] = steps_len
    await get_storage().write_yaml(project.root_path, BOOK_PREFS_PATH, doc)
    return {"preset": preset, "steps_len": steps_len}


@router.get("/volumes/{ref}/pacing")
async def get_volume_pacing(
    project_id: str,
    ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """卷配置＋展示预填＋生效配置＋段表（页签一次取全）。

    config＝卷列已保存且可解析的配置（None＝未配置/读不出）；prefill/source＝
    展示预填链（上一卷 → 书默认 → 题材映射 → 兜底），语义与升级前一致；
    effective/effective_source＝实际会进注入的完整配置（卷列 → 书默认 → 空）；
    config_present/config_invalid 区分「没存」与「存了但读不出」；
    plan＝章数目标×每段几章的段表口径（effective 优先，仅无生效时用预填预览）。
    """
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    vol = await _get_volume_row(db, project_id, ref)
    if vol is None:
        raise HTTPException(404, "Volume not found")

    config = _parse_pacing(vol)
    config_present = bool(vol.pacing_json)
    config_invalid = config_present and config is None
    from filesystem.paths import BOOK_PREFS_PATH

    try:
        prefs = await get_storage().read_yaml(project.root_path, BOOK_PREFS_PATH)
    except Exception:  # noqa: BLE001 — 与注入侧同口径：读不到书默认按未设
        prefs = None
    book_default = pc.book_pacing_default(prefs)
    effective, effective_source = pc.effective_of(config, book_default, vol.volume_no)
    theme, sub = await _theme_of(project)

    source = "genre"
    prefill = None
    if config:
        source = "volume"
        prefill = config
    else:
        # 预填链：上一卷（卷号更小、已配置）→ 书默认 → 题材映射
        prev = await _prev_pacing(db, project, vol)
        if prev:
            prefill = prev
            source = "prev"
        elif book_default:
            prefill = pc.prefill_chain(None, book_default, theme, sub)
            source = "book"
        else:
            prefill = pc.prefill_chain(None, None, theme, sub)

    target = int(vol.chapter_target or 0)
    steps_len = int((effective or prefill or {}).get("steps_len", 3))
    plan = pc.segment_plan(target, steps_len)
    return {
        "config": config,
        "prefill": prefill,
        "source": source,
        "effective": effective,
        "effective_source": effective_source,
        "config_present": config_present,
        "config_invalid": config_invalid,
        "book_default": book_default,
        "plan": {"target": target, "steps_len": steps_len, **plan},
        "presets": list(pc.PACING_PRESETS.values()),
        "theme": theme,
        "sub_genre": sub,
    }


async def _prev_pacing(db: AsyncSession, project, vol) -> dict | None:
    """上一卷（卷号更小的最大卷号）已保存的节奏配置；无 → None。"""
    from sqlalchemy import select

    from models.volume import Volume

    row = (
        await db.execute(
            select(Volume)
            .where(Volume.project_id == project.id, Volume.volume_no < vol.volume_no)
            .order_by(Volume.volume_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None or not row.pacing_json:
        return None
    try:
        return pc.normalize_pacing_config(json.loads(row.pacing_json))
    except (ValueError, TypeError):
        return None


@router.put("/volumes/{ref}/pacing")
async def put_volume_pacing(
    project_id: str,
    ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """保存卷节奏配置（编辑态「保存」；排段采纳也走此口径补 planned 标记）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    vol = await _get_volume_row(db, project_id, ref)
    if vol is None:
        raise HTTPException(404, "Volume not found")
    config = pc.normalize_pacing_config(body)
    if config is None:
        raise HTTPException(400, "节奏配置不完整：需选一个剧情套路")
    vol.pacing_json = json.dumps(config, ensure_ascii=False)
    await db.commit()
    return {"config": config}
