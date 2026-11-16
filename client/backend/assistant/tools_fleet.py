"""章内三面板收编工具（c-agent-fleet：推演/抽卡/盘点走 agent 对话）。

核直调同仓实现（write/plot_sim.plot_simulate／chapters/ai_cast.cast_ai_draw/
cast_ai_review）——Depends 占位按位传（tools_settings 同款）。产物一律人话
draft 卡（禁裸 JSON 上对话——boss 红线「对话框不要出现程序文案」）。
"""

from __future__ import annotations


from assistant.tools import Tool, ToolContext, ToolResult

# ── 章内三面板收编（c-agent-fleet：推演/抽卡/盘点走 agent 对话——boss 拍板
#    「调用架构要走 agent」；核直调同仓实现，Depends 占位按位传）─────────────


async def _resolve_chapter_ref(ctx: ToolContext, chapter_ref: str) -> str:
    """章锚三回落：显式 ref > 聚焦对象 > frontier（settings_og_fill 同款）。"""
    from chapters.frontier import frontier_info
    from db import async_session

    ref = (chapter_ref or "").strip() or (ctx.focus_ref or "").strip()
    if not ref:
        async with async_session() as db:
            info = await frontier_info(db, ctx.novel_id)
        fr = info.get("frontier") or {}
        ref = str(fr.get("ref") or "")
    return ref


def _fmt_draw(result: dict) -> str:
    """抽卡核结果→人话（卡×N：名/轴/差事/人设/进出场/合不合适/评级）。"""
    lines: list[str] = []
    for i, c in enumerate(result.get("cards") or [], 1):
        if not isinstance(c, dict):
            continue
        lines.append(f"卡{i} · {c.get('name') or '无名'}（{c.get('axis') or ''}）")
        for k, lab in (("duty", "差事"), ("persona", "人设"), ("entrance", "进场"), ("exit_note", "退场")):
            v = str(c.get(k) or "").strip()
            if v:
                lines.append(f"{lab}：{v}")
        reasons = c.get("reasons")
        good = str((reasons or {}).get("合不合适") or "").strip() if isinstance(reasons, dict) else ""
        if good:
            lines.append(f"合不合适：{good}")
        grade = str(c.get("grade") or "").strip()
        if grade:
            lines.append(f"评级：{grade}")
        lines.append("")
    note = str(result.get("note") or "").strip()
    if note:
        lines.append(f"备注：{note}")
    return "\n".join(lines).strip() or "（这抽没出卡——再抽一次试试。）"


def _fmt_review(result: dict) -> str:
    """盘点核结果→人话（逐段：原文摘｜判定｜人选｜演什么｜为什么＋建卡提示）。"""
    lines: list[str] = []
    for r in result.get("rows") or []:
        if not isinstance(r, dict):
            continue
        parts = [str(r.get("verdict") or "")]
        echo = str(r.get("echo") or "").strip()
        if echo:
            parts.append(f"段落：{echo[:40]}")
        who = "、".join(r.get("who") or [])
        if who:
            parts.append(f"人选：{who}")
        as_ = str(r.get("as") or "").strip()
        if as_:
            parts.append(f"演什么：{as_}")
        why = str(r.get("why") or "").strip()
        if why:
            parts.append(f"为什么：{why}")
        lines.append("｜".join(p for p in parts if p))
    for h in result.get("hints") or []:
        if isinstance(h, dict) and h.get("text"):
            lines.append(f"提示：{h['text']}")
    return "\n".join(lines).strip() or "（这一段没有需要新增或调整的角色——零新增是常态。）"


def _fmt_simulate(result: dict) -> str:
    """推演核结果→人话（进出场＋逐拍：拍点｜谁｜地点｜走向）。"""
    lines: list[str] = []
    entry = str(result.get("entry") or "").strip()
    exit_ = str(result.get("exit") or "").strip()
    if entry:
        lines.append(f"进场：{entry}")
    if exit_:
        lines.append(f"退场：{exit_}")
    for r in result.get("rounds") or []:
        if not isinstance(r, dict):
            continue
        seg = " → ".join(
            str(r.get(k) or "").strip() for k in ("beat", "who", "place") if str(r.get(k) or "").strip()
        )
        if seg:
            lines.append(f"- {seg}")
        moves = str(r.get("moves") or "").strip()
        if moves:
            lines.append(f"  {moves}")
    return "\n".join(lines).strip() or "（推演没出内容——再试一次。）"


