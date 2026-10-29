"""角色库域测试（c-character-library）：CRUD/收录幂等/同步/用到新书/随机名兜底/备份往返/带回计数。"""

import asyncio
import io
import json
import uuid
import zipfile

import pytest
import yaml
from fastapi.testclient import TestClient

from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.character import Character
from models.character_library import CharacterLibrary, CharacterLibraryBlob
from models.project import Novel
from models.user import User


def _run(coro):
    return asyncio.run(coro)


async def _seed(with_character: bool = True) -> dict:
    uid = f"chlib-{uuid.uuid4().hex[:8]}"
    slug = f"chlib-{uuid.uuid4().hex[:8]}"
    async with async_session() as db:
        db.add(User(
            id=uid, email=f"{uid}@t.local", password_hash="x", display_name="库测试",
            api_key="", api_base_url="", api_model="",
        ))
        novel = Novel(
            user_id=uid, name="库测试书", slug=slug, root_path=f"./data/{slug}",
            source="manual", current_phase="write",
        )
        db.add(novel)
        await db.flush()
        char_id = ""
        if with_character:
            char = Character(
                novel_id=novel.id, seq=1, name="沈青崖", role="主角",
                persona="看山人独子", dossier=json.dumps(
                    {"gender": "男", "age": "16", "speech": "话少"}, ensure_ascii=False),
                cog=json.dumps({"w1": "山里人", "b1": "克制"}, ensure_ascii=False),
            )
            db.add(char)
            await db.flush()
            char_id = char.id
        novel.character_seq_high = 1 if with_character else 0
        await db.commit()
        return {"uid": uid, "novel_id": novel.id, "char_id": char_id}


@pytest.fixture
def client():
    seed = _run(_seed())

    async def _override():
        return {"id": seed["uid"]}

    app.dependency_overrides[get_current_user] = _override
    with TestClient(app) as c:
        yield c, seed
    app.dependency_overrides.clear()


def _card_body(**over):
    body = {
        "name": "秦重霄",
        "aliases": ["大当家"],
        "role": "反派",
        "genre": "武侠",
        "kind": "敌人",
        "persona": "黑风寨大当家",
        "dossier": {"gender": "男", "age": "42", "speech": "骂人先问候对方娘亲"},
        "cog": {"b1": "暴躁易怒"},
    }
    body.update(over)
    return body


class TestCrud:
    def test_create_and_list(self, client):
        c, _ = client
        r = c.post("/api/character-library", json=_card_body())
        assert r.status_code == 200, r.text
        card = r.json()["data"]
        assert card["name"] == "秦重霄" and card["src"]["kind"] == "manual"

        listed = c.get("/api/character-library").json()["data"]
        assert listed["count"] == 1
        item = listed["items"][0]
        assert item["dossier"]["age"] == "42" and item["cog"]["b1"] == "暴躁易怒"
        assert item["avatar"]["has"] is False

    def test_update_whole_card(self, client):
        c, _ = client
        card_id = c.post("/api/character-library", json=_card_body()).json()["data"]["id"]
        r = c.put(f"/api/character-library/{card_id}", json=_card_body(
            name="苏晚晴", role="配角", genre="武侠", kind="挚友",
            dossier={"gender": "女", "age": "17"},
            cog={"s3": "来历成谜"},
        ))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["name"] == "苏晚晴" and data["rev"] == 2
        assert data["cog"] == {"s3": "来历成谜"}

    def test_delete_does_not_touch_book_card(self, client):
        c, seed = client
        card_id = c.post("/api/character-library", json=_card_body()).json()["data"]["id"]

        async def _count():
            async with async_session() as db:
                from sqlalchemy import select as sel
                rows = (await db.execute(sel(Character).where(
                    Character.novel_id == seed["novel_id"]))).scalars().all()
                return len(rows)

        before = _run(_count())
        assert c.delete(f"/api/character-library/{card_id}").status_code == 200
        assert _run(_count()) == before
        assert c.get(f"/api/character-library/{card_id}").status_code == 404

    def test_validation_rejects_unknown_cog_key(self, client):
        c, _ = client
        r = c.post("/api/character-library", json=_card_body(cog={"zz": "x"}))
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_cog"


