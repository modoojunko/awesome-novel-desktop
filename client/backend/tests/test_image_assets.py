"""c-cover-avatar 阶段 1：配置 CRUD、上传/采用/撤销/签名读取、每书绑定。

不触发生成/测试/试画；全部用临时库与本地 TestClient。
"""

import asyncio
import io
import os
import tempfile
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

_tmp_db = tempfile.NamedTemporaryFile(suffix="_image_assets.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_image_assets_")

import json

from api_configs.crypto import init_crypto
from auth_local.middleware import get_current_user
from db import Base, async_session, engine, get_db
from filesystem.storage import get_storage
from image_assets import service as img_svc
from main import app
from models.app_meta import AppMeta
from models.character import Character
from models.image_asset import ImageAsset, ImageAssetBlob
from models.novel_genre import NovelGenre
from models.project import Novel
from models.user import User

USER_ID = "imguser"


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        await init_crypto(session)
        session.add(User(id=USER_ID, email="img@test.com", password_hash="*", display_name="img"))
        await session.flush()
        session.add(Novel(
            id="novel-img", user_id=USER_ID, name="图像测试书",
            slug="novel-img", root_path="./data/novel-img",
        ))
        await session.flush()
        session.add(Character(id="char-img", novel_id="novel-img", seq=1, name="陈屿", role="主角"))
        session.add(User(id="other", email="other@test.com", password_hash="*", display_name="other"))
        session.add(User(id="cfguser", email="cfg@test.com", password_hash="*", display_name="cfg"))
        await session.flush()
        session.add(Novel(
            id="novel-other", user_id="other", name="别人的书",
            slug="novel-other", root_path="./data/novel-other",
        ))
        await session.flush()
        session.add(Character(
            id="char-other", novel_id="novel-other", seq=1, name="别人的角色", role="主角",
        ))
        await session.commit()


async def _override_db():
    async with async_session() as session:
        yield session


async def _override_user():
    return {"id": USER_ID}


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    _run(_setup())
    yield


