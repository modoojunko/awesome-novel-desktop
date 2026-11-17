"""世界观三件 caps（c-agent-tools-expand：settings/ai_router 的 world 能力直调）。

Depends 占位按位传（批4 同款）；失败归一 CapabilityError（人话，工具层直接回作家）。"""

from __future__ import annotations


async def draft_world_cap(novel_id: str, user_id: str, body: dict) -> dict:
    from db import async_session
    from settings.ai_router import draft_world_topic

    async with async_session() as db:
        return await draft_world_topic(novel_id, body, {"id": user_id}, True, True, db)


async def check_world_cap(novel_id: str, user_id: str, body: dict) -> dict:
    from db import async_session
    from settings.ai_router import check_world_consistency

    async with async_session() as db:
        return await check_world_consistency(novel_id, body, {"id": user_id}, True, True, db)


async def lore_suggest_cap(novel_id: str, user_id: str, body: dict) -> dict:
    from db import async_session
    from settings.ai_router import lore_suggest_world

    async with async_session() as db:
        return await lore_suggest_world(novel_id, body, {"id": user_id}, True, True, db)
