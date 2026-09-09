"""主线拆纲（story-arc-planning）测试：

- GET/PUT /api/novels/{id}/story/arc — 主线卡整存整取 + next_step 续步推断
- readiness 「story-arc」项 — 空卡 missing / 填卡通过 / 后卷待定口径
- PUT /settings/status/story-arc — 空卡 400，填卡可确认
- POST /api/novels/{id}/story/arc/wizard/{step} — 免费 403 / 会员 200（AI 打桩）/
  空 input 400 / 未知 step 400 / 坏 JSON 500

用法：
    cd client/backend
    python -m pytest tests/test_story_arc.py -v
"""

import asyncio
import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB) ───────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_story_arc.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_story_arc_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")
# 占位 Key（非真实凭据）：拼接构造，避免任何真实密钥形态的字面量
_FAKE_KEY = "".join(("sk-", "test-placeholder"))  # noqa: FLY002


def _set_tier(tier: str, expires_at: str = "", api_key: str = ""):
    _service.CONFIG_FILE = _CFG_PATH
    cfg = _service.get_local_config()
    cfg.update({"tier": tier, "expires_at": expires_at, "api_key": api_key})
    _service.save_local_config(cfg)


def _future_iso(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


from auth_local.deps import require_novel_model
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
    _run_async(_create_user("arcuser"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "arcuser"}


@pytest.fixture(autouse=True)
def _setup_overrides():
    # 不覆盖 require_ai_access：向导端点要测真实会员门控
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    # 本书模型门控：本模块测的是内容/其他门控，模型就绪另测（9.2）
    app.dependency_overrides[require_novel_model] = lambda: True
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_config():
    yield
    if os.path.exists(_CFG_PATH):
        os.remove(_CFG_PATH)


@pytest.fixture
def client():
    # 默认会员 + 占位 Key（向导 happy path 可过门控；AI client 由各用例打桩）
    _set_tier("monthly", _future_iso(), api_key=_FAKE_KEY)
    with TestClient(app) as c:
        yield c


def _create_project(client) -> str:
    import uuid

    r = client.post("/api/novels", json={"name": f"arc-test-{uuid.uuid4().hex[:6]}"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _member_project(client) -> str:
    return _create_project(client)


ARC_FULL = {
    "premise": "陆征追查苏棠失踪案，发现三年前旧案被压，越查越深触及警队内部势力",
    "ending": {"scene": "侦探所里看着旧卷宗", "hero": "破案但心里装了更多", "tone": "苍凉但平静"},
    "volumes": [
        {"title": "失踪", "conflict": "追查失踪案发现旧案被压", "chapters": "10"},
        {"title": "待定", "conflict": "待定", "chapters": "?"},
    ],
}


# ── 主线卡读写 ────────────────────────────────────────────────────────────


class TestArcEndpoints:
    def test_get_empty_arc(self, client):
        pid = _create_project(client)
        r = client.get(f"/api/novels/{pid}/story/arc")
        assert r.status_code == 200
        data = r.json()
        assert data["premise"] == ""
        assert data["ending"] == {"scene": "", "hero": "", "tone": ""}
        assert data["volumes"] == []
        assert data["next_step"] == 1
        assert data["has_content"] is False

    def test_put_roundtrip_and_next_step(self, client):
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/story/arc", json=ARC_FULL)
        assert r.status_code == 200, r.text
        assert r.json()["next_step"] == 4
        r = client.get(f"/api/novels/{pid}/story/arc")
        data = r.json()
        assert data["premise"] == ARC_FULL["premise"]
        assert data["volumes"][0]["title"] == "失踪"
        assert data["has_content"] is True
        # 后卷「待定」整行合法保存
        assert data["volumes"][1]["title"] == "待定"
        # story.yaml synopsis 共存不互踩
        assert client.get(f"/api/novels/{pid}/story").json()["synopsis"] == ""

    def test_put_empty_arc_ok(self, client):
        pid = _create_project(client)
        r = client.put(
            f"/api/novels/{pid}/story/arc",
            json={"premise": "", "ending": {}, "volumes": []},
        )
        assert r.status_code == 200
        assert client.get(f"/api/novels/{pid}/story/arc").json()["has_content"] is False

    def test_next_step_inference(self, client):
        """保守续步：无主线→1；有主线无结局→2；无有效分卷→3；齐→4。"""
        pid = _create_project(client)
        r = client.put(
            f"/api/novels/{pid}/story/arc",
            json={"premise": "一句话主线", "ending": {}, "volumes": []},
        )
        assert r.json()["next_step"] == 2
        r = client.put(
            f"/api/novels/{pid}/story/arc",
            json={"premise": "一句话主线", "ending": {"tone": "悲"}, "volumes": []},
        )
        assert r.json()["next_step"] == 3
        r = client.put(
            f"/api/novels/{pid}/story/arc",
            json={
                "premise": "一句话主线",
                "ending": {"tone": "悲"},
                "volumes": [{"title": "待定", "conflict": "待定", "chapters": "?"}],
            },
        )
        # 全待定分卷不算有效 → 仍停在 3
        assert r.json()["next_step"] == 3
        r = client.put(
            f"/api/novels/{pid}/story/arc",
            json={
                "premise": "一句话主线",
                "ending": {"tone": "悲"},
                "volumes": [{"title": "初章", "conflict": "起步", "chapters": "8"}],
            },
        )
        assert r.json()["next_step"] == 4

    def test_404(self, client):
        assert client.get("/api/novels/no-such/story/arc").status_code == 404


# ── readiness / 确认 ──────────────────────────────────────────────────────


class TestArcReadiness:
    def test_empty_arc_missing(self, client):
        pid = _create_project(client)
        missing = {
            m["key"]
            for m in client.get(f"/api/novels/{pid}/readiness").json()["missing"]
        }
        assert "story-arc" in missing

    def test_confirm_empty_rejected(self, client):
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/settings/status/story-arc")
        assert r.status_code == 400
        assert "还未填写" in r.json()["detail"]

    def test_premesse_only_passes(self, client):
        """只有一句话主线（无分卷）也算有内容——可确认。"""
        pid = _create_project(client)
        client.put(
            f"/api/novels/{pid}/story/arc",
            json={"premise": "一句话主线", "ending": {}, "volumes": []},
        )
        missing = {
            m["key"]
            for m in client.get(f"/api/novels/{pid}/readiness").json()["missing"]
        }
        assert "story-arc" not in missing
        r = client.put(f"/api/novels/{pid}/settings/status/story-arc")
        assert r.status_code == 200, r.text

    def test_all_tbd_volumes_not_content(self, client):
        """无主线+分卷全待定 → 仍算未填。"""
        pid = _create_project(client)
        client.put(
            f"/api/novels/{pid}/story/arc",
            json={
                "premise": "",
                "ending": {},
                "volumes": [{"title": "待定", "conflict": "待定", "chapters": "?"}],
            },
        )
        missing = {
            m["key"]
            for m in client.get(f"/api/novels/{pid}/readiness").json()["missing"]
        }
        assert "story-arc" in missing


# ── 向导端点 ──────────────────────────────────────────────────────────────


class _FakeAI:
    def __init__(self, text: str):
        self._text = text

    async def chat(self, **_kw):
        return self._text


@pytest.fixture
def stub_ai(monkeypatch):
    def _stub(text: str):
        import story.arc_wizard as wiz

        fake = _FakeAI(text)

        async def get_client(novel_id=None):
            return fake

        monkeypatch.setattr(wiz, "get_ai_client_for_novel", get_client)

    return _stub


class TestWizard:
    def test_free_user_403(self, client):
        # 先以会员身份建书（免费层 1 本上限会先拦住建书）
        pid = _create_project(client)
        _set_tier("none", api_key=_FAKE_KEY)
        r = client.post(
            f"/api/novels/{pid}/story/arc/wizard/condense",
            json={"input": "一段想法", "arc": {}},
        )
        assert r.status_code == 403
        assert r.json()["detail"]["reason"] == "member_required"

    def test_member_happy_path(self, client, stub_ai):
        pid = _member_project(client)
        stub_ai('```json\n{"premise": "一句话主线", "notes": "说明"}\n```')
        r = client.post(
            f"/api/novels/{pid}/story/arc/wizard/condense",
            json={"input": "陆征是私家侦探……", "arc": {}},
        )
        assert r.status_code == 200, r.text
        assert r.json()["value"]["premise"] == "一句话主线"

    def test_empty_input_400(self, client, stub_ai):
        pid = _member_project(client)
        r = client.post(
            f"/api/novels/{pid}/story/arc/wizard/condense",
            json={"input": "  ", "arc": {}},
        )
        assert r.status_code == 400

    def test_unknown_step_400(self, client):
        pid = _member_project(client)
        r = client.post(
            f"/api/novels/{pid}/story/arc/wizard/bogus",
            json={"input": "x", "arc": {}},
        )
        assert r.status_code == 400

    def test_bad_json_500(self, client, stub_ai):
        pid = _member_project(client)
        stub_ai("这不是 JSON")
        r = client.post(
            f"/api/novels/{pid}/story/arc/wizard/audit",
            json={"input": "自查一下", "arc": ARC_FULL},
        )
        assert r.status_code == 500
        assert "invalid JSON" in r.json()["detail"]

    def test_404_project(self, client):
        r = client.post(
            "/api/novels/no-such/story/arc/wizard/split",
            json={"input": "x", "arc": {}},
        )
        assert r.status_code == 404
