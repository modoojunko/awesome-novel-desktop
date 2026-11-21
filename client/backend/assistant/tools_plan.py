"""任务计划工具（c-agent-action-contract）。

会话内清单：只记录交付物与状态，不写书内数据、不吃授权梯度。计划快照随
ToolResult.meta 回给循环，循环发 `plan` 事件、路由层逐步落盘（role=event,
card_kind=plan）；应用重启按最近快照恢复。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from assistant.tools import Tool, ToolContext, ToolResult

PLAN_STATUSES = ("pending", "active", "done", "failed")
_STATUS_LABEL = {
    "pending": "还没动",
    "active": "在做",
    "done": "做完了",
    "failed": "没做成",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _counts(items: list[dict]) -> dict[str, int]:
    out = {s: 0 for s in PLAN_STATUSES}
    for it in items:
        st = str(it.get("status") or "pending")
        out[st if st in out else "pending"] += 1
    return out


def _plan_summary(plan: dict) -> str:
    items = plan.get("items") or []
    c = _counts(items)
    parts = [
        f"{_STATUS_LABEL[s]}{c[s]}"
        for s in PLAN_STATUSES
        if c[s]
    ]
    rows = "；".join(
        f"{i + 1}. {it.get('title', '')}·{_STATUS_LABEL.get(str(it.get('status')), '还没动')}"
        for i, it in enumerate(items)
    )
    return f"计划已更新：{len(items)} 件（{' / '.join(parts)}）——{rows}"


async def _update_plan(
    ctx: ToolContext,
    items: list | None = None,
    mode: str = "merge",
    note: str = "",
) -> ToolResult:
    """建立/更新会话内计划（merge 按 id/标题合并，replace 重开）。"""
    raw_items = items if isinstance(items, list) else []
    if not raw_items:
        return ToolResult(ok=False, summary="计划里至少要有一件事。")

    prev = ctx.scratch.get("plan") if isinstance(ctx.scratch.get("plan"), dict) else None
    if str(mode or "merge").strip() == "replace" or not prev:
        plan: dict = {"id": uuid.uuid4().hex[:12], "items": []}
    else:
        plan = {
            "id": str(prev.get("id") or uuid.uuid4().hex[:12]),
            "items": [dict(x) for x in (prev.get("items") or []) if isinstance(x, dict)],
        }

    by_id = {str(it.get("id")): it for it in plan["items"] if it.get("id")}
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        pid = str(raw.get("id") or "").strip()
        status = str(raw.get("status") or "pending").strip()
        if status not in PLAN_STATUSES:
            status = "pending"
        # 合并目标：先按 id；模型省略 id 时按标题兜底（避免同一条被拆成两行）
        target = by_id.get(pid) if pid else None
        if target is None:
            target = next(
                (it for it in plan["items"] if str(it.get("title")) == title), None
            )
        if target is not None:
            # merge 只改显式给出的字段——省略 status 不得把已做完打回还没动
            if raw.get("title") is not None:
                target["title"] = title
            if raw.get("status") is not None:
                target["status"] = status
            if pid:
                target["id"] = pid
                by_id[pid] = target
        else:
            item_id = pid or title
            it = {"id": item_id, "title": title, "status": status}
            plan["items"].append(it)
            by_id[item_id] = it

    if note:
        plan["note"] = str(note).strip()[:200]
    plan["updatedAt"] = _now()
    ctx.scratch["plan"] = plan
    return ToolResult(ok=True, summary=_plan_summary(plan), meta={"plan": plan})


PLAN_TOOLS = (
    Tool(
        name="update_plan",
        kind="read",
        risk_level="low",
        parameters={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "任务项列表（一件一行）",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "稳定 id（可省；缺省用标题）",
                            },
                            "title": {"type": "string", "description": "人话标题"},
                            "status": {
                                "type": "string",
                                "enum": list(PLAN_STATUSES),
                                "description": "pending 还没动 / active 在做 / done 做完 / failed 没做成",
                            },
                        },
                        "required": ["title"],
                    },
                },
                "mode": {
                    "type": "string",
                    "enum": ["merge", "replace"],
                    "description": "merge 更新已有项（缺省）；replace 重开计划",
                },
                "note": {"type": "string", "description": "给作家看的一句补充（可空）"},
            },
            "required": ["items"],
        },
        description=(
            "建立/更新这次要做的事（会话内清单，不写书、不需要授权）。"
            "作家一条消息里有两件以上独立交付物时先建计划，每完成一件更新状态，"
            "收口说清哪几件没做。单件事不要建计划。"
        ),
        fn=_update_plan,
    ),
)
