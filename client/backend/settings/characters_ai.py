"""角色 AI 能力端点（character-settings-v2 tasks 4.x）。

两条能力（design.md D6/D7）：
- POST /ai/characters/{cid}/draft?target=persona|dossier|cog
  「只补空格」以服务端此刻空值为唯一基准；targets 服务端算；脏返回域归一；
  人设是唯一覆盖型（act=replace，豁免非空检查，但空稿不落）。
- POST /ai/characters/{cid}/check
  四态 ok/warn/conflict/miss；项名与顺序服务端出（力量向/现实向两套）；
  输入缺失降级不 400；全空免调用；无副作用。

路径 /ai/characters/… 为三段（首段字面量），不会被 /ai/{stype}/{field} 两段兜底吃掉。
温度分档（spec 冻结）：人设 0.6 / 档案与认知 0.4 / 体检 0.3。
"""

from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import AITimeoutError, get_ai_client_for_novel
from ai_state import effective_model
from api_configs.usage import record_usage
from auth_local.deps import get_current_user, require_ai_access, require_novel_model
from db import get_db
from filesystem.storage import get_storage
from models.character import Character
from models.project import Novel
from settings.character_model import (
    CHAR_CHECK_STATUS,
    COG_FILL_KEYS,
    DOSSIER_FILL_KEYS,
    check_items,
    compute_targets,
)
from settings.character_service import _load_card, card_to_dict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels/{project_id}/settings", tags=["characters-ai"])

_CARD_MAX = 2000
_ROSTER_MAX = 12


def _clamp(v, n: int) -> str:
    return str(v or "")[:n]


def _parse_json(text: str, what: str) -> dict:
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        raise HTTPException(502, f"AI 返回的 {what} 无法解析，可重试")
    if not isinstance(data, dict):
        raise HTTPException(502, f"AI 返回的 {what} 结构异常，可重试")
    return data


async def _get_project(db: AsyncSession, project_id: str, user_id: str) -> Novel:
    project = await db.get(Novel, project_id)
    if project is None or project.status == "deleted" or project.user_id != user_id:
        raise HTTPException(404, "Project not found")
    return project


def _theme_of(story: dict) -> tuple[str, str]:
    return str(story.get("genre") or ""), str(story.get("genre_desc") or "")


async def _world_summary(root_path: str, limit: int = 1200) -> str:
    raw = await get_storage().read_yaml(root_path, "settings/world-setting.yaml") or {}
    if not raw:
        return ""
    lines = []
    for key in ("stage", "power", "cost"):
        if str(raw.get(key) or "").strip():
            lines.append(f"{key}：{raw[key]}")
    for entry in raw.get("factions") or []:
        if isinstance(entry, dict) and str(entry.get("value") or "").strip():
            lines.append(f"势力：{entry['value']}")
    return "\n".join(lines)[:limit]


async def _story_arc_text(root_path: str, limit: int = 600) -> str:
    story = await get_storage().read_yaml(root_path, "story.yaml") or {}
    arc = story.get("story_arc")
    if not isinstance(arc, dict):
        return ""
    parts = [str(arc.get(k) or "") for k in ("fullstory", "premise") if str(arc.get(k) or "").strip()]
    if not parts:
        ending = arc.get("ending")
        if isinstance(ending, dict):
            parts = [str(v or "") for v in ending.values() if str(v or "").strip()]
    return "\n".join(parts)[:limit]


async def _roster_text(db: AsyncSession, novel_id: str, exclude_id: str) -> str:
    cards = (
        await db.scalars(
            select(Character).where(Character.novel_id == novel_id).order_by(Character.seq)
        )
    ).all()
    lines = [
        f"{c.name}（{c.role}）：{c.persona}"
        for c in cards[:_ROSTER_MAX] if c.id != exclude_id and (c.name or c.persona)
    ]
    return "\n".join(lines)

