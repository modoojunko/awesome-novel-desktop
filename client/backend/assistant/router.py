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

from assistant import session_store, write_gate
from assistant.context import append_page_note, build_book_brief, build_page_note
from assistant.loop import AgentLoop, LoopConfig
from assistant.prompts import build_system_prompt
from assistant.tools import ToolContext
from auth_local.deps import ai_access_granted
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
    # 记账必须记真实模型（test_ai_prompt_and_boundary 护栏：符号别名不得落账）——
    # client.resolve("haiku") 落到本书绑定模型（AIClient.resolve 单源）
    used_model = client.resolve("haiku")
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
            model=used_model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    # ── 授权梯度 gate_fn（write_gate 方案 B）───────────────────────────────
    grants = json.loads(session.grants_json or "{}")
    tier = str(grants.get("tier") or write_gate.TIER_CONFIRM_EACH)

    async def _gate_fn(tool_name: str, args: dict[str, Any]) -> list[dict[str, Any]] | None:
        """写类工具：判定→停车弹授权卡（批准后继续）；档位放行→None。
        生成/读类：None（生成类自己的档位闸在执行端 ai_access_granted）。"""
        from assistant.tools import get_tool

        tool = get_tool(tool_name)
        if tool is None or tool.kind != "write":
            return None

        # 干活档位闸（PRO 起）：无权 → 升级引导事件（不停车）
        if tool.feature_key and not ai_access_granted(tool.feature_key):
            return [
                {
                    "type": "gate",
                    "feature": tool.feature_key,
                    "tier_required": "pro",
                    "approved": False,
                    "refusal": (
                        "直接动手改需要 PRO 档。你可以在授权卡里手动改，"
                        "或者去「查看档位」升级后让我来。"
                    ),
                }
            ]

        decision = write_gate.evaluate(tool_name, args, tier=tier)
        if decision.allowed:
            return None
        if not decision.needs_user:
            return [
                {
                    "type": "gate_result",
                    "gateId": "",
                    "approved": False,
                    "refusal": "这个操作没有通过授权检查。",
                }
            ]

        # 停车：发授权卡，等作家批复（超时/关应用＝未批；待决记录已持久化可审计）
        gate_id = write_gate.PARKING.register()
        await session_store.append_message(
            db,
            session.id,
            novel_id=project.id,
            role="event",
            page=page,
            payload={
                "pending_gate": {
                    "gate_id": gate_id,
                    "tool": tool_name,
                    "preview": decision.preview,
                    "human_only": decision.human_only,
                }
            },
            status="streaming",
        )
        events: list[dict[str, Any]] = [
            {
                "type": "permission_required",
                "gateId": gate_id,
                "preview": decision.preview,
                "humanOnly": decision.human_only,
                "reason": decision.reason,
            }
        ]
        approved = await write_gate.PARKING.wait(gate_id) == "approved"
        write_gate.PARKING.discard(gate_id)
        events.append(
            {
                "type": "gate_result",
                "gateId": gate_id,
                "approved": approved,
                "refusal": None if approved else "作家没有授权这个操作，我不做了。",
            }
        )
        return events

    loop = AgentLoop(
        client=client,
        system=system,
        transcript=transcript,
        tool_ctx=tool_ctx,
        compaction_state=compaction_state,
        config=LoopConfig(),
        on_compaction=_on_compaction,
        on_usage=_on_usage,
        gate_fn=_gate_fn,
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
                    "writeLog": event.get("writeLog"),  # 撤销数据源（previous 值）
                },
            )
        elif etype == "permission_required":
            await session_store.append_message(
                db,
                session.id,
                novel_id=project.id,
                role="event",
                content="",
                page=page,
                payload={
                    "authorization_card": {
                        "gateId": event.get("gateId"),
                        "preview": event.get("preview"),
                        "humanOnly": event.get("humanOnly"),
                        "reason": event.get("reason"),
                    }
                },
                card_kind="gate",
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


@router.post("/approve")
async def approve_gate(
    project_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """授权卡批复：body {"gateId": str, "decision": "approved"|"denied"}。

    停车中的 gate 被唤醒继续执行/拒绝；已过期（进程重启后待决记录）返回 409，
    卡在会话里标过期，作家重发指令即可。
    """
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    body: dict[str, Any] = {}
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            body = raw
    except (ValueError, UnicodeDecodeError):
        body = {}
    gate_id = str(body.get("gateId") or "")
    decision = str(body.get("decision") or "")
    if not gate_id or decision not in ("approved", "denied"):
        raise HTTPException(422, "gateId 与 decision(approved|denied) 必填")
    from assistant.write_gate import PARKING

    if not PARKING.resolve(gate_id, decision):
        raise HTTPException(409, "该授权已过期或已批复——请重发指令。")
    return {"ok": True, "decision": decision}


@router.post("/permission-tier")
async def set_permission_tier(
    project_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """设置授权档位（入口只在设置页；agent 工具清单结构性没有此操作——
    「agent 不能给自己授权」红线）。body {"tier": "confirm_each"|"allow_book"|"allow_all"}"""
    from assistant.write_gate import KNOWN_TIERS

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    body: dict[str, Any] = {}
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            body = raw
    except (ValueError, UnicodeDecodeError):
        body = {}
    tier = str(body.get("tier") or "")
    if tier not in KNOWN_TIERS:
        raise HTTPException(422, f"tier 必须是 {list(KNOWN_TIERS)} 之一")
    session = await session_store.get_or_create_session(
        db, user_id=user["id"], novel_id=project.id
    )
    grants = json.loads(session.grants_json or "{}")
    grants["tier"] = tier
    await session_store.touch_session(db, session.id, grants=grants)
    return {"ok": True, "tier": tier}


@router.post("/undo")
async def undo_assistant_write(
    project_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤销一次助手写入：body {"messageId": str}。

    数据源＝该消息 step_end 落盘的 writeLog.previous（写前值）；回写走与写入
    同一条 update_volume 校验链。撤销本身落一条 event 行（可审计、不可静默）。
    """
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    session = await session_store.get_or_create_session(
        db, user_id=user["id"], novel_id=project.id
    )
    body: dict[str, Any] = {}
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            body = raw
    except (ValueError, UnicodeDecodeError):
        body = {}
    message_id = str(body.get("messageId") or "")
    if not message_id:
        raise HTTPException(422, "messageId 必填")

    rows = await session_store.load_messages(db, session.id, heal=False)
    target = next((m for m in rows if m.id == message_id), None)
    if target is None:
        raise HTTPException(404, "消息不存在或不属于本书会话")
    payload = json.loads(target.payload_json or "{}")
    write_log = payload.get("writeLog")
    if not write_log:
        raise HTTPException(422, "这条消息没有可撤销的写入。")
    if payload.get("undone"):
        raise HTTPException(409, "这条写入已经撤销过了。")

    entity = str(write_log.get("entity", ""))
    previous = write_log.get("previous") or {}
    if not entity.startswith("volume:") or not previous:
        raise HTTPException(422, "当前只支持卷字段写入的撤销（其余实体批B 后续接入）。")
    ref = entity.split(":", 1)[1]

    from db import async_session
    from volumes.schemas import VolumeUpdate
    from volumes.service import update_volume

    async with async_session() as undo_db:
        undo_project = await get_novel(undo_db, project_id, user["id"])
        if undo_project is None:
            raise HTTPException(404, "Project not found")
        await update_volume(
            undo_db, undo_project, ref, VolumeUpdate(**{k: v for k, v in previous.items()})
        )

    payload["undone"] = True
    await session_store.append_message(
        db,
        session.id,
        novel_id=project.id,
        role="event",
        content="",
        page=target.page,
        payload={
            "undo_of": message_id,
            "entity": entity,
            "restored": previous,
        },
    )
    return {"ok": True, "entity": entity, "restored": previous}
