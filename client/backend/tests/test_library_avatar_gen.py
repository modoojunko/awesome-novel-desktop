"""库卡头像生成测试（c-library-avatar-gen）：prompt 组装/成功落图/缺配置/供应商失败/档位门。"""

import asyncio
import io
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api_configs.crypto import encrypt_api_key
from auth_local.deps import require_tier_access
from auth_local.middleware import get_current_user
from db import async_session
from image_assets import adapters as image_adapters
from image_assets.adapters import GeneratedImage, ImageProviderError
from image_assets.prompt_builder import build_library_avatar_prompt
from main import app
from models.character_library import CharacterLibrary, CharacterLibraryBlob
from models.image_asset import ImageConfig
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _webp(color=(120, 60, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="WEBP")
    return buf.getvalue()


async def _seed(with_config: bool = True) -> dict:
    uid = f"libav-{uuid.uuid4().hex[:8]}"
    cid = str(uuid.uuid4())
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="头像生成"))
        await db.flush()  # users 先落（image_configs.user_id FK）
        db.add(CharacterLibrary(
            id=cid, user_id=uid, name="秦重霄", aliases=json.dumps(["大当家"], ensure_ascii=False),
            role="反派", genre="武侠", kind="敌人", persona="黑风寨大当家，暴躁记仇",
            dossier=json.dumps({
                "gender": "男", "age": "42", "race": "人族",
                "look": "络腮胡，左颊刀疤", "faction": "黑风寨", "speech": "骂人",
            }, ensure_ascii=False),
        ))
        if with_config:
            db.add(ImageConfig(
                user_id=uid, name="图像配置", provider="volcengine",
                base_url="https://ark.example.com/v3", api_key=encrypt_api_key("test-key"),
                default_model="doubao-seedream", models="[]",
                declared_capabilities="{}", is_default=True, status="active",
            ))
        await db.commit()
    return {"uid": uid, "card_id": cid}


@pytest.fixture
def client():
    seed = _run(_seed())

    async def _override():
        return {"id": seed["uid"]}

    app.dependency_overrides[get_current_user] = _override
    app.dependency_overrides[require_tier_access] = lambda: True
    with TestClient(app) as c:
        yield c, seed
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_tier_access, None)


class TestPrompt:
    def test_library_prompt_uses_card_fields_and_redacts_name(self):
        seed = _run(_seed())

        async def _build():
            async with async_session() as db:
                card = await db.get(CharacterLibrary, seed["card_id"])
                return await build_library_avatar_prompt(db, seed["uid"], card)

        prompt = _run(_build())
        assert prompt["provider"] == "volcengine"
        assert prompt["model"] == "doubao-seedream"
        assert "络腮胡" in prompt["prompt"]
        assert "秦重霄" not in prompt["prompt"] and "大当家" not in prompt["prompt"]
        assert prompt["sources"]["library_card_id"] == seed["card_id"]

    def test_no_config_prompt_has_empty_provider(self):
        seed = _run(_seed(with_config=False))

        async def _build():
            async with async_session() as db:
                card = await db.get(CharacterLibrary, seed["card_id"])
                return await build_library_avatar_prompt(db, seed["uid"], card)

        assert _run(_build())["provider"] is None


class TestGenerate:
    def _mock_provider(self, monkeypatch, result):
        calls: dict = {}

        async def fake_generate_images(*, base_url, api_key, spec):
            calls.update(base_url=base_url, api_key=api_key, spec=spec)
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(image_adapters, "generate_images", fake_generate_images)
        return calls

    def test_success_writes_blobs_and_bumps_rev(self, client, monkeypatch):
        c, seed = client
        calls = self._mock_provider(
            monkeypatch, [GeneratedImage(data=_webp(), native_width=1024, native_height=1024)]
        )
        r = c.post(f"/api/character-library/{seed['card_id']}/avatar/generate", json={})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["avatar"]["has"] is True and data["rev"] == 2
        assert calls["spec"].kind == "avatar" and calls["spec"].n == 1
        assert calls["api_key"] == "test-key"
        assert calls["base_url"] == "https://ark.example.com/v3"

        async def _blobs():
            async with async_session() as db:
                rows = (await db.execute(
                    __import__("sqlalchemy").select(CharacterLibraryBlob).where(
                        CharacterLibraryBlob.library_id == seed["card_id"])
                )).scalars().all()
                return {b.variant: b.data for b in rows}

        blobs = _run(_blobs())
        assert set(blobs) == {"full", "thumb"}
        # 头像端点可读
        r2 = c.get(f"/api/character-library/{seed['card_id']}/avatar?variant=thumb")
        assert r2.status_code == 200 and r2.headers["content-type"] == "image/webp"
        assert r2.content == blobs["thumb"]

    def test_no_image_config_400(self, monkeypatch):
        seed = _run(_seed(with_config=False))

        async def _override():
            return {"id": seed["uid"]}

        app.dependency_overrides[get_current_user] = _override
        app.dependency_overrides[require_tier_access] = lambda: True
        try:
            with TestClient(app) as c:
                r = c.post(f"/api/character-library/{seed['card_id']}/avatar/generate", json={})
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(require_tier_access, None)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "no_image_config"

    def test_provider_error_502(self, client, monkeypatch):
        c, seed = client
        self._mock_provider(
            monkeypatch, ImageProviderError("auth", "图像配置缺少 API Key")
        )
        r = c.post(f"/api/character-library/{seed['card_id']}/avatar/generate", json={})
        assert r.status_code == 502
        assert "图像生成失败" in r.json()["detail"]["message"]

    def test_empty_images_502(self, client, monkeypatch):
        c, seed = client
        self._mock_provider(monkeypatch, [])
        r = c.post(f"/api/character-library/{seed['card_id']}/avatar/generate", json={})
        assert r.status_code == 502

    def test_service_timeout_maps_to_readable(self, client, monkeypatch):
        c, seed = client

        async def _slow(*args, **kwargs):
            raise TimeoutError()

        # wait_for 包裹：直接把 generate_images 换成永不返回的协程即可触发超时，
        # 这里用超时异常路径验证映射（timeout 文案）
        monkeypatch.setattr(image_adapters, "generate_images", _slow)
        r = c.post(f"/api/character-library/{seed['card_id']}/avatar/generate", json={})
        assert r.status_code == 502
        assert "超时" in r.json()["detail"]["message"]
