"""角色库适配器回归钉（c-kb-character-migration 刀2c ①）。

存储已切 kb_entries（parity 由 test_character_library.py 全套原样跑绿背书）；
本文件钉适配器特有的坑——都是 parity 套件盖不住、真机才炸的：
- 收录头像字节落 KbEntryBlob（CharacterLibraryBlob 有真 FK，entry id 键插不进去）
- 迁移存量头像经 src_key 回联读（legacy 双源）
- 删卡双清头像字节；软删卡重新收录＝同键复活
- 新卡头像字节进配置包往返（yaml 元数据＋zip 独立条目）
"""

import asyncio
import hashlib
import io
import json
import uuid
import zipfile

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import select as sel

from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.character import Character
from models.character_library import CharacterLibrary, CharacterLibraryBlob
from models.image_asset import ImageAsset, ImageAssetBlob
from models.kb import KbEntry, KbEntryBlob
from models.project import Novel
from models.user import User


def _run(coro):
    return asyncio.run(coro)


async def _seed(with_character: bool = True, with_book_avatar: bool = False) -> dict:
    uid = f"kbadap-{uuid.uuid4().hex[:8]}"
    slug = f"kbadap-{uuid.uuid4().hex[:8]}"
    async with async_session() as db:
        db.add(User(
            id=uid, email=f"{uid}@t.local", password_hash="x", display_name="适配钉",
            api_key="", api_base_url="", api_model="",
        ))
        novel = Novel(
            user_id=uid, name="适配钉书", slug=slug, root_path=f"./data/{slug}",
            source="manual", current_phase="write",
        )
        db.add(novel)
        await db.flush()
        char_id = ""
        if with_character:
            char = Character(
                novel_id=novel.id, seq=1, name="沈青崖", role="主角",
                persona="看山人独子",
                dossier=json.dumps({"gender": "男", "age": "16"}, ensure_ascii=False),
                cog="{}",
            )
            db.add(char)
            await db.flush()
            char_id = char.id
            if with_book_avatar:
                full, thumb = b"ADAPT-FULL", b"ADAPT-THUMB"
                asset = ImageAsset(
                    id=f"avatar-{uuid.uuid4().hex[:8]}", user_id=uid, novel_id=novel.id,
                    character_id=char.id, kind="avatar", status="current", version=1,
                    sha256=hashlib.sha256(full).hexdigest(), mime="image/webp",
                    width=512, height=512, bytes=len(full), source="upload",
                    style_key="ink", prompt_hash="h", prompt_text="p",
                    negative_prompt="n", prompt_template_version=1, seed=1,
                )
                db.add(asset)
                await db.flush()
                db.add(ImageAssetBlob(asset_id=asset.id, variant="full", data=full))
                db.add(ImageAssetBlob(asset_id=asset.id, variant="thumb", data=thumb))
        novel.character_seq_high = 1 if with_character else 0
        await db.commit()
        return {"uid": uid, "novel_id": novel.id, "char_id": char_id}


@pytest.fixture
def client():
    seed = _run(_seed(with_book_avatar=True))

    async def _override():
        return {"id": seed["uid"]}

    app.dependency_overrides[get_current_user] = _override
    with TestClient(app) as c:
        yield c, seed
    app.dependency_overrides.clear()


class TestCollectAvatarNewTable:
    def test_collect_copies_avatar_into_kb_entry_blobs(self, client):
        c, seed = client
        r = c.post("/api/character-library/import/book", json={
            "novel_id": seed["novel_id"], "character_id": seed["char_id"],
        })
        assert r.status_code == 200, r.text
        card = r.json()["data"]["card"]
        assert card["avatar"]["has"] is True

        async def _check():
            async with async_session() as db:
                new_rows = (await db.execute(
                    sel(KbEntryBlob).where(
                        KbEntryBlob.entry_id == card["id"])
                )).scalars().all()
                legacy_rows = (await db.execute(
                    sel(CharacterLibraryBlob).where(
                        CharacterLibraryBlob.library_id == card["id"])
                )).scalars().all()
                return {b.variant: b.data for b in new_rows}, len(legacy_rows)

        blobs, legacy_n = _run(_check())
        assert blobs == {"full": b"ADAPT-FULL", "thumb": b"ADAPT-THUMB"}
        assert legacy_n == 0  # 主表停写，头像也不再落 legacy 表（按本卡键核对）

        served = c.get(f"/api/character-library/{card['id']}/avatar?variant=thumb")
        assert served.status_code == 200 and served.content == b"ADAPT-THUMB"


