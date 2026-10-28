"""卷节奏三 AI 动作（c-volume-pacing）：排段 / 按这本书调一版套路 / 润一遍步骤说明。

全部「出预览不落库」——采纳走 PUT /volumes/{ref}/pacing（排段采纳补 planned 标记）。
归 `ai-plan` 族（标准档起），生成/重试/计量照 volumes/ai_plan 同款（_generate 复用）。

输入边界（防循环，见设计说明）：排段读**本卷卷纲**＋章数目标＋上一卷结尾＋节奏配置；
调套路读题材/简介/主线/结局/世界观/人物＋六预设菜单，**不读卷纲**；润说明只看步表。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import (
    ai_feature,
    get_current_user,
    require_ai_access,
    require_novel_model,
)
from db import get_db
from filesystem.storage import get_storage
from models.volume import Volume
from novels.service import get_novel
from prompts import load_layers
from volumes import pacing as pc
from volumes.ai_plan import _generate, _parse_json, resolve_prev_ending

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels/{project_id}", tags=["volume-pacing"])


class PolishBody(BaseModel):
    steps: list[dict] = Field(default_factory=list)


async def _volume_row(db: AsyncSession, project_id: str, ref: str) -> Volume:
    try:
        vol_no = int(ref.replace("vol-", "").removesuffix(".yaml"))
    except ValueError as exc:
        raise HTTPException(404, "Volume not found") from exc
    vol = (
        await db.execute(
            select(Volume).where(
                Volume.project_id == project_id, Volume.volume_no == vol_no
            )
        )
    ).scalar_one_or_none()
    if vol is None:
        raise HTTPException(404, "Volume not found")
    return vol


def _volume_config(vol: Volume) -> dict:
    """卷列配置 → 归一；未配置 422（排段/润说明需要一份已保存的配置）。"""
    try:
        config = pc.normalize_pacing_config(json.loads(vol.pacing_json or ""))
    except (ValueError, TypeError):
        config = None
    if config is None:
        raise HTTPException(
            422, "这一卷还没保存节奏配置——先在「节奏」页签保存，再让 AI 排段"
        )
    return config


async def _volume_material(db: AsyncSession, project, vol: Volume, config: dict) -> str:
    """排段素材：卷纲四问＋章数目标＋上一卷结尾＋节奏配置（作家语言块）。"""
    prev = await resolve_prev_ending(db, project, vol.volume_no)
    target = int(vol.chapter_target or 0)
    lines = [
        "【卷纲四问】",
        f"- 这一卷讲什么：{vol.summary or '（未填）'}",
        f"- 主要冲突：{vol.core_conflict or '（未填）'}",
        f"- 这一卷的坎：{(vol.antagonist_type or '')}{' · ' if vol.antagonist_type else ''}{vol.antagonist_line or '（未填）'}",
        f"- 卷末收在哪里：{vol.ending or '（未填）'}",
        f"【章数目标】{target if target else '未设（按每段默认估）'}",
        f"【上一卷的结尾】{prev['text']}（{prev['source']}）",
        "【节奏配置】",
        f"- 套路：{pc.preset_or_default(config['preset'])['label']}（{' → '.join(s['n'] for s in config['steps'])}）",
        f"- 一段剧情约 {config['steps_len']} 章",
    ]
    return "\n".join(lines)


@router.post("/volumes/{ref}/pacing/plan")
@ai_feature("ai-plan")
async def ai_pacing_plan(
    project_id: str,
    ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """排段预览（不落库）：照本卷卷纲把节奏切成段，给每段强度爬坡说明。

    段边界由配置实时推导（末段吸收余数）；AI 产出＝各段怎么走的解读，供作家
    采纳前审阅。采纳＝前端 PUT 卷配置（planned 置真）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    vol = await _volume_row(db, project_id, ref)
    config = _volume_config(vol)
    material = await _volume_material(db, project, vol, config)

    _sys_t, _usr_t = load_layers("volume_pacing_plan")
    user_msg = _usr_t.replace("<<material>>", material)
    raw, _u = await _generate(
        project, _sys_t, user_msg, temperature=0.5, db=db, user=user,
        operation="volume_pacing_plan",
    )
    parsed = _parse_json(raw)
    notes: list[dict] = []
    if isinstance(parsed, dict):
        raw_notes = parsed.get("notes")
        if isinstance(raw_notes, list):
            for item in raw_notes[:24]:
                if isinstance(item, dict) and str(item.get("text") or "").strip():
                    try:
                        seg = int(item.get("seg"))
                    except (TypeError, ValueError):
                        continue
                    notes.append({"seg": seg, "text": str(item["text"]).strip()[:160]})
    if not notes:
        text = (raw or "").strip()[:400]
        return {"ok": True, "degraded": True, "notes": [], "text": text}
    return {"ok": True, "degraded": False, "notes": notes, "text": ""}


