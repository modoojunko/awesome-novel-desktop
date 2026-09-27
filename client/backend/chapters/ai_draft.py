"""章纲 AI 起草（outline-ai-draft）。

素材包 = 主线卡 + 前情/设定（复用 build_chapter_context）+ 本章现有章纲（改写基底）；
产物只返回不落库，由前端表单承接；校验失败 502 可重试（与 prompt 润色同模式）。
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import AITimeoutError, get_ai_client_for_novel
from ai_state import effective_model
from auth_local.deps import require_ai_access, require_novel_model
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

# 读者获得类型单源＝write/chapter_writer.MICRO_PAYOFF_LABELS（中文标签表，含键集合）；
# 位置档随 c-og-slim-v2 退役（位置由剧情条目顺序表达）。
from write.chapter_writer import MICRO_PAYOFF_LABELS as _PAYOFF_LABELS

_PAYOFF_KINDS = set(_PAYOFF_LABELS)


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


def _sanitize_draft(d: dict) -> dict | None:
    """字段级兜底（与 chapterForm 回读同口径）；骨架缺失返回 None → 502。"""
    outline = d.get("outline") if isinstance(d.get("outline"), dict) else {}
    memo = d.get("memo") if isinstance(d.get("memo"), dict) else {}
    emotional = d.get("emotional_design") if isinstance(d.get("emotional_design"), dict) else {}
    pp = memo.get("payoff_plan") if isinstance(memo.get("payoff_plan"), dict) else {}

    summary = str(outline.get("summary", "") or "").strip()
    # 骨架＝章纲概要一项（c-og-slim-v2：段落规划随该格退役，不再作必备骨架）
    if not summary:
        return None

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
            }
        )

    return {
        "outline": {
            "summary": summary,
            "characters": _str_list(outline.get("characters")),
        },
        "memo": {
            "payoff_plan": {
                "must_resolve": _str_list(pp.get("must_resolve")),
                "must_hold": _str_list(pp.get("must_hold")),
            },
            "required_changes": _str_list(memo.get("required_changes")),
            "prohibitions": _str_list(memo.get("prohibitions")),
        },
        "emotional_design": {
            "primary_mood": str(emotional.get("primary_mood", "") or "").strip(),
        },
        "challenge": str(d.get("challenge", "") or "").strip()[:150],
        "plot_stage": str(d.get("plot_stage", "") or "").strip()[:20],
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
        lines.append(f"全书主线：{premise}")
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
    # 留存格子口径：任一章纲留存格有内容即视为「有现有章纲」（与前端覆盖确认判定同范围）
    # c-og-slim-v2：退役格子（关键事件/地点/时间/视角/预期/段落规划/场景卡/本章行动）
    # 一律不计入；剧情条目按既有口径不计入（「AI 起草不动剧情」）
    has = (
        any(str(v or "").strip() for v in o.values())
        or bool(chapter.get("micro_payoffs"))
        or str(chapter.get("ladder_exit", "") or "").strip()
        # c-chapter-plan-ai：拆章两格也计入——拆完的章不得被判空而遭起草覆盖
        or str(chapter.get("challenge", "") or "").strip()
        or str(chapter.get("plot_stage", "") or "").strip()
    )
    if not has:
        return "（无现有章纲，从零起草）"
    return json.dumps(
        {
            "outline": o,
            "memo": memo,
            "emotional_design": chapter.get("emotional_design") or {},
            "micro_payoffs": chapter.get("micro_payoffs") or [],
            "ladder_exit": chapter.get("ladder_exit", ""),
            "challenge": chapter.get("challenge", ""),
            "plot_stage": chapter.get("plot_stage", ""),
            "word_target": chapter.get("word_target"),
        },
        ensure_ascii=False,
    )


# 可补字段白名单＝前端 OgForm 能承接的键（前端 chapterForm 补丁表同单源口径）：
# 覆盖归档门槛六项（task/state/strategy/changes/mood/segs）与章纲其余可写格子。
# 后端只做白名单收口；具体下发哪些缺项由前端按缺口清单决定。
# c-og-slim-v2：白名单＝前端 OgForm 留存可写格——概要/出场角色/必须完成的变化/禁止事项/主情绪。
# 已退役键（关键事件/地点/时间/预期策略/预期细节/段落规划）与 plot_items 一律丢弃。
_FILLABLE_KEYS = {
    "summary", "characters", "changes", "prohibitions", "mood",
}
_LIST_KEYS = {"characters", "changes", "prohibitions"}


def _sanitize_fills(d: dict) -> dict:
    """只收缺失字段白名单键；空值丢弃（前端 patch 到 OgPane 表单）。

    - 行列表键（characters/changes/prohibitions）：逐行去空
    - 标量键（summary/mood）：去空白后非空才收
    """
    fills = d.get("fills") if isinstance(d, dict) else None
    if not isinstance(fills, dict):
        return {}
    out: dict = {}
    for k, v in fills.items():
        if k not in _FILLABLE_KEYS:
            continue
        elif k in _LIST_KEYS and isinstance(v, list):
            vals = [str(x).strip() for x in v if str(x).strip()]
            if vals:
                out[k] = vals
        elif isinstance(v, str) and v.strip():
            out[k] = v.strip()[:300]
    return out


@router.post("/fill-gaps")
async def fill_outline_gaps(
    project_id: str,
    chapter_ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """按缺失字段清单补全章纲（产物不落库，由前端表单承接后走既有保存链）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    missing = [str(x).strip()[:50] for x in (body.get("missing") or []) if str(x).strip()]
    if not missing:
        raise HTTPException(400, "缺少要补的字段清单（missing）")
    missing = [m for m in missing if m in _FILLABLE_KEYS][:12]
    if not missing:
        raise HTTPException(400, "没有可补的字段")

    ctx = await build_chapter_context(
        project.root_path, chapter_ref, project.name, novel_id=project.id
    )
    chapter = await load_chapter(project.root_path, chapter_ref) or {}
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    material = await _material_from_ctx(db, project, ctx, chapter)
    system = load_prompt("outline_fill_gaps").format(
        missing="、".join(missing), material=material
    )
    client = await get_ai_client_for_novel(project.id)
    usage: dict = {}
    try:
        raw = await client.chat(
            model="haiku", system=system,
            messages=[{"role": "user", "content": "请补齐缺失字段。"}],
            max_tokens=2000, usage=usage,
        )
    except AITimeoutError:
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation="outline_fill_gaps_fail",
            model=effective_model(project),
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation="outline_fill_gaps_fail",
            model=effective_model(project),
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, f"AI 调用失败，可重试：{e!s}") from e

    from api_configs.usage import record_usage

    # 记账先于解析：调用已完成（钱已花），产物不合格也要留痕
    await record_usage(
        db, user_id=project.user_id, project_id=project.id,
        chapter_id=chapter_ref, operation="outline_fill_gaps",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
    )

    parsed = None
    try:
        parsed = json.loads(strip_code_fences(raw))
    except (ValueError, TypeError):
        parsed = None
    fills = _sanitize_fills(parsed) if parsed is not None else {}
    if not fills:
        raise HTTPException(502, "补全结果为空或结构不完整，可重试")
    return {"ok": True, "fills": fills}


