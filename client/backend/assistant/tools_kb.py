"""知识库工具（c-writing-agent 批B 余项：能力围栏承诺的 KB 读/写/改域）。

知识库＝作家自己的资产（拍板④围栏内的合法操作域）。读类（kb_search/kb_read）
登录即可；写/改（kb_create_entry/kb_update_entry）走 write_gate 授权梯度＋既有
闸门（kb update_entry 自带 GateResult＋乐观并发，校验链原样生效）。
"""

from __future__ import annotations

import json
from typing import Any

from assistant.tools import Tool, ToolContext, ToolResult, _clip, _jsonable

_KB_ITEM_BUDGET = 500


async def _kb_search(ctx: ToolContext, q: str = "", genre: str = "", concept: str = "") -> ToolResult:
    """按关键词/题材/概念检索知识库条目（只读）。"""
    from db import async_session
    from kb.router import _entry_dict
    from kb.service import list_entries

    async with async_session() as session:
        entries, _cursor = await list_entries(
            session,
            user_id=ctx.user_id,
            genre=str(genre or "").strip(),
            concept=str(concept or "").strip(),
            q=str(q or "").strip(),
            limit=10,
        )
    if not entries:
        return ToolResult(ok=True, summary="（知识库没有匹配的条目）")
    lines = []
    for e in entries:
        it = _entry_dict(e)
        lines.append(
            f"- [{it.get('genre')}/{it.get('concept')}] {it.get('title') or it.get('id')}"
            f"（{_clip(str(it.get('instruction') or ''), 120)}）"
        )
    return ToolResult(ok=True, summary=_clip("\n".join(lines), _KB_ITEM_BUDGET * 2))


async def _kb_read(ctx: ToolContext, entry_id: str) -> ToolResult:
    """读一条知识库条目全文。"""
    from db import async_session
    from kb.router import _entry_dict
    from kb.service import get_entry

    entry_id = str(entry_id or "").strip()
    async with async_session() as session:
        entry = await get_entry(session, user_id=ctx.user_id, entry_id=entry_id)
    if entry is None:
        return ToolResult(ok=False, summary=f"条目不存在：{entry_id}")
    data = _entry_dict(entry)
    return ToolResult(ok=True, summary=_clip(json.dumps(data, ensure_ascii=False, default=str), _KB_ITEM_BUDGET * 2))


async def _kb_create_entry(
    ctx: ToolContext,
    genre: str,
    concept: str,
    title: str,
    payload: dict[str, Any],
    instruction: str = "",
    example: str = "",
) -> ToolResult:
    """新建知识库条目（写类：write_gate 授权梯度；走既有 create_entry 校验链）。"""
    from db import async_session
    from kb.service import create_entry

    if not str(genre or "").strip() or not str(concept or "").strip():
        return ToolResult(ok=False, summary="genre 与 concept 必填（先 read_settings/kb_search 确认题材与概念归属）。")
    if not isinstance(payload, dict) or not payload:
        return ToolResult(ok=False, summary="payload 必须是非空对象（条目内容）。")
    async with async_session() as session:
        entry = await create_entry(
            session,
            user_id=ctx.user_id,
            genre=str(genre).strip(),
            concept=str(concept).strip(),
            title=str(title or "").strip(),
            payload=payload,
            instruction=str(instruction or ""),
            example=str(example or ""),
            src_kind="assistant",
            src_ref="c-writing-agent",
        )
    return ToolResult(
        ok=True,
        summary=f"已新建知识库条目（{genre}/{concept}）：{_clip(str(title) or str(entry.id), 60)}",
        meta={"write_log": {"entity": f"kb:{entry.id}", "fields": {"genre": genre, "concept": concept, "payload": payload}, "previous": None}},
    )


async def _kb_update_entry(ctx: ToolContext, entry_id: str, fields: dict[str, Any]) -> ToolResult:
    """改知识库条目（写类：授权梯度；既有闸门 GateResult＋乐观并发原样生效）。"""
    from db import async_session
    from kb.service import get_entry, update_entry

    entry_id = str(entry_id or "").strip()
    fields = fields or {}
    if not fields:
        return ToolResult(ok=False, summary="没有要改的字段。")
    allowed = ("title", "instruction", "payload", "example", "negative_example", "genre")
    bad = [k for k in fields if k not in allowed]
    if bad:
        return ToolResult(ok=False, summary=f"字段不在白名单：{bad}（可改：{list(allowed)}）")

    async with async_session() as session:
        from kb.router import _entry_dict

        entry = await get_entry(session, user_id=ctx.user_id, entry_id=entry_id)
        if entry is None:
            return ToolResult(ok=False, summary=f"条目不存在：{entry_id}")
        prev = _entry_dict(entry)
        previous = {k: prev.get(k) for k in fields}
        entry2, gate, _detail = await update_entry(
            session, user_id=ctx.user_id, entry_id=entry_id,
            **{k: fields[k] for k in fields},
        )
        if gate is not None and not getattr(gate, "ok", True):
            return ToolResult(ok=False, summary=f"闸门未通过：{getattr(gate, 'reasons', '') or '条目校验未过'}")
        if entry2 is None:
            return ToolResult(ok=False, summary="更新失败（并发冲突或条目已删）。")
    return ToolResult(
        ok=True,
        summary=f"已更新条目 {entry_id}：{'、'.join(fields)}",
        meta={
            "write_log": {
                "entity": f"kb:{entry_id}",
                "fields": fields,
                "previous": {k: _jsonable(v) for k, v in previous.items()},
            }
        },
    )


KB_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="kb_search",
        kind="read",
        args_hint='{"q": "关键词", "genre": "", "concept": ""}',
        description="检索作家的知识库条目（按关键词/题材/概念；只读）。",
        fn=_kb_search,
    ),
    Tool(
        name="kb_read",
        kind="read",
        args_hint='{"entry_id": "条目 id"}',
        description="读一条知识库条目全文（只读）。",
        fn=_kb_read,
    ),
    Tool(
        name="kb_create_entry",
        kind="write",
        feature_key="ai-plan",
        args_hint='{"genre": "题材", "concept": "概念", "title": "标题", "payload": {...}, "instruction": ""}',
        description="新建知识库条目（受作家授权梯度管控；写入后有回执可撤销）。",
        fn=_kb_create_entry,
    ),
    Tool(
        name="kb_update_entry",
        kind="write",
        feature_key="ai-plan",
        args_hint='{"entry_id": "条目 id", "fields": {"title": …, "instruction": …, "payload": {...}}}',
        description="改知识库条目（受作家授权梯度管控；既有闸门校验原样生效；写入后有回执可撤销）。",
        fn=_kb_update_entry,
    ),
)
