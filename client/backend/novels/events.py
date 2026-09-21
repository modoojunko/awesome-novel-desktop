"""本地事件表（PRD §7 度量）：只落本机 SQLite，不外发、不上报。

两条入口：
- `log_event`（同步 Session）：历史调用点（workflow/router.py）沿用；
- `log_event_async`（AsyncSession）：异步路由用——`db.commit()` 是协程，同步版在
  异步会话下不落库（静默丢事件），新调用点一律用异步版。
"""

import json
import os
import time
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from models.event import Event


def events_enabled() -> bool:
    """度量总开关（PRD §7「本地可关」）：`NOVEL_EVENTS=off` 关闭全部写入。"""
    return (os.environ.get("NOVEL_EVENTS", "") or "").strip().lower() not in (
        "off",
        "0",
        "false",
    )


def _entry(user_id: str, event_type: str, payload: dict | None) -> Event:
    return Event(
        id=f"{int(time.time() * 1000)}_{user_id}",
        user_id=user_id,
        event_type=event_type,
        payload=json.dumps(payload or {}, ensure_ascii=False),
        created_at=datetime.now(UTC).isoformat(),
    )


def log_event(db: Session, user_id: str, event_type: str, payload: dict | None = None):
    if not events_enabled():
        return
    db.add(_entry(user_id, event_type, payload))
    db.commit()


async def log_event_async(
    db: AsyncSession, user_id: str, event_type: str, payload: dict | None = None
) -> None:
    """异步会话版本（真落库）。事件失败不得影响主流程——由调用方 best-effort 包住。"""
    if not events_enabled():
        return
    db.add(_entry(user_id, event_type, payload))
    await db.commit()
