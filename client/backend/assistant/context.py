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

from datetime import datetime
from typing import Any

from assistant.compact import apply_to_outbound
from assistant.compact import estimate_tokens as _estimate_tokens

# 书级 brief 预算（字符；write/chapter_writer.py 按字预算同风格）
BOOK_BRIEF_BUDGET_CHARS = 300
# 转写窗口预算（超出触发 compact 判定的估算信号走 compaction.should_compact）
WINDOW_BUDGET_CHARS = 120_000


async def build_book_brief_parts(novel: Any, db: Any) -> tuple[str, str]:
    """书级 brief 拆两段（c-agent-prompt-cache）：(稳定, 动态)。

    - 稳定段＝书名/题材：跨轮不变，进系统前缀（前缀缓存可复用）；
    - 动态段＝进度（frontier 三态真值/字数）：随写作变化，拼到当前 user 消息尾部。
    任一段失败降级为空串；`build_book_brief` 保持两段拼接的旧出口。
    """
    from chapters.frontier import frontier_info

    name = str(getattr(novel, "name", "") or "")
    stable_lines = [f"书名：{name}"]
    try:
        from genres.service import resolve_genre_context

        gctx = await resolve_genre_context(getattr(novel, "root_path", ""), novel.id)
        genre_name = str(gctx.get("genre") or gctx.get("genre_name") or "")
        if genre_name:
            stable_lines.append(f"题材：{genre_name}")
    except Exception as e:  # brief 缺题材不致命（BLE001 豁免）
        import logging

        logging.getLogger(__name__).debug("genre brief skipped: %s", e)
    dynamic_lines: list[str] = []
    try:
        info = await frontier_info(db, novel.id)
        chapters = info.get("chapters")
        if isinstance(chapters, list) and chapters:
            archived = sum(1 for ch in chapters if ch.get("archived"))
            fr = info.get("frontier") or {}
            # 三态真值（c-agent-writing-flow-context）：「草稿」一词掩盖「已写完未归档」
            # 与「没写」的差异——事故实锤模型据此锚死当前章。按 state 说真话，含字数。
            state = str(fr.get("state") or "")
            if state == "draft":
                progress = (
                    f"第 {fr.get('global_no')} 章 正文已写 "
                    f"{int(fr.get('word_count') or 0):,} 字·未归档"
                )
            elif state == "planned":
                progress = f"第 {fr.get('global_no')} 章 已排定·正文未写·未归档"
            else:  # pending 占位：主线全部归档
                progress = f"各章均已归档；下一章 第 {fr.get('global_no')} 章（待拆纲）"
            dynamic_lines.append(
                f"进度：全书 {len(chapters)} 章（已归档 {archived}）；{progress}"
            )
        else:
            dynamic_lines.append("进度：空书（还没有章节）")
    except Exception:  # noqa: BLE001
        pass
    stable = "；".join(stable_lines)
    dynamic = "；".join(dynamic_lines)
    if len(stable) > BOOK_BRIEF_BUDGET_CHARS:
        stable = stable[: BOOK_BRIEF_BUDGET_CHARS - 1] + "…"
    if len(dynamic) > BOOK_BRIEF_BUDGET_CHARS:
        dynamic = dynamic[: BOOK_BRIEF_BUDGET_CHARS - 1] + "…"
    return stable, dynamic


async def build_book_brief(novel: Any, db: Any) -> str:
    """≤300 字书级 brief：书名/题材/进度（frontier）。失败降级为仅书名。

    旧出口（两段拼接）；新调用方按稳定/动态分注入（c-agent-prompt-cache）。
    """
    stable, dynamic = await build_book_brief_parts(novel, db)
    brief = "；".join(p for p in (stable, dynamic) if p)
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


def latest_reminder_text(now: datetime | None = None) -> str:
    """DeepSeek 用户元信息标记（c-agent-latest-reminder）。

    格式 `<date>,<weekday>,<location>,<platform>,<language>`：日期/星期取
    Asia/Shanghai 本地日期、星期中文、location 留空、platform=App、language=中文。
    """
    from zoneinfo import ZoneInfo

    if now is None:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
    weekdays = "一二三四五六日"  # Monday=0
    return f"{now:%Y-%m-%d},星期{weekdays[now.weekday()]},,App,中文"


def build_outbound_window(
    transcript: list[dict[str, Any]],
    *,
    compaction_state: Any,
    keep_tokens: int | None = None,
    native: bool = False,
    reminder: str = "",
) -> tuple[list[dict[str, Any]], int]:
    """L3：转写 → 外发窗口（compact 应用）＋返回估算 tokens（供下一步触发判定）。

    native=True（c-agent-harness tasks 4.2）：保留 openai 原生形态——assistant 的
    tool_calls 与 role=tool 结果行原样携带（API 校验链必需）；文本协议口径不变
    （只留 user/assistant 的 role+content）。
    reminder 非空（c-agent-latest-reminder）：在**最后一条 user 消息之前**插入
    `{"role":"latest_reminder","content":...}`——只进当前外发窗口，不进历史/compact。
    """
    outbound = apply_to_outbound(transcript, compaction_state)
    if reminder:
        row = {"role": "latest_reminder", "content": reminder}
        last_user = -1
        for i, m in enumerate(outbound):
            if m.get("role") == "user":
                last_user = i
        if last_user >= 0:
            outbound = [*outbound[:last_user], row, *outbound[last_user:]]
        else:
            outbound = [*outbound, row]
    if native:
        clean: list[dict[str, Any]] = []
        for m in outbound:
            role = str(m.get("role"))
            if role not in ("user", "assistant", "tool", "latest_reminder"):
                continue
            entry: dict[str, Any] = {"role": role, "content": m.get("content") or ""}
            if role == "assistant" and m.get("tool_calls"):
                entry["tool_calls"] = m["tool_calls"]
            if role == "assistant" and m.get("reasoning_content"):
                # DeepSeek 带 tools 的历史回传要求（c-agent-native-tool-history）：
                # 存在才带；文本协议分支不读该字段，零影响。
                entry["reasoning_content"] = m["reasoning_content"]
            if role == "tool":
                entry["tool_call_id"] = str(m.get("tool_call_id") or "")
            clean.append(entry)
        return clean, _estimate_tokens(clean)
    clean = [
        {"role": str(m.get("role")), "content": str(m.get("content", ""))}
        for m in outbound
        if m.get("role") in ("user", "assistant")
        or (reminder and m.get("role") == "latest_reminder")
    ]
    return clean, _estimate_tokens(clean)
