"""
Tests for settings readiness (PRD 3.4):
- GET /api/novels/{id}/readiness — 7-item content check, Chinese missing labels
- PUT /api/novels/{id}/settings/status/{type} — judges content on "完成设定" click

Usage:
    cd client/backend
    python -m pytest tests/test_readiness.py -v
"""

import asyncio
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# ── Test environment ─────────────────────────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_readiness.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_readiness_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

# Change 002：无 config 默认免费旁路，phase-status 直接返回 tier_bypass（warnings 空）。
# 本模块断言 settings 真实 gate 警告，故显式以付费套餐运行。
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
    _run_async(_create_user("rduser"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "rduser"}


@pytest.fixture(autouse=True)
def _setup_overrides():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_ai_access] = lambda: True
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = lambda: True
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _pro_tier():
    """Change 002 适配：写付费套餐 config.json，使 phase-status 走真实 gate 警告。"""
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


def _create_project(client) -> str:
    name = f"rd-test-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), f"Create project failed: {r.text}"
    return r.json()["id"]


_WORLD_FIELDS = [
    ("geography", "scenes"), ("geography", "climate"), ("geography", "limits"),
    ("politics", "rule"), ("politics", "factions"), ("politics", "social"), ("politics", "cost"),
    ("rules", "world"), ("rules", "society"), ("rules", "personal"),
]


def _fill_world(client, pid: str, filled: int = 4):
    """按前端五格 payload 填充（契约 v2：stage/power/cost 段落 + extra 条目）。"""
    world: dict = {"no_power": False, "stage": "", "power": "", "cost": "",
                   "history": [], "factions": [], "constraints": [], "extra": []}
    slots = [("stage", None), ("power", None), ("cost", None),
             ("extra", "条目一"), ("extra", "条目二"), ("extra", "条目三")]
    for k, slot in enumerate(slots):
        if k >= filled:
            break
        if slot[0] == "extra":
            world["extra"].append({"key": slot[1], "value": "有内容"})
        else:
            world[slot[0]] = "有内容"
    client.put(f"/api/novels/{pid}/settings/world", json=world)


# ── GET /readiness ────────────────────────────────────────────────────────


class TestReadiness:
    def test_new_project_missing_defaults(self, client):
        """新项目：模板默认值算内容（style/anti-ai 通过），空项进入 missing。"""
        pid = _create_project(client)
        r = client.get(f"/api/novels/{pid}/readiness")
        assert r.status_code == 200
        data = r.json()
        keys = {m["key"] for m in data["missing"]}
        # synopsis/story-arc/genre/world/hooks/characters 为空 → missing；style/anti-ai 模板有默认 → 通过
        assert keys == {"synopsis", "story-arc", "genre", "world", "hooks", "characters"}
        assert not data["complete"]
        assert "还差" in data["warning"]
        # 中文 label + jump
        labels = {m["label"] for m in data["missing"]}
        assert labels == {"故事简介", "主线规划", "题材类型", "世界设定", "伏笔管理", "角色管理"}
        for m in data["missing"]:
            assert m["jump"] in {"synopsis", "story-arc", "genre", "world", "hooks", "characters"}

    def test_all_filled_complete(self, client):
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "一个关于稻田的故事"})
        client.put(
            f"/api/novels/{pid}/story/arc",
            json={"premise": "主角守护稻田对抗征迁", "ending": {}, "volumes": []},
        )
        client.put(f"/api/novels/{pid}/settings/genre", json={"core_promise": "以弱破强的痛快"})
        _fill_world(client, pid, filled=4)
        client.put(f"/api/novels/{pid}/settings/hooks", json={"active": [{"id": "h1", "description": "一个钩子"}]})
        client.put(f"/api/novels/{pid}/settings/character/张三", json={"name": "张三"})
        # style/anti-ai 模板默认已通过
        r = client.get(f"/api/novels/{pid}/readiness")
        data = r.json()
        assert data["complete"] is True, data
        assert data["missing"] == []
        assert data["warning"] == ""

    def test_world_any_nonempty_passes(self, client):
        """world 判定 v2：stage/power/cost/条目任一非空即通过（旧阈值作废）。"""
        pid = _create_project(client)
        _fill_world(client, pid, filled=0)
        r = client.get(f"/api/novels/{pid}/readiness")
        keys = {m["key"] for m in r.json()["missing"]}
        assert "world" in keys

        _fill_world(client, pid, filled=1)
        r = client.get(f"/api/novels/{pid}/readiness")
        keys = {m["key"] for m in r.json()["missing"]}
        assert "world" not in keys

    def test_confirm_on_legacy_shape_normalizes(self, client):
        """8.4 演练：旧十字段 KV 书走 GET/PUT/确认全链（读边界归一化，不 400）。"""
        pid = _create_project(client)
        v1 = {
            "geography": {"scenes": "南境边境城邦", "climate": "多雨", "limits": "北境雪山"},
            "politics": {"rule": "王朝", "factions": "两宗对立", "social": "修士在上", "cost": "逐出宗门"},
            "rules": {"world": "灵力九境", "society": "宗门律法", "personal": "血咒反噬"},
        }
        client.put(f"/api/novels/{pid}/settings/world", json=v1)
        r = client.put(f"/api/novels/{pid}/settings/status/world")
        assert r.status_code == 200, r.text
        status = client.get(f"/api/novels/{pid}/settings/status").json()
        assert status["world"] is True

    def test_ai_model_not_judged(self, client):
        pid = _create_project(client)
        r = client.get(f"/api/novels/{pid}/readiness")
        assert "ai-model" not in {m["key"] for m in r.json()["missing"]}

    def test_not_found_404(self, client):
        assert client.get("/api/novels/no-such/readiness").status_code == 404