class TestLegacyAvatarRelink:
    def test_migrated_card_serves_avatar_via_src_key(self):
        """迁移卡（src_ref=character_library）头像仍住 CharacterLibraryBlob：
        读写走 entry id，字节经 src_key 回联。"""
        suffix = uuid.uuid4().hex[:8]
        uid = f"kbaleg-{suffix}"
        old_card_id = f"lib-{suffix}"

        async def _seed():
            async with async_session() as db:
                db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x",
                            display_name="回联钉"))
                db.add(CharacterLibrary(
                    id=old_card_id, user_id=uid, name="秦重霄", role="反派",
                    persona="黑风寨大当家。",
                    dossier=json.dumps({"gender": "男"}, ensure_ascii=False), cog="{}",
                    src_kind="book", src_ref="n1", src_character_id="c1",
                ))
                await db.flush()
                db.add(CharacterLibraryBlob(library_id=old_card_id, variant="full", data=b"OLD-FULL"))
                db.add(CharacterLibraryBlob(library_id=old_card_id, variant="thumb", data=b"OLD-THUMB"))
                await db.commit()
                from kb.migrate_library import migrate_character_library

                r = await migrate_character_library(db, user_id=uid)
                assert r["migrated"] == 1
                row = (await db.execute(
                    sel(KbEntry).where(KbEntry.user_id == uid)
                )).scalars().one()
                return row.id

        entry_id = _run(_seed())

        async def _override():
            return {"id": uid}

        app.dependency_overrides[get_current_user] = _override
        try:
            with TestClient(app) as c:
                listed = c.get("/api/character-library").json()["data"]
                assert listed["count"] == 1
                item = listed["items"][0]
                assert item["avatar"]["has"] is True  # legacy 回联命中
                assert item["avatar"]["url"].endswith(f"/{entry_id}/avatar?variant=full")
                body = c.get(f"/api/character-library/{entry_id}/avatar?variant=full")
                assert body.status_code == 200 and body.content == b"OLD-FULL"
        finally:
            app.dependency_overrides.clear()


class TestDeleteAndRevive:
    def test_delete_clears_blobs_then_recollect_revives(self, client):
        c, seed = client
        body = {"novel_id": seed["novel_id"], "character_id": seed["char_id"]}
        card = c.post("/api/character-library/import/book", json=body).json()["data"]["card"]

        assert c.delete(f"/api/character-library/{card['id']}").status_code == 200

        async def _blobs_left():
            async with async_session() as db:
                rows = (await db.execute(
                    sel(KbEntryBlob).where(KbEntryBlob.entry_id == card["id"])
                )).scalars().all()
                return len(rows)

        assert _run(_blobs_left()) == 0  # 删卡双清：新表字节跟着走

        # 软删卡重新收录：unique 键被占 → 复活而非重插
        again = c.post("/api/character-library/import/book", json=body).json()["data"]
        assert again["created"] is True
        assert again["card"]["id"] == card["id"]  # 同一条目复活
        assert c.get("/api/character-library").json()["data"]["count"] == 1


class TestBackupRoundtripEntryBlobs:
    def test_kb_entry_avatar_survives_config_package(self, tmp_path):
        suffix = uuid.uuid4().hex[:8]
        uid = f"kbabk-{suffix}"
        uid2 = f"kbabk2-{suffix}"
        entry_id = f"ent-{suffix}"

        async def _seed():
            async with async_session() as db:
                db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x",
                            display_name="字节备份"))
                db.add(User(id=uid2, email=f"{uid2}@t.local", password_hash="x",
                            display_name="字节恢复"))
                db.add(KbEntry(
                    id=entry_id, user_id=uid, genre="", concept="角色设定",
                    concept_id=":角色设定", title="秦重霄",
                    payload_json=json.dumps({"archetype": "秦重霄"}, ensure_ascii=False),
                    instruction="黑风寨大当家。",
                ))
                db.add(KbEntryBlob(entry_id=entry_id, variant="full", data=b"ZIP-FULL"))
                db.add(KbEntryBlob(entry_id=entry_id, variant="thumb", data=b"ZIP-THUMB"))
                await db.commit()

        _run(_seed())

        async def _export():
            from backup.export import build_config_package_bytes

            async with async_session() as db:
                return await build_config_package_bytes(db, uid)
        blob, _name = _run(_export())
        zf = zipfile.ZipFile(io.BytesIO(blob))
        assert f"kb/entry-avatars/{entry_id}-full.webp" in zf.namelist()
        assert zf.read(f"kb/entry-avatars/{entry_id}-thumb.webp") == b"ZIP-THUMB"
        cfg = yaml.safe_load(zf.read("config.yaml"))
        meta = cfg["knowledge_base"]["entry_blobs"]
        assert {"entry_id": entry_id, "variant": "full"} in meta  # yaml 只留元数据
        assert all("data" not in row for row in meta)

        # 恢复走 parse_package 真链路（字节注入正是它做的）
        pkg = tmp_path / "config-backup.zip"
        pkg.write_bytes(blob)
        from backup.importer import parse_package

        cfg = parse_package([str(pkg)])["config"]
        assert cfg["knowledge_base"]["entry_blobs"][0]["data"] == b"ZIP-FULL"

        # 模拟换机：清源（共享库 db.get 不分用户，源行在会让「同 id 忽略」短路）
        async def _wipe_source():
            from sqlalchemy import delete as _del

            async with async_session() as db:
                await db.execute(_del(KbEntryBlob).where(KbEntryBlob.entry_id == entry_id))
                await db.execute(_del(KbEntry).where(KbEntry.id == entry_id))
                await db.commit()
        _run(_wipe_source())

        async def _restore():
            from backup.importer import _restore_config

            async with async_session() as db:
                summary = await _restore_config(db, uid2, cfg)
                await db.commit()
                return summary
        summary = _run(_restore())
        assert summary["knowledge_base"]["entry_blobs"]["created"] == 2

        async def _verify():
            async with async_session() as db:
                rows = (await db.execute(
                    sel(KbEntryBlob).where(
                        KbEntryBlob.entry_id == entry_id)
                )).scalars().all()
                return {b.variant: b.data for b in rows}
        assert _run(_verify()) == {"full": b"ZIP-FULL", "thumb": b"ZIP-THUMB"}
