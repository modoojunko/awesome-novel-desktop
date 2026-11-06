"""知识 v2 迁移（c-kb-knowledge-v2）：kb_entries 加列＋实例表。

- ensure_kb_knowledge_v2：幂等 DDL（ALTER TABLE ADD COLUMN / CREATE TABLE）
- populate_kb_instances_v1：从存量条目生成第 1 条实例（幂等：已有实例的知识跳过）
- boot 挂 main.lifespan（失败不挡启动，下次重试）
"""

from __future__ import annotations

from sqlalchemy import text


async def ensure_kb_knowledge_v2(db) -> dict[str, int]:
    """幂等 DDL：给 kb_entries 加 v2 列＋建 kb_knowledge_instances 表。"""
    added = 0
    cols = [r[1] for r in (await db.execute(
        text("PRAGMA table_info(kb_entries)")
    )).fetchall()]
    for col, ddl in [
        ("definition", "ALTER TABLE kb_entries ADD COLUMN definition TEXT NOT NULL DEFAULT ''"),
        ("version", "ALTER TABLE kb_entries ADD COLUMN version INTEGER NOT NULL DEFAULT 1"),
        ("origin", "ALTER TABLE kb_entries ADD COLUMN origin TEXT NOT NULL DEFAULT 'manual'"),
        ("archived_at", "ALTER TABLE kb_entries ADD COLUMN archived_at DATETIME"),
    ]:
        if col not in cols:
            await db.execute(text(ddl))
            added += 1
    await db.execute(text("""CREATE TABLE IF NOT EXISTS kb_knowledge_instances (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        knowledge_id TEXT NOT NULL REFERENCES kb_entries(id) ON DELETE CASCADE,
        text TEXT NOT NULL DEFAULT '',
        source_kind TEXT NOT NULL DEFAULT '拆书',
        source_novel TEXT NOT NULL DEFAULT '',
        source_chapter TEXT NOT NULL DEFAULT '',
        quote TEXT NOT NULL DEFAULT '',
        sort INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""))
    await db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_kb_instances_knowledge "
        "ON kb_knowledge_instances (knowledge_id, sort)"
    ))
    await db.commit()
    return {"ddl": added}


async def populate_kb_instances_v1(db) -> dict[str, int]:
    """为存量条目生成第 1 条实例（幂等：已有实例的知识跳过）。"""
    rows = (await db.execute(text("""
        SELECT id, instruction, evidence, example, src_kind, src_novel_name
        FROM kb_entries
        WHERE id NOT IN (SELECT knowledge_id FROM kb_knowledge_instances)
          AND (instruction != '' OR evidence != '' OR example != '')
    """))).fetchall()
    created = 0
    for r in rows:
        eid, inst_text, evid, example, src_kind, novel = r
        quote = evid or example
        source = '拆书' if 'deconstruct' in (src_kind or '').lower() else '手录'
        import uuid
        iid = str(uuid.uuid4())
        await db.execute(text("""
            INSERT INTO kb_knowledge_instances
                (id, knowledge_id, text, source_kind, source_novel, source_chapter, quote, fields_json, sort)
            VALUES (:id, :kid, :text, :sk, :novel, '', :quote, '{}', 0)
        """), {"id": iid, "kid": eid, "text": inst_text, "sk": source, "novel": novel or "",
               "quote": quote or ""})
        created += 1
    await db.commit()
    return {"instances": created}


async def migrate_kb_knowledge_v2() -> dict[str, int]:
    """入口：DDL ＋ 实例生成。"""
    from db import async_session

    async with async_session() as db:
        ddl = await ensure_kb_knowledge_v2(db)
        inst = await populate_kb_instances_v1(db)
        return {**ddl, **inst}
