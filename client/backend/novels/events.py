"""本地事件表（PRD §7 度量）：只落本机 SQLite，不外发、不上报。

两条入口：
- `log_event`（同步 Session）：历史调用点（workflow/router.py）沿用；
- `log_event_async`（AsyncSession）：异步路由用——`db.commit()` 是协程，同步版在
  异步会话下不落库（静默丢事件），新调用点一律用异步版。
"""

import json
import logging
import os
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from models.event import Event

logger = logging.getLogger(__name__)


def events_enabled() -> bool:
    """度量总开关（PRD §7「本地可关」）：`NOVEL_EVENTS=off` 关闭全部写入。"""
    return (os.environ.get("NOVEL_EVENTS", "") or "").strip().lower() not in (
        "off",
        "0",
        "false",
    )


# 单条 payload 上限（本地表，防联调/误用灌大行）；超限截断而不是拒绝（埋点不该拦业务）
_PAYLOAD_MAX = 2000


def _entry(user_id: str, event_type: str, payload: dict | None) -> Event:
    # 主键用 uuid：旧口径 `{ms}_{user_id}` 在同一用户同一毫秒发两条时撞 UNIQUE
    # （前端 desk_manual_create + volume_saved 就是同 tick 连发）→ 只剩一条。
    text = json.dumps(payload or {}, ensure_ascii=False)
    if len(text) > _PAYLOAD_MAX:
        text = json.dumps({"_truncated": True, "_raw_len": len(text)}, ensure_ascii=False)
    return Event(
        id=str(uuid.uuid4()),
        user_id=user_id,
        event_type=event_type,
        payload=text,
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
    """异步会话版本（真落库）。**自带 best-effort**：事件写失败只记日志，绝不冒泡——
    埋点不得把已经成功的业务动作变成 500（如 hooks 已入册却回「登记失败」）。"""
    if not events_enabled():
        return
    try:
        db.add(_entry(user_id, event_type, payload))
        await db.commit()
    except Exception:  # noqa: BLE001 —— 埋点失败绝不影响主流程
        logger.warning("event=metrics.write_failed type=%s", event_type, exc_info=True)
        await db.rollback()
