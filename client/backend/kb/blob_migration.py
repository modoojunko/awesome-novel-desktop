"""legacy 库卡头像字节搬迁（c-kb-character-migration 刀2c ③）。

CharacterLibraryBlob → kb_entry_blobs（entry id 键）：
- 回联键：blob.library_id＝迁移卡 id＝kb 条目 src_key（src_ref=character_library）
- 幂等：(entry_id, variant) 已在 kb 表＝跳过；同键多用户（同备份恢复到两账号）
  各自补齐；搬成功的 legacy 行删除（字节已全部在新表，删行省双份存储）
- 孤儿行（无对应条目）保留：旧包恢复链路仍写 legacy 行（union 读兜底），
  下一轮 boot 重试时随条目补齐再搬
- boot 挂 main.lifespan（照 import backfill 先例：失败不挡启动，下次重试）
"""

from __future__ import annotations

from sqlalchemy import delete, select

from models.character_library import CharacterLibraryBlob
from models.kb import KbEntry, KbEntryBlob


async def migrate_library_blobs_v1() -> dict[str, int]:
    """搬一个账号无关的全量 legacy 头像字节。返回 {migrated, skipped, orphaned, removed}。

    可重复执行：无 legacy 行时 O(1) 探测即返回；搬成功的键旧行删除。
    """
    from db import async_session

    async with async_session() as db:
        probe = (
            await db.execute(select(CharacterLibraryBlob.library_id).limit(1))
        ).scalar_one_or_none()
        if probe is None:
            return {"migrated": 0, "skipped": 0, "orphaned": 0, "removed": 0}

        rows = (await db.execute(select(CharacterLibraryBlob))).scalars().all()
        keys = sorted({r.library_id for r in rows})
        entries = (
            await db.execute(
                select(KbEntry).where(
                    KbEntry.src_ref == "character_library",
                    KbEntry.src_key.in_(keys),
                )
            )
        ).scalars().all()
        by_key: dict[str, list[KbEntry]] = {}
        for e in entries:
            by_key.setdefault(e.src_key, []).append(e)
        existing: set[tuple[str, str]] = set()
        if entries:
            existing = {
                (b.entry_id, b.variant)
                for b in (
                    await db.execute(
                        select(KbEntryBlob).where(
                            KbEntryBlob.entry_id.in_([e.id for e in entries])
                        )
                    )
                ).scalars()
            }

        migrated = skipped = orphaned = 0
        for r in rows:
            matched = by_key.get(r.library_id) or []
            if not matched:
                orphaned += 1
                continue
            inserted = 0
            for e in matched:
                if (e.id, r.variant) in existing:
                    continue
                db.add(KbEntryBlob(entry_id=e.id, variant=r.variant, data=r.data))
                existing.add((e.id, r.variant))
                inserted += 1
            migrated += inserted
            if not inserted:
                skipped += 1  # 全部匹配条目都已有字节 → 行冗余
        # 有条目回联的键：字节已全部在 kb 表（本轮插或早已在）→ 旧行删除；孤儿键保留
        removable = {r.library_id for r in rows if r.library_id in by_key}
        removed = 0
        if removable:
            res = await db.execute(
                delete(CharacterLibraryBlob).where(
                    CharacterLibraryBlob.library_id.in_(sorted(removable))
                )
            )
            removed = res.rowcount or 0
        await db.commit()
        return {
            "migrated": migrated,
            "skipped": skipped,
            "orphaned": orphaned,
            "removed": removed,
        }