async def _setting_blocks(db, project, ctx) -> list[str]:
    """设定素材块（c-ai-material-audit）：世界观全量（含铁律红线）＋题材全字段＋全人物一行卡。

    口径＝《提示词素材给量》逐环节表「章纲起草：世界观全部＋全人物一行卡＋卷纲」；
    零件与拆卷/主线同源（`world_summary_text(raw, None)`）。一行卡取人设原文全文不截断。
    """
    from settings.character_service import _display_name, list_characters
    from settings.world_model import world_summary_text

    blocks: list[str] = []
    world = world_summary_text(ctx.world_setting or {}, None).strip()
    blocks.append("【世界观】\n" + (world or "（世界设定：未填）"))
    blocks.append("【题材与节奏】\n" + (ctx.genre_section or "（题材：未填）"))
    chars = await list_characters(db, project.id)
    items = list(chars.get("items", []))
    items.sort(key=lambda it: 0 if it.get("role") == "主角" else 1)
    lines = [
        f"- {_display_name(str(it.get('name') or ''))}（{it.get('role') or ''}）："
        f"{str(it.get('persona') or '').strip()}"
        for it in items
    ]
    blocks.append("【人物】\n" + ("\n".join(lines) if lines else "（角色表：无）"))
    return blocks


async def _material_from_ctx(db, project, ctx, chapter: dict) -> str:
    blocks: list[str] = await _setting_blocks(db, project, ctx)
    if ctx.story_arc:
        blocks.append("【全书主线】\n" + ctx.story_arc)
    if ctx.volume_outline:
        blocks.append("【本卷卷纲】\n" + ctx.volume_outline)
    prev = ctx.previous_context or ctx.previous_chapter_recap
    if prev:
        blocks.append("【前情】\n" + prev[:800])
    outline = chapter.get("outline") or {}
    cur = [
        f"概要：{outline.get('summary', '') or '（空）'}",
        "出场角色：" + ("、".join(str(k) for k in outline.get("characters") or []) or "（空）"),
    ]
    blocks.append("【本章现有章纲】\n" + "\n".join(cur))
    return "\n\n".join(blocks)


