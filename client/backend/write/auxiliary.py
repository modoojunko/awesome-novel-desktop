"""Auxiliary writing service — continue, polish, and expand text via AI."""

import json

from ai_client import get_ai_client_for_novel
from filesystem.storage import get_storage
from prompts import load as load_prompt
from settings.render import depiction_techniques_str, flatten_principles
from workflow.engine import load_chapter, save_chapter


def _format_style(style: dict) -> str:
    """Format writing style dict into a readable string."""
    parts = []
    role = style.get("role", "")
    if role:
        parts.append(f"叙事角色：{role}")
    principles = flatten_principles(style.get("core_principles"))
    if principles:
        parts.append(f"写作原则：{'；'.join(principles[:3])}")
    techniques = depiction_techniques_str(style)
    if techniques:
        parts.append(techniques)
    return "\n".join(parts)


def _format_anti_ai(rules: dict) -> str:
    """Format anti-ai rules into a readable string."""
    parts = []
    fatigue = rules.get("fatigue_words_zh", {})
    words = []
    for category in fatigue.values():
        if isinstance(category, list):
            words.extend(category)
    if words:
        parts.append(f"禁止词汇：{'、'.join(words[:15])}")
    tic_patterns = rules.get("structural_tic_patterns", [])
    if tic_patterns:
        patterns = [r.get("pattern", "") for r in tic_patterns if isinstance(r, dict)]
        if patterns:
            parts.append(f"禁止句式：{'；'.join(patterns[:5])}")
    return "\n".join(parts)


async def build_auxiliary_context(
    root_path: str,
    chapter_ref: str,
    style_settings: dict | None = None,
) -> dict[str, str]:
    """Build context dictionary for auxiliary writing from chapter data and settings.

    Returns a dict with pre-formatted string values suitable for prompt templates:
        writing_style, anti_ai_rules, recent_context,
        character_snapshots, active_hooks, _role, _writing_model
    """
    ctx: dict[str, str] = {}

    # Writing style — resolve once and store metadata for caller
    style = (
        style_settings
        if style_settings is not None
        else (
            await get_storage().read_yaml(root_path, "settings/writing-style.yaml")
            or {}
        )
    )
    ctx["writing_style"] = _format_style(style)
    ctx["_role"] = style.get("role", "一位小说家")
    # D12：模型＝书级（novel.ai_model），writing_model 不再作为模型来源；
    # 这里只传符号别名，客户端层 resolve() 落到本书模型。
    ctx["_writing_model"] = "haiku"

    # Anti-ai rules
    anti_ai = await get_storage().read_yaml(root_path, "settings/anti-ai.yaml") or {}
    ctx["anti_ai_rules"] = _format_anti_ai(anti_ai)

    # Chapter — recent context from end of existing prose
    chapter = await load_chapter(root_path, chapter_ref)
    prose = chapter.get("prose", "")
    ctx["recent_context"] = prose[-1500:] if len(prose) > 1500 else prose

    # Character snapshots from chapter outline
    outline = chapter.get("outline", {})
    char_names = outline.get("characters", []) if isinstance(outline, dict) else []
    snap_lines = []
    if isinstance(char_names, list):
        for name in char_names[:5]:
            if isinstance(name, str):
                ch_data = (
                    await get_storage().read_yaml(
                        root_path, f"settings/character-setting/{name}.yaml"
                    )
                    or {}
                )
                state = ""
                state_history = ch_data.get("state_history", [])
                if isinstance(state_history, list) and state_history:
                    last = state_history[-1]
                    if isinstance(last, dict):
                        state = last.get("state", "")
                personality = ch_data.get("personality", "")
                if not state:
                    state = personality
                snap_lines.append(f"- {name}：{state}")
    ctx["character_snapshots"] = (
        "\n".join(snap_lines) if snap_lines else "（暂无角色信息）"
    )

    # Active hooks
    hooks_data = await get_storage().read_yaml(root_path, "settings/hooks.yaml") or {}
    hooks = hooks_data.get("active", [])
    if hooks and isinstance(hooks, list):
        hook_lines = [
            f"- {h.get('description', '?')}" for h in hooks[:8] if isinstance(h, dict)
        ]
        ctx["active_hooks"] = "\n".join(hook_lines)
    else:
        ctx["active_hooks"] = "（暂无活跃伏笔）"

    return ctx