class TestCollectAndSync:
    def test_collect_idempotent(self, client):
        c, seed = client
        body = {"novel_id": seed["novel_id"], "character_id": seed["char_id"]}
        first = c.post("/api/character-library/import/book", json=body).json()["data"]
        assert first["created"] is True
        assert first["card"]["name"] == "沈青崖"
        assert first["card"]["src"]["kind"] == "book"
        second = c.post("/api/character-library/import/book", json=body).json()["data"]
        assert second["created"] is False
        assert second["card"]["id"] == first["card"]["id"]
        assert c.get("/api/character-library").json()["data"]["count"] == 1

    def test_sync_pulls_book_fields_keeps_library_tags(self, client):
        c, seed = client
        body = {"novel_id": seed["novel_id"], "character_id": seed["char_id"]}
        card = c.post("/api/character-library/import/book", json=body).json()["data"]["card"]
        # 库里改分类；书里改语言特征
        card["kind"] = "其他"
        card["genre"] = "仙侠"
        c.put(f"/api/character-library/{card['id']}", json={
            "name": card["name"], "aliases": card["aliases"], "role": card["role"],
            "genre": "仙侠", "kind": "其他", "persona": card["persona"],
            "dossier": card["dossier"], "cog": card["cog"],
        })

        async def _edit_source():
            async with async_session() as db:
                ch = await db.get(Character, seed["char_id"])
                ch.dossier = json.dumps({"gender": "男", "age": "17", "speech": "急了才连成句"},
                                        ensure_ascii=False)
                ch.persona = "看山人独子（新版）"
                await db.commit()

        _run(_edit_source())
        synced = c.post(f"/api/character-library/{card['id']}/sync-from-book").json()["data"]
        assert synced["dossier"]["speech"] == "急了才连成句"
        assert synced["persona"] == "看山人独子（新版）"
        assert synced["genre"] == "仙侠" and synced["kind"] == "其他"  # 库分类不动

    def test_sync_source_gone(self, client):
        c, seed = client
        body = {"novel_id": seed["novel_id"], "character_id": seed["char_id"]}
        card = c.post("/api/character-library/import/book", json=body).json()["data"]["card"]

        async def _delete_char():
            async with async_session() as db:
                ch = await db.get(Character, seed["char_id"])
                await db.delete(ch)
                await db.commit()

        _run(_delete_char())
        r = c.post(f"/api/character-library/{card['id']}/sync-from-book")
        assert r.status_code == 410
        assert r.json()["detail"]["code"] == "source_gone"


class TestApplyToBook:
    def _make_card(self, c, **over):
        return c.post("/api/character-library", json=_card_body(**over)).json()["data"]

    def test_apply_copies_cog_and_resolves_name_conflict(self, client):
        c, seed = client
        card = self._make_card(c)
        # 书里先占一个同名角色 → 应自动后缀
        async def _occupy():
            async with async_session() as db:
                novel = await db.get(Novel, seed["novel_id"])
                novel.character_seq_high += 1
                db.add(Character(novel_id=novel.id, seq=novel.character_seq_high,
                                 name="秦重霄", role="反派"))
                await db.commit()
        _run(_occupy())
        r = c.post(f"/api/character-library/{card['id']}/apply-to-book",
                   json={"novel_id": seed["novel_id"]})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["name"].startswith("秦重霄（角色库")
        assert data["renamed"] is True

        async def _check():
            async with async_session() as db:
                ch = await db.get(Character, data["character_id"])
                return json.loads(ch.cog)
        assert _run(_check()) == {"b1": "暴躁易怒"}

    def test_apply_protagonist_demoted_when_book_has_one(self, client):
        c, seed = client
        card = self._make_card(c, role="主角", name="新主角")
        r = c.post(f"/api/character-library/{card['id']}/apply-to-book",
                   json={"novel_id": seed["novel_id"]})
        data = r.json()["data"]
        assert data["role"] == "配角" and data["demoted"] is True

        async def _protagonist():
            async with async_session() as db:
                from sqlalchemy import select as sel
                rows = (await db.execute(sel(Character).where(
                    Character.novel_id == seed["novel_id"],
                    Character.role == "主角"))).scalars().all()
                return [r.name for r in rows]
        assert _run(_protagonist()) == ["沈青崖"]  # 书内原主角未被降级

    def test_apply_unknown_novel_404(self, client):
        c, _ = client
        card = self._make_card(c)
        r = c.post(f"/api/character-library/{card['id']}/apply-to-book",
                   json={"novel_id": "no-such-novel"})
        assert r.status_code == 404


