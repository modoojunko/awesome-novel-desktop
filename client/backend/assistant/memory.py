"""book memory——书级 agent 记忆与项目决策（c-agent-chat-memory 批3/批4）。

四层记忆 scope 的「按书」新增层：助手对一本书积累的写作规矩（book_agent_memory）
＋协作方向性结论留痕（book_decisions）。注入 L1 系统提示词（身份→人格→书记忆→
围栏→协议→域纪律的书记忆位）；助手经记忆工具自主维护（免授权——只影响后续
提示词，不碰书稿）。生命周期随书：删书时应用层级联清理（novels/router.py
delete 调 delete_book_memory；image_assets 先例同款）。

容量护栏：记忆段超限截断降级（决策按时间倒序保最近），SHALL NOT 因记忆超限
拒答或挤掉身份/围栏段。注入与工具读同源（本模块单一实现）——两套口径漂移禁。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.assistant import BookAgentMemory, BookDecision

# 注入容量护栏（字符预算；超限决策从最旧截断、记忆条目超限裁剪）
MEMORY_CHAR_BUDGET = 800
DECISION_CHAR_BUDGET = 1200


def _now() -> str:
    # 微秒精度（决策同秒追加的倒序稳定——平局由 id 兜底仍可能翻，先提精度）
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")


def _new_id() -> str:
    return uuid.uuid4().hex


async def list_memories(db: AsyncSession, novel_id: str) -> list[BookAgentMemory]:
    """该书全部 agent 记忆（按更新时间新→旧）。"""
    rows = await db.execute(
        select(BookAgentMemory)
        .where(BookAgentMemory.novel_id == novel_id)
        .order_by(BookAgentMemory.updated_at.desc())
    )
    return list(rows.scalars())


async def list_decisions(db: AsyncSession, novel_id: str) -> list[BookDecision]:
    """该书全部项目决策（按时间新→旧——注入与截断的同一口径）。"""
    rows = await db.execute(
        select(BookDecision)
        .where(BookDecision.novel_id == novel_id)
        .order_by(BookDecision.created_at.desc(), BookDecision.id.desc())
    )
    return list(rows.scalars())


async def upsert_memory(
    db: AsyncSession, novel_id: str, content: str, memory_id: str | None = None
) -> BookAgentMemory:
    """增/改一条 agent 记忆（带 id 即改；内容剥空白，空内容拒绝）。"""
    text = (content or "").strip()
    if not text:
        raise ValueError("记忆内容不能为空")
    row: BookAgentMemory | None = None
    if memory_id:
        found = await db.execute(
            select(BookAgentMemory).where(
                BookAgentMemory.id == memory_id,
                BookAgentMemory.novel_id == novel_id,
            )
        )
        row = found.scalars().first()
    if row is None:
        row = BookAgentMemory(
            id=_new_id(), novel_id=novel_id, content=text, created_at=_now()
        )
        db.add(row)
    row.content = text
    row.updated_at = _now()
    await db.commit()
    return row


async def delete_memory(db: AsyncSession, novel_id: str, memory_id: str) -> bool:
    """删一条 agent 记忆（id 不存在或非本书＝False，工具层回人话）。"""
    result = await db.execute(
        sa_delete(BookAgentMemory).where(
            BookAgentMemory.id == memory_id,
            BookAgentMemory.novel_id == novel_id,
        )
    )
    await db.commit()
    return bool(result.rowcount)


async def add_decision(
    db: AsyncSession, novel_id: str, decision: str, reason: str = ""
) -> BookDecision:
    """追加一条项目决策（时间留痕；空决策拒绝）。"""
    text = (decision or "").strip()
    if not text:
        raise ValueError("决策内容不能为空")
    row = BookDecision(
        id=_new_id(),
        novel_id=novel_id,
        decision=text,
        reason=(reason or "").strip(),
        created_at=_now(),
    )
    db.add(row)
    await db.commit()
    return row


async def delete_book_memory(db: AsyncSession, novel_id: str) -> None:
    """删书级联：清空该书全部 agent 记忆与项目决策（零孤儿）。"""
    await db.execute(sa_delete(BookAgentMemory).where(BookAgentMemory.novel_id == novel_id))
    await db.execute(sa_delete(BookDecision).where(BookDecision.novel_id == novel_id))
    await db.commit()


def render_memory_section(memories: list[BookAgentMemory], decisions: list[BookDecision]) -> str:
    """书级记忆段（注入 L1；纯函数——容量护栏可单测）。

    记忆按预算逐条保留（新→旧），决策按预算逐条保留（新→旧）；超限截断。
    两表皆空返回空串（段整体省略——前缀缓存友好）。
    """
    lines: list[str] = []
    used = 0
    for m in memories:
        text = (m.content or "").strip()
        if not text:
            continue
        if used + len(text) > MEMORY_CHAR_BUDGET and lines:
            break
        lines.append(f"- {text}")
        used += len(text)
    decision_lines: list[str] = []
    used = 0
    for d in decisions:
        text = (d.decision or "").strip()
        if not text:
            continue
        extra = f"（理由：{(d.reason or '').strip()}）" if (d.reason or "").strip() else ""
        line = f"- {text}{extra}"
        if used + len(line) > DECISION_CHAR_BUDGET and decision_lines:
            break
        decision_lines.append(line)
        used += len(line)
    if not lines and not decision_lines:
        return ""
    parts: list[str] = ["── 这本书我们定下的规矩与决定 ──"]
    if lines:
        parts.append("写作规矩（我记下的）：")
        parts.extend(lines)
    if decision_lines:
        parts.append("项目决定（最近优先）：")
        parts.extend(decision_lines)
    return "\n".join(parts)


async def load_book_memory_section(db: AsyncSession, novel_id: str) -> str:
    """按书装载记忆段（注入与工具读同源；空书空串）。"""
    memories = await list_memories(db, novel_id)
    decisions = await list_decisions(db, novel_id)
    return render_memory_section(memories, decisions)
