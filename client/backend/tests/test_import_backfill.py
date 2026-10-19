"""旧导入书回填：只补 origin/import_kind，不改 status、幂等。"""

import uuid
from datetime import UTC, datetime, timedelta

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
        imported_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        book = Novel(
            user_id="backfill-test", name="旧导入", slug=slug,
            root_path=f"./data/{slug}", source="import", import_kind="authored",
            created_at=imported_at,
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
                created_at=imported_at + timedelta(seconds=no),
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
        imported_at2 = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2)
        book2 = Novel(
            user_id="backfill-test", name="later", slug=slug2,
            root_path=f"./data/{slug2}", source="import", import_kind="authored",
            created_at=imported_at2,
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
            created_at=imported_at2 + timedelta(seconds=1),
        ))
        await db.commit()
        book2_id = book2.id
    third = await backfill_import_origin_v1(force=True)
    assert third["skipped"] is False
    async with async_session() as db:
        assert (await db.get(Novel, book2_id)).import_kind == "legacy"
        ch = (await db.scalars(select(Chapter).where(Chapter.project_id == book2_id))).first()
        assert ch is not None and ch.origin == "import"


@pytest.mark.asyncio
async def test_backfill_does_not_touch_backup_restored_book():
    """备份恢复的书 source=import 但书创建时间远早于章行：不能把作者章全标成历史章。"""
    async with async_session() as db:
        slug = f"backup-{uuid.uuid4().hex[:8]}"
        book = Novel(
            user_id="backfill-test", name="备份恢复", slug=slug,
            root_path=f"./data/{slug}", source="import", import_kind="authored",
            created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30),
        )
        db.add(book)
        await db.flush()
        vol = Volume(project_id=book.id, volume_no=1, title="第1卷", summary="", chapter_count=2)
        db.add(vol)
        await db.flush()
        for no in (1, 2):
            db.add(Chapter(
                project_id=book.id, volume_id=vol.id, chapter_no=no,
                ref=f"vol-1-ch-{no}", title=f"第{no}章", status="draft",
                origin="authored", has_prose=True, word_count=10,
                created_at=datetime.now(UTC).replace(tzinfo=None),
            ))
        await db.commit()
        book_id = book.id

    await backfill_import_origin_v1(force=True)

    async with async_session() as db:
        assert (await db.get(Novel, book_id)).import_kind == "authored"
        chapters = (
            await db.scalars(select(Chapter).where(Chapter.project_id == book_id))
        ).all()
        assert [c.origin for c in chapters] == ["authored", "authored"]
        assert all(c.imported_at is None for c in chapters)


@pytest.mark.asyncio
async def test_backfill_marks_only_chapters_created_with_book():
    """旧导入书导入后作者续写的章（创建时间晚于导入窗口）保持 authored。"""
    async with async_session() as db:
        slug = f"mixed-{uuid.uuid4().hex[:8]}"
        imported_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=3)
        book = Novel(
            user_id="backfill-test", name="混合来源", slug=slug,
            root_path=f"./data/{slug}", source="import", import_kind="authored",
            created_at=imported_at,
        )
        db.add(book)
        await db.flush()
        vol = Volume(project_id=book.id, volume_no=1, title="第1卷", summary="", chapter_count=2)
        db.add(vol)
        await db.flush()
        db.add_all([
            Chapter(
                project_id=book.id, volume_id=vol.id, chapter_no=1,
                ref="vol-1-ch-1", title="导入章", status="draft",
                origin="authored", has_prose=True, word_count=10,
                created_at=imported_at + timedelta(seconds=5),
            ),
            Chapter(
                project_id=book.id, volume_id=vol.id, chapter_no=2,
                ref="vol-1-ch-2", title="后来写的", status="draft",
                origin="authored", has_prose=True, word_count=10,
                created_at=imported_at + timedelta(days=1),
            ),
        ])
        await db.commit()
        book_id = book.id

    await backfill_import_origin_v1(force=True)

    async with async_session() as db:
        chapters = (
            await db.scalars(
                select(Chapter)
                .where(Chapter.project_id == book_id)
                .order_by(Chapter.chapter_no)
            )
        ).all()
        assert [c.origin for c in chapters] == ["import", "authored"]
        assert chapters[0].imported_at is not None
        assert chapters[1].imported_at is None