class TestRandomName:
    def test_fallback_returns_name_and_age(self, client):
        c, _ = client
        r = c.post("/api/character-library/random-name", json={"gender": "女"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert 2 <= len(data["name"]) <= 4
        assert 16 <= data["age"] <= 55
        assert data["source"] in ("ai", "local")


class TestBackup:
    def test_config_package_roundtrip_with_avatar(self, tmp_path, request):
        from backup.export import build_config_package_bytes
        from backup.importer import _restore_config

        suffix = uuid.uuid4().hex[:8]
        uid = f"chlibbk-{suffix}"
        uid2 = f"chlibbk2-{suffix}"

        async def _seed_users():
            async with async_session() as db:
                db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="库备份"))
                db.add(User(id=uid2, email=f"{uid2}@t.local", password_hash="x", display_name="库恢复"))
                db.add(CharacterLibrary(
                    id=f"lib-{suffix}", user_id=uid, name="秦重霄", role="反派",
                    genre="武侠", kind="敌人", persona="黑风寨大当家",
                    dossier=json.dumps({"gender": "男", "age": "42"}, ensure_ascii=False),
                    cog=json.dumps({"b1": "暴躁易怒"}, ensure_ascii=False),
                    src_kind="book", src_ref="n1", src_character_id="c1",
                    src_novel_name="剑照山河",
                ))
                db.add(CharacterLibraryBlob(library_id=f"lib-{suffix}", variant="full", data=b"FULLBYTES"))
                db.add(CharacterLibraryBlob(library_id=f"lib-{suffix}", variant="thumb", data=b"THUMB"))
                await db.commit()

        _run(_seed_users())

        async def _export():
            async with async_session() as db:
                return await build_config_package_bytes(db, uid)
        blob, _name = _run(_export())
        zf = zipfile.ZipFile(io.BytesIO(blob))
        cfg = yaml.safe_load(zf.read("config.yaml"))
        assert cfg["format_version"] == 8
        entry = cfg["character_library"][0]
        assert entry["name"] == "秦重霄" and entry["avatar"]["full"]["sha256"]
        assert f"character_library/avatars/lib-{suffix}-full.webp" in zf.namelist()

        # parse_package 会读头像字节；这里直接模拟导入端结构
        entry["avatar_data"] = {
            "full": zf.read(f"character_library/avatars/lib-{suffix}-full.webp"),
            "thumb": zf.read(f"character_library/avatars/lib-{suffix}-thumb.webp"),
        }

        # 模拟换机：新机库里没有源卡（否则按 id 冲突「忽略」语义会短路）
        async def _wipe_source():
            async with async_session() as db:
                from sqlalchemy import delete as _del
                await db.execute(_del(CharacterLibraryBlob).where(
                    CharacterLibraryBlob.library_id == f"lib-{suffix}"))
                await db.execute(_del(CharacterLibrary).where(
                    CharacterLibrary.id == f"lib-{suffix}"))
                await db.commit()
        _run(_wipe_source())

        async def _restore():
            async with async_session() as db:
                summary = await _restore_config(db, uid2, cfg)
                await db.commit()
                return summary
        summary = _run(_restore())
        assert summary["library"]["created"] == 1

        async def _verify():
            async with async_session() as db:
                card = await db.get(CharacterLibrary, f"lib-{suffix}")
                thumbs = (await db.execute(
                    __import__("sqlalchemy").select(CharacterLibraryBlob).where(
                        CharacterLibraryBlob.library_id == card.id)
                )).scalars().all()
                return card.user_id, {b.variant: b.data for b in thumbs}
        owner, blobs = _run(_verify())
        assert owner == uid2
        assert blobs == {"full": b"FULLBYTES", "thumb": b"THUMB"}


class TestMigrationManifest:
    def test_library_total_in_manifest(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "novel-v0.41.0.db"
        con = sqlite3.connect(db_path)
        con.execute("CREATE TABLE novels (id TEXT PRIMARY KEY, name TEXT, created_at TEXT)")
        con.execute("CREATE TABLE character_library (id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO character_library VALUES ('a')")
        con.execute("INSERT INTO character_library VALUES ('b')")
        con.commit()
        con.close()

        from db_lifecycle import _manifest_rows

        con = sqlite3.connect(db_path)
        try:
            rows = _manifest_rows(con, 10)
        finally:
            con.close()
        assert rows["library_total"] == 2

    def test_manifest_old_db_without_library_table(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "novel-v0.30.0.db"
        con = sqlite3.connect(db_path)
        con.execute("CREATE TABLE novels (id TEXT PRIMARY KEY, name TEXT, created_at TEXT)")
        con.commit()
        con.close()

        from db_lifecycle import _manifest_rows

        con = sqlite3.connect(db_path)
        try:
            rows = _manifest_rows(con, 10)
        finally:
            con.close()
        assert rows["library_total"] == 0