async def _simulate_plot(ctx: ToolContext, chapter_ref: str = "") -> ToolResult:
    from assistant.tools_settings import _project_ok

    if not await _project_ok(ctx):
        return ToolResult(ok=False, summary="书不存在或不属于当前作家。")
    ref = await _resolve_chapter_ref(ctx, chapter_ref)
    if not ref:
        return ToolResult(ok=False, summary="定位不到章——给我章号或章名。")
    from assistant.caps.chapter import CapabilityError, simulate_chapter

    try:
        result = await simulate_chapter(ctx.novel_id, ref, ctx.user_id)
    except CapabilityError as e:
        return ToolResult(ok=False, summary=e.message)
    return ToolResult(
        ok=True,
        summary="剧情推演完成：进出场＋逐拍走向都出来了（推演是参考，采纳你说了算）。",
        card={"kind": "text", "payload": {"action": "simulate", "chapter_ref": ref, "draft": _fmt_simulate(result)}},
    )


async def _draw_plot_cards(ctx: ToolContext, extra: str = "") -> ToolResult:
    from assistant.tools_settings import _project_ok

    if not await _project_ok(ctx):
        return ToolResult(ok=False, summary="书不存在或不属于当前作家。")
    ref = await _resolve_chapter_ref(ctx, "")
    if not ref:
        return ToolResult(ok=False, summary="定位不到章——给我章号或章名。")
    from assistant.caps.chapter import CapabilityError, draw_plot_proposals

    # 重抽排除：本 run 内上次抽出的卡名进 exclude——同章纲再抽不再复读同一批
    prev_names = [str(n) for n in (ctx.scratch.get("draw_names") or [])]
    try:
        result = await draw_plot_proposals(
            ctx.novel_id, ref, ctx.user_id,
            exclude_names=prev_names, extra=str(extra or "")[:200],
        )
    except CapabilityError as e:
        return ToolResult(ok=False, summary=e.message)
    drawn = [str((c or {}).get("name") or "") for c in (result.get("cards") or []) if isinstance(c, dict)]
    if drawn:
        ctx.scratch["draw_names"] = (prev_names + drawn)[-9:]
    return ToolResult(
        ok=True,
        summary=(
            f"三张提案卡已抽并在上面产物卡里交付（互斥、照章纲门槛出）。"
            f"本轮抽卡完成——直接给作家讲卡面收口；{('作家明示「再抽」才会重抽，重抽会避开：' + '、'.join(prev_names)) if prev_names else '作家明示「再抽」才重抽'}。"
        ),
        card={"kind": "text", "payload": {"action": "draw", "chapter_ref": ref, "draft": _fmt_draw(result)}},
    )


async def _review_cast(ctx: ToolContext) -> ToolResult:
    from assistant.tools_settings import _project_ok

    if not await _project_ok(ctx):
        return ToolResult(ok=False, summary="书不存在或不属于当前作家。")
    ref = await _resolve_chapter_ref(ctx, "")
    if not ref:
        return ToolResult(ok=False, summary="定位不到章——给我章号或章名。")
    from assistant.caps.chapter import CapabilityError, review_chapter_cast

    try:
        result = await review_chapter_cast(ctx.novel_id, ref, ctx.user_id)
    except CapabilityError as e:
        return ToolResult(ok=False, summary=e.message)
    return ToolResult(
        ok=True,
        summary="人物盘点完成：逐段对照章纲与正文，只读不落库（零新增是常态输出）。",
        card={"kind": "text", "payload": {"action": "review", "chapter_ref": ref, "draft": _fmt_review(result)}},
    )


def _make_fleet_tools() -> tuple[Tool, ...]:
    return (
        Tool(
            name="simulate_plot",
            kind="card",
            feature_key="ai-plot",
            parameters={
                "type": "object",
                "properties": {
                    "chapter_ref": {"type": "string", "description": "章 ref（可空＝聚焦章）"},
                },
            },
            description="剧情推演：按本章章纲与已写内容推演后续走向（不落库，过目采纳）。",
            fn=_simulate_plot,
        ),
        Tool(
            name="draw_plot_cards",
            kind="card",
            feature_key="ai-plan",
            parameters={
                "type": "object",
                "properties": {
                    "extra": {"type": "string", "description": "想偏重的方向或补充要求（可空）"},
                },
            },
            description="剧情抽卡：一次抽 3 张互斥剧情提案卡（不落库）。抽完即收口——仅当作家明示「再抽」时才再调一次。",
            fn=_draw_plot_cards,
        ),
        Tool(
            name="review_cast",
            kind="card",
            feature_key="ai-plan",
            parameters={"type": "object", "properties": {}},
            description="人物盘点：逐段对照章纲与正文盘点出场角色（只读报告；零新增是常态输出）。",
            fn=_review_cast,
        ),
    )


FLEET_TOOLS: tuple[Tool, ...] = _make_fleet_tools()

