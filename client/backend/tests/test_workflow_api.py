"""Workflow + chapter confirm + settings AI contract tests (TestClient).

Replaces the old live-API test_api.py with isolated TestClient tests that
don't depend on a running server or DEV_MODE. Auth/permission dependencies
are overridden; real business logic (gates, transitions, validation) runs.

Usage:
    cd client/backend
    python -m pytest tests/test_workflow_api.py -v
"""

import asyncio
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB) ───────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_workflow.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_workflow_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

# Change 002：无 config 默认免费旁路。本模块断言真实 gate 拦截（不完整章节 400），
# 故显式以付费套餐运行（gate 拦截仅在 tier_bypass=False 时生效）。
import auth_local.service as _auth_service
from auth_local.deps import (
    require_ai_access,
    require_novel_model,
    require_project_limit,
)
from auth_local.middleware import get_current_user
from db import Base, async_session, engine, get_db
from main import app
from models.user import User

_PRO_CFG_PATH = os.path.join(_tmp_data_root, "config.json")

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
    _run_async(_create_user("wfuser"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "wfuser"}


async def _override_true():
    return True


@pytest.fixture(autouse=True)
def _setup_overrides():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_ai_access] = _override_true
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = _override_true
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _pro_tier():
    """Change 002 适配：写付费套餐 config.json，使真实 gate 拦截生效。"""
    _auth_service.CONFIG_FILE = _PRO_CFG_PATH
    _auth_service.save_local_config(
        {
            "tier": "monthly",
            "expires_at": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
            "api_key": "",
        }
    )
    yield
    if os.path.exists(_PRO_CFG_PATH):
        os.remove(_PRO_CFG_PATH)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ── Settings priming (mirror gate_settings_complete requirements) ─────────


def _prime_settings(client, pid: str):
    client.put(
        f"/api/novels/{pid}/settings/world",
        json={
            "name": "Test World",
            "summary": "A test world for workflow testing",
            "geography": {"scenes": "王国", "climate": "温带", "limits": ""},
            "politics": {"rule": "君主制", "factions": "", "social": "", "cost": ""},
            "rules": {"world": "", "society": "", "personal": ""},
        },
    )
    client.put(
        f"/api/novels/{pid}/settings/hooks",
        json={
            "active": [
                {"id": "hook-1", "description": "First hook", "introduced_in": "1-1", "status": "pending"},
                {"id": "hook-2", "description": "Second hook", "introduced_in": "1-1", "status": "pending"},
                {"id": "hook-3", "description": "Third hook", "introduced_in": "1-1", "status": "pending"},
            ]
        },
    )
    # synopsis / genre（PRD 3.4 判定口径对齐；transition 走软门控不 assert warnings，语义安全）
    client.put(f"/api/novels/{pid}/story", json={"synopsis": "A test synopsis"})
    client.put(f"/api/novels/{pid}/settings/genre", json={"genre_id": "fantasy"})


def _create_project_and_chapter(client) -> tuple[str, str]:
    """Create project + volume + fully-filled chapter. Returns (project_id, chapter_ref)."""
    name = f"wf-test-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), f"Create project failed: {r.text}"
    pid = r.json()["id"]

    _prime_settings(client, pid)

    r2 = client.post(
        f"/api/novels/{pid}/volumes",
        json={"vol_num": 1, "title": "Volume 1"},
    )
    assert r2.status_code in (200, 201), f"Create volume failed: {r2.text}"

    r3 = client.post(
        f"/api/novels/{pid}/volumes/{r2.json()['ref']}/chapters",
        json={"title": "第1章"},
    )
    assert r3.status_code in (200, 201), f"Create chapter failed: {r3.text}"
    chapter_ref = r3.json()["chapter_ref"]

    update_body = {
        "segments": [{"type": "narration", "content": "test"}],
        "emotional_design": {"primary_mood": "紧张"},
        "memo": {
            "current_task": "完成本章",
            "reader_expectation": {
                "state": "好奇",
                "strategy": "铺垫伏笔",
                "detail": "让读者想知道接下来发生了什么",
            },
            "payoff_plan": {"must_resolve": [], "must_hold": [], "partial_advance": []},
            "downtime_functions": [],
            "key_choices": [],
            "required_changes": ["调整节奏"],
            "prohibitions": [],
        },
    }
    r4 = client.put(
        f"/api/novels/{pid}/chapters/{chapter_ref}",
        json=update_body,
    )
    assert r4.status_code == 200, f"Update chapter failed: {r4.text}"
    return pid, chapter_ref


