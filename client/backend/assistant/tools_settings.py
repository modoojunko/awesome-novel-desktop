"""设定字段 AI 工具（c-writing-agent 收编：设定卡 16 行 AI 能力进 agent）。

boss 拍板 2026-11-15：调用架构改走 agent——agent 识别任务→分派给大模型→调
后端接口→产物卡回对话过目。本组工具包装 settings/ai_router 的生成核：
  - settings_genre_m1~m4：题材四问（主要看什么/绝对禁止/吃苦指数/本小说斗什么）
  - settings_intro / settings_world / settings_style：简介/世界/文风生成核
  - settings_hooks：伏笔起草/埋坑体检/查一致性
产物一律只产卡（kind="text"），作家过目后自行写回对应设置项——工具不直接
写设定（写回走前端采纳或作家手填，零新写回路径）。

字段错位判例（2026-11-15）：包装工具返回摘要必须对照数据源真实键名逐字段核。
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from assistant.tools import Tool, ToolContext, ToolResult
from db import async_session
from novels.service import get_novel
from settings.ai_router import generate_field


def _clip(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    return text[: budget - 1] + "…"


async def _project_ok(ctx: ToolContext) -> bool:
    async with async_session() as db:
        project = await get_novel(db, ctx.novel_id, ctx.user_id)
        return project is not None


async def _settings_field(
    ctx: ToolContext,
    stype: str,
    field: str,
    summary_head: str,
) -> ToolResult:
    """万能量：单字段生成核（generate_field 直调——与 HTTP 端点同核同提示词）。"""
    if not await _project_ok(ctx):
        return ToolResult(ok=False, summary="书不存在或不属于当前作家。")
    async with async_session() as db:
        body = {"context": {}}
        try:
            result = await generate_field(
                ctx.novel_id, stype, field, body,
                {"id": ctx.user_id}, True, True, db,
            )
        except HTTPException as e:
            return ToolResult(ok=False, summary=str(e.detail))
    value = result.get("value")
    payload = {"stype": stype, "field": field, "value": value}
    head_text = (
        value.get("value") if isinstance(value, dict) and value.get("value") else str(value)
    )
    return ToolResult(
        ok=True,
        summary=f"{summary_head} 候选已出：{_clip(head_text, 400)}（过目后填回对应设置项）",
        card={"kind": "text", "payload": payload},
    )


async def _settings_intro(ctx: ToolContext, action: str) -> ToolResult:
    """简介 AI 核（/ai/intro/{action} 的 run_intro_ai_action 直调）。"""
    if not await _project_ok(ctx):
        return ToolResult(ok=False, summary="书不存在或不属于当前作家。")
    from settings.ai_router import intro_ai

    async with async_session() as db:
        try:
            result = await intro_ai(
                ctx.novel_id, action, {},
                {"id": ctx.user_id}, True, True, db,
            )
        except HTTPException as e:
            return ToolResult(ok=False, summary=str(e.detail))
    head = "简介体检完成" if action == "check" else "简介候选已出"
    payload = {"action": action, "result": result}
    return ToolResult(
        ok=True,
        summary=f"{head}：{_clip(str(result)[:400])}（过目后填回简介栏）",
        card={"kind": "text", "payload": payload},
    )


def _make_hooks_tool(action: str, desc: str) -> Tool:
    async def _fn(ctx: ToolContext) -> ToolResult:
        if not await _project_ok(ctx):
            return ToolResult(ok=False, summary="书不存在或不属于当前作家。")
        from settings.ai_router import run_hooks_ai

        async with async_session() as db:
            try:
                result = await run_hooks_ai(
                    action, {},
                    {"id": ctx.user_id}, True, True, db,
                )
            except HTTPException as e:
                return ToolResult(ok=False, summary=str(e.detail))
        return ToolResult(
            ok=True,
            summary=f"伏笔 AI（{action}）完成：{_clip(str(result)[:300])}（过目后填回伏笔面板）",
            card={"kind": "text", "payload": result},
        )

    return Tool(
        name=f"settings_hooks_{action}",
        kind="card",
        feature_key="settings-ai-fields",
        args_hint="{}",
        description=desc,
        fn=_fn,
    )


# 题材四问（generate_field 直调；genre field 白名单见 _GENRE_PROMPTS）
def _make_genre_tool(field: str, desc: str) -> Tool:
    async def _fn(ctx: ToolContext) -> ToolResult:
        return await _settings_field(
            ctx, "genre", field, desc.split("：")[0].replace("题材·", "")
        )

    return Tool(
        name=f"settings_genre_{field}",
        kind="card",
        feature_key="settings-ai-fields",
        args_hint="{}",
        description=desc,
        fn=_fn,
    )




# ── 章纲补全缺失（#5 样板：agent 识别→直调 fill-gaps 核→产物卡）──────────────

_FILLABLE = ("summary", "characters", "changes", "prohibitions", "mood")
_GAP_LABELS = {
    "summary": "一句话概要",
    "characters": "出场角色",
    "changes": "必须完成的变化",
    "prohibitions": "必须维持悬念",
    "mood": "阶段",
}


async def _settings_og_fill(ctx: ToolContext, chapter_ref: str) -> ToolResult:
    """补全章纲缺失字段（openwriter fill-gaps 核直调；产物不落库，作家过目后
    在章纲表单采纳——写回走前端既有保存链）。"""
    if not await _project_ok(ctx):
        return ToolResult(ok=False, summary="书不存在或不属于当前作家。")
    from chapters.ai_draft import fill_outline_gaps, _FILLABLE_KEYS

    async with async_session() as db:
        body = {"missing": list(_FILLABLE_KEYS)}
        try:
            result = await fill_outline_gaps(
                ctx.novel_id, chapter_ref, body,
                {"id": ctx.user_id}, True, True, db,
            )
        except HTTPException as e:
            return ToolResult(ok=False, summary=str(e.detail))
    fills = result.get("fills") or {}
    if not fills:
        return ToolResult(ok=True, summary=f"{chapter_ref} 章纲五项齐全，没有要补的。")
    lines = [f"{_GAP_LABELS.get(k, k)}：{_clip(str(v), 160)}" for k, v in fills.items()]
    return ToolResult(
        ok=True,
        summary=f"{chapter_ref} 补了 {len(fills)} 项：{_clip('；'.join(lines), 400)}（过目后在章纲表单采纳）",
        card={"kind": "text", "payload": {"chapter_ref": chapter_ref, "fills": fills}},
    )


def _make_og_fill_tool() -> Tool:
    async def _fn(ctx: ToolContext, chapter_ref: str = "") -> ToolResult:
        # 章锚：作家给章 ref 就用；没给则用聚焦对象/当前 frontier
        from chapters.frontier import frontier_info
        from db import async_session

        ref = (chapter_ref or "").strip() or (ctx.focus_ref or "").strip()
        if not ref:
            async with async_session() as db:
                info = await frontier_info(db, ctx.novel_id)
            fr = info.get("frontier") or {}
            ref = str(fr.get("ref") or "")
        if not ref:
            return ToolResult(ok=False, summary="定位不到章——给我章号或章名。")
        return await _settings_og_fill(ctx, ref)

    return Tool(
        name="settings_og_fill",
        kind="card",
        feature_key="settings-ai-fields",
        args_hint='{"chapter_ref": "vol-1-ch-7（可空＝当前章）"}',
        description="章纲补全缺失：查本章章纲五项（概要/角色/变化/悬念/阶段）缺什么，AI 补候选（不落库，过目后采纳）",
        fn=_fn,
        risk_level="low",
    )


OG_FILL_TOOL = _make_og_fill_tool()
SETTINGS_FIELD_TOOLS: tuple[Tool, ...] = (
    OG_FILL_TOOL,
    _make_genre_tool("core_promise", "题材·主要看什么：给几个核心看点候选（勾选采纳）"),
    _make_genre_tool("forbidden_list", "题材·绝对禁止：这本书绝不出现什么（红线清单候选）"),
    _make_genre_tool("cost_ratio", "题材·吃苦指数：主角得到好处要付多大代价（代价配比建议）"),
    _make_genre_tool("battlefield", "题材·本小说斗什么：全书主要斗的是什么（对抗物候选）"),
    _make_hooks_tool("draft", "伏笔·起草：按简介＋题材＋世界＋主线给 3 条候选，配收束章"),
    _make_hooks_tool("check", "伏笔·埋坑体检：扫活跃伏笔×已写章纲，埋了没还的点名"),
    Tool(
        name="settings_intro",
        kind="card",
        feature_key="settings-ai-fields",
        args_hint='{"action": "draft|check"}',
        description="简介 AI：draft 按三问起草候选；check 体检简介是否只有设定没钩子",
        fn=_settings_intro,
    ),
)
