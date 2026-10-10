import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import AITimeoutError
from ai_state import effective_model
from auth_local.deps import (
    ai_feature,
    require_ai_access,
    require_novel_model,
    require_tier_access,
)
from auth_local.middleware import get_current_user
from db import get_db
from novels.service import get_novel
from workflow.engine import _validate_ref, advance_phase, load_chapter


def _advance_phase(project, target: str) -> None:
    """宽容推进（engine.advance_phase 单源）：阶段机只进不退，返工不允许回退——
    跳过推进而非抛 ValueError→500：生成结果本身已合法落库，阶段标记保持现状
    不影响后续操作（write/archive 均为幂等入口）。
    """
    advance_phase(project, target)
from write.ai_flavor_scan import build_problem_segments, quick_verdict, scan_prose
from write.auxiliary import polish_text
from write.quality import run_quality_checks

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/write",
    tags=["write"],
)


# 章前缀扫描路由（c-deai-wizard）：AI 味检查挂在章上而非 /write 下——它是读侧
# 规则扫描（0 模型 0 检测额度），不是写动作；与 zhuque-result 同章前缀惯例。
scan_router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}",
    tags=["write"],
)


@scan_router.post("/ai-flavor-scan")
async def ai_flavor_scan(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI 味检查（c-deai-wizard ①）：本地确定性规则扫描＋读朱雀存档，合并问题段清单。

    0 模型 0 检测额度；无检测存档时 detector.stored=false（规则模式）。
    """
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    chapter = await load_chapter(project.root_path, chapter_ref) or {}
    prose = chapter.get("prose") or ""
    if not prose.strip():
        raise HTTPException(400, "先写正文，再跑 AI 味检查")

    report = scan_prose(prose)
    paragraphs = [p.strip() for p in prose.split("\n") if p.strip()]

    from zhuque.service import get_stored_result

    stored = await get_stored_result(db, project_id=project_id, chapter_ref=chapter_ref)
    stored_segments = stored.get("result", {}).get("segments") if stored.get("stored") else None
    human_ratio = (
        stored.get("result", {}).get("summary", {}).get("human_ratio") if stored.get("stored") else None
    )

    problems = build_problem_segments(paragraphs, report, stored_segments)
    return {
        "ok": True,
        "report": report,
        "problems": problems,
        "detector": {
            "stored": bool(stored.get("stored")),
            "human_ratio": human_ratio,
            "stale_hint": None,
        },
    }


@router.post("/quality-check")
async def quality_check(
    project_id: str,
    chapter_ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    full_text = body.get("full_text", "")
    results = await run_quality_checks(project.root_path, full_text)
    return results


async def _stream_chapter(
    db,
    project,
    root_path: str,
    chapter_ref: str,
    *,
    prompt_override: str = "",
    override_client=None,
    override_model: str = "",
    override_config_id: str = "",
):
    """Generate chapter text via AI streaming, save on completion (BE-01: 写完刷新 DB 元数据).

    事件契约（c-prose-gen-phases）：`phase`（assemble|prompt|model，标记当前阶段**开始**）
    → `chunk`* → `done`｜`error`。阶段事件按真实进度下发，供首字前等待呈现消费
    （SHALL NOT 用固定时长剧本充数）。

    三工序（ai-prompt-crafting）：①system 注入写作铁律；②完成时字数校验（<90% 提示不拦）；
    ③完成时叙事自查清单（提示性质）——随 done 事件返回。

    准备段（素材组装／提示词定稿／恒定层组装）在**流内**执行并包错误收尾：原实现该段在
    响应开始之后、try 之外，一失败即「200 + 干净空流」——客户端收不到任何终态事件
    （c-prose-stream-silent-hang 路径①）。可读 4xx 校验（会员/档位/模型就绪/排队门禁/
    按次模型对）仍留在路由层、开流前。

    c-prose-model-select：`override_client` 给定时走**按次覆盖对**（开流前已校验，仅本次
    生成），否则流内按本书绑定构造；记账恒记**实际生效模型 id ＋ 配置 id**（成功/超时/失败
    三处同口径——原记别名 `haiku` 且配置为空，违反「计量层记实际模型 id」）。
    """
    import logging

    from ai_client import get_ai_client_for_novel
    from chapters.service import save_chapter
    from prompt.store import load_prompt, save_prompt
    from write.chapter_writer import (
        WRITE_CLOSING_LINE,
        build_chapter_context,
        normalize_generated_prose,
        should_refresh_stored_prompt,
        word_target_floor,
    )

    logger = logging.getLogger(__name__)

    def _phase(name: str) -> str:
        return f"data: {json.dumps({'type': 'phase', 'phase': name}, ensure_ascii=False)}\n\n"

    ctx = None
    client = None
    system = ""
    prompt = ""
    used_model = ""
    used_config_id = ""
    try:
        # ① 组装本章素材（章纲／卷纲／设定／世界观／角色档案／伏笔／前情／故事状态）
        yield _phase("assemble")
        ctx = await build_chapter_context(
            root_path, chapter_ref, project.name, novel_id=project.id
        )
        # ② 定稿提示词（弹窗覆盖 > 存量回升 > 本次组装）＋恒定层组装；阶段推进与存稿同批
        yield _phase("prompt")
        if prompt_override:
            prompt = prompt_override
        else:
            stored = (await load_prompt(root_path, chapter_ref, "write-prompt")).strip()
            prompt = (
                ctx.to_user_material()
                if should_refresh_stored_prompt(stored, ctx)
                else (stored or ctx.to_user_material())
            )
        await save_prompt(root_path, chapter_ref, "write-prompt", prompt)
        # 无覆盖直写路径：outline→prompt→write 桥接；返工回退跳过
        if project.current_phase == "outline":
            _advance_phase(project, "prompt")
        _advance_phase(project, "write")
        await db.commit()
        # system 恒定层（c-write-prompt-layering）：本书设定组装、逐章字节一致，
        # 铁律与仲裁句在模板 prompts/write_chapter.prompt；身份句走 resolve_persona 单源
        system = ctx.build_system_prompt()
        if override_client is not None:
            client = override_client
            used_model = override_model
            used_config_id = override_config_id
        else:
            client = await get_ai_client_for_novel(project.id)
            used_model = effective_model(project)
            used_config_id = project.ai_config_id or ""
    except Exception as e:  # noqa: BLE001 — 准备段失败也必须有终态事件（SHALL NOT 静默空流）
        from prompts import PromptPackMissing

        if isinstance(e, PromptPackMissing):
            # 写作能力（提示词包）未就绪：与 503 收敛点同款留痕（c-prompt-pack-client 4.1）
            # ——缺包信号进日志（uvicorn.error）：前端四态卡口径与测试「缺源跳过」判据同源
            logging.getLogger("uvicorn.error").info(
                "event=prompts_missing path=write/%s", chapter_ref
            )
            msg = "写作能力还没就绪 — 登录后会自动获取；也可点「重新获取」重试"
        else:
            msg = f"准备生成失败，可重试：{e!s}"
        logger.warning(
            "write prepare failed: project=%s ref=%s err=%s",
            project.id, chapter_ref, e, exc_info=True,
        )
        yield (
            "data: " + json.dumps({"type": "error", "error": msg}, ensure_ascii=False) + "\n\n"
        )
        return

    # 符号别名：模型由构造期 self._model 决定（D12，不再读 writing_model）
    model = "haiku"
    # 收尾重申行：user 内容最末字节强制追加（同词不同句），不落库不进预览
    prompt = f"{prompt.rstrip()}\n\n{WRITE_CLOSING_LINE}"
    full_text = ""
    # ③ 调用模型（首字前停留最久的一段；等待呈现以此阶段为当前步）
    yield _phase("model")

    try:
        async for event in client.chat_stream(
            model=model,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8192,
            operation="write_chapter",
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
                    api_config_id=used_config_id or None,
                    chapter_id=chapter_ref,
                    operation="write_chapter",
                    model=used_model,
                    tokens_out=event.tokens,
                    tokens_in=event.tokens_in,
                )
                done: dict = {"type": "done", "full_text": full_text, "tokens": event.tokens}
                # 工序②：写完字数校验（低于下限＝目标-10%，与提示词同口径；提示不拦落库）
                target = getattr(ctx, "word_target", 2500) or 2500
                actual = len(full_text)
                word_check = {
                    "target": target,
                    "actual": actual,
                    "below_limit": actual < word_target_floor(target),
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
            api_config_id=used_config_id or None,
            chapter_id=chapter_ref,
            operation="write_chapter_fail",
            model=used_model,
            force=True,
        )
        yield f"data: {json.dumps({'type': 'error', 'error': 'AI 服务响应超时，请稍后重试'}, ensure_ascii=False)}\n\n"
    except Exception as e:  # noqa: BLE001 — 流中断也留痕（调用已发生）
        from api_configs.usage import record_usage

        await record_usage(
            db,
            user_id=project.user_id,
            project_id=project.id,
            api_config_id=used_config_id or None,
            chapter_id=chapter_ref,
            operation="write_chapter_fail",
            model=used_model,
            force=True,
        )
        yield f"data: {json.dumps({'type': 'error', 'error': f'AI 生成失败，可重试：{e!s}'}, ensure_ascii=False)}\n\n"


@router.get("/prompt")
@ai_feature("prompt-panel")
async def get_write_prompt(
    project_id: str,
    chapter_ref: str,
    fresh: bool = False,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_tier_access),
    db: AsyncSession = Depends(get_db),
):
    """AI 弹窗提示词预览：存量 write-prompt 行优先（作家存稿/历史润色行），无则组装兜底。

    fresh=True（弹窗「刷新提示词」）：忽略存量行按当前素材重新组装，只回新稿
    不动存量行——落库走「存为本章提示词」与生成时的自动留存。
    """
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    from prompt.store import load_prompt
    from write.chapter_writer import (
        build_chapter_context,
        legacy_prompt_kind,
        should_refresh_stored_prompt,
    )

    ctx = await build_chapter_context(
        project.root_path, chapter_ref, project.name, novel_id=project.id
    )
    outline = ctx.chapter_outline or {}
    # c-og-slim-v2：关键事件/段落规划退役 → 有章纲的判定＝概要或剧情条目
    has_outline = bool(outline.get("summary") or ctx.plot_items)
    if not fresh:
        existing = await load_prompt(project.root_path, chapter_ref, "write-prompt")
        if existing.strip() and not should_refresh_stored_prompt(existing, ctx):
            # legacy：旧版整包行（含恒定设定）→ 弹窗分级提示（旧润色行信息性、旧粗组行建议刷新）
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


# 路径为空串：本 router 的 prefix 已以 /write 结尾，再写 "/write" 会注册成
# /write/write（qa-night 2026-09-19 P1：前端调 /write 恒 404、AI 生成正文不可用）
@router.post("")
@ai_feature("ai-generate")
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
    可选 body {"api_config_id": "...", "model": "..."}：**按次模型对**（c-prose-model-select
    「生成模型」选择位）——成对给出时本次生成用该配置+模型（不落库、不改本书绑定），
    开流前按绑定同源谓词校验，失败 400 可读错因；缺省 = 本书模型（今日路径逐字不变）。
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
    api_config_id = ""
    model_override = ""
    try:
        body = await request.json()
        if isinstance(body, dict):
            prompt_override = str(body.get("prompt") or "").strip()
            api_config_id = str(body.get("api_config_id") or "").strip()
            model_override = str(body.get("model") or "").strip()
    except (ValueError, UnicodeDecodeError):
        # 空体/非法 JSON = 无覆盖，走自动组装
        prompt_override = ""
        api_config_id = ""
        model_override = ""

    # 按次模型对：开流前解析覆盖客户端——非法对 400（可读错因、可换模型重试），
    # 不产生流式响应、不发起调用、不落任何副作用；缺省时保持今日路径（流内按本书绑定构造）
    override_client = None
    if api_config_id or model_override:
        from ai_client import get_ai_client_for_novel

        try:
            override_client = await get_ai_client_for_novel(
                project.id,
                api_config_id=api_config_id or None,
                model=model_override or None,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    # c-prose-gen-phases：准备段（素材组装／提示词定稿／存稿／阶段推进／恒定层组装）
    # 移入流内执行——阶段事件要按真实进度下发，且该段失败须以 error 事件收尾
    # （原先在响应开始后、try 之外，失败即静默 200 空流）。开流前只保留可读 4xx 校验。
    return StreamingResponse(
        _stream_chapter(
            db,
            project,
            project.root_path,
            chapter_ref,
            prompt_override=prompt_override,
            override_client=override_client,
            override_model=model_override,
            override_config_id=api_config_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )




@router.post("/polish")
@ai_feature("ai-polish")
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
    # c-deai-wizard：程序化派生（非模型自报）——changed 供向导区分「确诊零合法无操作」，
    # flags 为改稿快扫（新增红线 blocking／字数带等 advisory）。老客户端忽略附加字段。
    folded = lambda s: "".join(str(s or "").split())  # noqa: E731
    from settings.style_model import read_style_migrated

    style = await read_style_migrated(project.root_path)
    banned_words = [str(w) for w in (style.get("banned_words") or [])]
    verdict = quick_verdict(selected_text, text, banned_words)
    return {
        "polished_text": text,
        "changed": folded(text) != folded(selected_text),
        "flags": verdict["flags"],
        "flags_blocking": verdict["blocking"],
    }


    return {"compressed_text": text}


    return {"expanded_text": text}
