"""助手会话存储（c-writing-agent 批A 1.1）。

移植自 OpenWorker（MIT，`coworker/conversations.py`）的机制，载体从
「SQLite 索引＋每会话 JSONL append-only」改为宿主的 `assistant_sessions`/
`assistant_messages` 两表（消息本来就要逐步落盘，单一载体不再双写）。
照搬的机制（原注释保留语义）：
  - 会话 id 白名单（conversations.py:30-34）：id 会出现在日志/导出路径里，
    客户端可传的 id 必须挡住路径逃逸；
  - append-only＋seq 单调：正常路径只追加；缩写走「整段重写」且是单事务
    （SQL 行级原子性天然替代 tmp-then-replace，conversations.py:332-342）；
  - 自愈（conversations.py:157-261 的工具配对修复）：本 agent 的文本协议没有
    原生 tool 角色，对应物是「悬挂的 streaming 消息」——加载时把半路崩掉的
    streaming 行收尾为 error，崩前已产出的卡与轨迹原样保留（设计 §循环失控护栏）；
  - 标题三级优先（手动改名＞自动标题＞首行快照，conversations.py:57-62）。
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.assistant import AssistantMessage, AssistantSession

# 会话 id 白名单：单段良性路径组件（openwriter conversations.py:30 同款正则）。
# 会话 id 由服务端生成（uuid4 十六进制），此处防御的是 API 路径上传入的 id。
_SAFE_SESSION_ID = re.compile(r"\A[A-Za-z0-9_-]{1,128}\Z")


def is_safe_session_id(sid: str) -> bool:
    return bool(isinstance(sid, str) and _SAFE_SESSION_ID.match(sid))


def new_session_id() -> str:
    return uuid.uuid4().hex


def new_message_id() -> str:
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return default
    return value


async def get_or_create_session(
    db: AsyncSession, *, user_id: str, novel_id: str
) -> AssistantSession:
    """每书一会话（UNIQUE user_id+novel_id）；不存在则建空会话。"""
    row = (
        await db.scalars(
            select(AssistantSession).where(
                AssistantSession.user_id == user_id,
                AssistantSession.novel_id == novel_id,
            )
        )
    ).first()
    if row is not None:
        return row
    row = AssistantSession(
        id=new_session_id(),
        user_id=user_id,
        novel_id=novel_id,
        page_cursor="",
        grants_json="{}",
        compaction_json="{}",
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def load_session(
    db: AsyncSession, session_id: str, *, user_id: str
) -> AssistantSession | None:
    """按 id 取会话；归属校验（他人会话不可读）＋id 白名单。"""
    if not is_safe_session_id(session_id):
        return None
    row = (
        await db.scalars(
            select(AssistantSession).where(
                AssistantSession.id == session_id,
                AssistantSession.user_id == user_id,
            )
        )
    ).first()
    return row


async def load_messages(
    db: AsyncSession, session_id: str, *, heal: bool = True
) -> list[AssistantMessage]:
    """按 seq 有序取全量消息；自愈：悬挂的 streaming 行收尾为 error（崩前内容保留）。"""
    rows = (
        await db.scalars(
            select(AssistantMessage)
            .where(AssistantMessage.session_id == session_id)
            .order_by(AssistantMessage.seq)
        )
    ).all()
    if heal:
        for m in rows:
            if m.status == "streaming":
                m.status = "error"
                if not m.content:
                    m.content = "（这一轮没有完成——上次中途被打断了。）"
        if any(m.status == "error" for m in rows):
            await db.commit()
    return list(rows)


async def next_seq(db: AsyncSession, session_id: str) -> int:
    row = await db.scalars(
        select(AssistantMessage.seq)
        .where(AssistantMessage.session_id == session_id)
        .order_by(AssistantMessage.seq.desc())
        .limit(1)
    )
    return (row.first() or 0) + 1


async def append_message(
    db: AsyncSession,
    session_id: str,
    *,
    novel_id: str,
    role: str,
    content: str = "",
    page: str = "",
    payload: dict | None = None,
    card_kind: str = "",
    status: str = "done",
    run_id: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> AssistantMessage:
    """追加一条消息（seq 单调递增；step 级落盘——崩了留下完整轨迹非悬空流）。"""
    row = AssistantMessage(
        id=new_message_id(),
        session_id=session_id,
        novel_id=novel_id,
        seq=await next_seq(db, session_id),
        role=role,
        page=page or "",
        content=content or "",
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
        card_kind=card_kind or "",
        status=status or "done",
        run_id=run_id or "",
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        created_at=_now(),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_message_status(
    db: AsyncSession, message_id: str, *, status: str, content: str | None = None
) -> None:
    values: dict[str, Any] = {"status": status}
    if content is not None:
        values["content"] = content
    await db.execute(
        update(AssistantMessage).where(AssistantMessage.id == message_id).values(**values)
    )
    await db.commit()


async def touch_session(
    db: AsyncSession,
    session_id: str,
    *,
    page_cursor: str | None = None,
    grants: dict | None = None,
    compaction: dict | None = None,
) -> None:
    """会话级元数据更新（各列独立语义，None＝不动——对齐 conversations.py 的
    set_team/set_bindings「per-turn save 不碰专属列」纪律）。"""
    values: dict[str, Any] = {"updated_at": _now()}
    if page_cursor is not None:
        values["page_cursor"] = page_cursor
    if grants is not None:
        values["grants_json"] = json.dumps(grants, ensure_ascii=False)
    if compaction is not None:
        values["compaction_json"] = json.dumps(compaction, ensure_ascii=False)
    await db.execute(
        update(AssistantSession).where(AssistantSession.id == session_id).values(**values)
    )
    await db.commit()


async def load_compaction_state(db: AsyncSession, session: AssistantSession):
    """防御性解析 compact 状态（openwriter grants 同款：坏 JSON 返回 None）。"""
    from assistant.compact import CompactionState

    raw = _load_json(session.compaction_json, {})
    return CompactionState.from_dict(raw) if raw else None


async def save_compaction_state(
    db: AsyncSession, session_id: str, state: Any | None
) -> None:
    payload = state.as_dict() if state is not None else {}
    await touch_session(db, session_id, compaction=payload)


async def reset_session(db: AsyncSession, session_id: str) -> None:
    """清空会话消息（重置对话；会话行保留、compact 状态一并清零）。"""
    from sqlalchemy import delete as sa_delete

    await db.execute(
        sa_delete(AssistantMessage).where(AssistantMessage.session_id == session_id)
    )
    await touch_session(db, session_id, compaction={})
