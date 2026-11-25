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
import logging
import re

# 活跃 run 注册表（c-agent-chat-memory 批8 停止/打断）：key = f"{session_id}:{thread}"，
# 值 = 该 run 的协同取消事件。stop 路由/新消息打断置位，循环在检查点自收口
_ACTIVE_RUNS: dict[str, asyncio.Event] = {}

# 页签真值/导航意图（c-agent-nav 走查实锤）：thread 后缀 ↔ 页签中文名；窄意图正则
# 只吃「切/换/跳到 X」「看看 X」两类，意图外消息一个字都不多管——歧义交给模型问
_THREAD_TAB_ZH = {
    "og": "章纲", "prose": "正文", "settings": "设定", "relations": "角色关系",
    "hooks": "伏笔", "actions": "操作", "style": "文风",
}
_NAV_TAB_KEY = {v: k for k, v in _THREAD_TAB_ZH.items()}
# 设定面板名（c-agent-page-field-truth）：thread set:<panel> 后缀 ↔ 中文名。键集
# 对齐前端设定左栏（SettingsView SETTINGS_ITEMS / chatRegistry.threadKeyOf）；面板
# 名此前只编码在 thread 键里、后端无人解析——模型不知道作家在题材页还是角色页。
# default 与未知键回退空串（注入「设定」不带面板后缀）。
_SET_PANEL_ZH = {
    "genre": "题材", "intro": "简介", "world": "世界", "chars": "角色",
    "arc": "主线", "style": "文风", "foreshadow": "伏笔",
}


def settings_tab_label(thread: str) -> str:
    """set:* 线程 → 页签真值标签（c-agent-page-field-truth）：「设定·题材」形；
    set:default/未知面板键回退「设定」；非 set: 线程返回空串（调用方走 ch: 分支）。
    纯函数——钉子好写。"""
    thread = (thread or "").strip()
    if not thread.startswith("set:"):
        return ""
    panel = _SET_PANEL_ZH.get(thread.split(":", 1)[1], "")
    return f"设定·{panel}" if panel else "设定"


_NAV_INTENT_RE = re.compile(
    r"(?:把页面|页面|页签)?(?:切|换|跳)(?:到|去|至)\s*(正文|章纲|设定|文风|角色关系|伏笔|操作)"
    r"|(?:看看|看一下|看下)\s*(正文|章纲|设定|文风|角色关系|伏笔|操作)"
)


_GENRE_INTENT_RE = re.compile(
    r"(?:根据|按|照着).{0,8}(?:书名|标题|题目).{0,10}(?:选|定|判断|推荐|给).{0,6}题材"
    r"|(?:帮我|给我|你).{0,6}(?:选|定|判断|推荐).{0,6}题材"
    r"|(?:这|本).{0,4}书.{0,8}(?:算|是|属于).{0,4}(?:什么|哪个)题材"
)


def genre_prime_hint(thread: str, message: str, existing: dict | None = None) -> dict | None:
    """选题材意图 → read_genre_catalog prime（c-agent-genre-pick）。

    设定域内窄正则命中才 prime：先把封闭目录放进当轮上下文，模型再选大类/子类；
    显式 tool_hint 优先。纯读、零副作用——误命中最多多读一次目录。"""
    if existing is not None or not (thread or "").strip().startswith("set:"):
        return existing
    if not _GENRE_INTENT_RE.search(message or ""):
        return None
    return {"tool": "read_genre_catalog", "args": {}}


def nav_prime_hint(thread: str, message: str, existing: dict | None = None) -> dict | None:
    """导航意图 → switch_tab prime（c-agent-nav 走查实锤补刀）。

    窄正则命中「切到X／看看X」且目标≠当前页签才 prime；显式 tool_hint 优先；
    域外（非 ch:*）恒 None（工具不可见域模型本就无从调用）。纯函数——钉子好写。"""
    if existing is not None or not (thread or "").strip().startswith("ch:"):
        return existing
    m = _NAV_INTENT_RE.search(message or "")
    if not m:
        return None
    target_tab = _NAV_TAB_KEY.get(next((g for g in m.groups() if g), ""), "")
    if not target_tab or target_tab == thread.split(":", 1)[1]:
        return None
    return {"tool": "switch_tab", "args": {"tab": target_tab}}
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from assistant import compact as compact_mod
from assistant import identity as identity_mod
from assistant import session_store, write_gate
from assistant.context import (
    build_book_brief_parts,
    build_outbound_window,
    build_page_note,
    latest_reminder_text,
)
from assistant.loop import AgentLoop, LoopConfig, _finalize_plan
from assistant.prompts import build_system_prompt
from assistant.tools import PreviewRejected, ToolContext, _clip, get_tool
from auth_local.deps import ai_access_granted
from auth_local.middleware import get_current_user
from db import get_db
from models.project import Novel
from novels.service import get_novel

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels/{project_id}/assistant", tags=["assistant"])


