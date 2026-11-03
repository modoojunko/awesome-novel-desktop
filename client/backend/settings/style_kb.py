"""按题材从知识库取文风草稿（c-style-kb-fill）。

只读：不写任何 KV/表——文风面板右栏「按题材填文风」点开时调用，作家在弹窗里
挑选，采纳后由前端填进表单；真正落库仍走 PUT /settings/style。

取数口径（与知识库「默认库」一致）：
- 同账号用户条目：`concept ∈ 文风/文笔`、`status == active`、`genre ∈ (本书题材, 跨题材通用)`
- 官方基线（c-kb-baseline）：`kb.merged.load_baseline_entries` 取同题材料（已排 hide、
  已套 edit 副本），与用户条目合并
- 只取**基线**条目（`when_json` 为空）；挂场景/情绪/章位的条目留给写章写法块
- 同题材在前、跨题材通用在后；同组内用户条目在前、官方基线在后；文本去重

槽位映射复用 `kb.snapshot.build_members`（文风 role/sample、文笔 rule/craft/
banned_word/tic）。`tone/pov/register` 没有书内落点：只在缺「叙事身份」时用它们
各取第一条拼一句兜底。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kb.merged import load_baseline_entries
from kb.snapshot import build_members, slot_target
from models.kb import KbEntry

STYLE_CONCEPTS = ("文风", "文笔")
# 展示上限（弹窗内由作者自己挑；上限只防极端库把弹窗撑爆）
_MAX_RULES = 20
_MAX_CRAFT = 20
_MAX_SAMPLES = 6
_MAX_BANNED = 100
_MAX_TICS = 20
# 与 settings.style_model._VALUE_MAX 同口径：表单里能看全，保存时不静默截断
_ROLE_MAX = 500
_ROLE_FALLBACK_SLOTS = ("tone", "pov", "register")
# 槽位 → payload 里的结构化文本键。banned/tic 存的是词与正则，不是可自由改写的正文：
# 覆盖编辑（instruction 一段散文）SHALL NOT 顶替它们。
_SLOT_TEXT_KEYS: dict[str, tuple[str, ...]] = {
    "role": ("role",),
    "sample": ("sample",),
    "rule": ("rule",),
    "craft": ("craft",),
    "banned_word": ("banned",),
    "tic": ("tic_pattern",),
}
# 可以用 instruction（作者覆盖副本）当正文的落点；其余落点保留结构化值
_TEXT_OVERRIDE_TARGETS = frozenset({"role", "rules", "craft", "style_samples"})


def _payload_of(e: KbEntry) -> dict[str, Any]:
    try:
        p = json.loads(e.payload_json or "{}")
    except ValueError:
        return {}
    return p if isinstance(p, dict) else {}


def _when_of(e: KbEntry) -> dict[str, Any]:
    try:
        w = json.loads(e.when_json or "{}")
    except ValueError:
        return {}
    return w if isinstance(w, dict) else {}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        x = str(x).strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


async def style_draft_from_kb(
    db: AsyncSession, *, user_id: str, theme: str
) -> dict[str, Any]:
    """题材 → 文风草稿。无题材/无条目时返回空数组（不抛错）。"""
    theme = (theme or "").strip()
    empty = {
        "theme": theme,
        "role": "",
        "rules": [],
        "craft": [],
        "banned_words": [],
        "tic_patterns": [],
        "style_samples": [],
        "counts": {
            "role": 0,
            "rules": 0,
            "craft": 0,
            "banned_words": 0,
            "tic_patterns": 0,
            "style_samples": 0,
            "total": 0,
        },
    }
    if not theme:
        return empty

    user_rows = (
        (
            await db.execute(
                select(KbEntry)
                .where(
                    KbEntry.user_id == user_id,
                    KbEntry.status == "active",
                    KbEntry.concept.in_(STYLE_CONCEPTS),
                    KbEntry.genre.in_((theme, "")),
                )
                .order_by(KbEntry.created_at, KbEntry.id)
            )
        )
        .scalars()
        .all()
    )
    # 官方基线（c-kb-baseline）：只读 lower 层经 merged 视图取（已排 hide、已套 edit 副本）。
    # 与用户条目同口径：同题材 + 跨题材通用。
    baseline_rows: list[Any] = []
    for concept in STYLE_CONCEPTS:
        baseline_rows.extend(
            await load_baseline_entries(
                db,
                user_id=user_id,
                genre=theme,
                concept=concept,
                match_generic=True,
                limit=200,
            )
        )
    # 基线只取无场景条件的行（场景条留给写章写法块）；用户条目同判
    rows = [*user_rows, *baseline_rows]
    entries = [e for e in rows if not _when_of(e)]
    # 同题材在前；两段内用户条目在前、基线在后（sorted 稳定，语义明确）
    entries.sort(key=lambda e: 0 if e.genre == theme else 1)
    if not entries:
        return empty

    members = build_members(entries)
    # merged 语义：官方基线被作者编辑过时，覆盖文本只在 instruction（payload_json 仍是
    # 原件）——文本型落点改用 instruction；payload 缺文本而槽位仍有落点的（不同包形状）
    # 用 payload 字段/value 兜底补成员。结构化落点（禁用词/句式正则）始终保留原值：
    # 覆盖编辑的 instruction 是一段散文，顶替进去会把词表/正则弄坏。
    covered = {m["entry_id"]: m for m in members}
    for e in entries:
        overlaid = bool(getattr(e, "overlaid", False))
        instruction = str(getattr(e, "instruction", "") or "").strip()
        if e.id in covered:
            member = covered[e.id]
            if overlaid and instruction and member["target"] in _TEXT_OVERRIDE_TARGETS:
                member["text"] = instruction
            continue
        payload = _payload_of(e)
        slot = str(payload.get("slot") or "")
        target = slot_target(e.concept, slot)
        if not target:
            continue
        structured = next(
            (
                str(payload[k]).strip()
                for k in _SLOT_TEXT_KEYS.get(slot, ())
                if str(payload.get(k) or "").strip()
            ),
            "",
        )
        value = str(payload.get("value") or "").strip()
        if target in _TEXT_OVERRIDE_TARGETS:
            text = (instruction if overlaid else "") or structured or value or instruction
        else:
            text = structured or value
        if not text:
            continue
        members.append(
            {
                "entry_id": e.id,
                "title": e.title,
                "concept": e.concept,
                "slot": slot,
                "part": "",
                "target": target,
                "text": text,
                "severity": str(payload.get("tic_severity") or ""),
            }
        )
    # 兜底补的成员会 append 到队尾；按原 entries 顺序重排，保住「同题材在前、
    # 同组内用户条目在基线前」——role 取第一条时不能跨组抢位。
    order = {e.id: i for i, e in enumerate(entries)}
    members.sort(key=lambda m: order.get(m["entry_id"], len(entries)))

    role = ""
    for m in members:
        if m["target"] == "role":
            role = m["text"]
            break
    if not role:
        # 兜底：tone / pov / register 各取第一条，按固定槽位序拼一句
        picked: dict[str, str] = {}
        for e in entries:
            if e.concept != "文风":
                continue
            payload = _payload_of(e)
            slot = str(payload.get("slot") or "")
            if slot in _ROLE_FALLBACK_SLOTS and slot not in picked:
                if getattr(e, "overlaid", False):
                    text = str(getattr(e, "instruction", "") or "").strip()
                else:
                    text = str(payload.get("text") or payload.get("value") or "").strip()
                if text:
                    picked[slot] = text
        role = "；".join(picked[s] for s in _ROLE_FALLBACK_SLOTS if s in picked)
    role = role[:_ROLE_MAX]

    rules = _dedupe([m["text"] for m in members if m["target"] == "rules"])[:_MAX_RULES]
    craft = _dedupe([m["text"] for m in members if m["target"] == "craft"])[:_MAX_CRAFT]
    banned = _dedupe([m["text"] for m in members if m["target"] == "banned_words"])[:_MAX_BANNED]
    samples = _dedupe([m["text"] for m in members if m["target"] == "style_samples"])[:_MAX_SAMPLES]

    tics: list[dict[str, Any]] = []
    seen_patterns: set[str] = set()
    for m in members:
        if m["target"] != "tic_patterns":
            continue
        pattern = m["text"]
        if pattern in seen_patterns:
            continue
        seen_patterns.add(pattern)
        severity = m.get("severity") or "medium"
        if severity not in ("high", "medium", "low"):
            severity = "medium"
        tics.append(
            {
                "pattern": pattern,
                "name": m.get("title") or "",
                "threshold": 3,
                "severity": severity,
                "description": "",
            }
        )
        if len(tics) >= _MAX_TICS:
            break

    counts = {
        "role": 1 if role else 0,
        "rules": len(rules),
        "craft": len(craft),
        "banned_words": len(banned),
        "tic_patterns": len(tics),
        "style_samples": len(samples),
    }
    counts["total"] = sum(counts.values())
    return {
        "theme": theme,
        "role": role,
        "rules": rules,
        "craft": craft,
        "banned_words": banned,
        "tic_patterns": tics,
        "style_samples": samples,
        "counts": counts,
    }
