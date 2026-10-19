"""旧导入书回填：只补 origin/import_kind，不改 status、幂等。"""

import uuid

import pytest
from sqlalchemy import delete, select

from db import async_session
from models.app_meta import AppMeta
from models.chapter import Chapter
from models.project import Novel
from models.volume import Volume
from novels.import_backfill import BACKFILL_KEY, backfill_import_origin_v1


@pytest.mark.asyncio
async def test_backfill_legacy_import_books_is_idempotent():
    async with async_session() as db:
        await db.execute(delete(AppMeta).where(AppMeta.key == BACKFILL_KEY))
        slug = f"legacy-{uuid.uuid4().hex[:8]}"
        book = Novel(
            user_id="backfill-test", name="旧导入", slug=slug,
            root_path=f"./data/{slug}", source="import", import_kind="authored",
        )
        db.add(book)
        await db.flush()
        vol = Volume(project_id=book.id, volume_no=1, title="第1卷", summary="", chapter_count=2)
        db.add(vol)
        await db.flush()
        for no, status in ((1, "draft"), (2, "archived")):
            db.add(Chapter(
                project_id=book.id, volume_id=vol.id, chapter_no=no,
                ref=f"vol-1-ch-{no}", title=f"第{no}章", status=status,
                origin="authored", has_prose=True, word_count=10,
            ))
        await db.commit()
        book_id = book.id

    first = await backfill_import_origin_v1()
    assert first["skipped"] is False
    assert first["books"] >= 1
    async with async_session() as db:
        assert (await db.get(Novel, book_id)).import_kind == "legacy"
        chapters = (await db.scalars(select(Chapter).where(Chapter.project_id == book_id).order_by(Chapter.ref))).all()
        assert [c.origin for c in chapters] == ["import", "import"]
        assert [c.status for c in chapters] == ["draft", "archived"]
        assert all(c.imported_at is not None for c in chapters)

    second = await backfill_import_origin_v1()
    assert second["skipped"] is True

    # carry 后再带进来的旧书：force 回填，不被启动 marker 挡住。
    async with async_session() as db:
        slug2 = f"legacy2-{uuid.uuid4().hex[:8]}"
        book2 = Novel(
            user_id="backfill-test", name="later", slug=slug2,
            root_path=f"./data/{slug2}", source="import", import_kind="authored",
        )
        db.add(book2)
        await db.flush()
        vol2 = Volume(project_id=book2.id, volume_no=1, title="第1卷", summary="", chapter_count=1)
        db.add(vol2)
        await db.flush()
        db.add(Chapter(
            project_id=book2.id, volume_id=vol2.id, chapter_no=1,
            ref="vol-1-ch-1", title="第1章", status="draft",
            origin="authored", has_prose=True, word_count=10,
        ))
        await db.commit()
        book2_id = book2.id
    third = await backfill_import_origin_v1(force=True)
    assert third["skipped"] is False
    async with async_session() as db:
        assert (await db.get(Novel, book2_id)).import_kind == "legacy"
        ch = (await db.scalars(select(Chapter).where(Chapter.project_id == book2_id))).first()
        assert ch is not None and ch.origin == "import"
