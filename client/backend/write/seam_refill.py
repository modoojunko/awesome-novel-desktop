"""章际衔接修复（c-seam-refill）：知前后补中间——draft 三选一（SSE 流式）。

- `POST …/seam-refill/draft {para_count?, findings?, rejected?}`：
  读「前」（上章结尾原文）与「后」（断点后正文＋章末落点），起草 3 版互斥的开头重写
  方案（直承/过渡/重排）。SSE 事件：phase(assemble/model) → chunk(chars 计数) →
  done{options} ｜ error{error}。
- draft 不落库（关弹窗即弃）；应用＝前端按段号替换后走既有 PUT prose 链（作者确认制，
  版本快照即找回，不建 ghost）。
- 门控与计费：ai-generate ＋ PRO／本书模型双门控；operation=`seam_refill_draft(_fail)`。
- 模板 `seam_refill.prompt`（<<>> 顺序 replace，禁 str.format——契约含字面花括号）。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import get_ai_client_for_novel
from ai_state import effective_model
from auth_local.deps import ai_feature, require_ai_access, require_novel_model
from auth_local.middleware import get_current_user
from db import get_db
from novels.service import get_novel
from prompts import load_layers
from settings.render import style_section
from workflow.engine import _validate_ref, load_chapter
from write.chapter_writer import _story_state_block, build_chapter_context, strip_code_fences

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/seam-refill",
    tags=["seam-refill"],
)

logger = logging.getLogger("uvicorn.error")

MAX_FINDINGS = 8
STRATEGIES = [("direct", "直承"), ("transition", "过渡"), ("reframe", "重排")]


class RejectedVersion(BaseModel):
    approach: str = Field(default="", max_length=20)
    text: str = Field(default="", max_length=4000)


class SeamDraftBody(BaseModel):
    para_count: int = Field(default=3, ge=1, le=6)
    findings: list[dict] = Field(default_factory=list)
    rejected: list[RejectedVersion] = Field(default_factory=list)


def _paras(text: str) -> list[str]:
    return [p for p in (text or "").split("\n") if p.strip()]


def _parse_options(raw: str) -> list[dict] | None:
    """宽松解析三版 JSON（strip_code_fences＋花括号截取口径，同 _parse_findings）。

    校验：恰 3 版、approach ∈ {直承,过渡,重排} 且互不重复、text 非空。
    """
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except Exception:  # noqa: BLE001
        return None
    versions = data.get("versions") if isinstance(data, dict) else None
    if not isinstance(versions, list) or len(versions) != len(STRATEGIES):
        return None
    labels = dict(STRATEGIES)
    axis_keys = {label: key for key, label in STRATEGIES}  # 模板契约＝中文轴名（直承/过渡/重排）
    seen: set[str] = set()
    options: list[dict] = []
    for v in versions:
        if not isinstance(v, dict):
            return None
        approach = str(v.get("approach", "")).strip()
        text = str(v.get("text", "")).strip()
        note = str(v.get("note", "")).strip()[:60]
        key = axis_keys.get(approach) or (approach if approach in labels else None)
        if not key or not text or key in seen:
            return None
        seen.add(key)
        options.append({"key": key, "label": labels[key], "how": note, "text": text})
    return options


def _build_slots(ctx, prose: str, para_count: int, findings: list[dict], rejected: list) -> dict:
    """六槽组装：before/after/finding/rejected/story_state/style（模板 <<>> 一一对应）。"""
    paras = _paras(prose)
    para_count = min(para_count, len(paras))
    old_opening = "\n".join(paras[:para_count])
    after = "\n".join(paras[para_count:])[:2000]

    lines = [
        f"- {f.get('title', '')}：{f.get('detail', '')}"
        for f in findings
        if isinstance(f, dict) and (f.get("title") or f.get("detail"))
    ]
    finding = "（无——按三类断裂自查开场衔接）"
    if lines:
        finding = "\n".join(lines)
    finding += f"\n【待替换的开场原文（病文，禁止效仿其讲法）】\n{old_opening}"

    rej_lines = [f"- {r.approach}：{r.text[:120]}" for r in rejected if r.text.strip()]
    story = _story_state_block(ctx.story_state) or "（暂无故事状态）"

    return {
        "before": ctx.previous_tail or "（无）",
        "after": (after or "（本章没有后续段落）") + (
            f"\n\n【本章章末落点（硬边界，不得矛盾）】\n{ctx.ladder_exit}" if ctx.ladder_exit else ""
        ),
        "finding": finding,
        "rejected": "\n".join(rej_lines) if rej_lines else "（无）",
        "story_state": story,
        "style": style_section(ctx.style_setting) or "（未配置，以前后文自身文风为准）",
    }


@router.post("/draft")
@ai_feature("ai-generate")
async def draft(
    project_id: str,
    chapter_ref: str,
    body: SeamDraftBody | None = None,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """重写方案三选一（SSE）：draft 不落库，应用走前端替换＋既有 PUT prose 链。"""
    body = body or SeamDraftBody()
    if not 1 <= body.para_count <= 6:
        raise HTTPException(400, "para_count 取值 1-6")
    findings = [f for f in (body.findings or []) if isinstance(f, dict)][:MAX_FINDINGS]
    rejected = (body.rejected or [])[:3]

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    chapter = await load_chapter(project.root_path, chapter_ref) or {}
    prose = str(chapter.get("prose") or "")
    if not prose.strip():
        raise HTTPException(409, "本章还没有正文，没有可修复的开场")
    ctx = await build_chapter_context(
        project.root_path, chapter_ref, project.name, novel_id=project.id
    )
    if not (ctx.previous_tail or "").strip():
        raise HTTPException(409, "上一章没有可衔接的结尾（首章或上章未写），无需修复开场")

    client = await get_ai_client_for_novel(project.id)
    resolved_model = effective_model(project)
    slots = _build_slots(ctx, prose, body.para_count, findings, rejected)

    return StreamingResponse(
        _gen(project, ctx, chapter_ref, resolved_model, client, slots, db, user),
        media_type="text/event-stream",
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _gen(project, ctx, chapter_ref: str, resolved_model: str, client, slots: dict, db, user):
    from api_configs.usage import record_usage

    async def _fail(msg: str) -> None:
        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation="seam_refill_draft_fail",
            model=resolved_model, force=True,
        )
        logger.warning("event=seam_refill_draft_error err=%s", msg[:200])
        yield _sse({"type": "error", "error": msg})

    try:
        yield _sse({"type": "phase", "phase": "assemble"})
        _sys_t, _usr_t = load_layers("seam_refill")
        system = _sys_t
        user_msg = _render(_usr_t, slots)
        yield _sse({"type": "phase", "phase": "model"})

        buf: list[str] = []
        usage = {"tokens_in": 0, "tokens_out": 0}
        chars = 0
        async for ev in client.chat_stream(
            model=resolved_model,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=8192,
            operation="seam_refill_draft",
        ):
            if ev.error:
                raise RuntimeError(ev.error)
            if ev.text:
                buf.append(ev.text)
                chars += len(ev.text)
                yield _sse({"type": "chunk", "chars": chars})
            if ev.tokens_in:
                usage["tokens_in"] = ev.tokens_in
            if ev.tokens:
                usage["tokens_out"] = ev.tokens

        options = _parse_options(strip_code_fences("".join(buf)))
        if options is None:
            raise ValueError("方案解析失败（三版结构不完整），请重试")
        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation="seam_refill_draft",
            model=resolved_model,
            tokens_in=usage["tokens_in"], tokens_out=usage["tokens_out"],
        )
        yield _sse({"type": "done", "options": options})
    except Exception as e:  # noqa: BLE001
        async for piece in _fail(f"衔接方案生成失败，可重试：{e}"):
            yield piece


def _render(template: str, values: dict[str, str]) -> str:
    """顺序 replace（<<name>> 占位），禁 str.format——契约含字面花括号。"""
    out = template
    for key, val in values.items():
        out = out.replace(f"<<{key}>>", val)
    return out
