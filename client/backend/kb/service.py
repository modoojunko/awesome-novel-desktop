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
    KbKnowledgeInstance,
    KbKnowledgeRevision,
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
    definition: str = "",
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

    # 手录默认装载：表单只有一句自由文本，按概念装进默认槽位（编辑器可后续调）
    if not payload:
        text = instruction or title
        if concept == "手法":
            payload = {"instruction": text, "scene": "日常"}
        elif concept == "文笔":
            payload = {"slot": "rule", "rule": text}
        elif concept == "文风":
            payload = {"slot": "sample", "sample": text}
        elif concept == "世界设定":
            payload = {"part": "extra", "content": text}
        elif concept == "角色设定":
            payload = {"archetype": (text or "未命名")[:40]}

    # payload 校验
    try:
        clean_payload = validate_payload(concept, payload)
    except ValueError as e:
        return None, GateResult(ok=False, errors={"payload": f"{concept}的内容不完整：{str(e)[:120]}"}), None

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
        definition=definition,
        version=1,
        origin=src_kind if src_kind != "manual" else "manual",
    )
    db.add(entry)
    await db.flush()

    # 标签物化
    await _materialize_tags(db, entry, clean_payload, when_json or {})

    # 默认库生成
    await ensure_default_library(db, user_id, genre, concept)

    await db.commit()
    return entry, gate, None


def _tags_for(entry: KbEntry, payload: dict, when: dict) -> list[tuple[str, str]]:
    """条目 → 标签二元组（物化与备份恢复重建共用单源）。"""
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
    # alias（c-kb-organize：别名共现特征走物化标签，SHALL NOT 读 payload_json）
    for a in (payload.get("aliases") or []):
        a = str(a).strip()[:80]
        if a:
            tags.append(("alias", a))
    return tags


async def _materialize_tags(
    db: AsyncSession, entry: KbEntry, payload: dict, when: dict
) -> None:
    """标签物化——写入同事务重建。"""
    # 先删旧标签
    await db.execute(
        delete(KbEntryTag).where(KbEntryTag.entry_id == entry.id)
    )

    for dim, value in _tags_for(entry, payload, when):
        db.add(KbEntryTag(entry_id=entry.id, user_id=entry.user_id, dim=dim, value=value))


async def rebuild_tag_index(db: AsyncSession, *, user_id: str) -> int:
    """全量重建标签索引（备份恢复后调用；c-knowledge-base 批5）。

    物化索引可随时 DELETE+重建（models/kb.py 口径）；重建期间同事务，幂等。
    返回重建条目数。
    """
    rows = (
        (await db.execute(select(KbEntry).where(KbEntry.user_id == user_id, KbEntry.status == "active")))
        .scalars()
        .all()
    )
    if not rows:
        return 0
    await db.execute(delete(KbEntryTag).where(KbEntryTag.user_id == user_id))
    n = 0
    for e in rows:
        try:
            payload = json.loads(e.payload_json or "{}")
        except ValueError:
            payload = {}
        try:
            when = json.loads(e.when_json or "{}")
        except ValueError:
            when = {}
        for dim, value in _tags_for(e, payload if isinstance(payload, dict) else {}, when if isinstance(when, dict) else {}):
            db.add(KbEntryTag(entry_id=e.id, user_id=user_id, dim=dim, value=value))
            n += 1
    await db.commit()
    return n


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
        # 默认库生成即可用（书内来源行启用 picker 只列 enabled≠False 的库）；
        # 批3 漏传落 model default False，启用链对 auto 库全断——真机走查抓出
        enabled=True,
    )
    db.add(lib)
    # IntegrityError 由 partial unique index 兜底；调用方 catch 回读


# ─── 查询 ─────────────────────────────────────────────────

