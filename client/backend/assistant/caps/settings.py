"""设定域能力核（c-tool-flow 批4：对话与面板同调一层）。

包装 settings/ai_router 的端点核（generate_field/run_hooks_ai/intro_ai——
Depends 占位按位传），失败归一 CapabilityError（人话消息，工具层直接回作家）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CapabilityError(Exception):
    """能力核失败（message 为人话，可直接给作家）。"""

    message: str


def _cap_error_from_http(e: Exception) -> CapabilityError:
    detail = getattr(e, "detail", None)
    return CapabilityError(str(detail) if detail else str(e))


async def generate_settings_field(
    novel_id: str, stype: str, field: str, user_id: str, context: dict | None = None
) -> dict:
    """单字段生成核（题材四问等同源）。失败抛 CapabilityError。"""
    from db import async_session
    from settings.ai_router import generate_field

    try:
        async with async_session() as db:
            return await generate_field(
                novel_id, stype, field, {"context": context or {}},
                {"id": user_id}, True, True, db,
            )
    except Exception as e:  # noqa: BLE001——HTTPException 归一
        raise _cap_error_from_http(e) from e


async def hooks_ai_action(
    novel_id: str, action: str, user_id: str, body: dict | None = None
) -> dict:
    """伏笔 AI 四能力核（draft/payoff/audit/check）。失败抛 CapabilityError。"""
    from db import async_session
    from settings.ai_router import run_hooks_ai

    try:
        async with async_session() as db:
            return await run_hooks_ai(
                novel_id, action, body or {},
                {"id": user_id}, True, True, db,
            )
    except Exception as e:  # noqa: BLE001
        raise _cap_error_from_http(e) from e


async def intro_ai_action(
    novel_id: str, action: str, user_id: str, body: dict | None = None
) -> dict:
    """简介 AI 核（draft/check）。失败抛 CapabilityError。"""
    from db import async_session
    from settings.ai_router import intro_ai

    try:
        async with async_session() as db:
            return await intro_ai(
                novel_id, action, body or {},
                {"id": user_id}, True, True, db,
            )
    except Exception as e:  # noqa: BLE001
        raise _cap_error_from_http(e) from e


async def arc_ai_action(
    novel_id: str, action: str, user_id: str, input_text: str = ""
) -> dict:
    """主线四能力核（draft/calibrate/check/tone）。失败抛 CapabilityError。"""
    from db import async_session
    from settings.ai_router import run_arc_ai

    try:
        async with async_session() as db:
            return await run_arc_ai(
                project_id=novel_id,
                action=action,
                body={"input": str(input_text or "")},
                user={"id": user_id},
                _=True,
                __=True,
                db=db,
            )
    except Exception as e:  # noqa: BLE001
        raise _cap_error_from_http(e) from e