@pytest.fixture(autouse=True)
def overrides():
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _png(w=800, h=600, color=(40, 90, 80)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _config(client, name=None, **kw):
    body = {
        "name": name or f"主线 · {uuid.uuid4().hex[:6]}", "provider": "volcengine",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_key": "sk-test-1234567890", "default_model": "doubao-seedream-4-0-250828",
        "models": ["doubao-seedream-4-0-250828"],
    }
    body.update(kw)
    r = client.post("/api/image-configs", json=body)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _upload(client, kind="cover", character_id=None):
    data = {"kind": kind}
    if character_id:
        data["character_id"] = character_id
    r = client.post(
        "/api/novels/novel-img/image-assets",
        data=data,
        files={"file": ("a.png", _png(), "image/png")},
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_config_crud_default_and_soft_delete(client):
    c1 = _config(client, "主线 · 火山引擎")
    assert c1["api_key_masked"].startswith("sk-test")
    assert "*" in c1["api_key_masked"]
    c2 = _config(client, "备用 · 阿里云", provider="aliyun", api_key="sk-ali-1234567890")
    r = client.put(f"/api/image-configs/{c2['id']}", json={"is_default": True})
    assert r.status_code == 200, r.text
    rows = client.get("/api/image-configs").json()["data"]
    by_id = {x["id"]: x for x in rows}
    assert by_id[c2["id"]]["is_default"] is True
    assert by_id[c1["id"]]["is_default"] is False
    # 软删 + 同名重建（复活，不撞 UNIQUE(user_id,name)）
    assert client.delete(f"/api/image-configs/{c1['id']}").status_code == 200
    revived = _config(client, "主线 · 火山引擎")
    assert revived["id"] == c1["id"]
    # restore 已激活的应报 400
    assert client.post(f"/api/image-configs/{c1['id']}/restore").status_code == 400


def test_upload_adopt_undo_and_signed_read(client):
    asset = _upload(client, "cover")
    assert asset["kind"] == "cover"
    assert asset["status"] == "candidate"
    assert asset["width"] == 768 and asset["height"] == 1024
    links = asset["links"]
    assert links["full"].startswith("/api/image-assets/")
    r = client.get(links["full"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert r.headers["x-content-type-options"] == "nosniff"
    # 坏签名 403
    assert client.get(links["full"] + "x").status_code == 403
    # 采用
    adopted = client.post(f"/api/image-assets/{asset['asset_id']}/adopt").json()["data"]
    assert adopted["status"] == "current"
    token = adopted["undo_token"]
    assert token
    # 第二张采用 → 第一张 previous
    second = _upload(client, "cover")
    adopted2 = client.post(f"/api/image-assets/{second['asset_id']}/adopt").json()["data"]
    assert adopted2["version"] == 2
    # 撤销第二张 → 第一张回到 current
    und = client.post(f"/api/image-assets/{second['asset_id']}/undo", json={"token": adopted2["undo_token"]})
    assert und.status_code == 200, und.text
    assert und.json()["data"]["restored_asset_id"] == asset["asset_id"]
    assert _blob_count(second["asset_id"]) == 0
    # 第一张的撤销 token 已失效（它重新 current 但 token 被清）
    assert client.post(f"/api/image-assets/{asset['asset_id']}/undo", json={"token": token}).status_code == 409


def test_avatar_requires_character_and_upload(client):
    r = client.post(
        "/api/novels/novel-img/image-assets",
        data={"kind": "avatar"},
        files={"file": ("a.png", _png(), "image/png")},
    )
    assert r.status_code == 400
    asset = _upload(client, "avatar", character_id="char-img")
    assert asset["kind"] == "avatar"
    assert asset["character_id"] == "char-img"
    assert asset["width"] == 512 and asset["height"] == 512


def test_book_and_character_apis_include_images(client):
    cover = _upload(client, "cover")
    client.post(f"/api/image-assets/{cover['asset_id']}/adopt")
    detail = client.get("/api/novels/novel-img").json()
    assert detail["cover"]["asset_id"] == cover["asset_id"]
    assert detail["cover"]["thumb_url"].startswith("/api/image-assets/")
    books = client.get("/api/novels").json()
    book = next(b for b in books if b["id"] == "novel-img")
    assert book["cover"]["asset_id"] == cover["asset_id"]
    by_slug = client.get("/api/novels/by-slug/novel-img").json()
    assert by_slug["cover"]["asset_id"] == cover["asset_id"]

    avatar = _upload(client, "avatar", character_id="char-img")
    client.post(f"/api/image-assets/{avatar['asset_id']}/adopt")
    rows = client.get("/api/novels/novel-img/characters").json()["data"]["items"]
    row = next(c for c in rows if c["id"] == "char-img")
    assert row["avatar"]["asset_id"] == avatar["asset_id"]
    card = client.get("/api/novels/novel-img/characters/char-img").json()["data"]
    assert card["avatar"]["asset_id"] == avatar["asset_id"]


def test_delete_book_and_character_cascade_assets(client):
    async def _seed():
        async with async_session() as session:
            session.add(Novel(id="novel-del", user_id=USER_ID, name="删书测试",
                              slug="novel-del", root_path="./data/novel-del"))
            await session.flush()
            session.add(Character(id="char-del", novel_id="novel-del", seq=1, name="删角", role="配角"))
            await session.commit()

    async def _count(novel_id=None, character_id=None):
        async with async_session() as session:
            q = select(ImageAsset)
            if novel_id:
                q = q.where(ImageAsset.novel_id == novel_id)
            if character_id:
                q = q.where(ImageAsset.character_id == character_id)
            return len((await session.execute(q)).scalars().all())

    _run(_seed())
    c = _config(client)
    client.put("/api/novels/novel-del/image-settings", json={
        "style_key": "ink", "cover_prompt": "", "image_config_id": c["id"],
        "image_model": "doubao-seedream-4-0-250828",
    })
    cover = client.post(
        "/api/novels/novel-del/image-assets", data={"kind": "cover"},
        files={"file": ("a.png", _png(), "image/png")},
    ).json()["data"]
    avatar = client.post(
        "/api/novels/novel-del/image-assets", data={"kind": "avatar", "character_id": "char-del"},
        files={"file": ("a.png", _png(), "image/png")},
    ).json()["data"]
    client.post(f"/api/image-assets/{cover['asset_id']}/adopt")
    client.post(f"/api/image-assets/{avatar['asset_id']}/adopt")
    assert _run(_count(character_id="char-del")) == 1
    assert client.delete("/api/novels/novel-del/characters/char-del").status_code == 200
    assert _run(_count(character_id="char-del")) == 0
    assert _run(_count(novel_id="novel-del")) == 1  # 封面仍在
    assert client.delete("/api/novels/novel-del").status_code == 200
    assert _run(_count(novel_id="novel-del")) == 0


def test_prompt_uses_book_and_character_whitelists(client):
    c = _config(client)
    assert client.put("/api/novels/novel-img/image-settings", json={
        "style_key": "ink", "cover_prompt": "陈屿在夜里提一盏旧风灯",
        "image_config_id": c["id"], "image_model": "doubao-seedream-4-0-250828",
    }).status_code == 200
    assert client.put("/api/novels/novel-img/characters/char-img/image-settings", json={
        "avatar_prompt": "瘦高的陈屿，站在灯下",
    }).status_code == 200

    async def _seed():
        async with async_session() as session:
            storage = get_storage()
            await storage.write_yaml("./data/novel-img", "story.yaml", {
                "genre": "悬疑", "sub_genre": "民俗",
                "synopsis": "旧货街的夜明铺传了三代。",
            })
            await storage.write_yaml("./data/novel-img", "settings/world-setting.yaml", {
                "stage": "图像测试书里的雾津旧城，陈屿守着夜明铺，江雾终年不散", "no_power": True,
            })
            ch = await session.get(Character, "char-img")
            ch.persona = "陈屿守着夜明铺的年轻人，替人还灯。"
            ch.dossier = json.dumps({
                "gender": "男", "age": "27", "race": "汉",
                "look": "瘦高，指节有灯油烫痕", "faction": "夜明铺",
                "background": "SPOILER_BG", "plot": "SPOILER_PLOT",
            })
            session.add(NovelGenre(novel_id="novel-img", core_promise="替人还灯，也替人藏事"))
            await session.commit()

    _run(_seed())
    cover = client.get("/api/novels/novel-img/image-prompt").json()["data"]
    assert "悬疑" in cover["prompt"] and "替人还灯" in cover["prompt"]
    assert "SPOILER" not in cover["prompt"]
    assert "图像测试书" not in cover["prompt"]  # 书名只进 sources，不进画面
    assert "陈屿" not in cover["prompt"]  # 名字藏在 world_stage 也要脱敏
    assert "旧货街" not in cover["prompt"]  # 简介原文不当场景
    assert "。。" not in cover["prompt"]
    assert "没有任何文字" in cover["prompt"]  # 正向无文字，不只靠 negative
    assert cover["sources"]["theme"] == "悬疑 · 民俗"
    assert cover["sources"]["name"] == "图像测试书"
    assert cover["negative_prompt"] and "水印" in cover["negative_prompt"]
    assert cover["prompt_template_version"] == 3
    assert cover["size"] == {"width": 768, "height": 1024}
    assert cover["seed_source"] == "derived"  # 种子不再由用户提供，恒按书 id 派生
    assert cover["candidate_seeds"] == [cover["seed"], (cover["seed"] + 1) % 2**31]
    assert cover["model"] == "doubao-seedream-4-0-250828"
    assert cover["capabilities"]["negative_supported"] is True
    assert len(cover["prompt_hash"]) == 64
    assert client.get("/api/novels/novel-img/image-prompt").json()["data"]["prompt_hash"] == cover["prompt_hash"]

    # canonical hash 必须对 prompt 敏感（seed 恒派生，hash 变化只随画面/画风/模型）
    client.put("/api/novels/novel-img/image-settings", json={
        "style_key": "ink", "cover_prompt": "陈屿在夜里提一盏旧风灯，灯芯将尽",
        "image_config_id": c["id"], "image_model": "doubao-seedream-4-0-250828",
    })
    cover2 = client.get("/api/novels/novel-img/image-prompt").json()["data"]
    assert cover2["prompt_hash"] != cover["prompt_hash"]
    assert cover2["seed"] == cover["seed"]  # seed 不随设置漂移

    avatar = client.get("/api/novels/novel-img/characters/char-img/image-prompt").json()["data"]
    assert "瘦高" in avatar["prompt"] and "夜明铺" in avatar["prompt"]
    assert "SPOILER_BG" not in avatar["prompt"] and "SPOILER_PLOT" not in avatar["prompt"]
    assert "陈屿" not in avatar["prompt"]  # 角色名只进 sources
    assert "近景头肩像" in avatar["prompt"] and "只到肩部" in avatar["prompt"]
    assert "没有任何文字" in avatar["prompt"]
    assert "。。" not in avatar["prompt"]
    assert avatar["seed_source"] == "derived" and avatar["style_key"] == "ink"
    assert avatar["negative_prompt"] and avatar["prompt_template_version"] == 3
    assert "旧货街" not in avatar["prompt"]



def test_book_and_character_image_settings(client):
    c = _config(client)
    r = client.put("/api/novels/novel-img/image-settings", json={
        "style_key": "ink", "cover_prompt": "夜里的灯",
        "image_config_id": c["id"], "image_model": "doubao-seedream-4-0-250828",
    })
    assert r.status_code == 200, r.text
    data = client.get("/api/novels/novel-img/image-settings").json()["data"]
    assert data["image_config_id"] == c["id"]
    assert data["cover_prompt"] == "夜里的灯"
    assert data["effective_image_config_id"] == c["id"]
    assert data["effective_image_model"] == "doubao-seedream-4-0-250828"
    assert data["effective_source"] == "explicit"
    # PATCH 只改模型，不得清掉画风/描述
    assert client.patch("/api/novels/novel-img/image-settings", json={
        "image_model": "doubao-seedream-4-5-251128",
    }).status_code == 200
    patched = client.get("/api/novels/novel-img/image-settings").json()["data"]
    assert patched["style_key"] == "ink"
    assert patched["cover_prompt"] == "夜里的灯"
    assert patched["image_model"] == "doubao-seedream-4-5-251128"
    r = client.put("/api/novels/novel-img/characters/char-img/image-settings", json={
        "avatar_prompt": "瘦高的年轻人",
    })
    assert r.status_code == 200, r.text
    assert r.json()["data"]["avatar_prompt"] == "瘦高的年轻人"
    # PATCH 只改描述，返回形状完好（种子字段已退役）
    assert client.patch(
        "/api/novels/novel-img/characters/char-img/image-settings",
        json={"avatar_prompt": "瘦高的中年人"},
    ).status_code == 200
    got = client.get(
        "/api/novels/novel-img/characters/char-img/image-settings"
    ).json()["data"]
    assert got["avatar_prompt"] == "瘦高的中年人" and "seed" not in got
    assert client.put("/api/novels/novel-img/image-settings", json={
        "style_key": "not-a-style", "cover_prompt": "",
    }).status_code == 400



def _set_asset(asset_id, **fields):
    async def _do():
        async with async_session() as session:
            asset = await session.get(ImageAsset, asset_id)
            assert asset is not None
            for key, value in fields.items():
                setattr(asset, key, value)
            await session.commit()
    _run(_do())


def _asset_row(asset_id):
    async def _do():
        async with async_session() as session:
            return await session.get(ImageAsset, asset_id)
    return _run(_do())


def _blob_count(asset_id):
    async def _do():
        async with async_session() as session:
            return len((await session.execute(
                select(ImageAssetBlob).where(ImageAssetBlob.asset_id == asset_id)
            )).scalars().all())
    return _run(_do())


def _signing_key_row():
    async def _do():
        async with async_session() as session:
            return (await session.execute(
                select(AppMeta).where(AppMeta.key == img_svc.SIGNING_KEY_ROW)
            )).scalar_one_or_none()
    return _run(_do())


def test_character_routes_are_scoped_to_owner(client):
    avatar = _upload(client, "avatar", character_id="char-img")
    client.post(f"/api/image-assets/{avatar['asset_id']}/adopt")

    original = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: {"id": "other"}
    try:
        assert client.get("/api/novels/novel-img/characters").status_code == 404
        assert client.get("/api/novels/novel-img/characters/char-img").status_code == 404
        assert client.delete("/api/novels/novel-img/characters/char-img").status_code == 404
        settings = client.get("/api/novels/novel-img/characters/char-img/image-settings")
        assert settings.status_code == 400
        assert client.get("/api/novels/novel-img/image-settings").status_code == 400
        assert client.post(
            f"/api/image-assets/{avatar['asset_id']}/adopt"
        ).status_code == 400
    finally:
        app.dependency_overrides[get_current_user] = original

    # 越权删除失败后，卡和头像都还在
    card = client.get("/api/novels/novel-img/characters/char-img")
    assert card.status_code == 200
    assert card.json()["data"]["avatar"]["asset_id"] == avatar["asset_id"]


def test_asset_ttl_and_adopt_state_machine(client):
    candidate = _upload(client, "cover")
    _set_asset(candidate["asset_id"], expires_at=img_svc.now_utc() - timedelta(minutes=1))
    r = client.post(f"/api/image-assets/{candidate['asset_id']}/adopt")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "asset_expired"

    async def _sweep():
        async with async_session() as session:
            return await img_svc.sweep_expired_assets(session)

    assert _run(_sweep()) >= 1
    assert _asset_row(candidate["asset_id"]) is None
    assert _blob_count(candidate["asset_id"]) == 0

    first = _upload(client, "cover")
    adopted = client.post(f"/api/image-assets/{first['asset_id']}/adopt")
    assert adopted.status_code == 200
    # current 不能重复 adopt
    again = client.post(f"/api/image-assets/{first['asset_id']}/adopt")
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "asset_not_candidate"

    second = _upload(client, "cover")
    assert client.post(f"/api/image-assets/{second['asset_id']}/adopt").status_code == 200
    # previous 也不能再 adopt（旧实现会 500）
    previous = client.post(f"/api/image-assets/{first['asset_id']}/adopt")
    assert previous.status_code == 409
    assert previous.json()["detail"]["code"] == "asset_not_candidate"

    # 撤销窗口过期必须拒绝
    third = _upload(client, "cover")
    adopted3 = client.post(f"/api/image-assets/{third['asset_id']}/adopt").json()["data"]
    # 采用第三张时，第二张变 previous、第一张作为更早 previous 被物理删除
    assert _blob_count(first["asset_id"]) == 0
    _set_asset(third["asset_id"], undo_expires_at=img_svc.now_utc() - timedelta(seconds=1))
    expired = client.post(
        f"/api/image-assets/{third['asset_id']}/undo",
        json={"token": adopted3["undo_token"]},
    )
    assert expired.status_code == 409
    assert expired.json()["detail"]["code"] == "undo_expired"


def test_upload_format_asset_listing_and_signed_cache(client):
    gif = io.BytesIO()
    Image.new("RGB", (800, 600), (100, 100, 100)).save(gif, format="GIF")
    bad = client.post(
        "/api/novels/novel-img/image-assets",
        data={"kind": "cover"},
        files={"file": ("a.gif", gif.getvalue(), "image/gif")},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "unsupported_format"

    asset = _upload(client, "cover")
    assert asset["asset_id"] and "url_expires_at" in asset
    candidates = client.get(
        "/api/novels/novel-img/image-assets",
        params={"kind": "cover", "status": "candidate", "limit": 100},
    ).json()["data"]
    assert asset["asset_id"] in {a["asset_id"] for a in candidates}

    client.post(f"/api/image-assets/{asset['asset_id']}/adopt")
    candidates = client.get(
        "/api/novels/novel-img/image-assets",
        params={"kind": "cover", "status": "candidate", "limit": 100},
    ).json()["data"]
    assert asset["asset_id"] not in {a["asset_id"] for a in candidates}
    current = client.get(
        "/api/novels/novel-img/image-assets",
        params={"kind": "cover", "status": "current", "limit": 100},
    ).json()["data"]
    assert asset["asset_id"] in {a["asset_id"] for a in current}

    read = client.get(asset["links"]["full"])
    assert read.status_code == 200
    assert "immutable" not in read.headers["cache-control"]
    assert "max-age=3300" in read.headers["cache-control"]
    assert _signing_key_row() is not None


def test_deleted_config_listing_and_binding_cleanup(client):
    cfg = _config(client)
    assert client.put("/api/novels/novel-img/image-settings", json={
        "style_key": "ink", "cover_prompt": "绑定测试",
        "image_config_id": cfg["id"], "image_model": "doubao-seedream-4-0-250828",
    }).status_code == 200
    deleted_resp = client.delete(f"/api/image-configs/{cfg['id']}")
    assert deleted_resp.status_code == 200
    assert deleted_resp.json()["data"]["affected_book_count"] == 1
    active = client.get("/api/image-configs").json()["data"]
    assert cfg["id"] not in {c["id"] for c in active}
    all_rows = client.get(
        "/api/image-configs", params={"include_deleted": "true"}
    ).json()["data"]
    deleted = next(c for c in all_rows if c["id"] == cfg["id"])
    assert deleted["status"] == "deleted"
    settings = client.get("/api/novels/novel-img/image-settings").json()["data"]
    assert settings["image_config_id"] is None


def test_first_config_default_and_default_promotion(client):
    original = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: {"id": "cfguser"}
    try:
        first = _config(client, "第一套")
        assert first["is_default"] is True
        second = _config(client, "第二套", provider="aliyun")
        assert second["is_default"] is False
        deleted = client.delete(f"/api/image-configs/{first['id']}").json()["data"]
        assert deleted["default_image_config_id"] == second["id"]
        rows = client.get("/api/image-configs").json()["data"]
        assert next(c for c in rows if c["id"] == second["id"])["is_default"] is True
    finally:
        app.dependency_overrides[get_current_user] = original


def test_links_refresh_delete_candidate_and_utc_times(client):
    asset = _upload(client, "cover")
    assert asset["expires_at"].endswith("Z")
    assert asset["url_expires_at"].endswith("Z")
    assert asset["url"].startswith("/api/image-assets/")
    assert asset["links"]["full"] == asset["url"]

    links = client.get(f"/api/image-assets/{asset['asset_id']}/links")
    assert links.status_code == 200, links.text
    assert links.json()["data"]["url_expires_at"].endswith("Z")
    assert links.json()["data"]["links"]["full"].startswith("/api/image-assets/")

    # 候选可丢弃，BLOB 一起清
    assert client.delete(f"/api/image-assets/{asset['asset_id']}").status_code == 200
    assert _asset_row(asset["asset_id"]) is None
    assert _blob_count(asset["asset_id"]) == 0
    assert client.get(f"/api/image-assets/{asset['asset_id']}/links").status_code == 400

    current = _upload(client, "cover")
    adopted = client.post(f"/api/image-assets/{current['asset_id']}/adopt").json()["data"]
    assert adopted["undo_expires_at"].endswith("Z")
    assert client.delete(f"/api/image-assets/{current['asset_id']}").status_code == 409


def test_signing_key_missing_degrades_images_not_bookshelf(client):
    asset = _upload(client, "cover")
    client.post(f"/api/image-assets/{asset['asset_id']}/adopt")
    links = asset["links"]

    async def _drop_key():
        async with async_session() as session:
            row = (await session.execute(
                select(AppMeta).where(AppMeta.key == img_svc.SIGNING_KEY_ROW)
            )).scalar_one()
            await session.delete(row)
            await session.commit()

    _run(_drop_key())
    books = client.get("/api/novels")
    assert books.status_code == 200, books.text
    book = next(b for b in books.json() if b["id"] == "novel-img")
    assert book["cover"] is None
    assert client.get(links["full"]).status_code == 503

    # 写路径可重建密钥，恢复图像能力
    recovered = _upload(client, "cover")
    assert recovered["asset_id"]
    assert _signing_key_row() is not None


def test_undo_when_previous_cleaned_keeps_current(client):
    first = _upload(client, "cover")
    client.post(f"/api/image-assets/{first['asset_id']}/adopt")
    second = _upload(client, "cover")
    adopted = client.post(f"/api/image-assets/{second['asset_id']}/adopt").json()["data"]
    # 上一张被提前清理（模拟 sweep/丢失）
    assert client.delete(f"/api/image-assets/{first['asset_id']}").status_code == 200
    r = client.post(
        f"/api/image-assets/{second['asset_id']}/undo",
        json={"undo_token": adopted["undo_token"]},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "undo_expired"
    still = client.get(
        "/api/novels/novel-img/image-assets",
        params={"kind": "cover", "status": "current", "limit": 100},
    ).json()["data"]
    assert second["asset_id"] in {a["asset_id"] for a in still}


def test_concurrent_adopt_same_candidate_has_one_winner(client):
    asset = _upload(client, "cover")

    async def _adopt():
        async with async_session() as session:
            return await img_svc.adopt_asset(session, USER_ID, asset["asset_id"])

    async def _race():
        return await asyncio.gather(_adopt(), _adopt(), return_exceptions=True)

    results = _run(_race())
    conflicts = [r for r in results if isinstance(r, img_svc.Conflict)]
    wins = [r for r in results if not isinstance(r, Exception)]
    assert len(wins) <= 1
    assert len(conflicts) >= 1
    row = _asset_row(asset["asset_id"])
    assert row is not None and row.status == "current"


def test_sweep_does_not_delete_current(client):
    first = _upload(client, "cover")
    client.post(f"/api/image-assets/{first['asset_id']}/adopt")
    second = _upload(client, "cover")
    client.post(f"/api/image-assets/{second['asset_id']}/adopt")
    # first 是 previous；把它的保留窗口改成已过期后 sweep，second 不能受影响
    _set_asset(first["asset_id"], expires_at=img_svc.now_utc() - timedelta(seconds=1))

    async def _sweep():
        async with async_session() as session:
            return await img_svc.sweep_expired_assets(session)

    _run(_sweep())
    assert _asset_row(first["asset_id"]) is None
    row = _asset_row(second["asset_id"])
    assert row is not None and row.status == "current"


def test_image_validation_and_non_ascii_signature(client):
    # 种子字段已退役：老客户端残留的 cover_seed 被静默忽略（不再 422 也不再落库）
    r = client.put("/api/novels/novel-img/image-settings", json={
        "style_key": "ink", "cover_prompt": "", "cover_seed": -1,
    })
    assert r.status_code == 200
    assert "cover_seed" not in client.get(
        "/api/novels/novel-img/image-settings"
    ).json()["data"]

    asset = _upload(client, "cover")
    bad = client.get(asset["links"]["full"] + "汉字")
    assert bad.status_code == 403
    assert bad.json()["detail"]["code"] == "signature_invalid"


# ── 封面画面 AI 提取（c-cover-scene-extract）────────────────────────────────


def test_cover_scene_material_and_parse(client):
    """collect_material 只取书级白名单素材并截断；parse_scene 严进严出。"""
    from image_assets import cover_extract as cx

    async def _material():
        async with async_session() as session:
            storage = get_storage()
            await storage.write_yaml("./data/novel-img", "story.yaml", {
                "genre": "悬疑", "sub_genre": "都市怪谈",
                "synopsis": "末班公交总多停一站。",
                "story_arc": {"fullstory": "司机老周追查多停的一站，发现乘客都带着同一天的记忆。"},
            })
            await storage.write_yaml("./data/novel-img", "settings/world-setting.yaml", {
                "stage": "近现代都市，深夜公交网里藏着一条通往旧日的线路", "no_power": True,
            })
            novel = await session.get(Novel, "novel-img")
            return await cx.collect_material(session, novel)

    material = _run(_material())
    assert material["theme"] == "悬疑（都市怪谈）"
    assert "同一天的记忆" in material["fullstory"]
    assert "通往旧日的线路" in material["world_stage"]

    scene = cx.parse_scene(json.dumps({"scene": "x" * 500}, ensure_ascii=False))
    assert len(scene) == cx.SCENE_MAX  # 超长场景截断
    for bad in ("不是json", "[]", json.dumps({"scene": "  "})):
        try:
            cx.parse_scene(bad)
            raise AssertionError("应拒收")
        except Exception as e:
            assert getattr(e, "status_code", None) == 502


@pytest.mark.needs_prompts
def test_cover_scene_extract_happy_path(client, monkeypatch):
    from auth_local.deps import require_tier_access
    from image_assets import cover_extract as cx
    from image_assets import router as img_router

    app.dependency_overrides[require_tier_access] = lambda: True

    async def _gate(db, user_id, project_id):
        return True

    monkeypatch.setattr(img_router, "ensure_novel_model_ready", _gate)
    captured: list = []

    class _Fake:
        async def chat(self, **kwargs):
            captured.append(kwargs)
            return json.dumps({
                "scene": "深夜站台，末班公交的剪影驶近，车灯在湿漉漉的路面拖出两道黄光。",
            }, ensure_ascii=False)

    async def _fake(novel_id):
        return _Fake()

    monkeypatch.setattr(cx, "get_ai_client_for_novel", _fake)

    r = client.post("/api/novels/novel-img/image-prompt/cover-extract")
    assert r.status_code == 200, r.text
    assert "末班公交" in r.json()["data"]["scene"]
    assert captured[0]["json_mode"] is True
    prompt = captured[0]["messages"][0]["content"]
    assert "悬疑（都市怪谈）" in prompt  # 选题进素材
    assert "同一天的记忆" in prompt  # 主线进素材
    app.dependency_overrides.pop(require_tier_access, None)


@pytest.mark.needs_prompts
def test_cover_scene_extract_bad_json_502(client, monkeypatch):
    from auth_local.deps import require_tier_access
    from image_assets import cover_extract as cx
    from image_assets import router as img_router

    app.dependency_overrides[require_tier_access] = lambda: True

    async def _gate(db, user_id, project_id):
        return True

    monkeypatch.setattr(img_router, "ensure_novel_model_ready", _gate)

    class _Fake:
        async def chat(self, **kwargs):
            return "我觉得这张封面应该画一个站台（自然语言，不是 JSON）"

    async def _fake(novel_id):
        return _Fake()

    monkeypatch.setattr(cx, "get_ai_client_for_novel", _fake)

    r = client.post("/api/novels/novel-img/image-prompt/cover-extract")
    assert r.status_code == 502
    assert "可重试" in r.json()["detail"]
    app.dependency_overrides.pop(require_tier_access, None)


def test_cover_scene_extract_model_gate_503(client):
    """书未配写作模型：门控在端点内直调 ensure_novel_model_ready，503 引导。"""
    from auth_local.deps import require_tier_access

    app.dependency_overrides[require_tier_access] = lambda: True
    r = client.post("/api/novels/novel-img/image-prompt/cover-extract")
    assert r.status_code == 503
    assert "reason" in r.json()["detail"]
    app.dependency_overrides.pop(require_tier_access, None)


def test_cover_scene_extract_other_users_novel_404(client):
    from auth_local.deps import require_tier_access

    app.dependency_overrides[require_tier_access] = lambda: True
    r = client.post("/api/novels/novel-other/image-prompt/cover-extract")
    assert r.status_code == 404
    app.dependency_overrides.pop(require_tier_access, None)
