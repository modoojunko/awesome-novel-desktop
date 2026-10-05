"""提示词包本地端点（c-prompt-pack-client 3.4）：状态查询＋手动触发同步。

- GET  /api/prompt-pack/status —— `get_status()` 快照（前端四态卡数据面；
  `/auth/verify` 已挂同一快照，此端点供设置页/诊断单独取用）。
- POST /api/prompt-pack/check  —— 手动「检查写作能力」：后台触发一次同步，
  立即返回当前状态（不阻塞；完成后的状态由前端短轮询 status 感知）。
"""

from fastapi import APIRouter

from prompt_pack.sync import get_status, trigger_sync

router = APIRouter(prefix="/api/prompt-pack", tags=["prompt-pack"])


@router.get("/status")
async def api_pack_status() -> dict:
    return get_status()


@router.post("/check")
async def api_pack_check() -> dict:
    started = trigger_sync()
    return {"started": started, **get_status()}