@router.post("/ai-draft")
async def ai_draft_outline(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
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
    blocks.extend(await _setting_blocks(db, project, ctx))
    prev = ctx.previous_context or ctx.previous_chapter_recap
    if prev and prev != _CH1_PREVIOUS:
        blocks.append(f"【前情（上一章结尾处境）】\n{prev}")
    bg = []
    if ctx.premise:
        bg.append(f"故事前提：{ctx.premise}")
    if ctx.volume_outline:
        bg.append("本卷卷纲：\n" + ctx.volume_outline)
    if bg:
        blocks.append("【故事背景】\n" + "\n".join(bg))
    if ctx.characters:
        blocks.append(
            "【角色初始状态】\n"
            + "\n".join(
                f"- {c.get('name', '?')}：{c.get('state', '')}"
                for c in ctx.characters
            )
        )
    if ctx.hooks:
        hook_lines = []
        for h in ctx.hooks:
            code = h.get("code") or ""
            prefix = f"[{code}] " if code else ""
            hook_lines.append(f"- {prefix}{h.get('description', '?')}")
        blocks.append("【活跃伏笔】\n" + "\n".join(hook_lines))
    blocks.append(f"【本章现有章纲（改写基底）】\n{_existing_outline_markdown(chapter)}")
    material = "\n\n".join(blocks)

    system = load_prompt("outline_draft")
    client = await get_ai_client_for_novel(project.id)
    model = "haiku"  # 符号别名，落到本书模型（D12）
    usage: dict = {}
    try:
        raw = await client.chat(
            model=model,
            max_tokens=4000,
            system=system.format(material=material),
            messages=[{"role": "user", "content": "请为素材包中的本章起草章纲草稿。"}],
            usage=usage,
        )
    except AITimeoutError:
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=user["id"], project_id=project.id,
            chapter_id=chapter_ref, operation="outline_draft_fail",
            model=model,
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except HTTPException:
        raise
    except Exception as e:  # 模型/网络错误：留痕后可重试
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=user["id"], project_id=project.id,
            chapter_id=chapter_ref, operation="outline_draft_fail",
            model=model,
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, f"章纲起草调用失败：{e}") from e

    from api_configs.usage import record_usage

    # 记账先于解析：调用已完成（钱已花），产物不合格也要留痕
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

    draft = None
    try:
        parsed = json.loads(strip_code_fences(raw))
        draft = _sanitize_draft(parsed)
    except (ValueError, TypeError):
        draft = None
    if draft is None:
        raise HTTPException(502, "草稿结构不完整（缺梗概/核心任务/段落规划），未返回，可重试")

    await db.commit()
    return draft
