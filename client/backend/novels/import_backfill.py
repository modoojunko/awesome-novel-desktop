"""旧导入书回填（c-import-direct）：carry 完成后按 app_meta 标记幂等执行。

旧版本 source=import 的书没有 origin/import_kind；这里只补来源，不改 status，
让历史章由 origin=import 派生，续写落 N+1。
"""

from __future__ import annotations

from sqlalchemy import select, update

BACKFILL_KEY = "import_backfill_v1"


async def backfill_import_origin_v1() -> dict:
    from db import async_session
    from models.app_meta import AppMeta
    from models.chapter import Chapter
    from models.project import Novel

    async with async_session() as db:
        marker = await db.get(AppMeta, BACKFILL_KEY)
        if marker is not None:
            return {"skipped": True, "books": 0, "chapters": 0}
        ids = list(
            (
                await db.scalars(
                    select(Novel.id).where(
                        Novel.source == "import",
                        Novel.import_kind.in_(["authored", ""]),
                    )
                )
            ).all()
        )
        chapters = 0
        if ids:
            await db.execute(
                update(Novel).where(Novel.id.in_(ids)).values(import_kind="legacy")
            )
            result = await db.execute(
                update(Chapter)
                .where(Chapter.project_id.in_(ids))
                .values(origin="import", imported_at=Chapter.created_at)
            )
            chapters = result.rowcount or 0
        db.add(AppMeta(key=BACKFILL_KEY, value="done"))
        await db.commit()
        return {"skipped": False, "books": len(ids), "chapters": chapters}
