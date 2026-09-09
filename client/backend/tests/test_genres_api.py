"""题材库 CRUD 契约测试（TestClient，隔离临时 DB）。

覆盖：预置 seed（数量/只读标记）、幂等、POST→GET→PUT→DELETE 全链路、
重复 id 409、非法 id 422、预置 403、缺失 404、被引用删除 409（projects 列表）、
去鉴权 401。Auth/permission 依赖 override，真实业务逻辑运行。
"""

import asyncio
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB) ───────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_genres_api.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_genres_api_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from auth_local.deps import require_ai_access, require_project_limit
from auth_local.middleware import get_current_user
from db import Base, async_session, engine, get_db
from genres.presets import PRESET_GENRES
from genres.service import ensure_seed_genres, list_genres
from main import app
from models.user import User

# ── Helpers ───────────────────────────────────────────────────────────────


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _create_user(user_id: str) -> str:
    async with async_session() as session:
        session.add(
            User(
                id=user_id,
                email=f"{user_id}@test.com",
                password_hash="*",
                display_name=user_id,
            )
        )
        await session.commit()
    return user_id


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    _run_async(_create_tables())
    _run_async(_create_user("genuser"))
    _run_async(ensure_seed_genres())
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "genuser"}


async def _override_true():
    return True


@pytest.fixture(autouse=True)
def _setup_overrides():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_ai_access] = _override_true
    app.dependency_overrides[require_project_limit] = _override_true
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ── Seed ──────────────────────────────────────────────────────────────────


class TestGenreSeed:
    def test_list_includes_seeded_presets(self, client):
        r = client.get("/api/genres")
        assert r.status_code == 200, r.text
        genres = r.json()
        assert len(genres) >= len(PRESET_GENRES)
        # 逐一校验 24 个预置题材：存在、isPreset、category 与 seed 数据一致
        # （只按预置 id 断言，容忍共享 DB 里其他测试创建的自定义题材）
        for preset in PRESET_GENRES:
            found = next((g for g in genres if g["id"] == preset["id"]), None)
            assert found is not None, f"预置题材缺失: {preset['id']}"
            assert found["isPreset"] is True, preset["id"]
            assert found["category"] == preset["category"], preset["id"]

    def test_seed_is_idempotent(self):
        async def _count() -> int:
            async with async_session() as s:
                return len(await list_genres(s))

        before = _run_async(_count())
        _run_async(ensure_seed_genres())
        after = _run_async(_count())
        assert after == before
        assert before >= len(PRESET_GENRES)


# ── CRUD 全链路 ──────────────────────────────────────────────────────────


class TestGenreCRUD:
    def test_create_get_update_delete_roundtrip(self, client):
        body = {
            "id": "my-custom-genre",
            "name": "自定义题材",
            "category": "urban",
            "description": "测试自定义题材",
            "narratorRole": "贴近主角的第三人称",
            "promptInjection": "[测试基调] 保持真实",
            "taboos": ["俗套"],
            "toneBlueprint": {
                "defaultTone": "温暖",
                "atmosphereOptions": ["温馨"],
                "povOptions": ["第一人称"],
                "techniqueTags": ["细节"],
            },
            "genreConfig": {
                "fulfillmentTypes": ["成长"],
                "chapterTypes": ["日常"],
                "pacingRules": ["每章一个场景"],
                "fatigueWords": ["突然"],
            },
            "storyArcTemplates": [
                {"id": "a1", "name": "成长弧", "description": "d", "beats": ["b1"]}
            ],
        }
        r = client.post("/api/genres", json=body)
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["id"] == "my-custom-genre"
        assert created["isPreset"] is False
        assert created["name"] == "自定义题材"

        r2 = client.get("/api/genres/my-custom-genre")
        assert r2.status_code == 200, r2.text
        assert r2.json()["narratorRole"] == "贴近主角的第三人称"
        assert r2.json()["genreConfig"]["fatigueWords"] == ["突然"]

        r3 = client.put(
            "/api/genres/my-custom-genre", json={**body, "name": "改名字"}
        )
        assert r3.status_code == 200, r3.text
        assert r3.json()["name"] == "改名字"
        assert r3.json()["isPreset"] is False

        r4 = client.delete("/api/genres/my-custom-genre")
        assert r4.status_code == 200, r4.text
        assert r4.json()["ok"] is True

        r5 = client.get("/api/genres/my-custom-genre")
        assert r5.status_code == 404

    def test_minimal_create(self, client):
        """只填必填字段（id/name/category）也能创建，其余走默认。"""
        r = client.post(
            "/api/genres",
            json={"id": "minimal-genre", "name": "最小", "category": "scifi"},
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["description"] == ""
        assert data["taboos"] == []
        assert data["toneBlueprint"] == {}
        assert data["genreConfig"] == {}

    def test_create_duplicate_id_409(self, client):
        body = {"id": "dup-genre", "name": "重复", "category": "urban"}
        assert client.post("/api/genres", json=body).status_code == 201
        r = client.post("/api/genres", json=body)
        assert r.status_code == 409

    def test_create_invalid_id_422(self, client):
        r = client.post(
            "/api/genres", json={"id": "Bad_ID", "name": "非法", "category": "urban"}
        )
        assert r.status_code == 422

    def test_create_invalid_category_422(self, client):
        r = client.post(
            "/api/genres", json={"id": "bad-cat", "name": "非法", "category": "cooking"}
        )
        assert r.status_code == 422

    def test_get_missing_404(self, client):
        r = client.get("/api/genres/does-not-exist")
        assert r.status_code == 404


# ── 预置只读 ─────────────────────────────────────────────────────────────


class TestGenrePresetReadOnly:
    def test_update_preset_403(self, client):
        r = client.put(
            "/api/genres/urban-daily",
            json={"id": "urban-daily", "name": "改", "category": "urban"},
        )
        assert r.status_code == 403

    def test_delete_preset_403(self, client):
        r = client.delete("/api/genres/urban-daily")
        assert r.status_code == 403


# ── 被引用删除保护 ───────────────────────────────────────────────────────


class TestGenreDeleteReferenceGuard:
    def test_delete_referenced_409_with_projects(self, client):
        gid = "referenced-genre"
        r = client.post(
            "/api/genres", json={"id": gid, "name": "被引用", "category": "urban"}
        )
        assert r.status_code == 201, r.text

        name = f"ref-test-{uuid.uuid4().hex[:6]}"
        rp = client.post("/api/novels", json={"name": name})
        assert rp.status_code in (200, 201), rp.text
        pid = rp.json()["id"]
        rs = client.put(f"/api/novels/{pid}/settings/genre", json={"core_promise": "x"})
        assert rs.status_code in (200, 201), rs.text

        # genre-signup-redesign 6.6：本书题材改五字段契约、不再经 genre_id 引用题材库
        # → _find_referencing_projects 恒空，引用 guard 停用，删除直接成功
        r = client.delete(f"/api/genres/{gid}")
        assert r.status_code == 200, r.text

        # 删除未引用自定义题材仍成功（对照组）
        r2 = client.post(
            "/api/genres", json={"id": "unreferenced-genre", "name": "未引用", "category": "urban"}
        )
        assert r2.status_code == 201
        r3 = client.delete("/api/genres/unreferenced-genre")
        assert r3.status_code == 200


# ── 鉴权 ─────────────────────────────────────────────────────────────────


class TestGenreAuth:
    def test_unauthorized_401(self, client):
        app.dependency_overrides.pop(get_current_user, None)
        try:
            r = client.get("/api/genres")
            assert r.status_code in (401, 403)
        finally:
            app.dependency_overrides[get_current_user] = _override_current_user
