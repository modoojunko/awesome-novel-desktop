"""merged 视图（c-kb-baseline 批B）——基线只读层 ∪ 用户自有条目。

消费面（写法块选择器 / 知识库页）SHALL 走这里取数，不改 kb_entries 表：
- 基线层：kb_baseline_entries（uuid5 代理主键）− 用户 hide 白名单 ＋ 用户 edit 副本
  （写时复制：副本以 overlay.content 遮蔽原件文本，原件行永不改）。
- 用户条目：kb_entries 原样（该表零改动，src_kind SHALL NOT 落 "baseline"）。
- 基线行在 API/选择器里以 `MergedEntry` 呈现：属性面与 KbKnowledge 读口径一致
  （id/genre/concept/concept_id/title/instruction/when_json/payload_json/updated_at），
  并带 layer="baseline"、src_kind="baseline"（**随层派生，不落库**）、src_key。
- 设备级数据：基线层不按账号分行，hide/edit 才是账号级（overlays）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.kb import KbBaselineEntry, KbBaselineOverlay

# 文风 slot 白名单（进块的定性槽位；match.digest_candidates 与本模块单源）
STYLE_SLOTS_IN_BLOCK = ("tone", "register", "sample")


@dataclass(slots=True)
class MergedEntry:
    """基线条目的只读呈现（属性面照 KbKnowledge，前端/选择器零分支）。"""

    id: str
    user_id: str
    genre: str
    concept: str
    concept_id: str
    title: str
    instruction: str
    when_json: str = "{}"
    payload_json: str = "{}"
    example: str = ""
    negative_example: str = ""
    evidence: str = ""
    evidence_json: str = "{}"
    # v2 条目级字段（c-knowledge-source-align：基线投影知识对象形状）
    evidence_ch: str = ""
    confidence: str = ""
    kind: str = ""
    node_key: str = ""
    status: str = "active"
    rev: int = 1
    src_kind: str = "baseline"
    src_ref: str = ""
    src_key: str = ""
    src_novel_name: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    payload_version: int = 1
    # 层与覆盖（不进提示词，只做 API/操作面判定）
    layer: str = "baseline"
    pack_version: int = 0
    content_sha256: str = ""          # 当前原件指纹
    base_content_sha256: str = ""     # edit 副本记录的「当时原件」指纹
    overlaid: bool = False            # 该行文本来自用户副本
    hidden: bool = False              # 被用户隐藏（只出现在「已隐藏」列表）


def has_official_update(e: MergedEntry) -> bool:
    """双哈希「官方有新版」：仅 edit 副本且原件已修订时为真（零写放大）。"""
    return bool(
        e.overlaid and e.base_content_sha256 and e.base_content_sha256 != e.content_sha256
    )


def _to_merged(
    row: KbBaselineEntry,
    *,
    user_id: str,
    overlay: KbBaselineOverlay | None,
    hidden: bool = False,
) -> MergedEntry:
    text = row.instruction or ""
    overlaid = False
    base_sha = ""
    if overlay is not None and overlay.action == "edit":
        if (overlay.content or "").strip():
            text = overlay.content.strip()
            overlaid = True
        base_sha = overlay.base_content_sha256 or ""
    # v2 条目级字段投影（c-knowledge-source-align）：基线表新列优先，
    # 无列历史行回落 payload_json 内同义键（向前兼容 v2 包）
    _payload_text = row.payload_json or "{}"
    try:
        _pj = json.loads(_payload_text) if isinstance(_payload_text, str) else {}
    except ValueError:
        _pj = {}
    if not isinstance(_pj, dict):
        _pj = {}
    example = (getattr(row, "example", "") or "") or str(_pj.get("example") or "")
    evidence_ch = (getattr(row, "evidence_ch", "") or "") or str(_pj.get("evidence_ch") or "")
    confidence = (getattr(row, "confidence", "") or "") or str(_pj.get("confidence") or "")
    kind = (getattr(row, "kind", "") or "") or str(_pj.get("kind") or "")
    node_key = (getattr(row, "node_key", "") or "") or str(_pj.get("node_key") or "")
    return MergedEntry(
        id=row.entry_id,
        user_id=user_id,
        genre=row.genre or "",
        concept=row.concept or "",
        concept_id=f"{row.genre}:{row.concept}",
        title=row.title or "",
        instruction=text,
        when_json=row.when_json or "{}",
        payload_json=row.payload_json or "{}",
        example=example,
        evidence=evidence_ch,
        confidence=confidence,
        kind=kind,
        node_key=node_key,
        created_at=row.published_at,
        updated_at=row.published_at,
        src_key=row.src_key,
        pack_version=row.pack_version,
        content_sha256=row.content_sha256 or "",
        base_content_sha256=base_sha,
        overlaid=overlaid,
        hidden=hidden,
    )


def _hidden_clause(user_id: str):
    """SQL 层排 hide 白名单——分页/计数在库侧过滤，避免隐藏行占页位。"""
    return ~exists().where(
        and_(
            KbBaselineOverlay.user_id == user_id,
            KbBaselineOverlay.src_key == KbBaselineEntry.src_key,
            KbBaselineOverlay.action == "hide",
        )
    )


async def _overlays_for(
    db: AsyncSession, *, user_id: str, src_keys: list[str]
) -> dict[str, KbBaselineOverlay]:
    if not src_keys:
        return {}
    rows = (
        await db.execute(
            select(KbBaselineOverlay).where(
                KbBaselineOverlay.user_id == user_id,
                KbBaselineOverlay.src_key.in_(src_keys),
            )
        )
    ).scalars().all()
    return {r.src_key: r for r in rows}


async def load_baseline_entries(
    db: AsyncSession,
    *,
    user_id: str,
    genre: str = "",
    concept: str = "",
    q: str = "",
    ids: list[str] | None = None,
    cursor: str = "",
    limit: int | None = None,
    match_generic: bool = False,
) -> list[MergedEntry]:
    """基线层分页/按 id 取行（已排 hide、已套 edit 副本）。

    genre="" 表示不过滤；match_generic=True 时把跨题材通用（""）一并纳入
    （写法块选择器口径）；浏览页按题栏计数取精确匹配（与用户条目同口径）。
    """
    stmt = select(KbBaselineEntry).where(_hidden_clause(user_id))
    if ids is not None:
        if not ids:
            return []
        stmt = stmt.where(KbBaselineEntry.entry_id.in_(ids))
    if genre:
        stmt = stmt.where(
            KbBaselineEntry.genre.in_((genre, "")) if match_generic
            else KbBaselineEntry.genre == genre
        )
    if concept:
        stmt = stmt.where(KbBaselineEntry.concept == concept)
    if q:
        stmt = stmt.where(
            or_(
                KbBaselineEntry.title.contains(q),
                KbBaselineEntry.instruction.contains(q),
            )
        )
    if cursor:
        stmt = stmt.where(KbBaselineEntry.entry_id > cursor)
    stmt = stmt.order_by(KbBaselineEntry.entry_id)
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return []
    overlays = await _overlays_for(db, user_id=user_id, src_keys=[r.src_key for r in rows])
    return [_to_merged(r, user_id=user_id, overlay=overlays.get(r.src_key)) for r in rows]


async def get_merged_entry(
    db: AsyncSession, *, user_id: str, entry_id: str
) -> MergedEntry | None:
    """按代理 id 回读一条基线行（含 hide 排除 / edit 副本）。"""
    rows = await load_baseline_entries(db, user_id=user_id, ids=[entry_id], limit=1)
    return rows[0] if rows else None


async def baseline_genre_counts(
    db: AsyncSession, *, user_id: str
) -> dict[str, int]:
    """题材栏计数（基线段，已排 hide）——与用户段计数相加即 merged 口径。"""
    from sqlalchemy import func

    rows = (
        await db.execute(
            select(KbBaselineEntry.genre, func.count(KbBaselineEntry.entry_id))
            .where(_hidden_clause(user_id))
            .group_by(KbBaselineEntry.genre)
        )
    ).all()
    return {r[0]: r[1] for r in rows}


async def load_hidden_entries(
    db: AsyncSession,
    *,
    user_id: str,
    genre: str = "",
    concept: str = "",
    q: str = "",
    cursor: str = "",
    limit: int | None = None,
) -> list[MergedEntry]:
    """「已隐藏」列表（hide 白名单里的条目）——恢复默认的唯一入口。

    hide 只在用户层记一条白名单，基线原件仍在——把两者 join 回来给前端，
    否则「隐藏」在界面上不可逆（拿不到 id 就调不了恢复接口）。
    """
    stmt = (
        select(KbBaselineEntry, KbBaselineOverlay)
        .join(KbBaselineOverlay, KbBaselineOverlay.src_key == KbBaselineEntry.src_key)
        .where(
            KbBaselineOverlay.user_id == user_id,
            KbBaselineOverlay.action == "hide",
        )
    )
    if genre:
        stmt = stmt.where(KbBaselineEntry.genre == genre)
    if concept:
        stmt = stmt.where(KbBaselineEntry.concept == concept)
    if q:
        stmt = stmt.where(
            or_(
                KbBaselineEntry.title.contains(q),
                KbBaselineEntry.instruction.contains(q),
            )
        )
    if cursor:
        stmt = stmt.where(KbBaselineEntry.entry_id > cursor)
    stmt = stmt.order_by(KbBaselineEntry.entry_id)
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await db.execute(stmt)).all()
    return [
        _to_merged(row, user_id=user_id, overlay=ov, hidden=True)
        for row, ov in rows
    ]


async def baseline_cell_counts(
    db: AsyncSession, *, user_id: str
) -> dict[tuple[str, str], int]:
    """(题材, 概念) 格子计数（基线段，已排 hide）——图谱聚合与题材栏同口径。"""
    from sqlalchemy import func

    rows = (
        await db.execute(
            select(
                KbBaselineEntry.genre,
                KbBaselineEntry.concept,
                func.count(KbBaselineEntry.entry_id),
            )
            .where(_hidden_clause(user_id))
            .group_by(KbBaselineEntry.genre, KbBaselineEntry.concept)
        )
    ).all()
    return {(r[0], r[1]): int(r[2]) for r in rows}


async def digest_baseline_ids(
    db: AsyncSession, *, user_id: str, genre: str,
    concepts: tuple[str, ...] = ("手法", "文风", "文笔"),
) -> dict[str, set[str]]:
    """基线层候选 id 短名单（照 kb_entry_tags 两段式，读 kb_baseline_tags）。"""
    from models.kb import KbBaselineTag

    stmt = (
        select(KbBaselineTag.entry_id, KbBaselineTag.dim, KbBaselineTag.value)
        .select_from(KbBaselineTag)
        .join(KbBaselineEntry, KbBaselineEntry.entry_id == KbBaselineTag.entry_id)
        .where(
            KbBaselineTag.dim.in_(("concept", "scope", "slot")),
            _hidden_clause(user_id),
        )
    )
    if genre:
        stmt = stmt.where(KbBaselineEntry.genre.in_((genre, "")))
    concept: dict[str, str] = {}
    scope: dict[str, str] = {}
    slot: dict[str, str] = {}
    for entry_id, dim, value in (await db.execute(stmt)).all():
        if dim == "concept":
            if value in concepts:
                concept[entry_id] = value
        elif dim == "scope":
            scope[entry_id] = value
        elif dim == "slot":
            slot[entry_id] = value
    tech: set[str] = set()
    style: set[str] = set()
    for entry_id, cname in concept.items():
        if cname == "手法":
            tech.add(entry_id)
        elif (
            cname in ("文风", "文笔")
            and scope.get(entry_id) == "scene"
            and (cname == "文笔" or slot.get(entry_id, "") in STYLE_SLOTS_IN_BLOCK)
        ):
            style.add(entry_id)
    return {"tech": tech, "style": style}


# ── upper 层写时复制（B4 操作面）────────────────────────────

_OVERLAY_ACTIONS = ("hide", "edit")


async def set_overlay(
    db: AsyncSession,
    *,
    user_id: str,
    entry_id: str,
    action: str,
    instruction: str = "",
) -> dict:
    """写/改覆盖记录（写时复制）。返回 {"ok": True} 或 {"error": code, ...}。

    - edit：物化私有副本（content=用户文本），同时把 base_content_sha256 重锚到
      当前原件（用户改的永远是此刻看到的官方版）；过 C 端同套闸门（长度/回声/结构）。
    - hide：白名单外记录；已有 content 保留（edit→hide 转换后仍可还原原副本）。
    - 基线原件 SHALL NOT 被修改。
    """
    from kb.gates import check_gates

    if action not in _OVERLAY_ACTIONS:
        return {"error": "action"}
    row = await db.get(KbBaselineEntry, entry_id)
    if row is None:
        return {"error": "not_found"}
    text = (instruction or "").strip()
    if action == "edit":
        try:
            payload = json.loads(row.payload_json or "{}")
            when = json.loads(row.when_json or "{}")
        except ValueError:
            payload, when = {}, {}
        gate = check_gates(
            concept=row.concept or "", instruction=text,
            payload=payload if isinstance(payload, dict) else {},
            when_json=when if isinstance(when, dict) else {},
        )
        if not gate.ok:
            return {"error": "gate", "message": next(iter(gate.errors.values()), "内容校验未通过")}

    src_key = row.src_key
    base_sha = row.content_sha256 or ""
    ov = (
        await db.execute(
            select(KbBaselineOverlay).where(
                KbBaselineOverlay.user_id == user_id,
                KbBaselineOverlay.src_key == src_key,
            )
        )
    ).scalar_one_or_none()
    if ov is None:
        ov = KbBaselineOverlay(
            user_id=user_id, src_key=src_key, action=action, content="",
            base_content_sha256=base_sha,
        )
        db.add(ov)
    ov.action = action
    if action == "edit":
        ov.content = text
        ov.base_content_sha256 = base_sha
    try:
        await db.commit()
    except IntegrityError:
        # 并发首写撞 (user_id, src_key) 唯一索引：回滚后改更新赢家行（幂等）
        await db.rollback()
        ov = (
            await db.execute(
                select(KbBaselineOverlay).where(
                    KbBaselineOverlay.user_id == user_id,
                    KbBaselineOverlay.src_key == src_key,
                )
            )
        ).scalar_one_or_none()
        if ov is None:
            raise
        ov.action = action
        if action == "edit":
            ov.content = text
            ov.base_content_sha256 = base_sha
        await db.commit()
    return {"ok": True, "action": action}


async def clear_overlay(
    db: AsyncSession, *, user_id: str, entry_id: str
) -> dict:
    """恢复默认／恢复官方版＝删覆盖记录（原件重新透出；基线层零变化）。"""
    row = await db.get(KbBaselineEntry, entry_id)
    if row is None:
        return {"error": "not_found"}
    ov = (
        await db.execute(
            select(KbBaselineOverlay).where(
                KbBaselineOverlay.user_id == user_id,
                KbBaselineOverlay.src_key == row.src_key,
            )
        )
    ).scalar_one_or_none()
    if ov is not None:
        await db.delete(ov)
        await db.commit()
    return {"ok": True, "restored": True}