def _is_max_member() -> bool:
    """当前用户是否 MAX（allow_book 自动执行仅 MAX）。"""
    from auth_local.service import check_permission

    return str(check_permission().get("tier") or "") in ("max", "lifetime")


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def execute_gate_event(tool: Any) -> dict[str, Any] | None:
    """执行门（c-writing-agent-tier）：写类工具按声明要求 assistant-execute（标准起）。

    读类/产卡类不在此门管辖（产卡类走各自 feature_key 档位闸）。
    返回 None＝放行到后续授权梯度；返回 gate 事件＝无权（调用方 yield 后 return，
    不 403、不停车、不弹授权卡）。
    """
    feature = getattr(tool, "requires_feature", "")
    if not feature:
        return None
    if ai_access_granted(feature):
        return None
    return {
        "type": "gate",
        "feature": feature,
        "tier_required": _execute_tier_required(feature),
        "approved": False,
        "refusal": "动手的活要 PRO 档起我才能接。升级后我就能替你改设定、建章纲、收知识库。",
    }


def _execute_tier_required(feature: str) -> str:
    """执行键 → 最低档（与档位目录兜底表同源，未知键回落 standard）。"""
    from auth_local.service import STANDARD_FALLBACK

    for tier in ("standard", "pro", "max"):
        if feature in STANDARD_FALLBACK.get(tier, {}).get("features", []):
            return tier
    return "standard"


async def _build_gate_preview(tool: Any, args: dict[str, Any], project: Any, fallback: dict) -> dict:
    """授权卡 preview 装配（c-agent-page-ops 增强的接线点）。

    preview_builder 契约是 (args, project)——project 供 builder 读本书现值；曾按
    单参数调用，TypeError 被兜底吞掉后作家看到的是写工具裸 JSON（2026-11-21
    实锤）。PreviewRejected 向上抛（router 不弹卡，回喂模型改参数）；其余失败
    回落 write_gate 默认形状（闸不受影响）。"""
    builder = getattr(tool, "preview_builder", None)
    if builder is None:
        return fallback
    try:
        built = builder(args, project)
        if asyncio.iscoroutine(built):
            built = await built
    except PreviewRejected:
        raise
    except Exception:  # noqa: BLE001——preview 失败不阻断闸
        return fallback
    return built if isinstance(built, dict) and built else fallback


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
    project: Novel,
    user: dict,
    session: session_store.SessionMeta,
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
        session, role="assistant",
        content=reply, page=page,
    )
    yield _sse({"type": "narration", "text": reply})
    yield _sse({"type": "run_end", "runId": "cmd", "steps": 0, "toolCalls": 0,
                "degraded": False, "error": ""})


