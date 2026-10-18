"""Auxiliary writing 文风格式化单源（选区改写链已随 c-renwei-check 退役，仅留文风格式化）。"""


from settings.render import style_section


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
