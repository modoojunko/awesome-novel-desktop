"""旧导入书回填（c-import-direct）：carry 完成后按 app_meta 标记幂等执行。

旧版本 source=import 的书没有 origin/import_kind；这里只补来源，不改 status，
让历史章由 origin=import 派生，续写落 N+1。
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from sqlalchemy import delete, select, update

BACKFILL_KEY = "import_backfill_v1"


async def backfill_import_origin_v1(*, force: bool = False) -> dict:
    from db import async_session
    from models.app_meta import AppMeta
    from models.chapter import Chapter
    from models.project import Novel

    async with async_session() as db:
        marker = await db.get(AppMeta, BACKFILL_KEY)
        if marker is not None and not force:
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
        if not ids:
            # 空库/新库不要提前落 marker：用户之后 carry 进来的旧书还需要回填。
            return {"skipped": False, "books": 0, "chapters": 0}
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
        if marker is None:
            db.add(AppMeta(key=BACKFILL_KEY, value="done"))
        else:
            marker.value = "done"
        await db.commit()
        return {"skipped": False, "books": len(ids), "chapters": chapters}


async def cleanup_expired_import_sessions() -> int:
    """启动 sweep：清过期 import_sessions 行与源文件（成功落库后也会即时清）。"""
    from db import async_session
    from models.import_session import ImportSession

    now = datetime.now(UTC).replace(tzinfo=None)
    async with async_session() as db:
        rows = (
            await db.scalars(
                select(ImportSession).where(ImportSession.expires_at < now)
            )
        ).all()
        if not rows:
            return 0
        ids = [r.id for r in rows]
        paths = [r.source_path for r in rows]
        await db.execute(delete(ImportSession).where(ImportSession.id.in_(ids)))
        await db.commit()
    for path in paths:
        try:
            os.unlink(path)
        except OSError:
            pass
    return len(ids)