# ── PUT /settings/status/{type} — ConfirmToggle content judgement ─────────


class TestConfirmToggle:
    def test_confirm_empty_item_rejected(self, client):
        pid = _create_project(client)
        # world 为空 → 点完成设定 → 400 + 中文提示
        r = client.put(f"/api/novels/{pid}/settings/status/world")
        assert r.status_code == 400
        assert "还未填写" in r.json()["detail"]
        # 未被标记完成
        status = client.get(f"/api/novels/{pid}/settings/status").json()
        assert status["world"] is False

    def test_confirm_filled_item_accepted(self, client):
        pid = _create_project(client)
        _fill_world(client, pid, filled=4)
        r = client.put(f"/api/novels/{pid}/settings/status/world")
        assert r.status_code == 200, r.text
        assert r.json()["confirmed"] is True
        status = client.get(f"/api/novels/{pid}/settings/status").json()
        assert status["world"] is True

    def test_ai_model_confirm_retired_400(self, client):
        """D15/O-18：ai-model 不再是设定完成度项，可确认语义已移除 → 400。"""
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/settings/status/ai-model")
        assert r.status_code == 400

    def test_style_default_passes(self, client):
        """style.role 模板默认值算内容 → 点完成通过。"""
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/settings/status/style")
        assert r.status_code == 200, r.text

    def test_invalid_type_400(self, client):
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/settings/status/bogus")
        assert r.status_code == 400

    def test_confirm_synopsis(self, client):
        """synopsis 纳入确认：空简介 → 400；保存简介后 → 可确认。"""
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/settings/status/synopsis")
        assert r.status_code == 400
        assert "还未填写" in r.json()["detail"]
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "一个关于稻田的故事"})
        r = client.put(f"/api/novels/{pid}/settings/status/synopsis")
        assert r.status_code == 200, r.text
        assert r.json()["confirmed"] is True

    def test_confirm_genre(self, client):
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/settings/status/genre")
        assert r.status_code == 400
        client.put(f"/api/novels/{pid}/settings/genre", json={"core_promise": "以弱破强的痛快"})
        r = client.put(f"/api/novels/{pid}/settings/status/genre")
        assert r.status_code == 200, r.text
        assert r.json()["confirmed"] is True

    def test_confirm_characters(self, client):
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/settings/status/characters")
        assert r.status_code == 400
        client.put(f"/api/novels/{pid}/settings/character/张三", json={"name": "张三"})
        r = client.put(f"/api/novels/{pid}/settings/status/characters")
        assert r.status_code == 200, r.text
        assert r.json()["confirmed"] is True

    def test_confirm_hooks(self, client):
        """模板空钩子（id/description 空）不算内容 → 400；有效钩子后可确认。"""
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/settings/status/hooks")
        assert r.status_code == 400
        client.put(f"/api/novels/{pid}/settings/hooks", json={"active": [{"id": "h1", "description": "一个钩子"}]})
        r = client.put(f"/api/novels/{pid}/settings/status/hooks")
        assert r.status_code == 200, r.text
        assert r.json()["confirmed"] is True


