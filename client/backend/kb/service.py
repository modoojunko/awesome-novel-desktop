"""写作知识库核心服务——入库/查询/默认库/标签物化。"""

from __future__ import annotations

import json

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kb.concepts import THEMES
from kb.gates import GateResult, check_gates
from kb.infer import infer_concept
from kb.payloads import validate_payload
from models.kb import (
    KbEntry,
    KbEntryTag,
    KbLibrary,
)

# ─── 入库 ─────────────────────────────────────────────────

async def create_entry(
    db: AsyncSession,
    *,
    user_id: str,
    genre: str,
    concept: str,
    concept_id: str = "",
    title: str = "",
    payload: dict,
    instruction: str = "",
    example: str = "",
    negative_example: str = "",
    when_json: dict | None = None,
    evidence: str = "",
    evidence_json: dict | None = None,
    src_kind: str = "manual",
    src_ref: str = "",
    src_key: str = "",
    src_novel_name: str = "",
    original_texts: list[str] | None = None,
) -> tuple[KbEntry | None, GateResult, dict | None]:
    """入库一条知识：闸门→payload 校验→标签物化→默认库生成。
    返回 (entry, gate_result, error_dict)。error_dict 非 None 表示入库失败。"""

    # 概念推断（如果未指定）
    if not concept or concept not in (
        "文风", "文笔", "世界设定", "角色设定", "手法", "情节"
    ):
        concept = infer_concept(instruction or title or json.dumps(payload, ensure_ascii=False))

    # 情节拒收（消费链未建）
    if concept == "情节":
        return None, GateResult(ok=False, errors={"concept": "情节消费链未建，暂不支持手录"}), None

    # 题材归一
    if genre and genre not in THEMES:
        genre = ""  # 未定题材

    # payload 校验
    try:
        clean_payload = validate_payload(concept, payload)
    except ValueError as e:
        return None, GateResult(ok=False, errors={"payload": str(e)}), None

    # 闸门
    gate = check_gates(
        concept=concept,
        instruction=instruction,
        payload=clean_payload,
        example=example,
        negative_example=negative_example,
        when_json=when_json,
        original_texts=original_texts,
    )
    if not gate.ok:
        return None, gate, None

    # 标题自动截取
    if not title:
        title = instruction[:40].rstrip("。，、；：") if instruction else ""

    # 子概念叶子
    if not concept_id:
        concept_id = f"{genre}:{concept}"

    # 创建条目
    entry = KbEntry(
        user_id=user_id,
        genre=genre,
        concept=concept,
        concept_id=concept_id,
        title=title,
        payload_json=json.dumps(clean_payload, ensure_ascii=False),
        instruction=instruction,
        example=example,
        negative_example=negative_example or "",
        when_json=json.dumps(when_json or {}, ensure_ascii=False),
        evidence=evidence,
        evidence_json=json.dumps(evidence_json or {}, ensure_ascii=False),
        src_kind=src_kind,
        src_ref=src_ref,
        src_key=src_key,
        src_novel_name=src_novel_name,
    )
    db.add(entry)
    await db.flush()

    # 标签物化
    await _materialize_tags(db, entry, clean_payload, when_json or {})

    # 默认库生成
    await ensure_default_library(db, user_id, genre, concept)

    await db.commit()
    return entry, gate, None


async def _materialize_tags(
    db: AsyncSession, entry: KbEntry, payload: dict, when: dict
) -> None:
    """标签物化——写入同事务重建。"""
    # 先删旧标签
    await db.execute(
        delete(KbEntryTag).where(KbEntryTag.entry_id == entry.id)
    )

    tags: list[tuple[str, str]] = []
    if entry.genre:
        tags.append(("genre", entry.genre))
    tags.append(("concept", entry.concept))
    tags.append(("concept_id", entry.concept_id))
    # scope
    scope = "scene" if when else "base"
    tags.append(("scope", scope))
    # scene / emotion / chapter_pos
    for key in ("scene", "emotion", "chapter_pos"):
        v = when.get(key)
        if v:
            tags.append((key, v))
    # payload 内的 scene/emotion（手法）
    if entry.concept == "手法":
        p = payload
        if p.get("scene"):
            tags.append(("scene", p["scene"]))
        if p.get("emotion"):
            tags.append(("emotion", p["emotion"]))
    # slot
    slot = payload.get("slot")
    if slot:
        tags.append(("slot", slot))

    for dim, value in tags:
        db.add(KbEntryTag(entry_id=entry.id, user_id=entry.user_id, dim=dim, value=value))


