"""book memory——书级 agent 记忆与项目决策（c-agent-chat-memory 批3/批4）。

四层记忆 scope 的「按书」新增层：助手对一本书积累的写作规矩（book_agent_memory，
DB 表）＋协作方向性结论留痕（决策档案，c-agent-decision-archive 起改文件）。注入
L1 系统提示词（身份→人格→书记忆→围栏→协议→域纪律的书记忆位）；助手经记忆工具
自主维护（免授权——只影响后续提示词，不碰书稿）。生命周期随书：删书时应用层级
联清理（novels/router.py delete 调 delete_book_memory；image_assets 先例同款）。

决策档案（c-agent-decision-archive）：DATA_ROOT/decisions/<novel_id>.jsonl
append-only 全量留痕——**永不截断**。注入分层：预算内最近决策全文→更早决策
降级一行索引→尾注告知在档总数（模型经 recall_decisions 按需召回全文）。
旧的「超限静默丢弃」行为退役——半年前的决定不再被预算挤掉。

容量护栏：记忆段超限截断降级（决策降级为索引而非丢弃），SHALL NOT 因记忆超限
拒答或挤掉身份/围栏段。注入与工具读同源（本模块单一实现）——两套口径漂移禁。
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import DATA_ROOT
from models.assistant import BookAgentMemory, BookDecision

# 注入容量护栏（字符预算）：记忆条目超限裁剪；决策超限降级索引（不丢弃）
MEMORY_CHAR_BUDGET = 800
DECISION_CHAR_BUDGET = 1200
DECISION_INDEX_BUDGET = 600  # 索引行预算（日期+首句一行约 40 字 ≈ 15 条）


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


async def list_decisions(novel_id: str) -> list[DecisionRow]:
    """该书全部项目决策（决策档案文件；按时间新→旧——注入与召回同一口径）。"""
    return sorted(_read_decisions(novel_id), key=lambda d: (d.created_at, d.id), reverse=True)


@dataclass
class DecisionRow:
    """决策档案行（文件行的内存形态；字段名与原 BookDecision ORM 行同形）。"""

    id: str
    decision: str
    reason: str
    created_at: str


def _decisions_path(novel_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", novel_id or ""):
        raise ValueError(f"bad novel_id: {novel_id!r}")
    return Path(DATA_ROOT) / "decisions" / f"{novel_id}.jsonl"


def _read_decisions(novel_id: str) -> list[DecisionRow]:
    """读决策档案（坏行/半行跳过——崩溃残迹容忍，会话文件同款口径）。"""
    path = _decisions_path(novel_id)
    if not path.is_file():
        return []
    out: list[DecisionRow] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("id"):
            out.append(
                DecisionRow(
                    id=str(obj.get("id") or ""),
                    decision=str(obj.get("decision") or ""),
                    reason=str(obj.get("reason") or ""),
                    created_at=str(obj.get("created_at") or ""),
                )
            )
    return out


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


async def add_decision(novel_id: str, decision: str, reason: str = "") -> DecisionRow:
    """追加一条项目决策（决策档案 append-only 一行；空决策拒绝）。"""
    text = (decision or "").strip()
    if not text:
        raise ValueError("决策内容不能为空")
    row = DecisionRow(
        id=_new_id(),
        decision=text,
        reason=(reason or "").strip(),
        created_at=_now(),
    )
    path = _decisions_path(novel_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"id": row.id, "decision": row.decision, "reason": row.reason,
                 "created_at": row.created_at},
                ensure_ascii=False,
            )
            + "\n"
        )
    return row


async def delete_book_memory(db: AsyncSession, novel_id: str) -> None:
    """删书级联：清空该书全部 agent 记忆（DB）＋决策档案文件（零孤儿）。"""
    await db.execute(sa_delete(BookAgentMemory).where(BookAgentMemory.novel_id == novel_id))
    await db.commit()
    try:
        _decisions_path(novel_id).unlink(missing_ok=True)
    except OSError:
        pass


def render_memory_section(
    memories: list[BookAgentMemory], decisions: list[DecisionRow]
) -> str:
    """书级记忆段（注入 L1；纯函数——容量护栏可单测）。

    记忆按预算逐条保留（新→旧）；决策分层（c-agent-decision-archive）：预算内
    最近决策全文→更早决策降级「[日期] 一句话」索引行（索引自身预算封顶）→仍
    超限的以尾注告知在档总数——**不静默丢弃**（旧截断行为退役：半年前的决定
    不再被预算挤掉，agent 按索引/召回工具可取回全文）。两源皆空返回空串。
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
    archive: list[str] = []  # 超全文预算的更早决策（索引层素材，新→旧）
    for d in decisions:
        text = (d.decision or "").strip()
        if not text:
            continue
        extra = f"（理由：{(d.reason or '').strip()}）" if (d.reason or "").strip() else ""
        line = f"- {text}{extra}"
        if used + len(line) <= DECISION_CHAR_BUDGET or not decision_lines:
            decision_lines.append(line)
            used += len(line)
            continue
        archive.append(d)
    # 索引层：更早决策降级「[日期] 一句话」（首句 40 字封顶），索引预算封顶
    index_lines: list[str] = []
    idx_used = 0
    for d in archive:
        text = (d.decision or "").strip()
        first = re.split(r"[。；;\n]", text, 1)[0].strip()[:40]
        date = (d.created_at or "")[:10]
        line = f"- [{date}] {first}"
        if idx_used + len(line) > DECISION_INDEX_BUDGET and index_lines:
            break
        index_lines.append(line)
        idx_used += len(line)
    indexed = len(index_lines)
    older = len(archive) - indexed

    if not lines and not decision_lines and not index_lines:
        return ""
    parts: list[str] = ["── 这本书我们定下的规矩与决定 ──"]
    if lines:
        parts.append("写作规矩（我记下的）：")
        parts.extend(lines)
    if decision_lines:
        parts.append("项目决定（旧的也在档，可随时查）：")
        parts.extend(decision_lines)
    if index_lines:
        parts.append("更早的决定（索引）：")
        parts.extend(index_lines)
    if older > 0:
        parts.append(
            f"（另有 {older} 条更早的决定在档——作家提起旧决定时用 recall_decisions 查。）"
        )
    return "\n".join(parts)