# ── Chapter confirm ──────────────────────────────────────────────────────


class TestChapterConfirm:
    def test_confirm_chapter_sets_status(self, client):
        pid, chapter_ref = _create_project_and_chapter(client)
        r = client.post(f"/api/novels/{pid}/chapters/{chapter_ref}/confirm")
        assert r.status_code == 200, f"Confirm failed: {r.text}"
        assert r.json()["status"] == "confirmed"
        # confirm 不前进阶段，仍为 outline
        r2 = client.get(f"/api/novels/{pid}")
        assert r2.status_code == 200
        assert r2.json()["current_phase"] == "outline"

    def test_confirm_incomplete_chapter_returns_400(self, client):
        name = f"wf-incomplete-{uuid.uuid4().hex[:6]}"
        r = client.post("/api/novels", json={"name": name})
        assert r.status_code in (200, 201)
        pid = r.json()["id"]
        _prime_settings(client, pid)
        vol_res = client.post(
            f"/api/novels/{pid}/volumes", json={"vol_num": 1, "title": "Volume 1"}
        )
        r2 = client.post(
            f"/api/novels/{pid}/volumes/{vol_res.json()['ref']}/chapters",
            json={"title": "第1章"},
        )
        assert r2.status_code in (200, 201)
        chapter_ref = r2.json()["chapter_ref"]
        # 不填充必填字段直接 confirm -> 400
        r3 = client.post(f"/api/novels/{pid}/chapters/{chapter_ref}/confirm")
        assert r3.status_code == 400
        assert "章纲确认失败" in r3.text

    def test_confirm_unauthorized_returns_401(self, client):
        app.dependency_overrides.pop(get_current_user, None)
        try:
            r = client.post("/api/novels/nonexistent/chapters/vol-1-ch-1/confirm")
            assert r.status_code in (401, 403)
        finally:
            app.dependency_overrides[get_current_user] = _override_current_user


# ── Workflow transition ──────────────────────────────────────────────────


class TestWorkflowTransition:
    def test_transition_all_chapters_ready(self, client):
        pid, chapter_ref = _create_project_and_chapter(client)
        client.post(f"/api/novels/{pid}/chapters/{chapter_ref}/confirm")
        r = client.post(f"/api/novels/{pid}/workflow/transition", json={"target": "prompt"})
        assert r.status_code == 200, f"Transition failed: {r.text}"
        data = r.json()
        assert data["ok"] is True
        assert data["phase"] == "prompt"

    def test_transition_with_incomplete_chapter_returns_400(self, client):
        pid, _ = _create_project_and_chapter(client)
        # 第二个章节不填充必填字段
        r = client.post(
            f"/api/novels/{pid}/volumes/vol-1/chapters",
            json={"title": "第2章"},
        )
        assert r.status_code in (200, 201)
        r2 = client.post(f"/api/novels/{pid}/workflow/transition", json={"target": "prompt"})
        assert r2.status_code == 400
        assert "not ready" in r2.text.lower() or "failures" in r2.text.lower()

    def test_transition_missing_target_returns_400(self, client):
        pid, _ = _create_project_and_chapter(client)
        r = client.post(f"/api/novels/{pid}/workflow/transition", json={})
        assert r.status_code == 400
        assert "target is required" in r.text.lower()

    def test_transition_unsupported_target_returns_400(self, client):
        pid, _ = _create_project_and_chapter(client)
        r = client.post(
            f"/api/novels/{pid}/workflow/transition",
            json={"target": "invalid_target"},
        )
        assert r.status_code == 400
        assert "unsupported target" in r.text.lower()

    def test_transition_unauthorized_returns_401(self, client):
        app.dependency_overrides.pop(get_current_user, None)
        try:
            r = client.post(
                "/api/novels/nonexistent/workflow/transition",
                json={"target": "prompt"},
            )
            assert r.status_code in (401, 403)
        finally:
            app.dependency_overrides[get_current_user] = _override_current_user


# ── Settings AI field generation ──────────────────────────────────────────