async def ensure_default_library(
    db: AsyncSession, user_id: str, genre: str, concept: str
) -> None:
    """题材×概念首条目入库时自动生成默认库（partial unique index 兜并发）。"""
    # 检查是否已有
    stmt = select(KbLibrary).where(
        KbLibrary.user_id == user_id,
        KbLibrary.genre == genre,
        KbLibrary.concept == concept,
        KbLibrary.rule_kind == "auto",
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        return

    lib = KbLibrary(
        user_id=user_id,
        genre=genre,
        concept=concept,
        name=f"{concept}库",
        purpose=f"{genre}题材的{concept}知识",
        contract="live" if concept == "手法" else "snapshot",
        rule_kind="auto",
        rule_json=json.dumps({"genre": genre, "concept": concept}, ensure_ascii=False),
    )
    db.add(lib)
    # IntegrityError 由 partial unique index 兜底；调用方 catch 回读


# ─── 查询 ─────────────────────────────────────────────────

async def list_entries(
    db: AsyncSession,
    *,
    user_id: str,
    genre: str = "",
    concept: str = "",
    src: str = "",
    q: str = "",
    cursor: str = "",
    limit: int = 30,
) -> tuple[list[KbEntry], str]:
    """条目列表——游标分页。返回 (entries, next_cursor)。"""

    stmt = select(KbEntry).where(
        KbEntry.user_id == user_id,
        KbEntry.status == "active",
    )
    if genre and genre != "全部题材":
        stmt = stmt.where(KbEntry.genre == genre)
    if concept and concept != "全部":
        stmt = stmt.where(KbEntry.concept == concept)
    if src and src != "全部":
        if src == "手录":
            stmt = stmt.where(KbEntry.src_kind == "manual")
        elif src == "拆书":
            stmt = stmt.where(KbEntry.src_kind == "deconstruct")
    if q:
        stmt = stmt.where(KbEntry.title.contains(q) | KbEntry.instruction.contains(q))
    if cursor:
        stmt = stmt.where(KbEntry.id > cursor)

    stmt = stmt.order_by(KbEntry.id).limit(limit + 1)
    rows = (await db.execute(stmt)).scalars().all()

    has_more = len(rows) > limit
    entries = rows[:limit]
    next_cursor = entries[-1].id if has_more and entries else ""
    return entries, next_cursor


async def get_entry(db: AsyncSession, *, user_id: str, entry_id: str) -> KbEntry | None:
    stmt = select(KbEntry).where(
        KbEntry.id == entry_id, KbEntry.user_id == user_id, KbEntry.status == "active"
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_libraries(
    db: AsyncSession, *, user_id: str, genre: str = ""
) -> list[KbLibrary]:
    stmt = select(KbLibrary).where(KbLibrary.user_id == user_id, KbLibrary.status == "active")
    if genre and genre != "全部题材":
        stmt = stmt.where(KbLibrary.genre == genre)
    stmt = stmt.order_by(KbLibrary.genre, KbLibrary.sort)
    return list((await db.execute(stmt)).scalars().all())


async def genre_counts(db: AsyncSession, *, user_id: str) -> dict[str, int]:
    """题材→条目计数（只算 active）。"""
    stmt = (
        select(KbEntry.genre, func.count(KbEntry.id))
        .where(KbEntry.user_id == user_id, KbEntry.status == "active")
        .group_by(KbEntry.genre)
    )
    rows = (await db.execute(stmt)).all()
    return {r[0]: r[1] for r in rows}
