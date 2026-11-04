"""知识 v2 迁移（c-kb-knowledge-v2）：kb_entries / kb_relations → 知识 / 实例 / 关系三表。

- migrate_kb_knowledge_v1：一次性迁移（boot 挂 main.lifespan；失败不挡启动，下次重试）
  · kb_entries.id 原样保留为知识 id（关系两端不换 id，旧关系不断）
  · instruction → 第 1 条实例文本；example/negative_example/evidence/src_* 并入实例来源与原文摘句
  · knowledge.definition 置空（一般性定义是新字段，首轮显示「知识定义待补」）
  · 状态映射：active→formed；merged/archived→formed + archived_at=updated_at
  · 版本沿用旧 rev；时间戳原样
- 幂等：kb_knowledge 已有同 id＝跳过；关系 (from_id,to_id,rel_type) 已存在＝跳过
- 迁移前把将迁移的旧行落备份表 kb_knowledge_migration_backup（JSON 快照），可回放重建
"""

from __future__ import annotations

import json

from sqlalchemy import select

from models.kb import KbEntry, KbRelation
from models.kb_knowledge import (
    KbKnowledge,
    KbKnowledgeInstance,
    KbKnowledgeMigrationBackup,
    KbKnowledgeRelation,
)


def _origin(src_kind: str) -> str:
    """旧 src_kind → 新 origin 词表（manual/deconstruct/baseline/import）。"""
    k = (src_kind or "").lower()
    if "deconstruct" in k:
        return "deconstruct"
    if "baseline" in k:
        return "baseline"
    if "import" in k or "character_library" in k:
        return "import"
    return "manual"


def _instance_source(src_kind: str) -> str:
    """实例的来源类型：拆书来的标「拆书」，其余（手录/迁移卡）标「手录」。"""
    k = (src_kind or "").lower()
    return "拆书" if ("deconstruct" in k or k in ("baseline", "import")) else "手录"


def _entry_status(entry_status: str) -> str:
    """旧条目状态 → 新知识状态（draft/formed/needs_work）。"""
    return {"active": "formed"}.get(entry_status, "formed")


async def migrate_kb_knowledge_v1(
    user_ids: set[str] | None = None,
) -> dict[str, int]:
    """全量迁移一次。返回 {knowledge, instances, relations, backed_up, skipped}。

    可重复执行：kb_knowledge 已有同 id 的旧条目＝跳过；无待迁行时 O(1) 探测即返回。
    """
    from db import async_session

    async with async_session() as db:
        entries = (await db.execute(select(KbEntry))).scalars().all()
        relations = (await db.execute(select(KbRelation))).scalars().all()
        existing_k = set(
            (await db.execute(select(KbKnowledge.id))).scalars().all()
        )
        existing_rel = set(
            (
                await db.execute(
                    select(
                        KbKnowledgeRelation.from_id,
                        KbKnowledgeRelation.to_id,
                        KbKnowledgeRelation.rel_type,
                    )
                )
            ).all()
        )

        todo_e = [e for e in entries if e.id not in existing_k]
        # 只迁两端都能对上旧条目 id 的关系（旧表可能还挂概念 id，那些不进知识关系）
        entry_ids = existing_k | {e.id for e in todo_e}
        todo_r = [
            r
            for r in relations
            if r.from_id in entry_ids and r.to_id in entry_ids
            and (r.from_id, r.to_id, r.rel_type) not in existing_rel
        ]
        if not todo_e and not todo_r:
            return {"knowledge": 0, "instances": 0, "relations": 0,
                    "backed_up": 0, "skipped": 0}
        skipped = len(relations) - len(todo_r)

        # 迁移前备份：只备份将迁移的行（JSON 快照，可回放重建旧表行）
        backed_up = 0
        for e in todo_e:
            db.add(KbKnowledgeMigrationBackup(
                kind="kb_entries",
                row_key=e.id,
                payload_json=json.dumps({
                    "id": e.id, "user_id": e.user_id, "title": e.title,
                    "genre": e.genre, "concept": e.concept,
                    "concept_id": e.concept_id, "payload_json": e.payload_json,
                    "payload_version": e.payload_version,
                    "instruction": e.instruction, "example": e.example,
                    "negative_example": e.negative_example,
                    "when_json": e.when_json, "evidence": e.evidence,
                    "evidence_json": e.evidence_json, "status": e.status,
                    "rev": e.rev, "src_kind": e.src_kind, "src_ref": e.src_ref,
                    "src_key": e.src_key, "src_novel_name": e.src_novel_name,
                    "created_at": e.created_at.isoformat() if e.created_at else "",
                    "updated_at": e.updated_at.isoformat() if e.updated_at else "",
                }, ensure_ascii=False),
            ))
            backed_up += 1
        for r in todo_r:
            db.add(KbKnowledgeMigrationBackup(
                kind="kb_relations",
                row_key=f"{r.from_id}->{r.to_id}:{r.rel_type}",
                payload_json=json.dumps({
                    "id": r.id, "user_id": r.user_id, "from_id": r.from_id,
                    "to_id": r.to_id, "rel_type": r.rel_type,
                    "strength": r.strength, "source": r.source,
                    "confidence": r.confidence, "note": r.note,
                    "evidence": r.evidence, "status": r.status,
                    "run_id": r.run_id,
                }, ensure_ascii=False),
            ))
            backed_up += 1
        await db.flush()

        knowledge = instances = relations = 0
        for e in todo_e:
            archived = e.status in ("merged", "archived")
            db.add(KbKnowledge(
                id=e.id,
                user_id=e.user_id,
                title=e.title,
                genre=e.genre,
                category=e.concept,
                payload_json=e.payload_json,
                payload_version=e.payload_version,
                definition="",  # 一般性定义是新字段，首轮「知识定义待补」
                when_text="",
                when_json=e.when_json,
                status=_entry_status(e.status),
                version=max(e.rev, 1),
                origin=_origin(e.src_kind),
                src_kind=e.src_kind,
                src_ref=e.src_ref,
                src_key=e.src_key,
                src_novel_name=e.src_novel_name,
                archived_at=e.updated_at if archived else None,
                created_at=e.created_at,
                updated_at=e.updated_at,
            ))
            if e.instruction or e.evidence or e.example:
                db.add(KbKnowledgeInstance(
                    knowledge_id=e.id,
                    text=e.instruction,
                    source_kind=_instance_source(e.src_kind),
                    source_novel=e.src_novel_name,
                    source_chapter="",
                    quote=e.evidence or e.example,
                    sort=0,
                ))
                instances += 1
            knowledge += 1

        for r in todo_r:
            db.add(KbKnowledgeRelation(
                user_id=r.user_id if hasattr(r, "user_id") else "",
                from_id=r.from_id,
                to_id=r.to_id,
                rel_type=r.rel_type,
                note=r.note,
                confidence=r.confidence,
                evidence_json=json.dumps({
                    "evidence": r.evidence, "strength": r.strength,
                    "source": r.source, "run_id": r.run_id,
                }, ensure_ascii=False),
                status=r.status if r.status in ("active", "pending", "archived") else "active",
            ))
            relations += 1

        await db.commit()
        return {"knowledge": knowledge, "instances": instances,
                "relations": relations, "backed_up": backed_up, "skipped": skipped}
