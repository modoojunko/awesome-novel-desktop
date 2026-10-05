"""Auxiliary writing service — polish, expand, and compress text via AI."""


from ai_client import get_ai_client_for_novel
from prompts import load_layers
from settings.render import style_section
from workflow.engine import load_chapter


def _format_style(style: dict) -> str:
    """文风三区（style-settings-v2）：身份→红线→手法（单一来源，沿 chapter_writer 口径）。"""
    sec = style_section(style)
    return sec or (f"叙事角色：{style.get('role', '')}" if style.get("role") else "")


def _format_anti_ai(style: dict) -> str:
    """禁用词/句式提示（banned-words-into-style：单源自文风 KV 硬约束区）。

    c-ai-material-audit：旧实现只给前 15 个禁用词/5 条句式，而作者可填 100 条
    （`style_model._MAX_BANNED`）且写正文路径是全量注入——辅助路径同口径不截。
    """
    parts = []
    words = [str(w) for w in (style.get("banned_words") or [])]
    if words:
        parts.append(f"禁止词汇：{'、'.join(words)}")
    tic_patterns = style.get("tic_patterns") or []
    if tic_patterns:
        patterns = [r.get("pattern", "") for r in tic_patterns if isinstance(r, dict)]
        if patterns:
            parts.append(f"禁止句式：{'；'.join(patterns)}")
    return "\n".join(parts)


async def build_auxiliary_context(
    root_path: str,
    chapter_ref: str,
    style_settings: dict | None = None,
    novel_id: str | None = None,
) -> dict[str, str]:
    """Build context dictionary for auxiliary writing from chapter data and settings.

    Returns a dict with pre-formatted string values suitable for prompt templates:
        writing_style, anti_ai_rules,
        character_snapshots, active_hooks, _role, _writing_model
    """
    ctx: dict[str, str] = {}

    # Writing style — resolve once and store metadata for caller
    # banned-words-into-style：统一迁移感知读路径（禁用词/句式随 style 单源）
    if style_settings is not None:
        style = style_settings
    else:
        from settings.style_model import read_style_migrated

        style = await read_style_migrated(root_path)
    ctx["writing_style"] = _format_style(style)
    ctx["_role"] = style.get("role", "一位小说家")
    # D12：模型＝书级（novel.ai_model），writing_model 不再作为模型来源；
    # 这里只传符号别名，客户端层 resolve() 落到本书模型。
    ctx["_writing_model"] = "haiku"

    # Anti-ai rules（＝文风 KV 禁用词/句式，单源）
    ctx["anti_ai_rules"] = _format_anti_ai(style)

    # Chapter — 角色快照取章纲出场名单
    chapter = await load_chapter(root_path, chapter_ref)

    # Character snapshots from chapter outline
    outline = chapter.get("outline", {})
    char_names = outline.get("characters", []) if isinstance(outline, dict) else []
    snap_lines = []
    if isinstance(char_names, list) and char_names:
        # c-ai-material-audit：旧路径读已退役的 settings/character-setting/*.yaml（v2 起不再写）
        # → 「角色状态」恒为「（暂无角色信息）」，续写在不知道人物是谁的情况下写。
        # 改走真表，与写章同源：人设原文＋语言特征（取不名字→显式缺省，不静默）。
        if not novel_id:
            from write.chapter_writer import _novel_id_by_root

            novel_id = await _novel_id_by_root(root_path)
        cards: dict[str, dict] = {}
        if novel_id:
            from db import async_session
            from settings.character_service import list_characters

            async with async_session() as session:
                roster = await list_characters(session, novel_id)
            for item in roster.get("items", []):
                key = str(item.get("name") or "")
                if key:
                    cards[key] = item
                for alias in item.get("aliases") or []:
                    cards.setdefault(str(alias), item)
        for name in char_names:
            if not isinstance(name, str):
                continue
            card = cards.get(name)
            if card is None:
                snap_lines.append(f"- {name}：（未建卡）")
                continue
            state = str(card.get("persona") or "").strip()
            speech = str((card.get("dossier") or {}).get("speech") or "").strip()
            seg = f"- {card.get('name') or name}：{state}"
            if speech:
                seg += f"（语言特征：{speech}）"
            snap_lines.append(seg)
    ctx["character_snapshots"] = (
        "\n".join(snap_lines) if snap_lines else "（暂无角色信息）"
    )

    # Active hooks（真表 novel_hooks：status==active、本章引入按章 id 排除；
    # 无 novel_id 降级为空——KV 通道已随 foreshadow-settings-v2 退役）
    from prompt.context import active_hooks_for_chapter

    hooks = await active_hooks_for_chapter(root_path, chapter_ref, novel_id)
    if hooks:
        hook_lines = []
        for h in hooks[:8]:
            code = h.get("code") or ""
            prefix = f"[{code}] " if code else ""
            label = h.get("priority_label") or ""
            hook_lines.append(
                f"- {prefix}{h.get('description', '?')}"
                + (f"（优先级：{label}）" if label else "")
            )
        ctx["active_hooks"] = "\n".join(hook_lines)
    else:
        ctx["active_hooks"] = "（暂无活跃伏笔）"

    return ctx


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
    ctx = await build_auxiliary_context(
        root_path, chapter_ref, style_settings, novel_id=novel_id
    )
    ctx["selected_text"] = selected_text
    ctx["surrounding_context"] = surrounding_context
    # 去AI味：文风禁用词/句式单源注入（「（无）」兜底口径）；
    # 未配文风时给显式降级语，避免空节让弱模型脑补文风
    ctx["anti_ai_rules"] = ctx.get("anti_ai_rules") or "（无）"
    ctx["writing_style"] = ctx.get("writing_style") or "（未配置，以原文自身文风为准）"

    _sys_t, _usr_t = load_layers("polish_text")
    prompt = _usr_t.format(**ctx)

    resolved_model = model or ctx.pop("_writing_model", "haiku")
    # 计量口径：实际生效模型由端点用 effective_model(project) 记（见 D11 ⑧）
    role = ctx.pop("_role", "一位小说家")
    if usage is not None:
        usage.pop("model", None)  # 实际模型由端点记（effective_model）

    client = await get_ai_client_for_novel(novel_id)
    # c-polish-prompt-anti-ai 评审 P2：v4 信息轮次化放宽至 160% 且选区无长度上限，
    # 固定 2048 会在大选区上截断产物——预算随选区伸缩（产物 ≤1.6×选区，中文按约 1.5 token/字留余量），封顶 4096。
    max_tokens = min(4096, 1024 + 2 * len(selected_text))
    return await client.chat(
        model=resolved_model,
        system=((_sys_t.format(**ctx) + f"；叙事角色定位：{role}") if _sys_t else f"你是一位资深小说编辑，专治「AI 腔」，请遵循以下角色定位：{role}"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        usage=usage,
    )
