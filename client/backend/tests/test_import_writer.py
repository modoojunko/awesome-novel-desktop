"""A 路原子 writer：结构/正文/幂等/回滚/忽略章。"""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from db import async_session
from deconstruct.textparse import build_manifest
from models.chapter import Chapter, ChapterContent
from models.import_session import ImportSession
from models.project import Novel
from models.volume import Volume
from novels.import_structure import StructureError
from novels.import_writer import ImportSourceMismatch, persist_import

TEXT = (
    "第一卷 风起\n"
    "第1章 开端\n张三出门买药。\n\n"
    "第2章 遇敌\n李四拦路。\n\n"
    "第3章 归乡\n雪落。\n"
)


async def _seed_session(tmp_path, *, text: str = TEXT):
    raw = text.encode("utf-8")
    manifest = build_manifest(raw, "长夜灯.txt")
    path = tmp_path / "source.txt"
    path.write_bytes(raw)
    session_id = uuid.uuid4().hex
    async with async_session() as s:
        row = ImportSession(
            id=session_id,
            user_id="writer-test",
            source_path=str(path),
            filename="长夜灯.txt",
            manifest_json=json.dumps(manifest, ensure_ascii=False),
            source_sha256=hashlib.sha256(raw).hexdigest(),
            encoding=manifest["encoding"],
            char_count=manifest["char_count"],
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row


@pytest.mark.asyncio
async def test_persist_import_writes_authoritative_rows(tmp_path):
    session = await _seed_session(tmp_path)
    token = uuid.uuid4().hex
    name = f"原子导入-{uuid.uuid4().hex[:6]}"
    async with async_session() as db:
        book = await persist_import(
            db,
            user_id="writer-test",
            name=name,
            session=session,
            structure=[
                {"title": "风起", "chapter_from": 1, "chapter_to": 2},
                {"title": "归乡", "chapter_from": 3, "chapter_to": 3},
            ],
            import_token=token,
        )
        assert book.id
        assert book.import_kind == "direct"
        assert book.source == "import"
        assert book.total_chapters == 3
        vols = (await db.scalars(select(Volume).where(Volume.project_id == book.id).order_by(Volume.volume_no))).all()
        assert [v.title for v in vols] == ["风起", "归乡"]
        chs = (await db.scalars(select(Chapter).where(Chapter.project_id == book.id).order_by(Chapter.ref))).all()
        assert len(chs) == 3
        assert all(c.origin == "import" and c.status == "draft" for c in chs)
        assert all(c.has_prose and c.word_count > 0 for c in chs)
        assert [c.title for c in chs] == ["开端", "遇敌", "归乡"]
        contents = (await db.scalars(
            select(ChapterContent)
            .join(Chapter, Chapter.id == ChapterContent.chapter_id)
            .where(Chapter.project_id == book.id)
            .order_by(Chapter.ref)
        )).all()
        assert len(contents) == 3
        assert "张三出门买药" in contents[0].prose and "第1章" not in contents[0].prose
        assert "第一卷 风起" not in contents[0].prose


@pytest.mark.asyncio
async def test_persist_import_is_idempotent(tmp_path):
    session = await _seed_session(tmp_path)
    token = uuid.uuid4().hex
    async with async_session() as db:
        first = await persist_import(
            db, user_id="writer-test", name=f"幂等-{uuid.uuid4().hex[:6]}",
            session=session,
            structure=[{"title": "", "chapter_from": 1, "chapter_to": 3}],
            import_token=token,
        )
        second = await persist_import(
            db, user_id="writer-test", name="另一个名字",
            session=session,
            structure=[{"title": "", "chapter_from": 1, "chapter_to": 3}],
            import_token=token,
        )
        assert second.id == first.id
        count = len((await db.scalars(select(Chapter).where(Chapter.project_id == first.id))).all())
        assert count == 3


@pytest.mark.asyncio
async def test_persist_import_excludes_chapter(tmp_path):
    session = await _seed_session(tmp_path)
    async with async_session() as db:
        book = await persist_import(
            db, user_id="writer-test", name=f"忽略-{uuid.uuid4().hex[:6]}",
            session=session,
            structure=[{"title": "正文", "chapter_from": 1, "chapter_to": 2}],
            import_token=uuid.uuid4().hex,
            excluded_source_nos=[2],
        )
        chs = (await db.scalars(select(Chapter).where(Chapter.project_id == book.id).order_by(Chapter.ref))).all()
        assert [c.title for c in chs] == ["开端", "归乡"]
        assert [c.ref for c in chs] == ["vol-1-ch-1", "vol-1-ch-2"]


@pytest.mark.asyncio
async def test_persist_import_rejects_bad_structure_before_write(tmp_path):
    session = await _seed_session(tmp_path)
    async with async_session() as db:
        with pytest.raises(StructureError):
            await persist_import(
                db, user_id="writer-test", name=f"坏结构-{uuid.uuid4().hex[:6]}",
                session=session,
                structure=[{"title": "", "chapter_from": 1, "chapter_to": 2}],
                import_token=uuid.uuid4().hex,
            )
        assert (await db.scalar(select(Novel).where(Novel.name.like("坏结构-%")))) is None


@pytest.mark.asyncio
async def test_persist_import_source_sha_mismatch(tmp_path):
    session = await _seed_session(tmp_path)
    (tmp_path / "source.txt").write_text("changed", encoding="utf-8")
    async with async_session() as db:
        with pytest.raises(ImportSourceMismatch):
            await persist_import(
                db, user_id="writer-test", name=f"变源-{uuid.uuid4().hex[:6]}",
                session=session,
                structure=[{"title": "", "chapter_from": 1, "chapter_to": 3}],
                import_token=uuid.uuid4().hex,
            )


def _many_text(n: int = 240) -> str:
    return "第一卷 大书\n" + "\n".join(
        f"第{i}章 第{i}节\n" + "内容" * 20 for i in range(1, n + 1)
    )


@pytest.mark.asyncio
async def test_persist_import_240_chapters(tmp_path):
    session = await _seed_session(tmp_path, text=_many_text())
    async with async_session() as db:
        book = await persist_import(
            db, user_id="writer-test", name=f"大书-{uuid.uuid4().hex[:6]}",
            session=session,
            structure=[{"title": "大书", "chapter_from": 1, "chapter_to": 240}],
            import_token=uuid.uuid4().hex,
        )
        count = len((await db.scalars(select(Chapter).where(Chapter.project_id == book.id))).all())
        assert count == 240
        assert book.total_chapters == 240


@pytest.mark.asyncio
async def test_persist_import_240_chapters_failure_rolls_back(tmp_path, monkeypatch):
    session = await _seed_session(tmp_path, text=_many_text())
    token = uuid.uuid4().hex
    import novels.import_writer as writer_mod

    orig = writer_mod.count_chars
    calls = {"n": 0}

    def boom(text):
        calls["n"] += 1
        if calls["n"] == 120:
            raise RuntimeError("injected failure")
        return orig(text)

    monkeypatch.setattr(writer_mod, "count_chars", boom)
    async with async_session() as db:
        with pytest.raises(RuntimeError):
            await persist_import(
                db, user_id="writer-test", name=f"失败大书-{uuid.uuid4().hex[:6]}",
                session=session,
                structure=[{"title": "大书", "chapter_from": 1, "chapter_to": 240}],
                import_token=token,
            )
    async with async_session() as db:
        assert (await db.scalar(select(Novel).where(Novel.import_token == token))) is None
