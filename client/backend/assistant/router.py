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

import asyncio

# 活跃 run 注册表（c-agent-chat-memory 批8 停止/打断）：key = f"{session_id}:{thread}"，
# 值 = 该 run 的协同取消事件。stop 路由/新消息打断置位，循环在检查点自收口
_ACTIVE_RUNS: dict[str, asyncio.Event] = {}
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from assistant import compact as compact_mod
from assistant import identity as identity_mod
from assistant import session_store, write_gate
from assistant.context import build_book_brief, build_outbound_window, build_page_note
from assistant.loop import AgentLoop, LoopConfig
from assistant.prompts import build_system_prompt
from assistant.tools import ToolContext, _clip
from auth_local.deps import ai_access_granted
from auth_local.middleware import get_current_user
from db import get_db
from models.assistant import AssistantSession
from models.project import Novel
from novels.service import get_novel

router = APIRouter(prefix="/api/novels/{project_id}/assistant", tags=["assistant"])


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _history_transcript(rows: list[Any], exclude_message_id: str = "") -> list[dict[str, str]]:
    """持久化消息 → 循环转写（只取 user/assistant 文本行；工具/事件行不进转写——
    需要细节时 agent 用 read_* 重读，与 compact「细节优先牺牲」口径一致）。

    exclude_message_id＝本轮刚落库的那条用户消息：loop.run() 会把 user_input 再
    append 一次，不排除就双注入模型窗口（review 判例 2026-11-14）。

    跨天时间标记（c-agent-chat-memory 批8 记忆时序）：相邻消息跨日时插一条
    「[system] ── 时间跳到 M 月 D 日 ──」标记行——模型由此看出「这是几天前的话」，
    聚焦作家当前这条消息，不把昨日的任务指令翻出来当今日事项（openworker/
    coding agent 的会话时序口径）。"""
    out: list[dict[str, str]] = []
    last_day: str = ""
    for m in rows:
        if exclude_message_id and m.id == exclude_message_id:
            continue
        if m.role in ("user", "assistant") and m.content:
            day = str(getattr(m, "created_at", "") or "")[:10]
            if day and last_day and day != last_day:
                out.append({
                    "role": "assistant",
                    "content": f"[system] ── 时间跳到 {day[5:10].replace('-', ' 月 ')} 日 ──",
                })
            if day:
                last_day = day
            out.append({"role": m.role, "content": m.content})
    return out


def _resume_gap_note(rows: list[Any], *, threshold_hours: float = 6.0) -> str:
    """恢复聚焦提示：距上次对话超过阈值（默认 6h）时，给本轮注入一行聚焦提示——
    「聚焦本次新指令；此前未完的事只在作家提起时跟进」——模型不把历史任务
    翻出来主动汇报（openworker 恢复会话的聚焦口径）。无历史/未超阈值 → 空串。"""
    last_ts = ""
    for m in rows:
        ts = str(getattr(m, "created_at", "") or "")
        if ts:
            last_ts = ts  # rows 按 seq 有序——取最后一条带时间的
    if not last_ts:
        return ""
    try:
        from datetime import datetime as _dt

        last = _dt.strptime(last_ts, "%Y-%m-%d %H:%M:%S")
        gap_hours = (_dt.now() - last).total_seconds() / 3600
    except (ValueError, TypeError):
        return ""
    if gap_hours < threshold_hours:
        return ""
    if gap_hours < 24:
        gap_text = f"{int(gap_hours)} 个小时"
    elif gap_hours < 24 * 30:
        gap_text = f"{int(gap_hours // 24)} 天"
    else:
        gap_text = f"{int(gap_hours // (24 * 30))} 个月"
    return (
        f"（距上次对话已隔 {gap_text}。聚焦作家本次这条消息；"
        "此前未完的事只在作家提起时才跟进，不主动翻旧账。）"
    )