async def stream_continue(
    db,
    project,
    root_path: str,
    chapter_ref: str,
    cursor_position: int,
    style_settings: dict | None = None,
    model: str | None = None,
):
    """SSE-stream continuation text from a cursor position.

    Builds context, formats the continue_writing prompt, and streams
    AI-generated prose. On completion, saves the updated prose into
    the chapter and creates a version snapshot (BE-02: 续写后刷新 DB 元数据).

    Yields JSON-encoded SSE events: chunk, done, error.
    """
    # Load chapter and extract pre-cursor text as recent context
    chapter = await load_chapter(root_path, chapter_ref)
    existing_prose = chapter.get("prose", "")

    # Get context (will overwrite recent_context with cursor-specific text)
    ctx = await build_auxiliary_context(root_path, chapter_ref, style_settings)
    cursor_start = max(0, cursor_position - 1500)
    ctx["recent_context"] = existing_prose[cursor_start:cursor_position]
    ctx["anti_ai_rules"] = ctx.get("anti_ai_rules", "（无）")

    # Format the prompt
    prompt_template = load_prompt("continue_writing")
    prompt = prompt_template.format(**ctx)

    # Model and role from resolved context
    resolved_model = model or ctx.pop("_writing_model", "haiku")
    # 计量口径：实际生效模型由端点用 effective_model(project) 记（见 D11 ⑧）
    role = ctx.pop("_role", "一位小说家")

    # Stream
    client = await get_ai_client_for_novel(project.id)
    generated_text = ""

    async for event in client.chat_stream(
        model=resolved_model,
        system=role,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    ):
        if event.text:
            generated_text += event.text
            yield f"data: {json.dumps({'type': 'chunk', 'text': event.text}, ensure_ascii=False)}\n\n"
        elif event.is_done:
            # Save updated prose（统一写入口：落库 + 元数据派生 + 版本快照）
            new_prose = existing_prose[:cursor_position] + generated_text
            chapter["prose"] = new_prose
            await save_chapter(root_path, chapter_ref, chapter)

            from api_configs.usage import record_usage

            await record_usage(
                db,
                user_id=project.user_id,
                project_id=project.id,
                chapter_id=chapter_ref,
                operation="continue",
                model=resolved_model,
                tokens_out=event.tokens,
            )

            yield f"data: {json.dumps({'type': 'done', 'full_text': generated_text, 'tokens': event.tokens}, ensure_ascii=False)}\n\n"
        elif event.error:
            yield f"data: {json.dumps({'type': 'error', 'error': event.error}, ensure_ascii=False)}\n\n"


async def polish_text(
    novel_id: str,
    root_path: str,
    chapter_ref: str,
    selected_text: str,
    surrounding_context: str,
    style_settings: dict | None = None,
    model: str | None = None,
    usage: dict | None = None,
) -> str:
    """Polish selected text (non-streaming). Returns polished text string.

    usage: 可选 dict，调用后填充 {"model", "tokens_in", "tokens_out"}。
    """
    ctx = await build_auxiliary_context(root_path, chapter_ref, style_settings)
    ctx["selected_text"] = selected_text
    ctx["surrounding_context"] = surrounding_context

    prompt_template = load_prompt("polish_text")
    prompt = prompt_template.format(**ctx)

    resolved_model = model or ctx.pop("_writing_model", "haiku")
    # 计量口径：实际生效模型由端点用 effective_model(project) 记（见 D11 ⑧）
    role = ctx.pop("_role", "一位小说家")
    if usage is not None:
        usage.pop("model", None)  # 实际模型由端点记（effective_model）

    client = await get_ai_client_for_novel(novel_id)
    return await client.chat(
        model=resolved_model,
        system=f"你是一位文字编辑专家，请遵循以下角色定位：{role}",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
        usage=usage,
    )


async def expand_text(
    novel_id: str,
    root_path: str,
    chapter_ref: str,
    selected_text: str,
    surrounding_context: str,
    style_settings: dict | None = None,
    model: str | None = None,
    usage: dict | None = None,
) -> str:
    """Expand selected text (non-streaming). Returns expanded text string.

    usage: 可选 dict，调用后填充 {"model", "tokens_in", "tokens_out"}。
    """
    ctx = await build_auxiliary_context(root_path, chapter_ref, style_settings)
    ctx["selected_text"] = selected_text
    ctx["surrounding_context"] = surrounding_context

    prompt_template = load_prompt("expand_text")
    prompt = prompt_template.format(**ctx)

    resolved_model = model or ctx.pop("_writing_model", "haiku")
    # 计量口径：实际生效模型由端点用 effective_model(project) 记（见 D11 ⑧）
    role = ctx.pop("_role", "一位小说家")
    if usage is not None:
        usage.pop("model", None)  # 实际模型由端点记（effective_model）

    client = await get_ai_client_for_novel(novel_id)
    return await client.chat(
        model=resolved_model,
        system=f"你是一位擅长细节描写的文学作家，请遵循以下角色定位：{role}",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
        usage=usage,
    )
