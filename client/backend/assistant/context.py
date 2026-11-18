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


# 章节状态中文映射（brief/进度面向作家，禁内部词——frontier/draft 不出模型口）
_STATE_ZH = {"draft": "草稿", "pending": "待写", "confirmed": "章纲已确认", "archived": "已归档"}


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
            archived = sum(1 for ch in chapters if ch.get("archived"))
            fr = info.get("frontier") or {}
            state = _STATE_ZH.get(str(fr.get("state") or ""), "写作中")
            lines.append(
                f"进度：全书 {len(chapters)} 章（已归档 {archived}）；"
                f"当前写到 第 {fr.get('global_no')} 章（{state}）"
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
        # label 缺省回退 ref——不输出空的「聚焦对象：」（模型会照学「聚焦是空的」）
        label = str(focus.get("label") or focus.get("ref") or "").strip()
        if label:
            parts.append(f"［聚焦对象：{label}］")
    return " ".join(p for p in parts if p.strip())


def build_outbound_window(
    transcript: list[dict[str, Any]],
    *,
    compaction_state: Any,
    keep_tokens: int | None = None,
    native: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """L3：转写 → 外发窗口（compact 应用）＋返回估算 tokens（供下一步触发判定）。

    native=True（c-agent-harness tasks 4.2）：保留 openai 原生形态——assistant 的
    tool_calls 与 role=tool 结果行原样携带（API 校验链必需）；文本协议口径不变
    （只留 user/assistant 的 role+content）。
    """
    outbound = apply_to_outbound(transcript, compaction_state)
    if native:
        clean: list[dict[str, Any]] = []
        for m in outbound:
            role = str(m.get("role"))
            if role not in ("user", "assistant", "tool"):
                continue
            entry: dict[str, Any] = {"role": role, "content": m.get("content") or ""}
            if role == "assistant" and m.get("tool_calls"):
                entry["tool_calls"] = m["tool_calls"]
            if role == "tool":
                entry["tool_call_id"] = str(m.get("tool_call_id") or "")
            clean.append(entry)
        return clean, _estimate_tokens(clean)
    clean = [
        {"role": str(m.get("role")), "content": str(m.get("content", ""))}
        for m in outbound
        if m.get("role") in ("user", "assistant")
    ]
    return clean, _estimate_tokens(clean)
