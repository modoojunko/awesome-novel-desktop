"""旧导入书回填（c-import-direct）：carry 完成后按 app_meta 标记幂等执行。

旧版本 source=import 的书没有 origin/import_kind；这里只补来源，不改 status，
让历史章由 origin=import 派生，续写落 N+1。
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update

BACKFILL_KEY = "import_backfill_v1"

# 旧导入端点在同一个请求里连写书与章，created_at 落在同一小窗内；
# 备份恢复的书 createdAt 取自 project.yaml（原书创建时间），章行则是恢复时刻。
# 只回填与书创建时间同窗的章，避免把「备份恢复的作者书」或导入后作者续写的章误标历史章。
LEGACY_IMPORT_WINDOW = timedelta(minutes=10)


async def backfill_import_origin_v1(*, force: bool = False) -> dict:
    from db import async_session
    from models.app_meta import AppMeta
    from models.chapter import Chapter
    from models.project import Novel

    async with async_session() as db:
        marker = await db.get(AppMeta, BACKFILL_KEY)
        if marker is not None and not force:
            return {"skipped": True, "books": 0, "chapters": 0}
        candidates = (
            await db.execute(
                select(Novel.id, Novel.created_at).where(
                    Novel.source == "import",
                    Novel.import_kind.in_(["authored", ""]),
                )
            )
        ).all()
        if not candidates:
            # 空库/新库不要提前落 marker：用户之后 carry 进来的旧书还需要回填。
            return {"skipped": False, "books": 0, "chapters": 0}
        books = 0
        chapters = 0
        for book_id, book_created in candidates:
            # created_at 缺失时无法证明章属于导入窗口，宁可不动。
            if book_created is None:
                continue
            cutoff = book_created + LEGACY_IMPORT_WINDOW
            result = await db.execute(
                update(Chapter)
                .where(
                    Chapter.project_id == book_id,
                    Chapter.created_at.is_not(None),
                    Chapter.created_at <= cutoff,
                )
                .values(origin="import", imported_at=Chapter.created_at)
            )
            marked = result.rowcount or 0
            if marked:
                await db.execute(
                    update(Novel).where(Novel.id == book_id).values(import_kind="legacy")
                )
                books += 1
                chapters += marked
        if not books:
            # 没有可证明的旧导入书（例如只有备份恢复书）：不落 marker，等 carry 后再看。
            return {"skipped": False, "books": 0, "chapters": 0}
        if marker is None:
            db.add(AppMeta(key=BACKFILL_KEY, value="done"))
        else:
            marker.value = "done"
        await db.commit()
        return {"skipped": False, "books": books, "chapters": chapters}


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
        ids: list[str] = []
        for r in rows:
            try:
                os.unlink(r.source_path)
            except FileNotFoundError:
                ids.append(r.id)
            except OSError:
                # 文件删不掉就保留行，下一次 sweep 再试（避免行没了、文件成永久孤儿）。
                continue
            else:
                ids.append(r.id)
        if not ids:
            return 0
        await db.execute(delete(ImportSession).where(ImportSession.id.in_(ids)))
        await db.commit()
    return len(ids)
