"""上下文装配（c-writing-agent 批A 1.6）。

三层（design §上下文三层与 compact）：
  L1 书级冻结前缀 —— 会话建立时冻结：身份/围栏纪律（identity 提供）＋ ≤300 字书级
     brief（书名/题材/进度）。逐字节稳定（前缀缓存判例 write/router.py:191-193）。
  L2 页面级活注入 —— 附加到末条 user 消息（openwriter context_provider 模式）：
     当前页面、聚焦对象、作家画像相关项。
  L3 滑窗＋compact —— compact.py 的 apply_to_outbound（工具结果最先牺牲）。

预注入只留 brief；细节由 agent 按需 read_*（design：全量预注入对 8 步循环是 8 倍
重复计费）。
"""

from __future__ import annotations

from typing import Any

from assistant.compact import apply_to_outbound
from assistant.compact import estimate_tokens as _estimate_tokens

# 书级 brief 预算（字符；write/chapter_writer.py 按字预算同风格）
BOOK_BRIEF_BUDGET_CHARS = 300
# 转写窗口预算（超出触发 compact 判定的估算信号走 compaction.should_compact）
WINDOW_BUDGET_CHARS = 120_000


async def build_book_brief(novel: Any, db: Any) -> str:
    """≤300 字书级 brief：书名/题材/进度（frontier）。失败降级为仅书名。"""
    from chapters.frontier import frontier_info

    name = str(getattr(novel, "name", "") or "")
    lines = [f"书名：{name}"]
    try:
        from genres.service import resolve_genre_context

        gctx = await resolve_genre_context(getattr(novel, "root_path", ""), novel.id)
        genre_name = str(gctx.get("genre") or gctx.get("genre_name") or "")
        if genre_name:
            lines.append(f"题材：{genre_name}")
    except Exception as e:  # brief 缺题材不致命（BLE001 豁免）
        import logging

        logging.getLogger(__name__).debug("genre brief skipped: %s", e)
    try:
        info = await frontier_info(db, novel.id)
        chapters = info.get("chapters")
        if isinstance(chapters, list) and chapters:
            lines.append(
                f"进度：frontier 章 {info.get('ref')}（第 {info.get('global_no')} 章，{info.get('state')}）"
            )
        else:
            lines.append("进度：空书（还没有章节）")
    except Exception:  # noqa: BLE001
        pass
    brief = "；".join(lines)
    if len(brief) > BOOK_BRIEF_BUDGET_CHARS:
        brief = brief[: BOOK_BRIEF_BUDGET_CHARS - 1] + "…"
    return brief


def build_page_note(page: str, focus: dict[str, Any] | None = None) -> str:
    """L2 页面级注入文本（随当前消息尾随行进提示词，router 负责 消息\\n注入 的拼装）。
    注册制页面提供 focus 明细；批A 仅有页面名。"""
    if not page:
        return ""
    parts = [f"［当前页面：{page}］"]
    if focus:
        parts.append(f"［聚焦对象：{focus.get('label', '')}］")
    return " ".join(p for p in parts if p.strip())


def build_outbound_window(
    transcript: list[dict[str, Any]],
    *,
    compaction_state: Any,
    keep_tokens: int | None = None,
) -> tuple[list[dict[str, str]], int]:
    """L3：转写 → 外发窗口（compact 应用）＋返回估算 tokens（供下一步触发判定）。"""
    outbound = apply_to_outbound(transcript, compaction_state)
    clean = [
        {"role": str(m.get("role")), "content": str(m.get("content", ""))}
        for m in outbound
        if m.get("role") in ("user", "assistant")
    ]
    return clean, _estimate_tokens(clean)
