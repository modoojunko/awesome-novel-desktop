"""AI 审校（ai-check，右栏 AI 辅助检测族）。

- `POST …/ai-check {kind}`：六类案头检查（卷纲冲突/关系冲突/伏笔冲突/文风一致性/
  文风偏离段落/建议补边）——读章节与相应设定素材，产出 finding 列表（只报有证据的
  问题，上限 8 条、空数组合法）；PRO＋本书模型双门控；产物不落库（就地弹窗消费）。
- 提示词精修（refine）在 `write/router.py`：同族「提案制」端点，产物由弹窗确认后
  走既有提示词保存链写回。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import AITimeoutError, get_ai_client_for_novel
from ai_state import effective_model
from auth_local.deps import require_ai_access, require_novel_model
from auth_local.middleware import get_current_user
from db import get_db
from novels.service import get_novel
from prompts import load as load_prompt
from workflow.engine import _validate_ref, load_chapter
from write.chapter_writer import build_chapter_context, strip_code_fences

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/ai-check", tags=["ai-check"]
)

MAX_FINDINGS = 8

# 检查类别 → 指令（素材组装同源：章纲/正文/按需附设定）
CHECK_KINDS: dict[str, str] = {
    "volume_conflict": (
        "检查本章章纲与「本卷卷纲」是否冲突：目标是否偏离卷目标、关键事件与卷节点"
        "是否矛盾、必填项与卷面设定是否互斥。"
    ),
    "relations_conflict": (
        "检查本章正文/章纲与「全书角色关系」是否冲突：出现与台账相悖的敌友/亲疏"
        "关系、称呼与身份不符、单方视角被正文当成双向事实。"
    ),
    "hooks_conflict": (
        "检查本章正文/章纲与「伏笔台账」是否冲突：把已收束的伏笔当作未收束、"
        "本应维持的悬念被提前揭破、埋点章与台账不符。"
    ),
    "style_consistency": (
        "按「全书文风基线」检查本章正文：视角与人称是否漂移、句子与段落节奏是否"
        "明显偏离基线、禁用词与句式是否出现。"
    ),
    "style_deviations": (
        "找出本章正文中明显偏离「全书文风基线」的段落，逐条引用原文片段并说明偏离点。"
    ),
    "relation_suggest": (
        "根据本章发生的事，建议「全书角色关系」中缺失或可补充的关系边（含已有关系的"
        "立场/备注更新建议）。"
    ),
}


def _parse_findings(text: str) -> list[dict]:
    if not text:
        return []
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except Exception:  # noqa: BLE001
        return []
    items = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title", "")).strip()[:100]
        detail = str(it.get("detail", "")).strip()[:400]
        if title and detail:
            out.append({"title": title, "detail": detail})
        if len(out) >= MAX_FINDINGS:
            break
    return out


def _material(kind: str, chapter: dict, ctx) -> str:
    outline = chapter.get("outline") or {}
    memo = chapter.get("memo") or {}
    prose = str(chapter.get("prose") or "")
    blocks: list[str] = []
    ol_lines = [f"概要：{outline.get('summary', '') or '（未填）'}"]
    kps = [str(k) for k in (outline.get("key_points") or []) if str(k).strip()]
    if kps:
        ol_lines.append("关键事件：" + "；".join(kps))
    blocks.append("【本章章纲】\n" + "\n".join(ol_lines))
    if prose.strip():
        blocks.append("【本章正文（节选）】\n" + prose[:4000])

    if kind == "volume_conflict":
        blocks.append("【本卷卷纲】\n" + (ctx.volume_outline or "（未配置）"))
        if ctx.story_arc:
            blocks.append("【全书主线】\n" + ctx.story_arc)
    elif kind == "hooks_conflict":
        if ctx.hooks:
            lines = []
            for h in ctx.hooks[:8]:
                code = h.get("code") or ""
                prefix = f"[{code}] " if code else ""
                lines.append(f"- {prefix}{h.get('description', '?')}")
            blocks.append("【活跃伏笔台账】\n" + "\n".join(lines))
        else:
            blocks.append("【活跃伏笔台账】\n（暂无活跃伏笔）")
    if kind in ("style_consistency", "style_deviations"):
        from settings.render import quant_section, style_section

        style_lines = [style_section(ctx.style_setting)]
        q = quant_section(ctx.style_quant, ctx.style_shadow)
        if q:
            style_lines.append(q)
        blocks.append("【全书文风基线】\n" + "\n".join(x for x in style_lines if x))
    return "\n\n".join(blocks)


@router.post("")
async def run_ai_check(
    project_id: str,
    chapter_ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """六类案头检查：产出 findings（不落库，就地弹窗消费）。"""
    kind = str((body or {}).get("kind", "") or "").strip()
    if kind not in CHECK_KINDS:
        raise HTTPException(400, f"未知的检查类别：{kind}")
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    chapter = await load_chapter(project.root_path, chapter_ref) or {}
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    ctx = await build_chapter_context(
        project.root_path, chapter_ref, project.name, novel_id=project.id
    )
    material = _material(kind, chapter, ctx)
    if kind in ("relations_conflict", "relation_suggest"):
        # 关系素材在此补全（ctx 不含关系面）：从真表取
        from sqlalchemy import select

        from models.character import Character, CharacterRelation

        cards = (
            await db.scalars(select(Character).where(Character.novel_id == project.id))
        ).all()
        by_id = {c.id: c.name for c in cards}
        rels = (
            await db.scalars(
                select(CharacterRelation).where(
                    CharacterRelation.novel_id == project.id
                )
            )
        ).all()
        lines = [
            f"- {by_id.get(r.owner_id, r.owner_id)} → {by_id.get(r.other_id, r.other_id)}"
            f"：{r.rel_type}{(' · ' + r.stance) if r.stance else ''}"
            for r in rels
        ]
        material += "\n\n【全书角色关系】\n" + ("\n".join(lines) or "（暂无关系）")

    system = load_prompt("ai_check").format(
        instruction=CHECK_KINDS[kind], material=material
    )
    client = await get_ai_client_for_novel(project.id)
    usage: dict = {}
    try:
        raw = await client.chat(
            model="haiku",
            system=system,
            messages=[{"role": "user", "content": "请开始检查。"}],
            max_tokens=1600,
            usage=usage,
        )
    except AITimeoutError:
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation=f"ai_check_{kind}_fail",
            model=effective_model(project), force=True,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation=f"ai_check_{kind}_fail",
            model=effective_model(project),
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, f"AI 调用失败，可重试：{e!s}") from e

    from api_configs.usage import record_usage

    await record_usage(
        db, user_id=project.user_id, project_id=project.id,
        chapter_id=chapter_ref, operation=f"ai_check_{kind}",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
    )
    return {"ok": True, "kind": kind, "findings": _parse_findings(strip_code_fences(raw))}
