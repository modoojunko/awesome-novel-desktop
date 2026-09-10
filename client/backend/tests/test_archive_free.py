"""Change 002 — 免费归档测试（TE-03 P0 部分）

免费用户无 API Key：归档 200 + AI 摘要降级为正文前 200 字、归档列表/读取免费可用、
新书（settings 阶段）归档不 500（N9）、B4 回归（gate_archived 认 .md 后归档不再提示未归档）。

用法：
    cd client/backend
    python -m pytest tests/test_archive_free.py -v
"""

import asyncio
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB) ───────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_archive_free.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_archive_free_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")


def _set_tier(tier: str, expires_at: str = "", api_key: str = ""):
    _service.CONFIG_FILE = _CFG_PATH
    _service.save_local_config(
        {"tier": tier, "expires_at": expires_at, "api_key": api_key}
    )


def _future_iso(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


from auth_local.deps import require_novel_model, require_project_limit
from auth_local.middleware import get_current_user
from db import Base, async_session, engine, get_db
from main import app
from models.user import User


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
    _run_async(_create_user("archuser"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "archuser"}


async def _override_true():
    return True


@pytest.fixture(autouse=True)
def _setup_overrides():
    # 不覆盖 require_ai_access：证明归档端点在无 AI 权限时可用（N9）。
    # 覆盖 require_project_limit：项目配额非本 change 范围，会话共享 DB 使项目跨测试残留。
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    # 本书模型门控：本模块测的是内容/其他门控，模型就绪另测（9.2）
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = _override_true
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_config_after():
    yield
    if os.path.exists(_CFG_PATH):
        os.remove(_CFG_PATH)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _create_sparse_project(client) -> str:
    name = f"arch-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), f"Create failed: {r.text}"
    return r.json()["id"]


def _create_volume_and_chapter(client, pid: str) -> str:
    r = client.post(
        f"/api/novels/{pid}/volumes", json={"vol_num": 1, "title": "Volume 1"}
    )
    assert r.status_code in (200, 201), f"Volume failed: {r.text}"
    r2 = client.post(
        f"/api/novels/{pid}/volumes/{r.json()['ref']}/chapters",
        json={"title": "第1章"},
    )
    assert r2.status_code in (200, 201), f"Chapter failed: {r2.text}"
    return r2.json()["chapter_ref"]


LONG_TEXT = "（归档正文）灯火在雨里摇晃，她合上日志，决定明日启程。行囊里只有半册旧书，与一枚磨亮的铜哨。" * 20


class TestFreeArchive:
    def test_free_archive_without_key_200_and_summary_degrade(self, client):
        # 无 API Key → get_ai_client 抛错 → 摘要降级为正文前 200 字，不 500
        _set_tier("none", api_key="")
        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive", json={"full_text": LONG_TEXT}
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["summary"] == LONG_TEXT[:200]

    def test_free_list_and_read_archives(self, client):
        _set_tier("none", api_key="")
        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive", json={"full_text": LONG_TEXT}
        )
        assert r.status_code == 200, r.text
        filename = r.json()["archive_path"].split("/")[-1]

        r2 = client.get(f"/api/novels/{pid}/archives")
        assert r2.status_code == 200
        assert any(f["filename"] == filename for f in r2.json())

        r3 = client.get(f"/api/novels/{pid}/archives/{filename}")
        assert r3.status_code == 200, r3.text
        assert r3.json()["content"] == LONG_TEXT

    def test_new_book_settings_phase_archive_no_500(self, client):
        # N9：新书（settings 阶段）免费归档 —— tier_phase_transition force，不抛 ValueError
        # （settings→archive 为非法流转，修复前 update_phase 抛 ValueError → 500）。
        # 不建卷/章，current_phase 停留 settings。
        _set_tier("none", api_key="")
        pid = _create_sparse_project(client)
        r0 = client.get(f"/api/novels/{pid}")
        assert r0.status_code == 200
        assert r0.json()["current_phase"] == "settings"

        r = client.post(
            f"/api/novels/{pid}/chapters/vol-1-ch-1/archive",
            json={"full_text": LONG_TEXT},
        )
        assert r.status_code == 200, r.text

        r1 = client.get(f"/api/novels/{pid}")
        assert r1.json()["current_phase"] == "archive"

    def test_pro_archive_phase_status_no_archive_warning(self, client):
        # B4 回归：gate_archived 认 .md —— 归档后 phase-status 不再提示 "no chapters archived yet"
        _set_tier("none", api_key="")
        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive", json={"full_text": LONG_TEXT}
        )
        assert r.status_code == 200, r.text

        _set_tier("monthly", _future_iso())
        r2 = client.get(f"/api/novels/{pid}/workflow/phase-status")
        assert r2.status_code == 200
        warnings = r2.json().get("warnings", [])
        assert not any("no chapters archived yet" in w["message"] for w in warnings)

    def test_pro_manual_first_archive_outline_phase_no_500(self, client):
        # 用户真实场景：PRO 直接写第一章（建卷建章后 phase 停在 outline，手工保存正文
        # 不推进 phase）→ 点归档。修复前 tier_phase_transition 走 update_phase 严格校验，
        # outline→archive 非法 → ValueError → 500。修复后归档内容驱动（≥100 字已校验），
        # phase 仅记账，force 置 archive。
        _set_tier("monthly", _future_iso())
        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r0 = client.get(f"/api/novels/{pid}")
        assert r0.status_code == 200
        assert r0.json()["current_phase"] == "outline"

        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive", json={"full_text": LONG_TEXT}
        )
        assert r.status_code == 200, r.text

        r1 = client.get(f"/api/novels/{pid}")
        assert r1.json()["current_phase"] == "archive"