async def _stream_command_reply(
    db: AsyncSession,
    project: Novel,
    user: dict,
    session: AssistantSession,
    page: str,
    reply: str,
    *,
    clear: bool = False,
) -> AsyncIterator[str]:
    """斜杠命令的轻回复流（run_start＋narration＋run_end——前端气泡定位靠
    run 生命周期，缺 run_start 会把回执挂错位置/挂到旧回执上）。

    clear=True（/new）：先发 clear 事件——前端清空当前线程视图（服务端已清，
    视图必须跟着清，否则作家看到「说清了却还在」）。"""
    if clear:
        yield _sse({"type": "clear"})
    yield _sse({"type": "run_start", "runId": "cmd"})
    await session_store.append_message(
        db, session.id, novel_id=project.id, role="assistant",
        content=reply, page=page,
    )
    yield _sse({"type": "narration", "text": reply})
    yield _sse({"type": "run_end", "runId": "cmd", "steps": 0, "toolCalls": 0,
                "degraded": False, "error": ""})


async def _stream_compact(
    db: AsyncSession,
    project: Novel,
    user: dict,
    session: AssistantSession,
    page: str,
) -> AsyncIterator[str]:
    """「/compact」手动压缩：无条件走 build_state（阈值闸旁路），失败降级 trim。"""
    from ai_client import get_ai_client_for_novel
    from assistant.compact import (
        build_state as compact_build,
    )
    from assistant.compact import (
        estimate_tokens as est_tokens,
    )
    from assistant.compact import (
        remap_boundary,
    )
    from assistant.compact import (
        trim_state as compact_trim,
    )

    rows = await session_store.load_messages(db, session.id)
    transcript = _history_transcript(rows)
    prior = await session_store.load_compaction_state(db, session)
    prior = remap_boundary(prior, transcript)
    _messages, tokens_est = build_outbound_window(transcript, compaction_state=prior)

    if tokens_est < 2_000:
        reply = "这一页的对话还很短，不用压缩。"
        return _stream_command_reply(db, project, user, session, page, reply)

    client = await get_ai_client_for_novel(project.id)
    model_used = client.resolve("haiku")
    # openworker engine._compact_now 同口径：keep 只留触发线的 KEEP_RECENT_FRACTION 份
    keep = int(
        compact_mod.KEEP_RECENT_FRACTION * compact_mod.trigger_tokens(None)
    )

    async def _complete(system: str, user_text: str) -> str:
        return await client.chat(
            model="haiku", system=system,
            messages=[{"role": "user", "content": user_text}],
            max_tokens=3_000, operation="assistant_compact_manual",
        )

    async def _build():
        return await compact_build(
            transcript, complete_fn=_complete,
            keep_tokens=keep, prior=prior, model_used=model_used,
        )

    state = None
    failed = False
    for _attempt in range(2):  # 首试＋无条件单次重试（openworker 同款）
        try:
            state = await _build()
            failed = False
            break
        except Exception:  # noqa: BLE001——压缩失败降级裁剪（与自动压缩同政策）
            failed = True
    if state is not None:
        await session_store.save_compaction_state(db, session.id, state)
        after = est_tokens(
            [
                {"role": m.get("role"), "content": str(m.get("content", ""))}
                for m in compact_mod.apply_to_outbound(transcript, state)
                if m.get("role") in ("user", "assistant")
            ]
        )
        reply = (
            f"已压缩——更早的轮次收进了摘要，上下文从约 {tokens_est // 1000}K 降到约 {after // 1000}K。"
            "早前的细节需要时会自动重读。"
        )
        return _stream_command_reply(db, project, user, session, page, reply)
    if failed:
        # openworker 口径：重试仍败→裁剪最旧（摘要不可用也要让上下文回落）
        state = compact_trim(transcript, prior=prior)
        if state is None:
            reply = "这一页的对话还很短，不用压缩。"
            return _stream_command_reply(db, project, user, session, page, reply)
        await session_store.save_compaction_state(db, session.id, state)
        reply = "摘要没压成，我把最旧的轮次裁掉了——需要更早的细节会自动重读。"
        return _stream_command_reply(db, project, user, session, page, reply)
    reply = "这一页的对话还很短，不用压缩。"
    return _stream_command_reply(db, project, user, session, page, reply)