@router.post("/ai/characters/{character_id}/draft")
async def draft_character(
    project_id: str,
    character_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """角色补全。只返回建议不落库；采纳走单格 PATCH（act 由 target 决定）。"""
    from prompts import load as load_prompt

    project = await _get_project(db, project_id, user["id"])
    target = str(body.get("target") or "")
    if target not in ("persona", "dossier", "cog"):
        raise HTTPException(400, f"未知的补全目标：{target}")

    ch = await _load_card(db, project_id, character_id)
    persona = ch.persona
    dossier = json.loads(ch.dossier or "{}")
    cog = json.loads(ch.cog or "{}")

    targets = compute_targets(dossier, cog, persona, target)
    if not targets:
        return {"ok": True, "data": {"targets": [], "cells": [], "act": "replace" if target == "persona" else "insert"}}

    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    theme_label, _theme_desc = _theme_of(story)
    world = await _world_summary(project.root_path, 400 if target != "cog" else 1200)
    story_arc = await _story_arc_text(project.root_path) if target in ("cog", "check") else ""
    cog = cog or {}

    def _lines(bucket: dict, keys) -> str:
        rows = [f"{k}：{bucket[k]}" for k in keys if str(bucket.get(k) or "").strip()]
        return "\n".join(rows) if rows else "（无）"

    if target == "persona":
        prompt = load_prompt("settings_characters_persona").format(
            title=project.name,
            theme=theme_label or "（未确认）",
            synopsis=_clamp(story.get("synopsis"), 600) or "（未填写）",
            name=ch.name or "未命名",
            role=ch.role,
            aliases="、".join(json.loads(ch.aliases or "[]")) or "无",
            dossier_lines=_lines(dossier, [k for k in dossier]),
            cog_lines="\n".join(
                f"{cog.get(k, '')}" for k in ("w1", "s1", "v1", "p2", "b1", "e3") if str(cog.get(k) or "").strip()
            ) or "（无）",
        )
        temperature = 0.6
    elif target == "dossier":
        prompt = load_prompt("settings_characters_dossier").format(
            title=project.name,
            theme=theme_label or "（未确认）",
            synopsis=_clamp(story.get("synopsis"), 600) or "（未填写）",
            world=world or "（未填写）",
            name=ch.name or "未命名",
            role=ch.role,
            filled_lines=_lines(dossier, [k for k in dossier]),
            targets="、".join(targets),
        )
        temperature = 0.4
    else:
        prompt = load_prompt("settings_characters_cog").format(
            title=project.name,
            theme=theme_label or "（未确认）",
            world_power=world or "（未填写）",
            story_arc=story_arc or "（未填写）",
            name=ch.name or "未命名",
            role=ch.role,
            dossier_lines=_lines(dossier, [k for k in dossier]),
            filled_lines=_lines(cog, [k for k in cog]),
            targets="、".join(targets),
        )
        temperature = 0.4

    client = await get_ai_client_for_novel(project_id)
    usage: dict = {}
    try:
        text = await client.chat(
            model="haiku",
            system="你是小说设定专家。只输出 JSON，不要任何其他文字。",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            json_mode=True,
            usage=usage,
        )
    except AITimeoutError:
        await record_usage(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation=f"settings_char_draft_{target}_fail"[:50],
            model=effective_model(project),
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001
        await record_usage(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation=f"settings_char_draft_{target}_fail"[:50],
            model=effective_model(project),
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e

    data = _parse_json(text, "角色补全")
    fills = data.get("fills") if isinstance(data.get("fills"), dict) else {}
    if target == "persona":
        value = _clamp(data.get("persona"), 300)
        cells = [{"path": "persona", "value": value}] if value else []
        skipped = []
    else:
        allowed = set(DOSSIER_FILL_KEYS if target == "dossier" else COG_FILL_KEYS)
        cells, skipped = [], []
        for key, value in fills.items():
            if key not in allowed or key not in set(targets):
                continue  # 未知键 / 越界键静默丢（模型噪音）
            text_v = _clamp(value, 300)
            if not text_v.strip():
                continue
            cells.append({"path": f"{target}.{key}", "value": text_v})
        skipped = [
            {"key": s_.get("key"), "why": _clamp(s_.get("why"), 60)}
            for s_ in (data.get("skipped") or [])[:6] if isinstance(s_, dict)
        ]
    if not cells:
        await record_usage(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation=f"settings_char_draft_{target}_fail"[:50],
            model=effective_model(project),
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, "AI 没给出可用的内容，可重试")

    await record_usage(
        db, user_id=user["id"], project_id=project.id,
        api_config_id=project.ai_config_id,
        operation=f"settings_char_draft_{target}"[:50],
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
    )
    return {"ok": True, "data": {"targets": targets, "cells": cells, "skipped": skipped, "act": "replace" if target == "persona" else "insert"}}


@router.post("/ai/characters/{character_id}/check")
async def check_character(
    project_id: str,
    character_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """角色 × 整体设定体检。四态；服务端项名；降级不 400；无副作用。"""
    from prompts import load as load_prompt

    project = await _get_project(db, project_id, user["id"])
    ch = await _load_card(db, project_id, character_id)
    if ch.role == "路人":
        return {"ok": True, "data": {
            "items": [], "degraded": True,
            "degraded_reasons": ["路人卡只有基础档案，没有可对照的认知层"],
            "verdict": "路人卡不参与体检",
        }}

    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    theme_label, theme_desc = _theme_of(story)
    world = await _world_summary(project.root_path)
    story_arc = await _story_arc_text(project.root_path)
    roster = await _roster_text(db, project_id, ch.id)

    synopsis = str(story.get("synopsis") or "")
    world_raw_filled = bool(world.strip())
    no_power = "power：" not in world  # 世界没写力量体系 → 现实向项名
    items_spec = check_items(has_power=not no_power and world_raw_filled)
    item_names = [name for name, _goto in items_spec]
    goto_map = dict(items_spec)

    degraded_reasons: list[str] = []
    if not synopsis.strip():
        degraded_reasons.append("简介未填")
    if not theme_label:
        degraded_reasons.append("题材未确认")
    if not world.strip():
        degraded_reasons.append("世界未填")
    if not story_arc.strip():
        degraded_reasons.append("主线未填")

    card_view = card_to_dict(ch)
    card_text = json.dumps(
        {k: card_view[k] for k in ("name", "role", "persona", "dossier", "cog")},
        ensure_ascii=False,
    )[:_CARD_MAX]

    def _miss_row(name: str, note: str) -> dict:
        return {"name": name, "status": "miss", "note": note, "goto": goto_map.get(name, "")}

    if len(degraded_reasons) >= 4:
        return {"ok": True, "data": {
            "items": [_miss_row(n, f"输入缺失：{r}——先去补，再体检更准") for n, r in
                      zip(item_names, degraded_reasons + ["设定缺失"] * len(item_names))],
            "degraded": True, "degraded_reasons": degraded_reasons,
            "verdict": "简介 / 题材 / 世界 / 主线都还没写，体检无从对照",
        }}
    if not str(ch.persona or "").strip() and not str(ch.name or "").strip():
        return {"ok": True, "data": {
            "items": [_miss_row(n, "这张卡还没写——先写两句再体检") for n in item_names],
            "degraded": True, "degraded_reasons": ["角色卡全空"],
            "verdict": "先把这张卡写几句，再体检",
        }}

    prompt = load_prompt("settings_characters_check").format(
        card=card_text,
        synopsis=_clamp(synopsis, 600) or "（未填写）",
        theme=theme_label or "（未确认）",
        theme_desc=theme_desc or "（无）",
        world=world or "（未填写）",
        story_arc=story_arc or "（未填写）",
        roster=roster or "（暂无其他角色）",
        mode_line="本书为现实向：没有超自然力量，用物理与法律规则判断" if no_power else "",
        items=" / ".join(item_names),
    )

    client = await get_ai_client_for_novel(project_id)
    usage: dict = {}
    try:
        text = await client.chat(
            model="haiku",
            system="你是小说设定一致性审校。只输出 JSON，不要任何其他文字。",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            json_mode=True,
            usage=usage,
        )
    except AITimeoutError:
        await record_usage(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation="settings_char_check_fail",
            model=effective_model(project),
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001
        await record_usage(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation="settings_char_check_fail",
            model=effective_model(project),
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, f"体检失败，可重试：{e!s}") from e

    data = _parse_json(text, "角色体检")

    def _name_key(n: str) -> str:
        return re.sub(r"[\s×xX*·・]", "", n)

    ai_items: dict = {}
    for item in (data.get("items") if isinstance(data, dict) else []) or []:
        if not isinstance(item, dict):
            continue
        name = _clamp(item.get("name"), 40)
        status = str(item.get("status", "")).strip()
        nk = _name_key(name)
        official = next((n for n in item_names if _name_key(n) == nk), None)
        if official and nk not in ai_items and status in CHAR_CHECK_STATUS:
            ai_items[nk] = {
                "name": official, "status": status,
                "note": _clamp(item.get("note"), 120),
                "goto": goto_map.get(official, ""),
            }

    items_out = [
        ai_items.get(_name_key(n)) or _miss_row(n, "AI 未给出该项，可重跑体检")
        for n in item_names
    ]
    if not synopsis.strip():
        for row in items_out:
            if "简介" in row["name"]:
                row.update(status="miss", note="输入缺失：简介未填——先去补简介，再重新体检")
    if not theme_label:
        for row in items_out:
            if "题材" in row["name"]:
                row.update(status="miss", note="输入缺失：题材未确认——先去题材页确认，再重新体检")
    if not world.strip():
        for row in items_out:
            if "世界" in row["name"] or "势力" in row["name"]:
                row.update(status="miss", note="输入缺失：世界未填——先去世界页补力量与势力，再重新体检")
    if not story_arc.strip():
        for row in items_out:
            if "主线" in row["name"]:
                row.update(status="miss", note="输入缺失：主线未填——先去主线页，再重新体检")

    await record_usage(
        db, user_id=user["id"], project_id=project.id,
        api_config_id=project.ai_config_id,
        operation="settings_char_check",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
    )
    verdict = _clamp(data.get("verdict"), 120) if isinstance(data, dict) else ""
    if degraded_reasons and not verdict:
        verdict = "体检输入不完整（" + "、".join(degraded_reasons) + "），结果仅供参考"
    return {"ok": True, "data": {
        "items": items_out, "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons, "verdict": verdict,
    }}