async def load_book_memory_section(db: AsyncSession, novel_id: str) -> str:
    """按书装载记忆段（注入与工具读同源；空书空串）。"""
    memories = await list_memories(db, novel_id)
    decisions = await list_decisions(novel_id)
    return render_memory_section(memories, decisions)


async def migrate_book_decisions() -> dict[str, int]:
    """DB book_decisions 存量 → 决策档案（c-agent-decision-archive D5）。

    幂等：同 id 已在档即跳过；fail-soft 由调用方兜（本函数只管搬）。
    DB 行保留归档（代码不再读写）。"""
    from db import async_session

    out = {"migrated": 0, "skipped": 0}
    async with async_session() as db:
        rows = (
            await db.execute(
                select(BookDecision).order_by(BookDecision.created_at, BookDecision.id)
            )
        )
        legacy = list(rows.scalars())
    seen: set[str] = set()
    paths: dict[str, Path] = {}
    for row in legacy:
        if row.novel_id not in paths:
            paths[row.novel_id] = _decisions_path(row.novel_id)
        path = paths[row.novel_id]
        existing = {d.id for d in _read_decisions(row.novel_id)}
        if row.id in seen or row.id in existing:
            out["skipped"] += 1
            seen.add(row.id)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"id": row.id, "decision": row.decision, "reason": row.reason,
                     "created_at": row.created_at},
                    ensure_ascii=False,
                )
                + "\n"
            )
        seen.add(row.id)
        out["migrated"] += 1
    return out
