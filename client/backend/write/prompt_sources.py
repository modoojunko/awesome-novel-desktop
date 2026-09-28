"""提示词组装来源（prompt-sources，storyline.html 四期尾）：七处来源的只读展示（c-chapter-dossier 增第七处）。

复用写作侧同一套组装链（build_chapter_context + 同款渲染函数），返回每处来源的
字数与摘录，供「提示词」页签展示「由什么拼成的」——只读投影，不改任何设定。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.middleware import get_current_user
from db import get_db
from novels.service import get_novel
from prompt.context import inject_world_setting
from settings.render import quant_section, style_section
from workflow.engine import _validate_ref
from write.chapter_writer import build_chapter_context

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/prompt-sources",
    tags=["prompt-sources"],
)

_PREVIEW = 120


def _block(key: str, label: str, text: str) -> dict:
    text = (text or "").strip()
    flat = " ".join(text.split())
    return {
        "key": key,
        "label": label,
        "chars": len(text),
        "preview": flat[:_PREVIEW],
        "empty": not text,
    }


async def _story_state_gap(
    db: AsyncSession, novel_id: str, root_path: str, ctx
) -> str:
    """故事状态缺口标注：上一章未归档 / 提取中 / 缺 N 条未确认（把静默劣化变可见）。"""
    from sqlalchemy import func, select

    from models.chapter import (
        Chapter,
        ChapterItemChange,
        ChapterKnowledgeChange,
        ChapterRelationChange,
        ChapterSettingChange,
    )
    from write.chapter_writer import _prev_chapter_ref

    if ctx.volume_no is None or ctx.chapter_no is None:
        return ""
    prev_ref = await _prev_chapter_ref(root_path, ctx.volume_no, ctx.chapter_no)
    if not prev_ref:
        return ""
    prev = (
        await db.scalars(
            select(Chapter).where(
                Chapter.project_id == novel_id, Chapter.ref == prev_ref
            )
        )
    ).first()
    if prev is None:
        return ""
    if prev.status != "archived":
        return "上一章未归档" if prev.has_prose else ""
    pending = 0
    for model in (
        ChapterSettingChange, ChapterRelationChange,
        ChapterItemChange, ChapterKnowledgeChange,
    ):
        pending += (
            await db.scalar(
                select(func.count()).select_from(model).where(
                    model.chapter_id == prev.id, model.status == "pending"
                )
            )
        ) or 0
    if pending:
        return f"缺 {pending} 条未确认"
    return ""


@router.get("")
async def prompt_sources(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """七处来源（行序固定）：全书设定 / 大纲·卷纲 / 本章章纲 / 全书文风＋本章调整 /
    伏笔进展·截至上一章 / 本章涉及角色 / 故事状态·截至上章。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    # 章不存在 → 404（与 style-shadow/推演等章级端点同语义；
    # build_chapter_context 对缺章是宽容的，会返回六空来源——那会让调用方误以为章存在）
    from chapters.store import load_chapter as _load_chapter

    if not await _load_chapter(project.root_path, chapter_ref):
        raise HTTPException(404, "Chapter not found")

    ctx = await build_chapter_context(
        project.root_path, chapter_ref, project.name, novel_id=project.id
    )

    # ① 全书设定：题材定义 + 故事前提/全书主线 + 世界设定
    book_lines = []
    if ctx.genre_section:
        book_lines.append(ctx.genre_section)
    if ctx.premise:
        book_lines.append(f"故事前提：{ctx.premise}")
    if ctx.story_arc:
        book_lines.append(f"全书主线：{ctx.story_arc}")
    world = inject_world_setting(ctx.world_setting)
    if world:
        book_lines.append(world)

    # ② 大纲 · 卷纲：本卷概要
    volume = ctx.volume_outline or ""

    # ③ 本章章纲：概要 + 出场角色 + 剧情条目（c-og-slim-v2：关键情节点与场景行退役）
    outline = ctx.chapter_outline if isinstance(ctx.chapter_outline, dict) else {}
    outline_lines = []
    if outline.get("summary"):
        outline_lines.append(f"章纲概要：{outline.get('summary')}")
    cast = [str(c).strip() for c in (outline.get("characters") or []) if str(c).strip()]
    if cast:
        outline_lines.append("出场角色：" + "、".join(cast))
    # c-plot-split：剧情条目计入章纲来源（一条一行，空则不计）
    plots = [str(p).strip() for p in ctx.plot_items if str(p).strip()]
    if plots:
        outline_lines.append("剧情条目：" + "\n".join(plots))

    # ④ 全书文风 ＋ 本章调整：定性层 + 量化基线（影子行显示为本章覆盖）
    style_lines = [style_section(ctx.style_setting)]
    quant = quant_section(ctx.style_quant, ctx.style_shadow)
    if quant:
        style_lines.append(quant)
    banned = [str(w) for w in (ctx.style_setting.get("banned_words") or [])]
    tics = [
        r.get("pattern", "")
        for r in (ctx.style_setting.get("tic_patterns") or [])
        if isinstance(r, dict)
    ]
    if banned:
        style_lines.append("禁用词：" + "、".join(banned))
    if tics:
        style_lines.append("禁用句式：" + "、".join(tics))

    # ⑤ 伏笔进展 · 截至上一章：活跃伏笔（真表 active，已按本章引入排除）
    hook_lines = []
    for h in ctx.hooks:
        code = h.get("code") or ""
        prefix = f"[{code}] " if code else ""
        hook_lines.append(f"- {prefix}{h.get('description', '?')}")

    # ⑥ 本章涉及角色：认知层主格摘要 + 语言特征（writer 同款投影）
    char_lines = []
    for c in ctx.characters[:5]:
        seg = f"- {c.get('name', '?')}：{c.get('state', '')}"
        speech = c.get("speech", "")
        if speech:
            seg += f"（语言特征：{speech}）"
        char_lines.append(seg)

    # ⑦ 故事状态 · 截至上一章（c-chapter-dossier）：章档已采纳折叠态，与写章组装
    # 同一单源渲染；缺口标注把「不采纳 → 下章静默缺状态」变成可见权衡。
    from write.chapter_writer import _story_state_block

    story_state_text = _story_state_block(ctx.story_state)
    story_block = _block("story_state", "故事状态（截至上章）", story_state_text)
    story_block["note"] = await _story_state_gap(db, project_id, project.root_path, ctx)

    sources = [
        _block("book", "全书设定", "\n".join(book_lines)),
        _block("volume", "大纲 · 卷纲", volume),
        _block("outline", "本章章纲", "\n".join(outline_lines)),
        _block("style", "全书文风 ＋ 本章调整", "\n".join(x for x in style_lines if x)),
        _block("hooks", "伏笔进展 · 截至上一章", "\n".join(hook_lines)),
        _block("cast", "本章涉及角色", "\n".join(char_lines)),
        story_block,
    ]
    return {
        "sources": sources,
        "total_chars": sum(s["chars"] for s in sources),
        "cast_count": len(cast),
    }
