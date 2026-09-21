"""度量事件落点（PRD §7，c-volume-antagonist tasks 5.3）。

前端意图事件（打开规划台/选中卡/直建…）只在前端知道，走这里落本地 events 表；
服务端自己就知道的事件（hooks 入册、卷体检）在各自端点内直接 log，不走这条。

白名单收口：只接受 §7 列出的前端事件名——不做通用写入口（避免任意 event_type
灌表）。免费可用（不挂 require_ai_access），失败静默不影响主流程。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import get_current_user
from db import get_db
from novels.events import events_enabled, log_event_async

router = APIRouter(prefix="/api/events", tags=["events"])

# PRD §7 事件表里「由前端意图产生」的部分（服务端两条：hooks_registered/check_run）
CLIENT_EVENT_TYPES = frozenset(
    {
        "plan_entry_open",  # {tier}
        "pick_drawn",  # {tier, count}
        "pick_redraw",
        "pick_select",  # {no}
        "pick_confirm_ok",  # {vol_no}
        "pick_confirm_fail",  # {reason}
        "desk_manual_create",  # {vol_no}
        "desk_expand",  # {vol_no}
        "volume_saved",  # {vol_no, source}
        "first_chapter_in_vol",  # {vol_no}
    }
)


@router.post("")
async def post_event(
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event_type = str(body.get("event_type") or "").strip()
    if event_type not in CLIENT_EVENT_TYPES:
        raise HTTPException(422, "unknown event_type")
    payload = body.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    if not events_enabled():  # 总开关关闭：收下不落库（前端无需感知）
        return {"ok": True, "skipped": True}
    await log_event_async(db, user["id"], event_type, payload)
    return {"ok": True}