class TestSettingsAIFieldGenerate:
    def test_field_generate_invalid_type_returns_400(self, client):
        name = f"AINovel-{uuid.uuid4().hex[:6]}"
        r = client.post("/api/novels", json={"name": name})
        assert r.status_code in (200, 201)
        pid = r.json()["id"]
        # anti-ai 不在 FIELD_GENERATABLE 中 -> 400 not supported
        r2 = client.post(
            f"/api/novels/{pid}/settings/ai/anti-ai/some-field",
            json={"context": {}},
        )
        assert r2.status_code == 400
        assert "not supported" in str(r2.json().get("detail", "")).lower()


# ── 导入持久化往返（persist → 读回）──────────────────────────────────────


class TestImportPersist:
    def test_persist_then_read_chapter(self, client):
        """导入入库后按 vol-N-ch-M 约定可读回章节正文。"""
        r = client.post(
            "/api/novels/import/persist",
            json={
                "name": "导入测试",
                "volumes": [
                    {
                        "title": "第一卷",
                        "chapters": [{"title": "第一章", "content": "正文内容"}],
                    }
                ],
            },
        )
        assert r.status_code == 201, f"Persist failed: {r.text}"
        novel_id = r.json()["id"]

        # 项目可查
        r2 = client.get(f"/api/novels/{novel_id}")
        assert r2.status_code == 200

        # 章节按数字约定 vol-1-ch-1 读回
        r3 = client.get(f"/api/novels/{novel_id}/chapters/vol-1-ch-1")
        assert r3.status_code == 200, f"Chapter read failed: {r3.text}"
        assert r3.json().get("prose") == "正文内容"

    def test_persist_writes_volume_file_by_number(self, client):
        """卷文件必须写为 vol-{N}.yaml，与 create_volume 约定一致。"""

        r = client.post(
            "/api/novels/import/persist",
            json={
                "name": "卷名测试",
                "volumes": [
                    {
                        "title": "第一卷 风云",
                        "chapters": [{"title": "第一章", "content": "内容"}],
                    }
                ],
            },
        )
        assert r.status_code == 201, r.text
        # 从项目详情/tree 确认卷结构（persist 返回不含 root_path）
        novel_id = r.json()["id"]
        tree = client.get(f"/api/novels/{novel_id}/tree")
        assert tree.status_code == 200
        vols = tree.json().get("volumes", [])
        assert vols and vols[0].get("ref") == "vol-1"


# ── Novel 查询/删除（by-slug / delete）──────────────────────────────────


class TestNovelQueries:
    def test_get_by_slug(self, client):
        name = f"slug-test-{uuid.uuid4().hex[:6]}"
        r = client.post("/api/novels", json={"name": name})
        assert r.status_code in (200, 201), f"Create failed: {r.text}"
        slug = r.json()["slug"]
        r2 = client.get(f"/api/novels/by-slug/{slug}")
        assert r2.status_code == 200, f"by-slug failed: {r2.text}"
        assert r2.json()["name"] == name

    def test_delete_project(self, client):
        name = f"delete-me-{uuid.uuid4().hex[:6]}"
        r = client.post("/api/novels", json={"name": name})
        assert r.status_code in (200, 201)
        pid = r.json()["id"]
        r2 = client.delete(f"/api/novels/{pid}")
        assert r2.status_code in (200, 204), f"Delete failed: {r2.text}"
        # 删除后列表不含该项目
        r3 = client.get("/api/novels")
        assert r3.status_code == 200
        assert all(p["id"] != pid for p in r3.json())


# ── update_phase 幂等性（阶段机 self-transition）────────────────────────


class TestUpdatePhaseIdempotency:
    def test_self_transition_is_noop(self):
        """重新生成提示词等操作类场景：prompt→prompt 不抛错、状态不变。"""
        import types

        from workflow.engine import update_phase

        project = types.SimpleNamespace(current_phase="prompt")
        update_phase(project, "prompt")  # 不应抛 ValueError
        assert project.current_phase == "prompt"

    def test_illegal_transition_still_rejected(self):
        """真正的非法流转（init→write）仍被阶段机拒绝。"""
        import types

        import pytest

        from workflow.engine import update_phase

        project = types.SimpleNamespace(current_phase="init")
        with pytest.raises(ValueError):
            update_phase(project, "write")
        assert project.current_phase == "init"

    def test_legal_transition_still_works(self):
        """合法流转（outline→prompt）不受幂等化影响。"""
        import types

        from workflow.engine import update_phase

        project = types.SimpleNamespace(current_phase="outline")
        update_phase(project, "prompt")
        assert project.current_phase == "prompt"
