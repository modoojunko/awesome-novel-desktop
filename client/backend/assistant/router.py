"""助手对话端点（c-writing-agent 批A 1.3＋1.8）。

- POST /api/novels/{project_id}/assistant/chat           SSE 流式对话（批A 主端点）
- GET  /api/novels/{project_id}/assistant/session        会话回看（messages 按 seq）
- POST /api/novels/{project_id}/assistant/session/reset  重置对话

纪律（write/router.py 同款）：开流前只留可读 4xx（书不存在 404）；未配 Key 不 503
——流内 `gate{reason:"no_key"}` 引导事件收尾，不打断对话流；循环失败一律流内
error 事件收尾，不得静默 200 空流。用量按步落账（record_usage，短事务）。
会话/消息逐步落 assistant_messages（转写即状态：崩溃留下完整轨迹非悬空流）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from assistant import session_store
from assistant.context import append_page_note, build_book_brief, build_page_note
from assistant.loop import AgentLoop, LoopConfig
from assistant.prompts import build_system_prompt
from assistant.tools import ToolContext
from auth_local.middleware import get_current_user
from db import get_db
from models.assistant import AssistantSession
from models.project import Novel
from novels.service import get_novel

router = APIRouter(prefix="/api/novels/{project_id}/assistant", tags=["assistant"])


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _history_transcript(rows: list[Any]) -> list[dict[str, str]]:
    """持久化消息 → 循环转写（只取 user/assistant 文本行；工具/事件行不进转写——
    需要细节时 agent 用 read_* 重读，与 compact「细节优先牺牲」口径一致）。"""
    out: list[dict[str, str]] = []
    for m in rows:
        if m.role in ("user", "assistant") and m.content:
            out.append({"role": m.role, "content": m.content})
    return out


async def _stream_chat(
    db: AsyncSession,
    project: Novel,
    user: dict,
    session: AssistantSession,
    message: str,
    page: str,
) -> AsyncIterator[str]:
    """SSE generator：no-key 引导 → 组装 → 循环 → 逐步落盘。"""

    # ── no-key：不 503，流内引导卡收尾（历史保留）───────────────────────────
    from ai_state import user_has_ai_key

    if not await user_has_ai_key(db, user["id"]):
        guide = "还没配模型的钥匙——去「模型配置」加一个，我就能开工了。"
        yield _sse({"type": "gate", "reason": "no_key", "message": guide})
        await session_store.append_message(
            db,
            session.id,
            novel_id=project.id,
            role="assistant",
            content=guide,
            page=page,
            payload={"gate": "no_key"},
            card_kind="gate",
        )
        return

    # ── 组装 ────────────────────────────────────────────────────────────────
    brief = await build_book_brief(project, db)
    system = build_system_prompt(brief)
    rows = await session_store.load_messages(db, session.id)
    transcript = _history_transcript(rows)
    note = build_page_note(page)
    if note:
        transcript = append_page_note(transcript, note)

    try:
        from ai_client import get_ai_client_for_novel

        client = await get_ai_client_for_novel(project.id)
    except ValueError as e:
        msg = f"模型的钥匙配了但用不了：{e}"
        yield _sse({"type": "gate", "reason": "client_error", "message": msg})
        await session_store.append_message(
            db,
            session.id,
            novel_id=project.id,
            role="assistant",
            content=msg,
            page=page,
            payload={"gate": "client_error"},
            card_kind="gate",
        )
        return

    tool_ctx = ToolContext(
        novel_id=project.id, root_path=project.root_path, user_id=user["id"], page=page
    )
    compaction_state = await session_store.load_compaction_state(db, session)

    async def _on_compaction(state: Any) -> None:
        await session_store.save_compaction_state(db, session.id, state)

    async def _on_usage(tokens_in: int, tokens_out: int) -> None:
        from api_configs.usage import record_usage

        await record_usage(
            db,
            user_id=user["id"],
            project_id=project.id,
            operation="assistant_step",
            model="haiku",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    loop = AgentLoop(
        client=client,
        system=system,
        transcript=transcript,
        tool_ctx=tool_ctx,
        compaction_state=compaction_state,
        config=LoopConfig(),
        on_compaction=_on_compaction,
        on_usage=_on_usage,
        gate_fn=None,  # 批B 接 write_gate
    )

    # ── 逐步落盘＋SSE 下发 ─────────────────────────────────────────────────
    pending_assistant = await session_store.append_message(
        db,
        session.id,
        novel_id=project.id,
        role="assistant",
        content="",
        page=page,
        status="streaming",
    )
    reply_parts: list[str] = []
    final_status = "done"

    async for event in loop.run(message):
        etype = event.get("type")
        if etype == "narration":
            reply_parts.append(str(event.get("text", "")))
        elif etype == "step_end":
            await session_store.append_message(
                db,
                session.id,
                novel_id=project.id,
                role="tool",
                content=str(event.get("resultNote", "")),
                page=page,
                payload={
                    "tool": event.get("tool"),
                    "stepId": event.get("stepId"),
                    "runId": event.get("runId"),
                },
            )
        elif etype == "error":
            final_status = "error"
        if etype == "thinking":
            continue  # 思考增量不落盘（会话回看不需要逐字思考；轨迹在 tool 行）
        yield _sse(event)

    full_reply = "\n".join(p for p in reply_parts if p)
    await session_store.update_message_status(
        db,
        pending_assistant.id,
        status=final_status,
        content=full_reply or pending_assistant.content,
    )
    if loop.result.tokens_in or loop.result.tokens_out:
        await session_store.append_message(
            db,
            session.id,
            novel_id=project.id,
            role="event",
            content="",
            page=page,
            payload={
                "usage": {
                    "tokens_in": loop.result.tokens_in,
                    "tokens_out": loop.result.tokens_out,
                }
            },
        )
    if page:
        await session_store.touch_session(db, session.id, page_cursor=page)


@router.post("/chat")
async def assistant_chat(
    project_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """流式对话。body {"message": str, "page": str}。

    批A 读类工具先行（围栏封闭清单见 assistant/tools.py）；产卡/写类/发散批B 挂载。
    """
    body: dict[str, Any] = {}
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            body = raw
    except (ValueError, UnicodeDecodeError):
        body = {}
    message = str(body.get("message") or "").strip()
    page = str(body.get("page") or "").strip()[:64]
    if not message:
        raise HTTPException(422, "message 不能为空")

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    session = await session_store.get_or_create_session(
        db, user_id=user["id"], novel_id=project.id
    )
    await session_store.append_message(
        db,
        session.id,
        novel_id=project.id,
        role="user",
        content=message,
        page=page,
    )

    return StreamingResponse(
        _stream_chat(db, project, user, session, message, page),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/session")
async def get_assistant_session(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """会话回看：messages 按 seq 全量（含状态），会话元数据带授权档位与 compact 有无。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    session = await session_store.get_or_create_session(
        db, user_id=user["id"], novel_id=project.id
    )
    rows = await session_store.load_messages(db, session.id)
    return {
        "sessionId": session.id,
        "pageCursor": session.page_cursor,
        "grants": json.loads(session.grants_json or "{}"),
        "compacted": bool(session.compaction_json and session.compaction_json != "{}"),
        "messages": [
            {
                "id": m.id,
                "seq": m.seq,
                "role": m.role,
                "page": m.page,
                "content": m.content,
                "cardKind": m.card_kind,
                "status": m.status,
                "payload": json.loads(m.payload_json or "{}"),
                "createdAt": m.created_at,
            }
            for m in rows
        ],
    }


@router.post("/session/reset")
async def reset_assistant_session(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    session = await session_store.get_or_create_session(
        db, user_id=user["id"], novel_id=project.id
    )
    await session_store.reset_session(db, session.id)
    return {"ok": True}
