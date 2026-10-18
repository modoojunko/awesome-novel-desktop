"""frontier 跳过历史章、global_no、archived 只读。"""

import uuid

import pytest

from chapters.frontier import frontier_info, is_writable
from db import async_session
from models.chapter import Chapter
from models.project import Novel
from models.volume import Volume


async def _seed(chapters):
    async with async_session() as db:
        slug = f"frontier-{uuid.uuid4().hex[:8]}"
        book = Novel(user_id="frontier-test", name="frontier", slug=slug, root_path=f"./data/{slug}")
        db.add(book)
        await db.flush()
        vol = Volume(project_id=book.id, volume_no=1, title="第1卷", summary="", chapter_count=len(chapters))
        db.add(vol)
        await db.flush()
        for no, (status, origin, has_prose) in enumerate(chapters, start=1):
            db.add(Chapter(
                project_id=book.id, volume_id=vol.id, chapter_no=no,
                ref=f"vol-1-ch-{no}", title=f"第{no}章", status=status,
                origin=origin, has_prose=has_prose,
                word_count=100 if has_prose else 0,
            ))
        await db.commit()
        return book.id


@pytest.mark.asyncio
async def test_imported_book_frontier_is_pending_n_plus_one():
    book_id = await _seed([("draft", "import", True)] * 3)
    async with async_session() as db:
        info = await frontier_info(db, book_id)
    assert info["frontier"]["pending"] is True
    assert info["frontier"]["global_no"] == 4
    assert info["frontier"]["chapter_no"] == 4
    assert [c["global_no"] for c in info["chapters"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_mixed_book_frontier_is_first_authored_planned():
    book_id = await _seed([
        ("draft", "import", True),
        ("draft", "import", True),
        ("outline", "authored", False),
        ("outline", "authored", False),
    ])
    async with async_session() as db:
        info = await frontier_info(db, book_id)
        assert info["frontier"]["ref"] == "vol-1-ch-3"
        assert info["frontier"]["global_no"] == 3
        assert await is_writable(db, book_id, "vol-1-ch-2") == (True, "")
        assert (await is_writable(db, book_id, "vol-1-ch-4"))[0] is False


@pytest.mark.asyncio
async def test_archived_chapter_is_read_only():
    book_id = await _seed([("archived", "authored", True)])
    async with async_session() as db:
        ok, reason = await is_writable(db, book_id, "vol-1-ch-1")
    assert ok is False
    assert "归档" in reason


@pytest.mark.asyncio
async def test_global_no_across_two_volumes():
    async with async_session() as db:
        slug = f"frontier2-{uuid.uuid4().hex[:8]}"
        book = Novel(user_id="frontier-test", name="frontier2", slug=slug, root_path=f"./data/{slug}")
        db.add(book)
        await db.flush()
        v1 = Volume(project_id=book.id, volume_no=1, title="第1卷", summary="", chapter_count=24)
        v2 = Volume(project_id=book.id, volume_no=2, title="第2卷", summary="", chapter_count=18)
        db.add_all([v1, v2])
        await db.flush()
        for no in range(1, 25):
            db.add(Chapter(project_id=book.id, volume_id=v1.id, chapter_no=no,
                           ref=f"vol-1-ch-{no}", title=f"第{no}章", status="draft",
                           origin="import", has_prose=True, word_count=10))
        for no in range(1, 19):
            db.add(Chapter(project_id=book.id, volume_id=v2.id, chapter_no=no,
                           ref=f"vol-2-ch-{no}", title=f"第{24 + no}章", status="draft",
                           origin="import", has_prose=True, word_count=10))
        await db.commit()
        book_id = book.id
    async with async_session() as db:
        info = await frontier_info(db, book_id)
    by_ref = {c["ref"]: c for c in info["chapters"]}
    assert by_ref["vol-2-ch-3"]["global_no"] == 27
    assert info["frontier"]["pending"] is True
    assert info["frontier"]["global_no"] == 43