# ── Gate — settings 完成判定联动（PRD 3.4 AC-4.1）──────────────────────


def _create_project_with_chapter(client) -> str:
    """建项目 + 卷 + 章（推进 phase 到 outline，使 phase-status 返回 settings warnings）。"""
    pid = _create_project(client)
    # PUT /settings/{type} 会把 phase 从 init 推进到 settings（settings/router.py:87）。
    # 必须先推进，否则 create_volume 的 update_phase("outline") 从 init 直接转 outline 被 engine 拒绝。
    client.put(f"/api/novels/{pid}/settings/world", json={"geography": {"scenes": "g"}, "politics": {}, "rules": {}})
    client.post(f"/api/novels/{pid}/volumes", json={"vol_num": 1, "title": "第一卷"})
    r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第1章"})
    assert r.status_code in (200, 201), r.text
    return pid


def _settings_warnings(client, pid: str) -> list[str]:
    r = client.get(f"/api/novels/{pid}/workflow/phase-status")
    assert r.status_code == 200, r.text
    return [w["message"] for w in r.json()["warnings"] if w["phase"] == "settings"]


class TestGateSettingsWarnings:
    def test_synopsis_unconfirmed_warns(self, client):
        """未确认简介 → settings 警告含「故事简介」。"""
        pid = _create_project_with_chapter(client)
        msgs = _settings_warnings(client, pid)
        assert any("故事简介" in m for m in msgs), msgs

    def test_synopsis_confirmed_removes_warning(self, client):
        """保存简介并确认 → settings 警告不再含「故事简介」。"""
        pid = _create_project_with_chapter(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "一个关于稻田的故事"})
        r = client.put(f"/api/novels/{pid}/settings/status/synopsis")
        assert r.status_code == 200, r.text
        msgs = _settings_warnings(client, pid)
        assert not any("故事简介" in m for m in msgs), msgs

    def test_all_complete_no_settings_warning(self, client):
        """7 项内容填满 + 全部确认 → settings 无警告（AC-4.1）。"""
        pid = _create_project_with_chapter(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "一个关于稻田的故事"})
        client.put(
            f"/api/novels/{pid}/story/arc",
            json={"premise": "主角守护稻田对抗征迁", "ending": {}, "volumes": []},
        )
        client.put(f"/api/novels/{pid}/settings/genre", json={"core_promise": "以弱破强的痛快"})
        _fill_world(client, pid, filled=4)
        client.put(f"/api/novels/{pid}/settings/hooks", json={"active": [{"id": "h1", "description": "一个钩子"}]})
        client.put(f"/api/novels/{pid}/settings/character/张三", json={"name": "张三"})
        # style/anti-ai 模板默认已通过内容判定
        for t in ["synopsis", "story-arc", "genre", "world", "style", "anti-ai", "hooks", "characters"]:
            r = client.put(f"/api/novels/{pid}/settings/status/{t}")
            assert r.status_code == 200, f"confirm {t} failed: {r.text}"
        msgs = _settings_warnings(client, pid)
        assert msgs == [], msgs


# ── 泛化 /settings/{type} 端点：目录型明确拒绝（500 回归）─────────────────