async def _tailor_material(project, config: dict | None) -> str:
    """调套路素材：题材/简介/主线/结局/世界/人物（精简块）＋六预设菜单＋当前配置。"""
    storage = get_storage()
    story = await storage.read_yaml(project.root_path, "story.yaml") or {}
    theme = str(story.get("genre") or "")
    sub = str(story.get("sub_genre") or "")
    menu = "\n".join(
        f"- {p['label']}（{p['sub']}）：步＝{'/'.join(s['n'] for s in p['steps'])}"
        for p in pc.PACING_PRESETS.values()
    )
    lines = [
        f"【题材】{theme or '（未填）'}{' · ' + sub if sub else ''}",
        f"【简介】{str(story.get('synopsis') or '（未填）')[:600]}",
        f"【主线全景】{str(story.get('story_arc', {}).get('fullstory') if isinstance(story.get('story_arc'), dict) else '') or '（未填）'}"[:600],
        f"【题材→套路建议】{pc.preset_for_genre(theme, sub) or '（无）'}（仅参照，你可以不选它）",
        "【六套预设菜单】",
        menu,
    ]
    if config:
        lines.append(
            f"【当前配置】{pc.preset_or_default(config['preset'])['label']} · 每段 {config['steps_len']} 章"
        )
    return "\n".join(lines)


@router.post("/volumes/{ref}/pacing/tailor")
@ai_feature("ai-plan")
async def ai_pacing_tailor(
    project_id: str,
    ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """按这本书调一版套路（不落库）：读题材、简介和主线，出套路＋步表＋每段几章建议。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    vol = await _volume_row(db, project_id, ref)
    try:
        config = pc.normalize_pacing_config(json.loads(vol.pacing_json or ""))
    except (ValueError, TypeError):
        config = None
    material = await _tailor_material(project, config)

    _sys_t, _usr_t = load_layers("volume_pacing_tailor")
    user_msg = _usr_t.replace("<<material>>", material)
    raw, _u = await _generate(
        project, _sys_t, user_msg, temperature=0.6, db=db, user=user,
        operation="volume_pacing_tailor",
    )
    parsed = _parse_json(raw)
    if not isinstance(parsed, dict) or parsed.get("preset") not in pc.PACING_PRESETS:
        return {
            "ok": True, "degraded": True, "config": None,
            "note": (raw or "").strip()[:300] or "AI 没给出可用的套路建议，请重试",
        }
    config = pc.build_config(
        str(parsed["preset"]),
        pc._clamp_len(parsed.get("steps_len"), int(pc.preset_or_default(parsed["preset"])["steps_len"])),
        steps=parsed.get("steps") if isinstance(parsed.get("steps"), list) else None,
    )
    note = str(parsed.get("note") or "").strip()[:160]
    return {"ok": True, "degraded": False, "config": config, "note": note}


@router.post("/volumes/{ref}/pacing/polish")
@ai_feature("ai-plan")
async def ai_pacing_polish(
    project_id: str,
    ref: str,
    body: PolishBody,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """润一遍步骤说明（不落库）：只顺措辞；步数、步序、步名都不动。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    await _volume_row(db, project_id, ref)  # 存在性校验
    steps = pc.normalize_steps(body.steps, pc.DEFAULT_PRESET_KEY)
    if not steps:
        raise HTTPException(422, "还没有可润的步骤说明")

    _sys_t, _usr_t = load_layers("volume_pacing_polish")
    step_lines = "\n".join(f"{i + 1}. {s['n']}：{s['t']}" for i, s in enumerate(steps))
    user_msg = _usr_t.replace("<<steps>>", step_lines)
    raw, _u = await _generate(
        project, _sys_t, user_msg, temperature=0.4, db=db, user=user,
        operation="volume_pacing_polish",
    )
    parsed = _parse_json(raw)
    out: list[dict] = []
    if isinstance(parsed, dict) and isinstance(parsed.get("steps"), list):
        raw_steps = parsed["steps"]
        if isinstance(raw_steps, list):
            for i, item in enumerate(raw_steps[: len(steps)]):
                if isinstance(item, dict):
                    t = str(item.get("t") or "").strip()[:80]
                    out.append({"n": steps[i]["n"], "t": t or steps[i]["t"]})
    if len(out) != len(steps):
        return {
            "ok": True, "degraded": True, "steps": steps,
            "note": (raw or "").strip()[:200] or "AI 没给出可用的润色结果，请重试",
        }
    return {"ok": True, "degraded": False, "steps": out, "note": ""}