async def _stream_compact(
    project: Novel,
    user: dict,
    session: session_store.SessionMeta,
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

    rows = await session_store.load_messages(session)
    transcript = _history_transcript(rows)
    prior = await session_store.load_compaction_state(session)
    prior = remap_boundary(prior, transcript)
    _messages, tokens_est = build_outbound_window(transcript, compaction_state=prior)

    if tokens_est < 2_000:
        reply = "这一页的对话还很短，不用压缩。"
        return _stream_command_reply(project, user, session, page, reply)

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
        await session_store.save_compaction_state(session, state)
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
        return _stream_command_reply(project, user, session, page, reply)
    if failed:
        # openworker 口径：重试仍败→裁剪最旧（摘要不可用也要让上下文回落）
        state = compact_trim(transcript, prior=prior)
        if state is None:
            reply = "这一页的对话还很短，不用压缩。"
            return _stream_command_reply(project, user, session, page, reply)
        await session_store.save_compaction_state(session, state)
        reply = "摘要没压成，我把最旧的轮次裁掉了——需要更早的细节会自动重读。"
        return _stream_command_reply(project, user, session, page, reply)
    reply = "这一页的对话还很短，不用压缩。"
    return _stream_command_reply(project, user, session, page, reply)


async def _stream_chat(
    db: AsyncSession,
    project: Novel,
    user: dict,
    session: session_store.SessionMeta,
    message: str,
    page: str,
    user_message_id: str = "",
    body_focus: dict[str, Any] | None = None,
    page_unsaved: list[str] | None = None,
    page_prose: str = "",
    thread: str = "",
    tool_hint: dict[str, Any] | None = None,
    api_config_id: str = "",
    model: str = "",
    thinking_override: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """SSE generator：no-key 引导 → 组装 → 循环 → 逐步落盘。"""

    # ── no-key：不 503，流内引导卡收尾（历史保留）───────────────────────────
    from ai_state import user_has_ai_key

    if not await user_has_ai_key(db, user["id"]):
        # 走完整 run 生命周期（run_start→gate→run_end）——前端无终态会判死出
        # 「连接中断」假错误（2026-11-18 boss 走查实锤）；补救语句带可点击出口
        # （action: config_model → 前端导航到设定·AI 模型配置，§13 口径）
        guide = "还没配模型的钥匙——去「模型配置」加一个，我就能开工了。"
        yield _sse({"type": "run_start", "runId": "nokey"})
        yield _sse({"type": "gate", "reason": "no_key", "message": guide, "action": "config_model"})
        await session_store.append_message(
            session,
            role="assistant",
            content=guide,
            page=page,
            payload={"gate": "no_key", "action": "config_model"},
            card_kind="gate",
        )
        yield _sse({"type": "run_end", "runId": "nokey", "steps": 0, "toolCalls": 0, "degraded": False, "error": ""})
        return

    # ── 组装 ────────────────────────────────────────────────────────────────
    identity = await identity_mod.load_identity_for_user(db, user["id"])
    # 书级 brief 拆稳定/动态（c-agent-prompt-cache）：稳定段（书名/题材）进
    # 系统前缀；动态进度拼到当前 user 消息尾部——写作进度一变不会废掉整段前缀缓存。
    stable_brief, dynamic_brief = await build_book_brief_parts(project, db)
    # 书级记忆段（c-agent-chat-memory 批4）：agent 记忆＋项目决策，按书装载；
    # 动态段不进系统前缀（前缀缓存），与页面注入一起拼当前 user 消息尾部。
    try:
        from assistant.memory import load_book_memory_section

        memory_section = await load_book_memory_section(db, str(project.id))
    except Exception:  # noqa: BLE001——记忆缺席不致命（BLE001 豁免）
        memory_section = ""
    from assistant.scopes import discipline_of_thread

    thread = session_store.sanitize_thread_key(thread)
    system = build_system_prompt(
        identity_mod.identity_system_section(identity),
        stable_brief,
        thread=thread,
        domain_discipline=discipline_of_thread(thread),
        memory_section="",
    )
    rows = await session_store.load_messages(session)
    transcript = _history_transcript(rows, exclude_message_id=user_message_id)
    # 聚焦对象（作家说「这章/这一卷」的锚）：前端随消息带 focus={ref}
    note = build_page_note(page, body_focus if isinstance(body_focus, dict) else None)
    # 页面状态随行（c-agent-page-ops）：未保存标记只进模型提示词——写改前知悉，
    # 不静默覆盖作家未保存内容（界面零渲染）。
    if page_unsaved:
        note = (
            (note + " " if note else "")
            + f"［未保存：{'、'.join(page_unsaved)}——写改该页前先提醒作家，避免覆盖其未保存内容］"
        )
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
    # 页签真值注入（c-agent-nav 走查实锤）：thread 即当前页签，服务端是唯一真值源
    # ——不注入模型就信被污染的历史（「页签已经在正文了」幻觉实锤 0/3 服从）
    if thread.startswith("ch:"):
        _cur_tab = _THREAD_TAB_ZH.get(thread.split(":", 1)[1], "")
        if _cur_tab:
            note = (note + " " if note else "") + f"［当前页签：{_cur_tab}］"
    elif thread.startswith("set:"):
        # 面板真值（c-agent-page-field-truth）：设定面板名原只编码在 thread 键里，
        # 后端无人解析——模型不知道作家在题材页还是角色页（page 字符串不分面板）。
        _tab_label = settings_tab_label(thread)
        note = (note + " " if note else "") + f"［当前页签：{_tab_label}］"
    # 动态书情/记忆拼当前 user 消息尾部（c-agent-prompt-cache）：系统前缀只留
    # 稳定段（书名/题材/身份/协议/工具目录），进度变化不废前缀缓存。
    for part in (dynamic_brief, memory_section):
        if part:
            note = (note + "\n\n" if note else "") + part
    # L2 注入随当前消息进提示词（不落库不进 UI）——历史已排除当前消息
    # （_history_transcript），旧「拼到末条 user 行」锚点不复存在
    message_for_model = f"{message}\n{note}" if note else message

    # 导航意图 prime（c-agent-nav 走查实锤）：flash 长历史服从 0/3——「切到X」类
    # 窄意图直接 prime switch_tab 首步（chips tool_hint 同款确定性机制，模型只管
    # 事后叙述）。仅章节域内（switch_tab 可见域）、目标≠当前页签才 prime；同页签
    # 请求由页签真值注入兜住（模型如实回答「已在正文」）。读类零风险，误命中代价
    # ＝一次无副作用翻页。
    tool_hint = nav_prime_hint(thread, message, tool_hint)
    tool_hint = genre_prime_hint(thread, message, tool_hint)

    try:
        from ai_client import get_ai_client_for_novel

        # 按次模型覆盖对（c-agent-thinking-bubbles）：与正文生成弹窗同源机制——
        # 仅本轮生效、不改本书绑定；校验失败在流内给可读出口。
        if api_config_id or model:
            client = await get_ai_client_for_novel(
                project.id,
                api_config_id=api_config_id or None,
                model=model or None,
            )
        else:
            client = await get_ai_client_for_novel(project.id)
    except ValueError as e:
        msg = (
            f"你选的助手模型用不了：{e}"
            if (api_config_id or model)
            else f"模型的钥匙配了但用不了：{e}"
        )
        yield _sse({"type": "gate", "reason": "client_error", "message": msg})
        await session_store.append_message(
            session,
            role="assistant",
            content=msg,
            page=page,
            payload={"gate": "client_error"},
            card_kind="gate",
        )
        return

    prior_plan = session_store.latest_plan(rows)
    tool_ctx = ToolContext(
        novel_id=project.id,
        root_path=project.root_path,
        user_id=user["id"],
        page=page,
        focus_ref=(body_focus or {}).get("ref", ""),
        thread=thread,
        page_unsaved=tuple(page_unsaved or ()),
        page_prose=page_prose,
        scratch={"plan": prior_plan} if prior_plan else {},
    )
    # 记账必须记真实模型（test_ai_prompt_and_boundary 护栏：符号别名不得落账）——
    # client.resolve("haiku") 落到本书绑定模型（AIClient.resolve 单源）
    used_model = client.resolve("haiku")
    # DeepSeek 当前日期标记（c-agent-latest-reminder）：能力位门控，只 openai+deepseek
    _supports_reminder = getattr(client, "supports_latest_reminder", None)
    latest_reminder = (
        latest_reminder_text()
        if callable(_supports_reminder) and _supports_reminder()
        else ""
    )
    if latest_reminder:
        # 静态纪律行（不含动态日期，前缀稳定）：告诉模型 latest_reminder 是可信
        # 当前日期来源——否则长人设下模型会按训练记忆/「没有日历」拒答。
        system += (
            "\n\n── 当前时间 ──\n"
            "当前日期/星期由 latest_reminder 消息提供（格式：YYYY-MM-DD,星期X,...）；"
            "问到或用到「今天」时以它为准，不要凭训练记忆猜。"
        )
    compaction_state = await session_store.load_compaction_state(session)
    # 跨轮重映射（compact.py remap_boundary）：持久化边界是轮内转写的裸索引，下一轮
    # 转写由落库投影重建、构成不同——先映射回本列表再进循环（映射不上则作废重建）
    from assistant.compact import remap_boundary

    compaction_state = remap_boundary(compaction_state, transcript)

    async def _on_compaction(state: Any) -> None:
        await session_store.save_compaction_state(session, state)

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

    async def _gate_fn(
        tool_name: str, args: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """工具闸统一入口（异步生成器：yield 即下发）：
        - 读类：放行（登录即可）；
        - 产卡类：档位闸（ai-plan 系 PRO / assistant-diverge MAX）——无权出升级
          引导事件（不停车），有权放行执行；
        - 写类：档位闸 ＋ write_gate 三档梯度（停车弹授权卡）。

        停车口径：permission_required **先 yield 再等批复**——SSE 客户端拿到卡
        才有得批；旧实现等批复完才把事件交出去，授权卡永远晚于停车结果，前端
        只看见「进行中」空等 300s 超时（2026-11-21 真机实锤）。"""
        from assistant.tools import get_tool

        tool = get_tool(tool_name)
        if tool is None or tool.kind == "read":
            return

        # 执行门（c-writing-agent-tier）：写类先过 assistant-execute（标准起）。
        # 无权 → 升级引导事件后收口；不走后续 feature_key 闸与授权停车。
        gate_event = execute_gate_event(tool)
        if gate_event is not None:
            yield gate_event
            return

        # 档位闸（三档：标准免费只读；PRO=AI 写手；MAX=写作秘书）
        _MAX_ONLY = {
            "human-taste", "image-generate", "assistant-diverge",
            "ai-plot", "style-quant", "deconstruct-import",
        }
        tier_required = "max" if tool.feature_key in _MAX_ONLY else "pro"
        if tool.feature_key and not ai_access_granted(tool.feature_key):
            upgrade_copy = {
                "assistant-diverge": (
                    "发散造人是 MAX 档的能力。升级后告诉我大概剧情，"
                    "我就能自己添人添事给你出草案。"
                ),
                "human-taste": (
                    "人味检测和逐行改法是 MAX 档的能力。升级后我就能替你查人味、给改法。"
                ),
                "kb-official": (
                    "官方写作知识库是 PRO 档的能力。升级后我就能用 331 本书的写法帮你。"
                ),
                "ai-generate": (
                    "写正文是 PRO 档的能力。升级后我就能在对话里出正文方案、整章生成。"
                ),
            }.get(
                tool.feature_key,
                "这个要 MAX 档才能让我接。" if tier_required == "max"
                else "这个要 PRO 档才能让我接。",
            )
            yield {
                "type": "gate",
                "feature": tool.feature_key,
                "tier_required": tier_required,
                "approved": False,
                "refusal": upgrade_copy,
            }
            return

        if tool.kind != "write":
            return

        # allow_book 自动执行仅 MAX；非 MAX 即使存量 grants 为自动档也回退每写必确认
        if tier in (write_gate.TIER_ALLOW_BOOK, write_gate.TIER_ALLOW_ALL) and not _is_max_member():
            tier = write_gate.TIER_CONFIRM_EACH
        decision = write_gate.evaluate(tool_name, args, tier=tier)
        if decision.allowed:
            return
        if not decision.needs_user:
            yield {
                "type": "gate_result",
                "gateId": "",
                "approved": False,
                "refusal": "这个操作没有通过授权检查。",
            }
            return

        # 停车：发授权卡，等作家批复（超时/关应用＝未批；待决记录已持久化可审计）
        # preview 增强（c-agent-page-ops）：写工具可挂 preview_builder（读现值构造
        # 「字段：写入前→写入后」对比）。参数本身不合法（字段名不存在）不弹卡——
        # 回喂模型改对再来，作家不看写不成的授权单。
        try:
            preview = await _build_gate_preview(tool, args, project, decision.preview)
        except PreviewRejected as e:
            # 异步闸契约：只能 yield＋裸 return（带值 return 在 async generator 里
            # 是 SyntaxError——#1105 改造后合并曾踩，review P1 实编译实锤）。
            # 裸 gate_result：loop 末项 approved=False 即拒，不发卡不等批复。
            yield {
                "type": "gate_result",
                "gateId": "",
                "approved": False,
                "refusal": str(e),
            }
            return
        gate_id = write_gate.PARKING.register()
        await session_store.append_message(
            session,
            role="event",
            page=page,
            payload={
                "pending_gate": {
                    "gate_id": gate_id,
                    "tool": tool_name,
                    "preview": preview,
                    "human_only": decision.human_only,
                }
            },
            status="streaming",
        )
        # 先下发授权卡（SSE 立刻可见），再停车等批复
        yield {
            "type": "permission_required",
            "gateId": gate_id,
            "preview": preview,
            "humanOnly": decision.human_only,
            "reason": decision.reason,
        }
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
            yield {
                "type": "gate_result",
                "gateId": gate_id,
                "approved": False,
                "refusal": "已停止——这一步没有执行。",
            }
            return
        approved = wait_task.result() == "approved"
        write_gate.PARKING.discard(gate_id)
        yield {
            "type": "gate_result",
            "gateId": gate_id,
            "approved": approved,
            "refusal": None if approved else "作家没有授权这个操作，我不做了。",
        }

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
        config=LoopConfig(thinking=thinking_override, latest_reminder=latest_reminder),
        on_compaction=_on_compaction,
        on_usage=_on_usage,
        gate_fn=_gate_fn,
        cancel_event=cancel_event,
    )

    # ── 逐步落盘＋SSE 下发 ─────────────────────────────────────────────────
    pending_assistant = await session_store.append_message(
        session,
        role="assistant",
        content="",
        page=page,
        status="streaming",
    )
    reply_parts: list[str] = []
    final_status = "done"
    # Effect 收集（c-agent-effects）：本 run 内成功写步的刷新指令，run_end 注入。
    # 2026-11-18 boss 走查实锤：只写消费不写收集＝NameError 在 _drive 里炸掉
    # → _STOP 永不入队 → SSE 永挂（前端「进行中」卡死）。收集与消费必须同侧成对。
    run_effects: list[dict[str, Any]] = []
    # 过程轨迹（c-agent-thinking-bubbles）：思考/工具按发生顺序收集，收尾并入
    # assistant 行 payload——前端重开书/切页签按同样顺序复原独立过程泡泡。
    process_items: list[dict[str, Any]] = []

    async def _consume(event: dict[str, Any]) -> list[dict[str, Any]]:
        """落盘分支（消费副作用）：narration 攒回执、tool/授权卡/产物卡落行。
        返回本事件衍生的即时 SSE 事件（c-agent-nav navigate effect），由 _drive
        紧随本事件按序入队。

        文件后端（c-agent-session-files）：落盘自持文件路径，不再需要 DB 会话
        （旧判例「drive 自有短会话」随载体退役）。"""
        nonlocal final_status
        etype = event.get("type")
        if etype == "narration":
            reply_parts.append(str(event.get("text", "")))
            return []
        if etype == "plan" and isinstance(event.get("plan"), dict):
            # 计划快照逐步落盘（c-agent-action-contract）：append-only，
            # 恢复按最近一条；旧前端对空 content event 行天然跳过
            await session_store.append_message(
                session,
                role="event",
                content="",
                page=page,
                payload={"plan": event.get("plan")},
                card_kind="plan",
            )
            return []
        if etype == "run_end" and isinstance(event.get("plan"), dict):
            # 收口安全网后的最终快照（active 已降级）也要落盘
            await session_store.append_message(
                session,
                role="event",
                content="",
                page=page,
                payload={"plan": event.get("plan")},
                card_kind="plan",
            )
            return []
        if etype == "thinking":
            chunk = str(event.get("text") or "")
            if chunk:
                last = process_items[-1] if process_items else None
                if last is not None and last.get("kind") == "thinking":
                    last["text"] = str(last.get("text") or "") + chunk
                else:
                    process_items.append({"kind": "thinking", "text": chunk})
            return []
        if etype == "step_start":
            step_id = str(event.get("stepId") or "")
            item: dict[str, Any] = {
                "kind": "tool",
                "stepId": step_id,
                "tool": str(event.get("tool") or ""),
                "running": True,
            }
            label = str(event.get("label") or "")
            if label:
                item["label"] = label[:80]
            process_items.append(item)
            return []
        if etype == "step_end":
            step_id = str(event.get("stepId") or "")
            note = str(event.get("resultNote", ""))
            # 参数预览（c-agent-process-progress）：工具卡展开可见，截 600 防大字段
            args_raw = event.get("args")
            args_preview = (
                _clip(json.dumps(args_raw, ensure_ascii=False), 600)
                if isinstance(args_raw, dict) and args_raw
                else ""
            )
            for item in process_items:
                if item.get("kind") == "tool" and item.get("stepId") == step_id:
                    item["running"] = False
                    item["note"] = note
                    if args_preview:
                        item["args"] = args_preview
                    if "ok" in event:
                        item["ok"] = bool(event.get("ok"))
                    if event.get("apiCalls"):
                        item["apiCalls"] = event["apiCalls"]
                    break
            else:
                # 未先收到 step_start（旧桩/极端乱序）：补一条已完成的工具项
                fallback: dict[str, Any] = {
                    "kind": "tool",
                    "stepId": step_id,
                    "tool": str(event.get("tool") or ""),
                    "running": False,
                    "note": note,
                }
                if args_preview:
                    fallback["args"] = args_preview
                if "ok" in event:
                    fallback["ok"] = bool(event.get("ok"))
                if event.get("apiCalls"):
                    fallback["apiCalls"] = event["apiCalls"]
                process_items.append(fallback)
            await session_store.append_message(
                session,
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
            # Effect 生成（c-agent-effects 收集＋c-agent-nav v2）：注册表声明了
            # effect_domain 且本步成功才触发（失败写不改数据，反馈＝假）。
            # navigate＝前端动作 → 即时事件紧随 step_end（中途翻页），不入
            # run_effects（不落库不进收尾汇总——历史回放不 teleport）；
            # refresh＝数据域刷新 → 维持 run_end 批量（写步常连发，批量省抖动）。
            tool_meta = get_tool(str(event.get("tool") or ""))
            if event.get("ok") and tool_meta is not None and tool_meta.effect_domain:
                action = str(getattr(tool_meta, "effect_action", "") or "refresh")
                effect: dict[str, Any] = {
                    "action": action,
                    "domain": tool_meta.effect_domain,
                    "description": str(event.get("resultNote", ""))[:120],
                }
                target_key = str(getattr(tool_meta, "effect_target_from", "") or "")
                if target_key and isinstance(event.get("args"), dict):
                    effect["target"] = str(event["args"].get(target_key) or "")
                if action == "navigate":
                    return [{"type": "effect", **effect}]
                run_effects.append(effect)
            return []
        if etype == "permission_required":
            await session_store.append_message(
                session,
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
                session,
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
        return []

    async def _finalize() -> None:
        """收尾落盘（openwriter INTERRUPTED 同款）：停止/断开/正常收口都把已达
        内容定稿——不留 streaming 悬行，也不丢半截。文件自持，断开照常落。"""
        full_reply = "\n".join(p for p in reply_parts if p)
        content = full_reply or pending_assistant.content
        if final_status == "done" and not content:
            content = "（停止时这一轮还没有产出文字。）"
        # 未收口的工具项标打断（停止/断连时步已开始但没拿到结果）——回看如实
        for item in process_items:
            if item.get("kind") == "tool" and item.get("running"):
                item["running"] = False
                item["interrupted"] = True
        # 断连/停止也补一条最终计划快照：残留 active 降级，避免重开会话
        # 看到「在做」却没有任何 run 在跑（正常收口已在 run_end 落过，去重）
        final_plan = _finalize_plan(
            loop.result.plan, failed=(final_status == "error")
        )
        if final_plan is not None and final_plan != loop.result.plan:
            await session_store.append_message(
                session,
                role="event",
                content="",
                page=page,
                payload={"plan": final_plan},
                card_kind="plan",
            )
        await session_store.update_message_status(
            pending_assistant,
            status=final_status,
            content=content,
            payload={"process": process_items} if process_items else None,
        )

    async def _drive() -> None:
        """自管消费任务（c-agent-harness 6.3 断连定诊）：循环消费＋落盘挪进独立
        task——断开时框架可能既不迭代也不关闭 SSE 生成器（starlette 1.9 实测
        streaming 悬行），消费挂 task 后由本任务自己的 finally 兜底定稿，任何
        出口（正常收口/被关停/被框架遗弃后跑完）都不丢尾。落盘走文件后端
        （c-agent-session-files）：自持文件路径，断开照常落。"""
        try:
            async for event in loop.run(message_for_model, prime=tool_hint):
                immediate = await _consume(event)
                # thinking 照发 SSE（dock 实时思考回看，run_end 时前端收进
                # run 气泡）；落盘分支不匹配 thinking——回看不存逐字思考
                # Effect 注入（c-agent-effects）：run_end 携带本轮写操作 effects
                if event.get("type") == "run_end" and run_effects:
                    event["effects"] = list(run_effects)
                await queue.put(event)
                for extra in immediate:
                    # 即时衍生事件（c-agent-nav navigate effect）：紧随本事件
                    # 按序下发——step_end（轨迹行）→ effect（页面翻）
                    await queue.put(extra)
            if loop.result.tokens_in or loop.result.tokens_out:
                await session_store.append_message(
                    session,
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
                await session_store.touch_session(session, page_cursor=page)
        except asyncio.CancelledError:
            raise  # 消费端取消＝正常收口路径，交 finally 落库
        except Exception:  # noqa: BLE001——drive 崩溃必须显式收口（2026-11-18 实锤：
            # _drive 静默死亡→_STOP 永不入队→SSE 永挂「进行中」卡死＋零遥测）
            _log.exception("assistant run drive crashed (session=%s)", session.id)
            try:
                await queue.put({"type": "error", "message": "这一轮处理出了问题，已产出的内容都保留着——重发即可继续。"})
            except Exception:  # noqa: BLE001——连 error 事件都发不出时仍要走 finally 收口
                pass
        finally:
            await queue.put(_STOP)  # 恒收口：任何出口消费端都见哨兵即退（body 出口）
            # 收尾落盘加盾（2026-11-17 竞态根修）：消费端收到 STOP 会立刻
            # cancel 本任务——取消正好落在 _finalize 的 await 上＝落盘被
            # 打断，streaming 行悬挂、下轮被自愈盖「中途被打断」。shield
            # +独立 task 让定稿在取消后仍独立完成。
            try:
                await asyncio.shield(asyncio.ensure_future(_finalize()))
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


@router.get("/capabilities")
async def assistant_capabilities(
    project_id: str,
    user: dict = Depends(get_current_user),
):
    """助手能力面（c-agent-dialog-prose）：前端按此切 chip 形态，env 熔断回退直开。

    ASSISTANT_PROSE_FLOW=off → dialog_prose=false（正文页「生成正文」回退直开路径，
    不进对话框编排）；缺省/其他值恒 true。轻端点：不查书（chip 形态判定与书无关）。
    """
    import os

    return {
        "dialog_prose": os.environ.get("ASSISTANT_PROSE_FLOW", "").strip().lower() != "off"
    }


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
        user_id=user["id"], novel_id=project.id, thread_key=thread
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
        user_id=user["id"], novel_id=project.id, thread_key=thread
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


    # /auth（c-agent-page-ops）：授权专用命令——即时切两层档位；裸 /auth 报当前档。
    # /mode 不承载授权（boss 拍板 2026-11-19：单独搞一个）；两层＝确认/自动
    # （allow_all 行为本等价 allow_book——存量值前端与命令侧都映射为自动档）。
    auth_names = {
        "confirm_each": "每写必确认（默认）",
        "allow_book": "自动执行·本书内",
    }
    if message == "/auth":
        grants_now = json.loads(session.grants_json or "{}")
        cur_raw = str(grants_now.get("tier") or "confirm_each")
        cur = "allow_book" if cur_raw == "allow_all" else cur_raw
        reply = (
            f"当前授权：{auth_names.get(cur, cur)}。"
            "切换：/auth 确认（每写必确认）｜/auth 自动（自动执行·本书内）。"
        )
        return StreamingResponse(
            _stream_command_reply(project, user, session, page, reply),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    if message.startswith("/auth "):
        arg = message.split(None, 1)[1].strip().lower()
        arg_map = {
            "confirm": "confirm_each", "each": "confirm_each", "confirm_each": "confirm_each",
            "确认": "confirm_each", "每写必确认": "confirm_each",
            "auto": "allow_book", "book": "allow_book", "allow_book": "allow_book",
            "自动": "allow_book", "自动执行": "allow_book",
        }
        if arg not in arg_map:
            reply = "没这个档位——/auth 确认（每写必确认）｜/auth 自动（自动执行·本书内）。"
            return StreamingResponse(
                _stream_command_reply(project, user, session, page, reply),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        tier = arg_map[arg]
        # 文件后端（c-agent-session-files）：本书全部会话文件的 grants 统一改写
        for meta_m in await session_store.iter_novel_sessions(project.id):
            if meta_m.user_id != user["id"]:
                continue
            g = json.loads(meta_m.grants_json or "{}")
            g["tier"] = tier
            await session_store.touch_session(meta_m, grants=g)
        reply = f"授权已切到「{auth_names[tier]}」——对这本书的所有页签生效。"
        return StreamingResponse(
            _stream_command_reply(project, user, session, page, reply),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    # 斜杠命令（coding agent 命令行习惯，boss 拍板 2026-11-15）：命令本身不进对话历史
    if message == "/new":
        # /new 对齐 coding agent：新开会话文件（旧文件留档）——session 重绑新文件
        session = await session_store.reset_session(session)
        return StreamingResponse(
            _stream_command_reply(
                project, user, session, page,
                "已开新对话——之前的内容都清掉了，想从哪儿说起？",
                clear=True,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    if message == "/compact":
        return StreamingResponse(
            await _stream_compact(project, user, session, page),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    body_focus = body.get("focus")
    if not isinstance(body_focus, dict):
        body_focus = None
    # 页面状态随行（c-agent-page-ops）：前端未保存标记上行，只进模型提示词
    body_page_state = body.get("page_state")
    page_unsaved = (
        [str(x) for x in body_page_state.get("unsaved", [])]
        if isinstance(body_page_state, dict) and isinstance(body_page_state.get("unsaved"), list)
        else []
    )
    # 屏上正文随行（c-agent-prose-checks）：只进 ToolContext（read_prose_checks 用），
    # 绝不进提示词；长度上限防御（正常一章几千字，超限视为异常丢弃）
    body_prose = body_page_state.get("prose_text") if isinstance(body_page_state, dict) else None
    page_prose = (
        body_prose.strip()
        if isinstance(body_prose, str) and len(body_prose) <= 50000
        else ""
    )
    user_row = await session_store.append_message(
        session,
        role="user",
        content=message,
        page=page,
    )

    tool_hint = body.get("tool_hint")
    if not (isinstance(tool_hint, dict) and isinstance(tool_hint.get("tool"), str) and tool_hint.get("tool").strip()):
        tool_hint = None
    # 按次模型覆盖对（c-agent-thinking-bubbles）：前端底栏选择才带；缺一半即交给
    # get_ai_client_for_novel 报「选择不完整」的可读错误。
    body_api_config_id = body.get("api_config_id")
    body_model = body.get("model")
    api_config_id = body_api_config_id.strip() if isinstance(body_api_config_id, str) else ""
    model = body_model.strip() if isinstance(body_model, str) else ""
    # 深度思考开关：显式按次覆盖 API 配置（缺省＝沿用配置）
    body_thinking = body.get("thinking")
    thinking_override: dict[str, Any] | None = None
    if isinstance(body_thinking, bool):
        thinking_override = {"type": "enabled" if body_thinking else "disabled"}
    return StreamingResponse(
        _stream_chat(
            db, project, user, session, message, page,
            user_message_id=user_row.id, body_focus=body_focus,
            page_unsaved=page_unsaved,
            page_prose=page_prose,
            thread=thread, tool_hint=tool_hint,
            api_config_id=api_config_id, model=model,
            thinking_override=thinking_override,
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
        user_id=user["id"], novel_id=project.id,
        thread_key=session_store.sanitize_thread_key(thread),
    )
    rows = await session_store.load_messages(session)
    # 上下文容量（coding agent 口径，boss 拍板 2026-11-15）：外发窗口估算 vs 窗口
    from assistant.compact import DEFAULT_CONTEXT_WINDOW

    _msgs, tokens_est = build_outbound_window(
        _history_transcript(rows),
        compaction_state=await session_store.load_compaction_state(session),
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
        user_id=user["id"], novel_id=project.id,
        thread_key=session_store.sanitize_thread_key(body.get("thread")),
    )
    await session_store.reset_session(session)
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
    if tier in ("allow_book", "allow_all") and not _is_max_member():
        raise HTTPException(
            403,
            detail={
                "reason": "feature_required",
                "feature": "assistant-diverge",
                "tier_required": "max",
                "message": "自动执行是 MAX 专属；升级后我就能在本书内放手干活。",
            },
        )
    # 授权档位书级语义（boss 拍板：切页签/线程不重置授权）——更新本书全部会话文件
    metas = [
        m
        for m in await session_store.iter_novel_sessions(project.id)
        if m.user_id == user["id"]
    ]
    for meta_m in metas:
        grants = json.loads(meta_m.grants_json or "{}")
        grants["tier"] = tier
        await session_store.touch_session(meta_m, grants=grants)
    if not metas:
        await session_store.get_or_create_session(
            user_id=user["id"], novel_id=project.id,
            thread_key=session_store.sanitize_thread_key(body.get("thread")),
        )
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
    target = await session_store.find_message(project.id, message_id)
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
    undo_meta = await session_store.meta_from_path(target.path)
    if undo_meta is not None:
        await session_store.append_message(
            undo_meta,
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
    # 跨线程找产物卡（卡可能在任意页签线程产生）——文件后端扫书目录
    target = await session_store.find_card_message(project.id, card_id)
    if target is None:
        raise HTTPException(404, "产物卡不存在或不属于本书会话。")
    if target.status != "adopted":
        await session_store.update_message_status(target, status="adopted")
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