class TestGenericSettingsTypes:
    """`/settings/characters` 是多文件目录型（character-setting/{name}.yaml），
    无单文件端点 → 应返回 400 + 指引，而非 500（FILE_MAP KeyError 回归）。"""

    def test_get_characters_directory_type_rejected(self, client):
        pid = _create_project(client)
        r = client.get(f"/api/novels/{pid}/settings/characters")
        assert r.status_code == 400, r.text
        assert "/character/" in r.json()["detail"]

    def test_put_characters_directory_type_rejected(self, client):
        pid = _create_project(client)
        r = client.put(
            f"/api/novels/{pid}/settings/characters",
            json={"characters": [{"name": "张三"}]},
        )
        assert r.status_code == 400, r.text
        assert "/character/" in r.json()["detail"]

    def test_get_invalid_type_400(self, client):
        pid = _create_project(client)
        r = client.get(f"/api/novels/{pid}/settings/bogus")
        assert r.status_code == 400, r.text

    def test_get_single_file_type_still_works(self, client):
        """推导（KEY_TO_PATH）不能破坏正常单文件路径。"""
        pid = _create_project(client)
        r = client.get(f"/api/novels/{pid}/settings/world")
        assert r.status_code == 200, r.text
        assert "stage" in r.json() and "_legacy" not in r.json()

    def test_put_single_file_type_still_works(self, client):
        pid = _create_project(client)
        r = client.put(
            f"/api/novels/{pid}/settings/hooks",
            json={"active": [{"id": "h1", "description": "一个钩子"}]},
        )
        assert r.status_code == 200, r.text
        r = client.get(f"/api/novels/{pid}/settings/hooks")
        assert r.json()["active"][0]["id"] == "h1"


class TestCharactersEndpoints:
    """characters 专用端点端到端（HTTP 层）。"""

    def test_character_roundtrip(self, client):
        pid = _create_project(client)
        payload = {"name": "张三", "role": "protagonist", "values": "重情义"}
        r = client.put(f"/api/novels/{pid}/settings/character/张三", json=payload)
        assert r.status_code == 200, r.text
        r = client.get(f"/api/novels/{pid}/settings/character/张三")
        assert r.status_code == 200, r.text
        assert r.json()["values"] == "重情义"

    def test_character_list_and_delete(self, client):
        pid = _create_project(client)
        # 新项目无角色
        r = client.get(f"/api/novels/{pid}/settings/characters/list")
        assert r.json() == []
        # 写入 → list 含张三
        client.put(f"/api/novels/{pid}/settings/character/张三", json={"name": "张三"})
        r = client.get(f"/api/novels/{pid}/settings/characters/list")
        assert "张三" in r.json()
        # 删除 → list 空
        r = client.delete(f"/api/novels/{pid}/settings/character/张三")
        assert r.status_code == 200, r.text
        r = client.get(f"/api/novels/{pid}/settings/characters/list")
        assert "张三" not in r.json()


class TestGenreReadinessContract:
    """9.2.12：题材就绪判据＝新契约核心键任一非空（01 口味胶囊不落库、不计入）。"""

    def test_flavor_only_not_filled(self, client):
        """只点口味胶囊（不落库）→ 题材仍未填 → 确认 400。"""
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/settings/status/genre")
        assert r.status_code == 400

    @pytest.mark.parametrize(
        "payload",
        [
            {"cost_ratio": 5},
            {"battlefield": ["battlefield:resources"]},
            {"promise_note": "读者要看到弱者用脑子翻盘"},
            {"forbidden_list": [{"tagId": "forbidden:no-deus-ex-machina"}]},
        ],
    )
    def test_any_core_key_fills(self, client, payload):
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/settings/genre", json=payload)
        assert r.status_code == 200, r.text
        assert client.put(f"/api/novels/{pid}/settings/status/genre").status_code == 200

    def test_sentence_alone_counts(self, client):
        """02 主输入＝作家写的那句话（promise_note）；只写一句也算已填。

        用户 2026-09-10 改版：选项只是几个词，让作家写一句完整的话更好（AI 给草稿、可改）。
        旧口径「promise_note 不单独计入」随之作废。
        """
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/settings/genre", json={"promise_note": "读者要看翻盘"})
        assert client.put(f"/api/novels/{pid}/settings/status/genre").status_code == 200

    def test_whitespace_only_not_filled(self, client):
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/settings/genre", json={"core_promise": "   "})
        assert client.put(f"/api/novels/{pid}/settings/status/genre").status_code == 400
