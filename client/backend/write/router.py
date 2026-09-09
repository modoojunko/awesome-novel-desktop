import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_state import effective_model
from auth_local.deps import require_ai_access, require_novel_model
from auth_local.middleware import get_current_user
from db import get_db
from novels.service import get_novel
from workflow.engine import _validate_ref, can_transition, load_chapter, update_phase


def _advance_phase(project, target: str) -> None:
    """宽容推进：阶段机只进不退，返工（如 write 阶段重润色→prompt）不允许回退。

    此时跳过推进而非抛 ValueError→500——润色/生成结果本身已合法落库，
    阶段标记保持现状不影响后续操作（write/archive 均为幂等入口）。
    """
    if project.current_phase == target or can_transition(
        project.current_phase, target
    ):
        update_phase(project, target)
from write.auxiliary import expand_text, polish_text, stream_continue
from write.quality import run_quality_checks

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/write",
    tags=["write"],
)


@router.post("/quality-check")
async def quality_check(
    project_id: str,
    chapter_ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    full_text = body.get("full_text", "")
    results = await run_quality_checks(project.root_path, full_text)
    return results


async def _stream_chapter(db, project, root_path: str, chapter_ref: str, ctx, prompt: str):
    """Generate chapter text via AI streaming, save on completion (BE-01: 写完刷新 DB 元数据).

    三工序（ai-prompt-crafting）：①system 注入写作铁律；②完成时字数校验（<90% 提示不拦）；
    ③完成时叙事自查清单（提示性质）——随 done 事件返回。
    """
    from ai_client import get_ai_client_for_novel
    from chapters.service import save_chapter
    from write.chapter_writer import WRITING_IRON_RULES

    client = await get_ai_client_for_novel(project.id)
    # 符号别名：模型由本书绑定决定（D12，不再读 writing_model）
    model = "haiku"
    role = (
        ctx.style_setting.get("role", "一位小说家")
        if hasattr(ctx, "style_setting")
        else "一位小说家"
    )
    system = f"{role}\n\n{WRITING_IRON_RULES}"
    full_text = ""

    async for event in client.chat_stream(
        model=model,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8192,
    ):
        if event.text:
            full_text += event.text
            yield f"data: {json.dumps({'type': 'chunk', 'text': event.text}, ensure_ascii=False)}\n\n"
        elif event.is_done:
            chapter = await load_chapter(root_path, chapter_ref)
            chapter["prose"] = full_text
            # 统一写入口（修直写缺陷）：拆装落库 + 元数据派生 + 版本快照
            await save_chapter(db, project, chapter_ref, chapter)
            from api_configs.usage import record_usage

            await record_usage(
                db,
                user_id=project.user_id,
                project_id=project.id,
                chapter_id=chapter_ref,
                operation="write_chapter",
                model=model,
                tokens_out=event.tokens,
            )
            done: dict = {"type": "done", "full_text": full_text, "tokens": event.tokens}
            # 工序②：写完字数校验（<90% 显式提示，不拦落库）
            target = getattr(ctx, "word_target", 2500) or 2500
            actual = len(full_text)
            word_check = {
                "target": target,
                "actual": actual,
                "below_limit": actual < int(target * 0.9),
            }
            if word_check["below_limit"]:
                word_check["message"] = f"字数不足：目标 {target}，实写 {actual}"
            done["word_check"] = word_check
            # 工序③：写后叙事自查（七条规则确定性扫描，提示性质）
            from write.quality import run_narrative_self_check

            done["self_check"] = run_narrative_self_check(full_text)
            yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
        elif event.error:
            yield f"data: {json.dumps({'type': 'error', 'error': event.error}, ensure_ascii=False)}\n\n"


@router.get("/prompt")
async def get_write_prompt(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """AI 弹窗提示词预览：存量 write-prompt 行优先（润色/编辑结果），无则粗组兜底。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    from prompt.store import load_prompt
    from write.chapter_writer import build_chapter_context

    ctx = await build_chapter_context(
        project.root_path, chapter_ref, project.name, novel_id=project.id
    )
    outline = ctx.chapter_outline or {}
    has_outline = bool(
        outline.get("summary") or outline.get("key_points") or outline.get("segments")
    )
    existing = await load_prompt(project.root_path, chapter_ref, "write-prompt")
    if existing.strip():
        return {"prompt": existing, "has_outline": has_outline, "polished": True}
    return {"prompt": ctx.to_prompt(), "has_outline": has_outline, "polished": False}


@router.post("/prompt/polish")
async def polish_write_prompt(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """两段式第二段：素材包 → 大模型润色 → 轻校验 → 覆盖写 write-prompt 行。

    校验不合格或模型报错时不落库（既有行保持原样），前端可重试。
    """
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    from ai_client import get_ai_client_for_novel
    from write.chapter_writer import (
        build_chapter_context,
        strip_code_fences,
        validate_polished_prompt,
    )

    ctx = await build_chapter_context(
        project.root_path, chapter_ref, project.name, novel_id=project.id
    )

    from prompts import load

    system = load("prompt_crafting")
    client = await get_ai_client_for_novel(project.id)
    model = "haiku"  # 符号别名，落到本书模型
    usage: dict = {}
    try:
        raw = await client.chat(
            model=model,
            max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": ctx.material_markdown()}],
            usage=usage,
        )
    except HTTPException:
        raise
    except Exception as e:  # 模型/网络错误：不落库，前端可重试
        raise HTTPException(502, f"润色调用失败：{e}") from e
    polished = strip_code_fences(raw)

    missing = validate_polished_prompt(polished, ctx)
    if missing:
        raise HTTPException(
            502,
            f"润色产物未覆盖必备段（{'、'.join(missing)}），未落库，可重试",
        )

    from prompt.store import save_prompt

    await save_prompt(project.root_path, chapter_ref, "write-prompt", polished)
    # 润色接管分段 generate 退役后的阶段推进（outline→prompt；返工回退跳过）
    _advance_phase(project, "prompt")
    await db.commit()

    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=user["id"],
        project_id=project.id,
        chapter_id=chapter_ref,
        operation="prompt_polish",
        model=model,
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )
    return {"prompt": polished, "polished": True}


@router.post("/write")
async def write_chapter(
    project_id: str,
    chapter_ref: str,
    request: Request,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """Stream an AI-written chapter based on all context data.

    可选 body {"prompt": "..."}：AI 弹窗编辑后的提示词覆盖（空/缺省 = 自动组装）。
    """
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    prompt_override = ""
    try:
        body = await request.json()
        if isinstance(body, dict):
            prompt_override = str(body.get("prompt") or "").strip()
    except (ValueError, UnicodeDecodeError):
        # 空体/非法 JSON = 无覆盖，走自动组装
        prompt_override = ""

    from write.chapter_writer import build_chapter_context

    ctx = await build_chapter_context(
        project.root_path, chapter_ref, project.name, novel_id=project.id
    )
    if prompt_override:
        prompt = prompt_override
    else:
        # 无覆盖直写：优先复用存量 write-prompt（通常是已润色版），与 GET 端点同优先级；
        # 避免粗组兜底静默覆盖已润色内容。无存量才落粗组。
        from prompt.store import load_prompt

        stored = (await load_prompt(project.root_path, chapter_ref, "write-prompt")).strip()
        prompt = stored or ctx.to_prompt()

    # Save prompt for review（chapter_prompts 表，PR④）
    from prompt.store import save_prompt

    await save_prompt(project.root_path, chapter_ref, "write-prompt", prompt)

    # 粗组兜底路径允许跳过润色直写：outline→prompt→write 桥接；返工回退跳过
    if project.current_phase == "outline":
        _advance_phase(project, "prompt")
    _advance_phase(project, "write")
    await db.commit()

    return StreamingResponse(
        _stream_chapter(db, project, project.root_path, chapter_ref, ctx, prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/continue")
async def continue_writing(
    project_id: str,
    chapter_ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """Stream continuation text from a cursor position."""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    cursor_position = body.get("cursor_position", -1)
    if cursor_position < 0:
        raise HTTPException(400, "cursor_position is required and must be >= 0")

    return StreamingResponse(
        stream_continue(db, project, project.root_path, chapter_ref, cursor_position),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/polish")
async def polish_writing(
    project_id: str,
    chapter_ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """Polish selected text (non-streaming)."""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    selected_text = body.get("selected_text", "")
    if not selected_text:
        raise HTTPException(400, "selected_text is required")
    context_before = body.get("context_before", "")
    context_after = body.get("context_after", "")
    surrounding_context = (context_before + "\n" + context_after).strip()

    usage: dict = {}
    text = await polish_text(
        project.id, project.root_path, chapter_ref, selected_text, surrounding_context, usage=usage
    )
    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=project.user_id,
        project_id=project.id,
        chapter_id=chapter_ref,
        operation="polish",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )
    return {"polished_text": text}


@router.post("/expand")
async def expand_writing(
    project_id: str,
    chapter_ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """Expand selected text (non-streaming)."""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    selected_text = body.get("selected_text", "")
    if not selected_text:
        raise HTTPException(400, "selected_text is required")
    context_before = body.get("context_before", "")
    context_after = body.get("context_after", "")
    surrounding_context = (context_before + "\n" + context_after).strip()

    usage: dict = {}
    text = await expand_text(
        project.id, project.root_path, chapter_ref, selected_text, surrounding_context, usage=usage
    )
    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=project.user_id,
        project_id=project.id,
        chapter_id=chapter_ref,
        operation="expand",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )
    return {"expanded_text": text}
