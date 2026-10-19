"""A 路 parse/persist API：txt-only、manifest、TTL、幂等、配额门。"""

import io
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update
from starlette.datastructures import UploadFile

from db import async_session
from deconstruct.textparse import MAX_SOURCE_BYTES
from models.import_session import ImportSession
from models.project import Novel
from novels.router import ImportOwnPersistBody, import_own_parse, import_own_persist

TEXT = "第一卷 风起\n第1章 开端\n张三出门。\n第2章 遇敌\n李四拦路。\n"


def _upload(raw: bytes, filename: str = "长夜灯.txt") -> UploadFile:
    return UploadFile(file=io.BytesIO(raw), filename=filename)


async def _parse(db, user_id: str, raw: bytes = TEXT.encode("utf-8"), filename: str = "长夜灯.txt"):
    return await import_own_parse(
        file=_upload(raw, filename),
        user={"id": user_id},
        db=db,
    )


@pytest.mark.asyncio
async def test_parse_returns_manifest_preview(monkeypatch):
    async def _noop(*args, **kwargs):
        return True

    monkeypatch.setattr("auth_local.deps.require_project_limit", _noop)
    user_id = f"api-{uuid.uuid4().hex[:8]}"
    async with async_session() as db:
        out = await _parse(db, user_id)
    assert out["import_id"]
    assert out["encoding"] in ("utf-8", "utf-8-sig")
    assert out["chapter_count"] == 2
    assert [c["title"] for c in out["chapters"]] == ["开端", "遇敌"]
    assert out["volumes"][0]["title"] == "风起"
    assert out["risk"]["level"] in ("ok", "warn", "risk")


@pytest.mark.asyncio
async def test_parse_rejects_non_txt():
    async with async_session() as db:
        with pytest.raises(HTTPException) as ei:
            await _parse(db, "api-bad", b"# hi", "x.md")
    assert ei.value.status_code == 415


@pytest.mark.asyncio
async def test_parse_rejects_over_50mb():
    async with async_session() as db:
        with pytest.raises(HTTPException) as ei:
            await _parse(db, "api-huge", b"x" * (MAX_SOURCE_BYTES + 1), "huge.txt")
    assert ei.value.status_code == 413


@pytest.mark.asyncio
async def test_persist_creates_book_and_is_idempotent(monkeypatch):
    async def _noop(*args, **kwargs):
        return True

    monkeypatch.setattr("auth_local.deps.require_project_limit", _noop)
    user_id = f"api-{uuid.uuid4().hex[:8]}"
    token = uuid.uuid4().hex
    async with async_session() as db:
        out = await _parse(db, user_id)
    body = ImportOwnPersistBody(
        import_id=out["import_id"],
        name=f"接口导入-{uuid.uuid4().hex[:6]}",
        volumes=[{"title": "风起", "chapter_from": 1, "chapter_to": 2}],
        import_token=token,
    )
    async with async_session() as db:
        first = await import_own_persist(body, user={"id": user_id}, db=db)
    async with async_session() as db:
        assert (await db.get(ImportSession, out["import_id"])) is None
    assert not os.path.exists(
        os.path.join(os.environ["DATA_ROOT"], "import-sessions", out["import_id"] + ".txt")
    )
    async with async_session() as db:
        second = await import_own_persist(body, user={"id": user_id}, db=db)
    assert second["id"] == first["id"]
    async with async_session() as db:
        book = await db.get(Novel, first["id"])
        assert book is not None
        assert book.import_kind == "direct"
        assert book.import_token == token


@pytest.mark.asyncio
async def test_persist_rejects_expired_session(monkeypatch):
    async def _noop(*args, **kwargs):
        return True

    monkeypatch.setattr("auth_local.deps.require_project_limit", _noop)
    user_id = f"api-{uuid.uuid4().hex[:8]}"
    async with async_session() as db:
        out = await _parse(db, user_id)
    import_id = out["import_id"]
    async with async_session() as db:
        row = await db.get(ImportSession, import_id)
        path = row.source_path
        await db.execute(
            update(ImportSession).where(ImportSession.id == import_id).values(
                expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
            )
        )
        await db.commit()
    body = ImportOwnPersistBody(
        import_id=import_id, name="过期", volumes=[{"title": "", "chapter_from": 1, "chapter_to": 2}],
        import_token=uuid.uuid4().hex,
    )
    async with async_session() as db:
        with pytest.raises(HTTPException) as ei:
            await import_own_persist(body, user={"id": user_id}, db=db)
    assert ei.value.status_code == 410
    import os
    assert not os.path.exists(path)


@pytest.mark.asyncio
async def test_persist_quota_gate_blocks_new_book(monkeypatch):
    async def _deny(*args, **kwargs):
        raise HTTPException(403, "书架已满")

    monkeypatch.setattr("auth_local.deps.require_project_limit", _deny)
    user_id = f"api-{uuid.uuid4().hex[:8]}"
    async with async_session() as db:
        out = await _parse(db, user_id)
    body = ImportOwnPersistBody(
        import_id=out["import_id"], name="配额满",
        volumes=[{"title": "", "chapter_from": 1, "chapter_to": 2}],
        import_token=uuid.uuid4().hex,
    )
    async with async_session() as db:
        with pytest.raises(HTTPException) as ei:
            await import_own_persist(body, user={"id": user_id}, db=db)
    assert ei.value.status_code == 403
    async with async_session() as db:
        assert (await db.scalar(select(Novel).where(Novel.name == "配额满"))) is None


@pytest.mark.asyncio
async def test_cleanup_expired_sessions_removes_row_and_file(tmp_path):
    from novels.import_backfill import cleanup_expired_import_sessions

    path = tmp_path / "expired.txt"
    path.write_text("x", encoding="utf-8")
    sid = uuid.uuid4().hex
    async with async_session() as db:
        db.add(ImportSession(
            id=sid, user_id="cleanup", source_path=str(path), filename="x.txt",
            manifest_json="{}", source_sha256="x", encoding="utf-8", char_count=1,
            expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1),
        ))
        await db.commit()
    assert await cleanup_expired_import_sessions() >= 1
    async with async_session() as db:
        assert (await db.get(ImportSession, sid)) is None
    assert not path.exists()