async def update_entry(
    db: AsyncSession,
    *,
    user_id: str,
    entry_id: str,
    rev: int | None = None,
    title: str | None = None,
    instruction: str | None = None,
    payload: dict | None = None,
    example: str | None = None,
    negative_example: str | None = None,
    when_json: dict | None = None,
    genre: str | None = None,
    src_novel_name: str | None = None,
) -> tuple[KbEntry | None, GateResult, dict | None]:
    """编辑条目（c-kb-character-migration 刀2a）：闸门复用＋乐观并发。

    concept 不可变（跨概念移动走删建）；genre 默认不动，传入即改并同步 concept_id
    （角色库适配器刀2c ①：库卡题材是可编辑分类格）；payload/when 变更后标签物化重建。
    返回 (entry, gate, error_dict)。error_dict={"code": ...} 非 None 即失败。
    """
    e = await get_entry(db, user_id=user_id, entry_id=entry_id)
    if not e:
        return None, GateResult(ok=False), {"code": "not_found"}
    if rev is not None and rev != e.rev:
        return None, GateResult(ok=False), {"code": "rev_conflict", "current_rev": e.rev}

    clean_payload = None
    if payload is not None:
        try:
            clean_payload = validate_payload(e.concept, payload)
        except ValueError as ex:
            return None, GateResult(ok=False), {"code": "payload", "message": str(ex)}
    gate = check_gates(
        concept=e.concept,
        instruction=instruction if instruction is not None else e.instruction,
        payload=clean_payload if clean_payload is not None else _json_of(e.payload_json),
        example=example if example is not None else e.example,
        negative_example=negative_example if negative_example is not None else e.negative_example,
        when_json=when_json if when_json is not None else _json_of(e.when_json),
    )
    if not gate.ok:
        return None, gate, {"code": "gates"}

    if title is not None:
        e.title = title[:40]
    if instruction is not None:
        e.instruction = instruction
    if clean_payload is not None:
        e.payload_json = json.dumps(clean_payload, ensure_ascii=False)
    if example is not None:
        e.example = example
    if negative_example is not None:
        e.negative_example = negative_example
    if when_json is not None:
        e.when_json = json.dumps(when_json, ensure_ascii=False)
    if genre is not None:
        e.genre = genre
        e.concept_id = f"{genre}:{e.concept}"
    if src_novel_name is not None:
        e.src_novel_name = src_novel_name[:100]
    e.rev += 1
    await _materialize_tags(db, e, _json_of(e.payload_json), _json_of(e.when_json))
    await db.commit()
    await db.refresh(e)  # commit 后属性过期，router 读列需重载
    return e, gate, None


async def delete_entry(db: AsyncSession, *, user_id: str, entry_id: str) -> bool:
    """删条目＝软删（status=archived；列表/快照/全局图均只出 active）。"""
    e = await get_entry(db, user_id=user_id, entry_id=entry_id)
    if not e:
        return False
    e.status = "archived"
    e.rev += 1
    await db.commit()
    return True


def _json_of(raw: str) -> dict:
    try:
        v = json.loads(raw or "{}")
    except ValueError:
        v = {}
    return v if isinstance(v, dict) else {}


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
) -> tuple[list, str]:
    """条目列表——merged 视图游标分页。返回 (entries, next_cursor)。

    merged 域（c-kb-baseline 批B）：基线段（已排 hide、edit 副本已套）∪ 用户条目。
    两段各按 id 游标取页后在 Python 归并（基线 ≤1000 行、单页有界），
    保证跨表分页不重不漏。来源筛选："官方精选" 只取基线；手录/拆书 只取用户条目。
    """
    from kb.merged import load_baseline_entries, load_hidden_entries

    src_hidden_only = src == "已隐藏"
    src_base_only = src == "官方精选"
    src_user_only = src in ("手录", "拆书")

    g = genre if genre and genre != "全部题材" else ""
    c = concept if concept and concept != "全部" else ""

    entries: list = []
    next_cursor = ""
    if src_hidden_only:
        # 「已隐藏」＝hide 白名单回读（恢复默认的唯一入口，否则隐藏不可逆）
        rows = await load_hidden_entries(
            db, user_id=user_id, genre=g, concept=c, q=q, cursor=cursor, limit=limit + 1,
        )
        has_more = len(rows) > limit
        entries = rows[:limit]
        next_cursor = entries[-1].id if has_more and entries else ""
        return entries, next_cursor
    if src_base_only:
        rows = await load_baseline_entries(
            db, user_id=user_id, genre=g, concept=c, q=q, cursor=cursor, limit=limit + 1,
        )
        has_more = len(rows) > limit
        entries = rows[:limit]
        next_cursor = entries[-1].id if has_more and entries else ""
        return entries, next_cursor

    stmt = select(KbEntry).where(
        KbEntry.user_id == user_id,
        KbEntry.status == "active",
    )
    if g:
        stmt = stmt.where(KbEntry.genre == g)
    if c:
        stmt = stmt.where(KbEntry.concept == c)
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
    user_rows = list((await db.execute(stmt)).scalars().all())

    if src_user_only:
        rows = user_rows
        has_more = len(rows) > limit
        entries = rows[:limit]
        next_cursor = entries[-1].id if has_more and entries else ""
        return entries, next_cursor

    base_rows = await load_baseline_entries(
        db, user_id=user_id, genre=g, concept=c, q=q, cursor=cursor, limit=limit + 1,
    )
    merged = sorted(user_rows + base_rows, key=lambda e: e.id)
    has_more = len(merged) > limit
    entries = merged[:limit]
    next_cursor = entries[-1].id if has_more and entries else ""
    return entries, next_cursor


