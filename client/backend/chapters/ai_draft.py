"""章纲缺项补全（outline-ai-draft 家族的 fill-gaps；起草端点随 c-og-ai-draft-retire 退役）。

按前端给的缺失字段清单补全章纲格子：素材包 = 设定全量（世界观/题材/人物）+ 主线/卷纲
+ 前情 + 本章现有章纲（复用 build_chapter_context）；产物只返回不落库，由前端表单承接
后走既有保存链；校验失败 502 可重试（与 prompt 润色同模式）。
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import AITimeoutError, get_ai_client_for_novel
from ai_state import effective_model
from auth_local.deps import require_ai_access, require_novel_model
from auth_local.middleware import get_current_user
from db import get_db
from novels.service import get_novel
from prompts import load_layers
from workflow.engine import _validate_ref, load_chapter
from write.chapter_writer import build_chapter_context, strip_code_fences

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/outline", tags=["chapters"]
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
    _sys_t, _usr_t = load_layers("outline_fill_gaps")
    system = _sys_t
    user_content = _usr_t.format(missing="、".join(missing), material=material)
    client = await get_ai_client_for_novel(project.id)
    usage: dict = {}
    try:
        raw = await client.chat(
            model="haiku", system=system,
            messages=[{"role": "user", "content": user_content + "\n\n请补齐缺失字段。"}],
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
