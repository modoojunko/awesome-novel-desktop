import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import AITimeoutError
from ai_state import effective_model
from auth_local.deps import require_ai_access, require_novel_model
from auth_local.middleware import get_current_user
from db import get_db
from novels.service import get_novel
from prompts import load as load_prompt
from prompts import load_layers
from workflow.engine import _validate_ref, advance_phase, load_chapter


def _advance_phase(project, target: str) -> None:
    """宽容推进（engine.advance_phase 单源）：阶段机只进不退，返工（如 write 阶段
    重润色→prompt）不允许回退——跳过推进而非抛 ValueError→500：润色/生成结果
    本身已合法落库，阶段标记保持现状不影响后续操作（write/archive 均为幂等入口）。
    """
    advance_phase(project, target)
from write.auxiliary import compress_text, expand_text, polish_text, stream_continue
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
    from write.chapter_writer import WRITE_CLOSING_LINE, normalize_generated_prose

    client = await get_ai_client_for_novel(project.id)
    # 符号别名：模型由本书绑定决定（D12，不再读 writing_model）
    model = "haiku"
    # system 恒定层（c-write-prompt-layering）：本书设定组装、逐章字节一致，
    # 铁律与仲裁句在模板 prompts/write_chapter.prompt；身份句走 resolve_persona 单源
    system = ctx.build_system_prompt()
    # 收尾重申行：user 内容最末字节强制追加（同词不同句），不落库不进预览
    prompt = f"{prompt.rstrip()}\n\n{WRITE_CLOSING_LINE}"
    full_text = ""

    try:
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
                # 分段归一（段间空行→单换行）：字数校验/自查/落库/done 全用同一份
                full_text = normalize_generated_prose(full_text)
                try:
                    chapter = await load_chapter(root_path, chapter_ref)
                    chapter["prose"] = full_text
                    # 统一写入口（修直写缺陷）：拆装落库 + 元数据派生 + 版本快照
                    await save_chapter(db, project, chapter_ref, chapter)
                except Exception as e:  # noqa: BLE001 — AI 已成功，落库失败不记 _fail
                    yield f"data: {json.dumps({'type': 'error', 'error': f'内容已生成，但保存失败：{e!s}'}, ensure_ascii=False)}\n\n"
                    return
                from api_configs.usage import record_usage

                await record_usage(
                    db,
                    user_id=project.user_id,
                    project_id=project.id,
                    chapter_id=chapter_ref,
                    operation="write_chapter",
                    model=model,
                    tokens_out=event.tokens,
                    tokens_in=event.tokens_in,
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
    except AITimeoutError:
        from api_configs.usage import record_usage

        await record_usage(
            db,
            user_id=project.user_id,
            project_id=project.id,
            chapter_id=chapter_ref,
            operation="write_chapter_fail",
            model=model,
            force=True,
        )
        yield f"data: {json.dumps({'type': 'error', 'error': 'AI 服务响应超时，请稍后重试'}, ensure_ascii=False)}\n\n"
    except Exception as e:  # noqa: BLE001 — 流中断也留痕（调用已发生）
        from api_configs.usage import record_usage

        await record_usage(
            db,
            user_id=project.user_id,
            project_id=project.id,
            chapter_id=chapter_ref,
            operation="write_chapter_fail",
            model=model,
            force=True,
        )
        yield f"data: {json.dumps({'type': 'error', 'error': f'AI 生成失败，可重试：{e!s}'}, ensure_ascii=False)}\n\n"


@router.get("/prompt")
async def get_write_prompt(
    project_id: str,
    chapter_ref: str,
    fresh: bool = False,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """AI 弹窗提示词预览：存量 write-prompt 行优先（润色/编辑结果），无则粗组兜底。

    fresh=True（弹窗「刷新提示词」）：忽略存量行按当前素材重新组装，只回新稿
    不动存量行——落库仍只走润色/「存为本章提示词」。
    """
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    from prompt.store import load_prompt
    from write.chapter_writer import build_chapter_context, legacy_prompt_kind

    ctx = await build_chapter_context(
        project.root_path, chapter_ref, project.name, novel_id=project.id
    )
    outline = ctx.chapter_outline or {}
    # c-og-slim-v2：关键事件/段落规划退役 → 有章纲的判定＝概要或剧情条目
    has_outline = bool(outline.get("summary") or ctx.plot_items)
    if not fresh:
        existing = await load_prompt(project.root_path, chapter_ref, "write-prompt")
        if existing.strip():
            # legacy：旧版整包行（含恒定设定）→ 弹窗分级提示（润色行信息性、粗组行建议刷新）
            return {
                "prompt": existing,
                "has_outline": has_outline,
                "polished": True,
                "legacy": bool(legacy_prompt_kind(existing)),
                "legacy_kind": legacy_prompt_kind(existing),
                "warnings": ctx.lint_warnings,
            }
    return {
        "prompt": ctx.to_user_material(),
        "has_outline": has_outline,
        "polished": False,
        "legacy": False,
        "warnings": ctx.lint_warnings,
    }


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

    from prompts import load_layers

    system, _craft_user_t = load_layers("prompt_crafting")
    client = await get_ai_client_for_novel(project.id)
    model = "haiku"  # 符号别名，落到本书模型
    usage: dict = {}
    try:
        raw = await client.chat(
            model=model,
            max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": _craft_user_t.format(material=ctx.material_markdown())}],
            usage=usage,
        )
    except AITimeoutError:
        from api_configs.usage import record_usage

        await record_usage(
            db,
            user_id=user["id"],
            project_id=project.id,
            chapter_id=chapter_ref,
            operation="prompt_polish_fail",
            model=model,
            tokens_in=usage.get("tokens_in", 0),
            tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except HTTPException:
        raise
    except Exception as e:  # 模型/网络错误：不落库，前端可重试
        from api_configs.usage import record_usage

        await record_usage(
            db,
            user_id=user["id"],
            project_id=project.id,
            chapter_id=chapter_ref,
            operation="prompt_polish_fail",
            model=model,
            tokens_in=usage.get("tokens_in", 0),
            tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, f"润色调用失败：{e}") from e

    from api_configs.usage import record_usage

    # 记账先于校验：调用已完成（钱已花），产物不合格也要留痕
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
    return {"prompt": polished, "polished": True}


# 路径为空串：本 router 的 prefix 已以 /write 结尾，再写 "/write" 会注册成
# /write/write（qa-night 2026-09-19 P1：前端调 /write 恒 404、AI 生成正文不可用）
@router.post("")
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
    # 排队门禁（workbench-frontier）：拟态章按主线顺序开写
    from chapters.frontier import is_writable

    writable, reason = await is_writable(db, project.id, chapter_ref)
    if not writable:
        raise HTTPException(409, reason)

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
        prompt = stored or ctx.to_user_material()

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
    # 排队门禁（workbench-frontier）：拟态章按主线顺序开写
    from chapters.frontier import is_writable

    writable, reason = await is_writable(db, project.id, chapter_ref)
    if not writable:
        raise HTTPException(409, reason)

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
    try:
        text = await polish_text(
            project.id, project.root_path, chapter_ref, selected_text, surrounding_context, usage=usage
        )
    except AITimeoutError:
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation="polish_fail",
            model=effective_model(project), force=True,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001 — 失败也留痕（调用已发生）
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation="polish_fail",
            model=effective_model(project),
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e
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


_REFINE_MODES = {
    "negative": "补全「负向约束」：从本章章纲与设定里提炼出必须避免的写法（例如视角越界、"
    "提前揭破悬念、情绪直说），追加到「不可违反规则」段，不删既有红线。",
    "concise": "精简提示词：删去重复与可从别处推出的表述，保留全部约束与关键设定，"
    "整体篇幅压到原文的六到八成。",
}


@router.post("/prompt/refine")
async def refine_write_prompt(
    project_id: str,
    chapter_ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """按模式修订整章写作提示词（产物不落库；作者在弹窗确认后走既有保存链）。"""
    mode = str((body or {}).get("mode", "") or "").strip()
    if mode not in _REFINE_MODES:
        raise HTTPException(400, f"未知的修订模式：{mode}")
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    from ai_client import get_ai_client_for_novel
    from write.chapter_writer import build_chapter_context, strip_code_fences

    current = str((body or {}).get("current_prompt", "") or "").strip()
    if not current:
        # 未传（未润色过的章）：以服务端组装稿为基底
        ctx = await build_chapter_context(
            project.root_path, chapter_ref, project.name, novel_id=project.id
        )
        current = ctx.to_user_material()
    if not current:
        raise HTTPException(409, "本章还没有可修订的提示词")

    _sys_t, _usr_t = load_layers("prompt_refine")
    system = _sys_t
    refined_user = _usr_t.format(
        # c-ai-material-audit：旧 `[:12000]` 会把组装稿尾部静默切掉（分层协议同批取消）
        instruction=_REFINE_MODES[mode], current_prompt=current
    )
    client = await get_ai_client_for_novel(project.id)
    usage: dict = {}
    try:
        raw = await client.chat(
            model="haiku", system=system,
            messages=[{"role": "user", "content": refined_user}],
            max_tokens=4000, usage=usage,
        )
    except AITimeoutError:
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation=f"prompt_refine_{mode}_fail",
            model=effective_model(project), force=True,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation=f"prompt_refine_{mode}_fail",
            model=effective_model(project),
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, f"AI 调用失败，可重试：{e!s}") from e

    from api_configs.usage import record_usage

    await record_usage(
        db, user_id=project.user_id, project_id=project.id,
        chapter_id=chapter_ref, operation=f"prompt_refine_{mode}",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
    )
    refined = strip_code_fences(raw).strip()
    if not refined:
        raise HTTPException(502, "修订结果为空，可重试")
    return {"ok": True, "mode": mode, "prompt": refined}


@router.post("/compress")
async def compress_writing(
    project_id: str,
    chapter_ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """Compress selected text (non-streaming)."""
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
    try:
        text = await compress_text(
            project.id, project.root_path, chapter_ref, selected_text, surrounding_context, usage=usage
        )
    except AITimeoutError:
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation="compress_fail",
            model=effective_model(project), force=True,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001 — 失败也留痕（调用已发生）
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation="compress_fail",
            model=effective_model(project),
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e
    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=project.user_id,
        project_id=project.id,
        chapter_id=chapter_ref,
        operation="compress",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )
    return {"compressed_text": text}


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
    try:
        text = await expand_text(
            project.id, project.root_path, chapter_ref, selected_text, surrounding_context, usage=usage
        )
    except AITimeoutError:
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation="expand_fail",
            model=effective_model(project), force=True,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001 — 失败也留痕（调用已发生）
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation="expand_fail",
            model=effective_model(project),
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
            force=True,
        )
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e
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
