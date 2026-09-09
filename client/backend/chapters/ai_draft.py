"""章纲 AI 起草（outline-ai-draft）。

素材包 = 主线卡 + 前情/设定（复用 build_chapter_context）+ 本章现有章纲（改写基底）；
产物只返回不落库，由前端表单承接；校验失败 502 可重试（与 prompt 润色同模式）。
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import get_ai_client
from auth_local.deps import require_ai_access
from auth_local.middleware import get_current_user
from db import get_db
from filesystem.storage import get_storage
from novels.service import get_novel
from prompts import load as load_prompt
from workflow.engine import _validate_ref, load_chapter
from write.chapter_writer import (
    _CH1_PREVIOUS,
    build_chapter_context,
    strip_code_fences,
)

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/outline", tags=["chapters"]
)

_SCENE_WEIGHTS = {"high", "mid", "low"}
_SCENE_FOCUS = {"核心冲突", "人物情绪", "信息差"}
_PAYOFF_KINDS = {"clue", "reveal", "twist", "emotion", "power", "relation", "relief"}
_PAYOFF_LOCATIONS = {"前段", "中段", "后段"}


def _clamp_word_target(v) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return min(6000, max(500, n))


def _str_list(v) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()]


def _seg_words(v) -> int:
    """段落字数规整：字符串/非法值转 int，失败回落 800（与 word_target clamp 同风格）。"""
    try:
        return int(v)
    except (TypeError, ValueError):
        return 800


def _sanitize_draft(d: dict) -> dict | None:
    """字段级兜底（与 chapterForm 回读同口径）；骨架缺失返回 None → 502。"""
    outline = d.get("outline") if isinstance(d.get("outline"), dict) else {}
    memo = d.get("memo") if isinstance(d.get("memo"), dict) else {}
    emotional = d.get("emotional_design") if isinstance(d.get("emotional_design"), dict) else {}
    re_ = memo.get("reader_expectation") if isinstance(memo.get("reader_expectation"), dict) else {}
    pp = memo.get("payoff_plan") if isinstance(memo.get("payoff_plan"), dict) else {}

    summary = str(outline.get("summary", "") or "").strip()
    task = str(memo.get("current_task", "") or "").strip()
    segments = [
        {
            "summary": str(s.get("summary", "") or "").strip(),
            "target_words": _seg_words(s.get("target_words", 800)),
        }
        for s in (d.get("segments") if isinstance(d.get("segments"), list) else [])
        if isinstance(s, dict) and str(s.get("summary", "") or "").strip()
    ]
    if not summary or not task or not segments:
        return None

    scenes = [
        {
            "scene_name": str(sc.get("scene_name", "") or "").strip(),
            "goal": str(sc.get("goal", "") or "").strip(),
            "obstacle": str(sc.get("obstacle", "") or "").strip(),
            "hook": str(sc.get("hook", "") or "").strip(),
            **({"weight": sc["weight"]} if sc.get("weight") in _SCENE_WEIGHTS else {}),
            **({"focus": sc["focus"]} if sc.get("focus") in _SCENE_FOCUS else {}),
        }
        for sc in (d.get("scene_cards") if isinstance(d.get("scene_cards"), list) else [])
        if isinstance(sc, dict) and str(sc.get("scene_name", "") or "").strip()
    ]
    payoffs = []
    for mp in d.get("micro_payoffs") if isinstance(d.get("micro_payoffs"), list) else []:
        if not isinstance(mp, dict):
            continue
        desc = str(mp.get("description", "") or "").strip()
        if not desc:
            continue
        payoffs.append(
            {
                "kind": mp.get("kind") if mp.get("kind") in _PAYOFF_KINDS else "clue",
                "description": desc,
                **(
                    {"location": mp["location"]}
                    if mp.get("location") in _PAYOFF_LOCATIONS
                    else {}
                ),
            }
        )

    return {
        "outline": {
            "summary": summary,
            "key_points": _str_list(outline.get("key_points")),
            "characters": _str_list(outline.get("characters")),
            "location": str(outline.get("location", "") or "").strip(),
            "time": str(outline.get("time", "") or "").strip(),
            "narrative_pov": str(outline.get("narrative_pov", "") or "").strip(),
            "perspective_guidance": str(outline.get("perspective_guidance", "") or "").strip(),
        },
        "memo": {
            "current_task": task,
            "reader_expectation": {
                "state": str(re_.get("state", "") or "").strip(),
                "strategy": str(re_.get("strategy", "") or "").strip(),
                "detail": str(re_.get("detail", "") or "").strip(),
            },
            "payoff_plan": {
                "must_resolve": _str_list(pp.get("must_resolve")),
                "must_hold": _str_list(pp.get("must_hold")),
                "partial_advance": _str_list(pp.get("partial_advance")),
            },
            "required_changes": _str_list(memo.get("required_changes")),
            "prohibitions": _str_list(memo.get("prohibitions")),
        },
        "emotional_design": {
            "primary_mood": str(emotional.get("primary_mood", "") or "").strip(),
            "mood_progression": str(emotional.get("mood_progression", "") or "").strip(),
            "emotional_hook": str(emotional.get("emotional_hook", "") or "").strip(),
        },
        "segments": segments,
        "scene_cards": scenes,
        "micro_payoffs": payoffs,
        "ladder_exit": str(d.get("ladder_exit", "") or "").strip(),
        "word_target": _clamp_word_target(d.get("word_target")),
    }


def _arc_markdown(story: dict) -> str:
    """主线卡素材段；无内容返回空串（调用方据此 422）。"""
    arc = story.get("story_arc") if isinstance(story.get("story_arc"), dict) else {}
    ending = arc.get("ending") if isinstance(arc.get("ending"), dict) else {}
    volumes = arc.get("volumes") if isinstance(arc.get("volumes"), list) else []
    lines = []
    premise = str(arc.get("premise", "") or "").strip()
    if premise:
        lines.append(f"一句话主线：{premise}")
    for f, label in (("scene", "终局场景"), ("hero", "主角归宿"), ("tone", "基调")):
        v = str(ending.get(f, "") or "").strip()
        if v and v != "待定":
            lines.append(f"{label}：{v}")
    for v in volumes:
        if not isinstance(v, dict):
            continue
        row = [
            str(v.get(f, "") or "").strip()
            for f in ("title", "conflict", "chapters")
            if str(v.get(f, "") or "").strip()
        ]
        if row:
            lines.append("分卷｜" + "；".join(row))
    return "\n".join(lines)


def _existing_outline_markdown(chapter: dict) -> str:
    """本章现有章纲（改写基底）；空返回提示行。"""
    o = chapter.get("outline") if isinstance(chapter.get("outline"), dict) else {}
    memo = chapter.get("memo") if isinstance(chapter.get("memo"), dict) else {}
    # 全格子口径：任一章纲格子有内容即视为「有现有章纲」（与前端覆盖确认判定同范围）
    has = (
        any(str(v or "").strip() for v in o.values())
        or str(memo.get("current_task", "") or "").strip()
        or any(
            isinstance(s, dict) and str(s.get("summary", "") or "").strip()
            for s in chapter.get("segments") or []
        )
        or bool(chapter.get("scene_cards"))
        or bool(chapter.get("micro_payoffs"))
        or str(chapter.get("ladder_exit", "") or "").strip()
    )
    if not has:
        return "（无现有章纲，从零起草）"
    return json.dumps(
        {
            "outline": o,
            "memo": memo,
            "emotional_design": chapter.get("emotional_design") or {},
            "segments": chapter.get("segments") or [],
            "scene_cards": chapter.get("scene_cards") or [],
            "micro_payoffs": chapter.get("micro_payoffs") or [],
            "ladder_exit": chapter.get("ladder_exit", ""),
            "word_target": chapter.get("word_target"),
        },
        ensure_ascii=False,
    )


@router.post("/ai-draft")
async def ai_draft_outline(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """章纲 AI 起草：返回结构化草稿，不落库（作者表单承接后走既有保存链路）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    arc_md = _arc_markdown(story)
    if not arc_md:
        raise HTTPException(422, "主线卡为空，请先在设定中完成主线拆纲再起草章纲")

    ctx = await build_chapter_context(
        project.root_path, chapter_ref, project.name, novel_id=project.id
    )
    chapter = await load_chapter(project.root_path, chapter_ref) or {}
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    blocks = [f"# 《{project.name}》章纲起草素材包"]
    blocks.append(f"【主线卡】\n{arc_md}")
    prev = ctx.previous_context or ctx.previous_chapter_recap
    if prev and prev != _CH1_PREVIOUS:
        blocks.append(f"【前情（上一章结尾处境）】\n{prev}")
    bg = []
    if ctx.premise:
        bg.append(f"故事前提：{ctx.premise}")
    if ctx.volume_summary:
        bg.append(f"本卷概要：{ctx.volume_summary}")
    if bg:
        blocks.append("【故事背景】\n" + "\n".join(bg))
    if ctx.characters:
        blocks.append(
            "【角色初始状态】\n"
            + "\n".join(
                f"- {c.get('name', '?')}：{c.get('state', '')}"
                for c in ctx.characters[:5]
            )
        )
    if ctx.hooks:
        blocks.append(
            "【活跃伏笔】\n" + "\n".join(f"- {h.get('description', '?')}" for h in ctx.hooks[:8])
        )
    blocks.append(f"【本章现有章纲（改写基底）】\n{_existing_outline_markdown(chapter)}")
    material = "\n\n".join(blocks)

    system = load_prompt("outline_draft")
    client = await get_ai_client()
    model = ctx.style_setting.get("writing_model", "haiku")
    usage: dict = {}
    try:
        raw = await client.chat(
            model=model,
            max_tokens=4000,
            system=system.format(material=material),
            messages=[{"role": "user", "content": "请为素材包中的本章起草章纲草稿。"}],
            usage=usage,
        )
    except HTTPException:
        raise
    except Exception as e:  # 模型/网络错误：不计量，可重试
        raise HTTPException(502, f"章纲起草调用失败：{e}") from e

    draft = None
    try:
        parsed = json.loads(strip_code_fences(raw))
        draft = _sanitize_draft(parsed)
    except (ValueError, TypeError):
        draft = None
    if draft is None:
        raise HTTPException(502, "草稿结构不完整（缺梗概/核心任务/段落规划），未返回，可重试")

    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=user["id"],
        project_id=project.id,
        chapter_id=chapter_ref,
        operation="outline_draft",
        model=model,
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )
    await db.commit()
    return draft