async def _stream_chat(
    db: AsyncSession,
    project: Novel,
    user: dict,
    session: AssistantSession,
    message: str,
    page: str,
    user_message_id: str = "",
    body_focus: dict[str, Any] | None = None,
    thread: str = "",
    tool_hint: dict[str, Any] | None = None,
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
    identity = await identity_mod.load_identity_for_user(db, user["id"])
    brief = await build_book_brief(project, db)
    # 书级记忆段（c-agent-chat-memory 批4）：agent 记忆＋项目决策，按书装载
    # 全页签生效；空书空段（前缀缓存友好）。缺席不致命（fail-soft）。
    try:
        from assistant.memory import load_book_memory_section

        memory_section = await load_book_memory_section(db, str(project.id))
    except Exception:  # noqa: BLE001——记忆缺席不致命（BLE001 豁免）
        memory_section = ""
    from assistant.scopes import discipline_of_thread

    thread = session_store.sanitize_thread_key(thread)
    system = build_system_prompt(
        identity_mod.identity_system_section(identity),
        brief,
        thread=thread,
        domain_discipline=discipline_of_thread(thread),
        memory_section=memory_section,
    )
    rows = await session_store.load_messages(db, session.id)
    transcript = _history_transcript(rows, exclude_message_id=user_message_id)
    # 聚焦对象（作家说「这章/这一卷」的锚）：前端随消息带 focus={ref}
    note = build_page_note(page, body_focus if isinstance(body_focus, dict) else None)
    # L2 画像注入（批C 3.3）：口味/雷点裁一段拼进页面注入——起草/发散先懂作家
    try:
        from assistant.profile import load_sections

        sections = await load_sections(db, user["id"])
        if sections:
            note = (
                (note + " " if note else "")
                + f"［作家画像（体谅口味、避开雷点）：{_clip(json.dumps(sections, ensure_ascii=False), 400)}］"
            )
    except Exception:  # noqa: BLE001——画像缺席不致命（BLE001 豁免）
        pass
    # 恢复聚焦（c-agent-chat-memory 批8 记忆时序）：隔了较久回来 → 提醒模型
    # 聚焦本次新指令，不把历史任务翻出来主动汇报
    gap_note = _resume_gap_note(rows)
    if gap_note:
        note = (note + " " if note else "") + gap_note
    # L2 注入随当前消息进提示词（不落库不进 UI）——历史已排除当前消息
    # （_history_transcript），旧「拼到末条 user 行」锚点不复存在
    message_for_model = f"{message}\n{note}" if note else message

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
        novel_id=project.id,
        root_path=project.root_path,
        user_id=user["id"],
        page=page,
        focus_ref=(body_focus or {}).get("ref", ""),
        thread=thread,
    )
    # 记账必须记真实模型（test_ai_prompt_and_boundary 护栏：符号别名不得落账）——
    # client.resolve("haiku") 落到本书绑定模型（AIClient.resolve 单源）
    used_model = client.resolve("haiku")
    compaction_state = await session_store.load_compaction_state(db, session)
    # 跨轮重映射（compact.py remap_boundary）：持久化边界是轮内转写的裸索引，下一轮
    # 转写由落库投影重建、构成不同——先映射回本列表再进循环（映射不上则作废重建）
    from assistant.compact import remap_boundary

    compaction_state = remap_boundary(compaction_state, transcript)

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
        """工具闸统一入口：
        - 读类：放行（登录即可）；
        - 产卡类：档位闸（ai-plan 系 PRO / assistant-diverge MAX）——无权出升级
          引导事件（不停车），有权放行执行；
        - 写类：档位闸 ＋ write_gate 三档梯度（停车弹授权卡）。"""
        from assistant.tools import get_tool

        tool = get_tool(tool_name)
        if tool is None or tool.kind == "read":
            return None

        # 档位闸（产卡/写类都有 feature_key；发散=max，干活=pro 系）
        tier_required = {"ai-plan": "pro", "settings-ai-fields": "standard"}.get(
            tool.feature_key, "pro"
        )
        if tool.feature_key and not ai_access_granted(tool.feature_key):
            upgrade_copy = {
                "assistant-diverge": (
                    "发散造人是 MAX 档的能力。升级后告诉我大概剧情，"
                    "我就能自己添人添事给你出草案。"
                ),
            }.get(
                tool.feature_key,
                "这个要 PRO 档才能让我动手。升级后我就能自己干活了。",
            )
            return [
                {
                    "type": "gate",
                    "feature": tool.feature_key,
                    "tier_required": "max" if tool.feature_key == "assistant-diverge" else tier_required,
                    "approved": False,
                    "refusal": upgrade_copy,
                }
            ]

        if tool.kind != "write":
            return None

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
        # 停车等待与取消赛跑：停止/打断到达时不再傻等 300s 批复（openworker 同款）
        wait_task = asyncio.ensure_future(write_gate.PARKING.wait(gate_id))
        cancel_wait = (
            asyncio.ensure_future(cancel_event.wait())
            if cancel_event is not None
            else None
        )
        pending_set = {wait_task, *([cancel_wait] if cancel_wait else [])}
        try:
            _done, _ = await asyncio.wait(pending_set, return_when=asyncio.FIRST_COMPLETED)
        finally:
            if cancel_wait is not None and not cancel_wait.done():
                cancel_wait.cancel()
        if cancel_wait is not None and cancel_wait.done() and not wait_task.done():
            write_gate.PARKING.discard(gate_id)
            return events + [
                {
                    "type": "gate_result",
                    "gateId": gate_id,
                    "approved": False,
                    "refusal": "已停止——这一步没有执行。",
                }
            ]
        approved = wait_task.result() == "approved"
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

    # 协同取消（停止/打断/断连即停——openworker 语义）：每会话线程一个取消事件，
    # stop 路由/新消息打断/断连收尸都只置位，循环在最近检查点自己收口（工具与
    # 落库链照常收尾，已产出保留）
    run_key = f"{session.id}:{thread}"
    cancel_event = asyncio.Event()

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
        cancel_event=cancel_event,
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

    async def _consume(drv_db: AsyncSession, event: dict[str, Any]) -> None:
        """落盘分支（消费副作用）：narration 攒回执、tool/授权卡/产物卡落行。

        用 drive 自有会话——请求级 db 随断开即被依赖清理关闭，断开后继续落库
        的会话必须自持（判例：读面写库自开短会话）。"""
        nonlocal final_status
        etype = event.get("type")
        if etype == "narration":
            reply_parts.append(str(event.get("text", "")))
        elif etype == "step_end":
            await session_store.append_message(
                drv_db,
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
                    "apiCalls": event.get("apiCalls"),  # 本步模型调用记录（反馈流可见）
                },
            )
        elif etype == "permission_required":
            await session_store.append_message(
                drv_db,
                session.id,
                novel_id=project.id,
                role="event",
                content="",
                page=page,
                payload={
                    "authorization_card": {
                        "gateId": event.get("gateId"),
                        "preview": event.get("preview"),
                        "humanOnly": event.get("human_only"),
                        "reason": event.get("reason"),
                    }
                },
                card_kind="gate",
            )
        elif etype == "artifact":
            # 产物卡持久化（对话流回看；adopted 状态由采纳端点推进）
            await session_store.append_message(
                drv_db,
                session.id,
                novel_id=project.id,
                role="assistant",
                content="",
                page=page,
                payload={
                    "card": event.get("payload") or {},
                    "cardId": event.get("cardId"),
                    "runId": event.get("runId"),
                },
                card_kind=str(event.get("kind", "text")),
                status="done",
            )
        elif etype == "error":
            final_status = "error"

    async def _finalize(drv_db: AsyncSession) -> None:
        """收尾落库（openwriter INTERRUPTED 同款）：停止/断开/正常收口都把已达
        内容定稿——不留 streaming 悬行，也不丢半截。会话自持（断开后仍要落）。"""
        full_reply = "\n".join(p for p in reply_parts if p)
        content = full_reply or pending_assistant.content
        if final_status == "done" and not content:
            content = "（停止时这一轮还没有产出文字。）"
        await session_store.update_message_status(
            drv_db,
            pending_assistant.id,
            status=final_status,
            content=content,
        )

    async def _drive() -> None:
        """自管消费任务（c-agent-harness 6.3 断连定诊）：循环消费＋落盘挪进独立
        task——断开时框架可能既不迭代也不关闭 SSE 生成器（starlette 1.9 实测
        streaming 悬行），消费挂 task 后由本任务自己的 finally 兜底定稿，任何
        出口（正常收口/被关停/被框架遗弃后跑完）都不丢尾。会话自持：请求级 db
        随断开即被依赖清理关闭，断开后继续落库必须用自有短会话。"""
        from db import async_session

        async with async_session() as drv_db:
            try:
                async for event in loop.run(message_for_model, prime=tool_hint):
                    await _consume(drv_db, event)
                    # thinking 照发 SSE（dock 实时思考回看，run_end 时前端收进
                    # run 气泡）；落盘分支不匹配 thinking——回看不存逐字思考
                    # Effect 注入（c-agent-effects）：run_end 携带本轮写操作 effects
                    if event.get("type") == "run_end" and run_effects:
                        event["effects"] = list(run_effects)
                    await queue.put(event)
                if loop.result.tokens_in or loop.result.tokens_out:
                    await session_store.append_message(
                        drv_db,
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
                    await session_store.touch_session(drv_db, session.id, page_cursor=page)
                await queue.put(_STOP)  # 正常收口：消费端见哨兵即退（body 出口）
            finally:
                # 收尾落库加盾（2026-11-17 竞态根修）：消费端收到 STOP 会立刻
                # cancel 本任务——取消正好落在 _finalize 的 await 上＝落库被
                # 打断，streaming 行悬挂、下轮被自愈盖「中途被打断」。shield
                # +独立 task 让定稿在取消后仍独立完成。
                try:
                    await asyncio.shield(asyncio.ensure_future(_finalize(drv_db)))
                except (asyncio.CancelledError, Exception):  # noqa: BLE001——定稿失败不炸收尾
                    pass

    queue: asyncio.Queue = asyncio.Queue()
    _STOP: dict[str, Any] = {"__stop__": True}
    _ACTIVE_RUNS[run_key] = cancel_event
    drive_task = asyncio.create_task(_drive())

    try:
        while True:
            event = await queue.get()
            if event is _STOP:
                break
            yield _sse(event)
    finally:
        # 断连/关停即停（尽力语义——starlette 可能不回调，stop 路由是主路径）：
        # 置位协同取消，循环在最近检查点自收口；正常收口时 drive 已结束，置位无害
        cancel_event.set()
        # 限时等待 drive 自然收口（含落库定稿）——急杀会把 _finalize 的
        # 落库打断（streaming 悬行→自愈盖「中途被打断」，2026-11-17 实锤）
        if not drive_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(drive_task), timeout=8)
            except (TimeoutError, asyncio.CancelledError, Exception):  # noqa: BLE001
                drive_task.cancel()
                try:
                    await asyncio.shield(drive_task)
                except (asyncio.CancelledError, Exception):  # noqa: BLE001——兜底吞一切
                    pass
        _ACTIVE_RUNS.pop(run_key, None)

    # ── 定期总结画像（批C 3.4）：非阻塞后台任务，失败静默（autotitle 模式）────
    asyncio.create_task(_profile_summary_task(user["id"], project.id))