async def get_entry(
    db: AsyncSession, *, user_id: str, entry_id: str, include_merged: bool = False
) -> KbEntry | None:
    """取条目（active）；include_merged 放行 merged（c-kb-organize 详情追溯口，
    配合 kb_entry_merges 返回原载荷与指向）。archived 仍不可达。"""
    stmt = select(KbEntry).where(
        KbEntry.id == entry_id, KbEntry.user_id == user_id, KbEntry.status == "active"
    )
    if include_merged:
        stmt = select(KbEntry).where(
            KbEntry.id == entry_id,
            KbEntry.user_id == user_id,
            KbEntry.status.in_(("active", "merged")),
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
    """题材→条目计数（只算 active）；merged 口径＝用户段∪基线段（已排 hide）。"""
    from kb.merged import baseline_genre_counts

    stmt = (
        select(KbEntry.genre, func.count(KbEntry.id))
        .where(KbEntry.user_id == user_id, KbEntry.status == "active")
        .group_by(KbEntry.genre)
    )
    rows = (await db.execute(stmt)).all()
    counts = {r[0]: r[1] for r in rows}
    for g, n in (await baseline_genre_counts(db, user_id=user_id)).items():
        counts[g] = counts.get(g, 0) + n
    return counts


# ── 知识 v2：归档/恢复/实例（c-kb-knowledge-v2）─────────────────────────


async def archive_knowledge(db: AsyncSession, *, user_id: str, entry_id: str) -> bool:
    """归档：写 archived_at，不硬删。返回是否生效。"""
    from datetime import datetime

    e = await db.get(KbEntry, entry_id)
    if not e or e.user_id != user_id or e.archived_at:
        return False
    e.archived_at = datetime.now()
    e.version += 1
    await db.commit()
    return True


async def restore_knowledge(db: AsyncSession, *, user_id: str, entry_id: str) -> bool:
    """恢复归档知识。返回是否生效。"""
    e = await db.get(KbEntry, entry_id)
    if not e or e.user_id != user_id or not e.archived_at:
        return False
    e.archived_at = None
    e.version += 1
    await db.commit()
    return True


async def list_instances(db: AsyncSession, *, knowledge_id: str) -> list:
    from sqlalchemy import select

    from models.kb import KbKnowledgeInstance

    return (await db.execute(
        select(KbKnowledgeInstance)
        .where(KbKnowledgeInstance.knowledge_id == knowledge_id)
        .order_by(KbKnowledgeInstance.sort)
    )).scalars().all()


async def add_instance(
    db: AsyncSession, *, knowledge_id: str,
    text: str = "", source_kind: str = "拆书",
    source_novel: str = "", source_chapter: str = "",
    quote: str = "", sort: int = 0,
) -> KbKnowledgeInstance:
    from models.kb import KbKnowledgeInstance

    inst = KbKnowledgeInstance(
        knowledge_id=knowledge_id, text=text,
        source_kind=source_kind, source_novel=source_novel,
        source_chapter=source_chapter, quote=quote, sort=sort,
    )
    db.add(inst)
    await db.commit()
    return inst


# ── 知识 v2：别名检索＋版本快照（c-kb-knowledge-v2 任务 3.4）────────────


async def sync_aliases(db: AsyncSession, *, knowledge_id: str, aliases: list[str]) -> int:
    """同步别名到 kb_knowledge_aliases 表。返回写入数。"""
    from sqlalchemy import delete as sa_delete

    from models.kb import KbKnowledgeAlias

    await db.execute(
        sa_delete(KbKnowledgeAlias).where(KbKnowledgeAlias.knowledge_id == knowledge_id)
    )
    for a in aliases:
        trimmed = a.strip()
        if trimmed:
            db.add(KbKnowledgeAlias(knowledge_id=knowledge_id, alias=trimmed))
    await db.flush()
    return len(aliases)


async def search_by_alias(db: AsyncSession, *, user_id: str, query: str) -> list[str]:
    """按别名检索知识 id 列表。"""
    from sqlalchemy import select

    from models.kb import KbKnowledgeAlias

    rows = (await db.execute(
        select(KbKnowledgeAlias.knowledge_id)
        .where(KbKnowledgeAlias.alias.contains(query))
    )).scalars().all()
    return list(rows)


async def write_revision(
    db: AsyncSession, *, knowledge_id: str, version: int, snapshot: dict
) -> None:
    """写版本快照到 kb_knowledge_revisions。"""

    db.add(KbKnowledgeRevision(
        knowledge_id=knowledge_id, version=version,
        snapshot_json=json.dumps(snapshot, ensure_ascii=False),
    ))
    await db.flush()


async def list_revisions(db: AsyncSession, *, knowledge_id: str, limit: int = 20) -> list[dict]:
    """取版本快照列表（最近 N 版）。"""
    from sqlalchemy import select


    rows = (await db.execute(
        select(KbKnowledgeRevision)
        .where(KbKnowledgeRevision.knowledge_id == knowledge_id)
        .order_by(KbKnowledgeRevision.version.desc())
        .limit(limit)
    )).scalars().all()
    return [
        {"version": r.version, "snapshot": json.loads(r.snapshot_json), "created_at": r.created_at.isoformat()}
        for r in rows
    ]
