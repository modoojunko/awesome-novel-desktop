"""提示词包本地端点（c-prompt-pack-client 3.4 / c-prompt-pack-onboard-modal）：状态查询＋探测＋手动触发。

- GET  /api/prompt-pack/status —— `get_status()` 快照（前端四态卡数据面；
  `/auth/verify` 已挂同一快照，此端点供设置页/诊断单独取用）。
- GET  /api/prompt-pack/probe  —— 版本探测（c-prompt-pack-onboard-modal）：
  `probe_latest()` 只查 CDN 最新版并比对已装版本，不下载不安装不调 S端；
  供「我的作品」页静默检测更新与引导弹窗消费。
- POST /api/prompt-pack/check  —— 手动「检查写作能力」：后台触发一次同步，
  立即返回当前状态（不阻塞；完成后的状态由前端短轮询 status 感知）。
"""

import asyncio

from fastapi import APIRouter

from prompt_pack.sync import get_status, probe_latest, trigger_sync

router = APIRouter(prefix="/api/prompt-pack", tags=["prompt-pack"])


@router.get("/status")
async def api_pack_status() -> dict:
    return get_status()


@router.get("/probe")
async def api_pack_probe() -> dict:
    # probe_latest 是同步 httpx＋DNS 解析（CDN 不可达时最坏 6s×2 候选）：丢线程池，
    # 不得阻塞事件循环（评审 P1-1——小说列表/保存/弹窗轮询共用它）
    return await asyncio.to_thread(probe_latest)


@router.post("/check")
async def api_pack_check() -> dict:
    started = trigger_sync()
    return {"started": started, **get_status()}