async def _profile_summary_task(user_id: str, novel_id: str) -> None:
    """画像定期总结的后台任务体（自有会话＋自有客户端；永不冒泡成会话错误）。"""
    import logging

    try:
        from ai_client import get_ai_client_for_novel
        from assistant import profile
        from db import async_session

        async with async_session() as s:
            client = await get_ai_client_for_novel(novel_id)

            async def _complete(system: str, user_text: str) -> str:
                return await client.chat(
                    model="haiku",
                    system=system,
                    messages=[{"role": "user", "content": user_text}],
                    max_tokens=1024,
                    operation="assistant_profile_summary",
                )

            result = await profile.maybe_summarize(
                s, user_id=user_id, novel_id=novel_id, complete_fn=_complete
            )
            logging.getLogger(__name__).info(
                "assistant profile summarize: %s", result
            )
    except Exception as e:  # noqa: BLE001——静默（总结失败不影响任何会话）
        logging.getLogger(__name__).info("assistant profile summarize skipped: %s", e)


@router.post("/stop")
async def assistant_stop(
    project_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """停止当前线程的在跑 run（协同取消——已产出保留，openworker 停止语义）。

    无在跑 run 时幂等返回 stopped=false。"""
    body: dict[str, Any] = {}
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            body = raw
    except (ValueError, UnicodeDecodeError):
        body = {}
    thread = session_store.sanitize_thread_key(body.get("thread"))
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    session = await session_store.get_or_create_session(
        db, user_id=user["id"], novel_id=project.id, thread_key=thread
    )
    run_key = f"{session.id}:{thread}"
    ev = _ACTIVE_RUNS.get(run_key)
    if ev is None:
        return {"ok": True, "stopped": False}
    ev.set()
    for _ in range(20):
        if run_key not in _ACTIVE_RUNS:
            break
        await asyncio.sleep(0.1)
    return {"ok": True, "stopped": True}


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
    thread = session_store.sanitize_thread_key(body.get("thread"))
    if not message:
        raise HTTPException(422, "message 不能为空")

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    session = await session_store.get_or_create_session(
        db, user_id=user["id"], novel_id=project.id, thread_key=thread
    )
    # ── 打断（openworker 语义）：同线程上一轮在跑 → 置位取消并等它收口（≤4s）──
    run_key = f"{session.id}:{thread}"
    prev_event = _ACTIVE_RUNS.get(run_key)
    if prev_event is not None:
        prev_event.set()
        for _ in range(20):
            if run_key not in _ACTIVE_RUNS:
                break
            await asyncio.sleep(0.2)
        else:
            raise HTTPException(409, "上一轮还在收尾，稍候一拍再发")


    # /mode（openworker 对齐）：即时切授权档位；裸 /mode 报当前档
    mode_names = {
        "confirm_each": "每写必确认（默认）",
        "allow_book": "本书内自动放行",
        "allow_all": "全部自动放行",
    }
    if message == "/mode":
        grants_now = json.loads(session.grants_json or "{}")
        cur = str(grants_now.get("tier") or "confirm_each")
        reply = (
            f"当前授权：{mode_names.get(cur, cur)}。"
            "切换：/mode confirm（每写必确认）｜/mode book（本书放行）｜/mode all（全部放行）。"
        )
        return StreamingResponse(
            _stream_command_reply(db, project, user, session, page, reply),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    if message.startswith("/mode "):
        arg = message.split(None, 1)[1].strip().lower()
        arg_map = {
            "confirm": "confirm_each", "each": "confirm_each", "confirm_each": "confirm_each",
            "book": "allow_book", "allow_book": "allow_book",
            "all": "allow_all", "allow_all": "allow_all",
        }
        if arg not in arg_map:
            reply = "没这个档位——/mode confirm（每写必确认）｜/mode book（本书放行）｜/mode all（全部放行）。"
            return StreamingResponse(
                _stream_command_reply(db, project, user, session, page, reply),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        tier = arg_map[arg]
        rows_mode = (
            await db.scalars(
                select(AssistantSession).where(
                    AssistantSession.user_id == user["id"],
                    AssistantSession.novel_id == project.id,
                )
            )
        ).all()
        for row_m in rows_mode:
            g = json.loads(row_m.grants_json or "{}")
            g["tier"] = tier
            row_m.grants_json = json.dumps(g, ensure_ascii=False)
            row_m.updated_at = session_store._now()
        await db.commit()
        reply = f"授权已切到「{mode_names[tier]}」——对这本书的所有页签生效。"
        return StreamingResponse(
            _stream_command_reply(db, project, user, session, page, reply),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    # 斜杠命令（coding agent 命令行习惯，boss 拍板 2026-11-15）：命令本身不进对话历史
    if message == "/new":
        await session_store.reset_session(db, session.id)
        return StreamingResponse(
            _stream_command_reply(
                db, project, user, session, page,
                "已开新对话——之前的内容都清掉了，想从哪儿说起？",
                clear=True,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    if message == "/compact":
        return StreamingResponse(
            await _stream_compact(db, project, user, session, page),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    body_focus = body.get("focus")
    if not isinstance(body_focus, dict):
        body_focus = None
    user_row = await session_store.append_message(
        db,
        session.id,
        novel_id=project.id,
        role="user",
        content=message,
        page=page,
    )

    tool_hint = body.get("tool_hint")
    if not (isinstance(tool_hint, dict) and isinstance(tool_hint.get("tool"), str) and tool_hint.get("tool").strip()):
        tool_hint = None
    return StreamingResponse(
        _stream_chat(
            db, project, user, session, message, page,
            user_message_id=user_row.id, body_focus=body_focus,
            thread=thread, tool_hint=tool_hint,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/session")
async def get_assistant_session(
    project_id: str,
    thread: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """会话回看（按线程）：messages 按 seq 全量（含状态），元数据带授权档位与 compact 有无。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    session = await session_store.get_or_create_session(
        db, user_id=user["id"], novel_id=project.id,
        thread_key=session_store.sanitize_thread_key(thread),
    )
    rows = await session_store.load_messages(db, session.id)
    # 上下文容量（coding agent 口径，boss 拍板 2026-11-15）：外发窗口估算 vs 窗口
    from assistant.compact import DEFAULT_CONTEXT_WINDOW

    _msgs, tokens_est = build_outbound_window(
        _history_transcript(rows),
        compaction_state=await session_store.load_compaction_state(db, session),
    )
    context = {
        "estTokens": tokens_est,
        "window": DEFAULT_CONTEXT_WINDOW,
        "pct": round(tokens_est / DEFAULT_CONTEXT_WINDOW * 100, 1),
    }
    return {
        "sessionId": session.id,
        "pageCursor": session.page_cursor,
        "grants": json.loads(session.grants_json or "{}"),
        "compacted": bool(session.compaction_json and session.compaction_json != "{}"),
        "context": context,
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
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
    session = await session_store.get_or_create_session(
        db, user_id=user["id"], novel_id=project.id,
        thread_key=session_store.sanitize_thread_key(body.get("thread")),
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
    # 授权档位书级语义（boss 拍板：切页签/线程不重置授权）——更新本书全部线程
    rows = (
        await db.scalars(
            select(AssistantSession).where(
                AssistantSession.user_id == user["id"],
                AssistantSession.novel_id == project.id,
            )
        )
    ).all()
    for row in rows:
        grants = json.loads(row.grants_json or "{}")
        grants["tier"] = tier
        row.grants_json = json.dumps(grants, ensure_ascii=False)
        row.updated_at = session_store._now()
    if not rows:
        await session_store.get_or_create_session(
            db, user_id=user["id"], novel_id=project.id,
            thread_key=session_store.sanitize_thread_key(body.get("thread")),
        )
    await db.commit()
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

    # 跨线程找消息（写入可能发生在任意页签线程；归属由 novel_id+书主权保证）
    from models.assistant import AssistantMessage

    target = (
        await db.scalars(
            select(AssistantMessage).where(
                AssistantMessage.novel_id == project.id,
                AssistantMessage.id == message_id,
            )
        )
    ).first()
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
        target.session_id,
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


@router.post("/messages/{card_id}/adopt")
async def adopt_assistant_message(
    project_id: str,
    card_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """产物卡采纳回执落库（重开书后「已采纳」徽标与 stale 防护不丢——review P3）。

    按 payload.cardId（run_id-step_no，全局唯一）定位本会话的产物卡行；幂等。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    # 跨线程找产物卡（卡可能在任意页签线程产生）
    from models.assistant import AssistantMessage

    rows = (
        await db.scalars(
            select(AssistantMessage).where(
                AssistantMessage.novel_id == project.id,
                AssistantMessage.card_kind.not_in(("", "gate")),
            )
        )
    ).all()
    target = None
    for m in rows:
        payload = json.loads(m.payload_json or "{}")
        if str(payload.get("cardId") or "") == card_id:
            target = m
    if target is None:
        raise HTTPException(404, "产物卡不存在或不属于本书会话。")
    if target.status != "adopted":
        await session_store.update_message_status(db, target.id, status="adopted")
    return {"ok": True, "cardId": card_id}


@router.get("/persona")
async def get_assistant_persona(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """助手人格查看（顶栏控制中心入口）：返回当前生效人格＋是否自定义覆盖。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    custom = await identity_mod.load_persona(db, user["id"])
    if custom:
        try:
            identity = identity_mod.validate_identity(custom)
            return {"identity": identity, "customized": True}
        except (RuntimeError, TypeError):
            pass  # 覆盖残缺：照常回落展示生效人格
    return {"identity": await identity_mod.load_identity(), "customized": False}


@router.put("/persona")
async def update_assistant_persona(
    project_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """助手人格编辑（作家自定义搭档人设；四字段必需齐全，fail-loud 校验）。"""
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
    identity_raw = body.get("identity")
    if not isinstance(identity_raw, dict):
        raise HTTPException(422, "identity 必填（对象）")
    try:
        saved = await identity_mod.save_persona(db, user["id"], identity_raw)
    except (RuntimeError, TypeError) as e:
        raise HTTPException(422, f"人格字段不完整：{e}") from e
    return {"ok": True, "identity": saved, "customized": True}


@router.delete("/persona")
async def reset_assistant_persona(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """助手人格恢复默认（删除用户覆盖 → 回到提示词包/内置兜底）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    await identity_mod.clear_persona(db, user["id"])
    return {"ok": True, "customized": False}


@router.get("/profile")
async def get_writer_profile(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """画像查看（四条件之一：可查看/可编辑/可清空/可暂停——本端点族承载）。"""
    from assistant.profile import get_or_create_profile

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    row = await get_or_create_profile(db, user["id"])
    return {
        "sections": json.loads(row.sections_json or "{}"),
        "paused": bool(row.paused),
        "updatedAt": row.updated_at,
    }


@router.post("/profile/update")
async def update_writer_profile(
    project_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """画像手填/编辑（作家自己改；与 agent 写入同一条 update_sections 链）。"""
    body: dict[str, Any] = {}
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            body = raw
    except (ValueError, UnicodeDecodeError):
        body = {}
    updates = body.get("updates")
    if not isinstance(updates, dict) or not updates:
        raise HTTPException(422, "updates 必填")
    from assistant.profile import update_sections

    result = await update_sections(
        db, user_id=user["id"], novel_id=project_id, updates=updates, kind="manual"
    )
    return result


@router.post("/profile/clear")
async def clear_writer_profile(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """一键清空画像（可清空是画像四条件之一）。"""
    from assistant.profile import clear_profile

    await clear_profile(db, user["id"])
    return {"ok": True}


@router.post("/profile/pause")
async def pause_writer_profile(
    project_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """「暂停画像学习」开关（即时生效；已有内容保留）。body {"paused": bool}"""
    body: dict[str, Any] = {}
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            body = raw
    except (ValueError, UnicodeDecodeError):
        body = {}
    paused = bool(body.get("paused"))
    from assistant.profile import set_paused

    await set_paused(db, user["id"], paused)
    return {"ok": True, "paused": paused}
