"""主线设定（storyline-settings-v2）测试：

- GET/PUT /api/novels/{id}/story/arc — fullstory/ending 契约、双写镜像、volumes 保留、硬上限
- readiness 「story-arc」项 — 空卡 missing / fullstory-only / tone-only / legacy premise 归一 / 全空 400
- POST /api/novels/{id}/settings/ai/arc/{action} — 四能力（draft/calibrate/check/tone）：
  免费 403 / 会员 200（AI 打桩）/ 空素材 400 / 未知 action 400 / 坏 JSON 502

用法：
    cd client/backend
    .venv/bin/python -m pytest tests/test_story_arc.py -v
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
    # 不覆盖 require_ai_access：AI 端点要测真实会员门控
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    # 本书模型门控：本模块测的是内容/其他门控，模型就绪另测
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
    # 默认会员 + 占位 Key（AI happy path 可过门控；AI client 由各用例打桩）
    _set_tier("monthly", _future_iso(), api_key=_FAKE_KEY)
    with TestClient(app) as c:
        yield c


def _create_project(client) -> str:
    import uuid

    r = client.post("/api/novels", json={"name": f"arc-test-{uuid.uuid4().hex[:6]}"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


ARC_FULL = {
    "fullstory": "陆征追查苏棠失踪案，从坊市查进警队，发现三年前旧案被压，越查越深触及内部势力，最后在听证会上揭开真相。",
    "ending": {"scene": "侦探所里看着旧卷宗", "hero": "破案但心里装了更多", "tone": "苍凉但平静"},
}


# ── 主线卡读写（fullstory 契约 + 双写镜像 + volumes 保留 + 硬上限）────────


class TestArcEndpoints:
    def test_get_empty_arc(self, client):
        pid = _create_project(client)
        r = client.get(f"/api/novels/{pid}/story/arc")
        assert r.status_code == 200
        data = r.json()
        assert data["fullstory"] == ""
        assert data["ending"] == {"scene": "", "hero": "", "tone": ""}
        assert data["volumes"] == []
        assert data["has_content"] is False

    def test_put_roundtrip_and_mirror(self, client):
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/story/arc", json=ARC_FULL)
        assert r.status_code == 200, r.text
        r = client.get(f"/api/novels/{pid}/story/arc")
        data = r.json()
        assert data["fullstory"] == ARC_FULL["fullstory"]
        assert data["ending"] == ARC_FULL["ending"]
        assert data["has_content"] is True
        # 双写镜像：premise 与 fullstory 等价（legacy 读方兜底）
        assert data["premise"] == ARC_FULL["fullstory"]
        # story.yaml synopsis 共存不互踩
        assert client.get(f"/api/novels/{pid}/story").json()["synopsis"] == ""

    def test_put_empty_arc_ok(self, client):
        pid = _create_project(client)
        r = client.put(
            f"/api/novels/{pid}/story/arc",
            json={"fullstory": "", "ending": {}, "volumes": []},
        )
        assert r.status_code == 200
        assert client.get(f"/api/novels/{pid}/story/arc").json()["has_content"] is False

    def test_fullstory_hard_limit(self, client):
        pid = _create_project(client)
        ok = client.put(
            f"/api/novels/{pid}/story/arc",
            json={"fullstory": "字" * 2000, "ending": {}},
        )
        assert ok.status_code == 200
        over = client.put(
            f"/api/novels/{pid}/story/arc",
            json={"fullstory": "字" * 2001, "ending": {}},
        )
        assert over.status_code == 400
        assert "主线全文过长" in over.json()["detail"]

    def test_ending_field_hard_limit(self, client):
        pid = _create_project(client)
        over = client.put(
            f"/api/novels/{pid}/story/arc",
            json={"fullstory": "", "ending": {"scene": "画" * 201, "hero": "", "tone": ""}},
        )
        assert over.status_code == 400
        assert "过长" in over.json()["detail"]
        ok = client.put(
            f"/api/novels/{pid}/story/arc",
            json={"fullstory": "", "ending": {"scene": "画" * 200, "hero": "", "tone": ""}},
        )
        assert ok.status_code == 200

    def test_volumes_preserved_on_put_without_volumes(self, client):
        """新契约 PUT 不带 volumes：KV 里的存量分卷行原样保留不删（移交写作阶段）。"""
        pid = _create_project(client)
        legacy = {
            "premise": "旧一句话主线",
            "ending": {"scene": "", "hero": "", "tone": ""},
            "volumes": [
                {"title": "失踪", "conflict": "追查失踪案", "chapters": "10"},
                {"title": "待定", "conflict": "待定", "chapters": "?"},
            ],
        }
        assert client.put(f"/api/novels/{pid}/story/arc", json=legacy).status_code == 200
        r = client.put(
            f"/api/novels/{pid}/story/arc",
            json={"fullstory": "新全景主线", "ending": {}},
        )
        assert r.status_code == 200
        data = client.get(f"/api/novels/{pid}/story/arc").json()
        assert data["fullstory"] == "新全景主线"
        assert [v["title"] for v in data["volumes"]] == ["失踪", "待定"]

    def test_legacy_premise_normalized_on_get(self, client):
        """存量旧书（只有 premise）：GET 归一进 fullstory（前端无感迁移）。"""
        pid = _create_project(client)
        client.put(
            f"/api/novels/{pid}/story/arc",
            json={"premise": "旧一句话主线", "ending": {}, "volumes": []},
        )
        data = client.get(f"/api/novels/{pid}/story/arc").json()
        assert data["fullstory"] == "旧一句话主线"
        assert data["premise"] == "旧一句话主线"
        assert data["has_content"] is True

    def test_404(self, client):
        assert client.get("/api/novels/no-such/story/arc").status_code == 404


# ── readiness / 确认 ──────────────────────────────────────────────────────


class TestArcReadiness:
    def _missing(self, client, pid) -> set[str]:
        return {
            m["key"]
            for m in client.get(f"/api/novels/{pid}/readiness").json()["missing"]
        }

    def test_empty_arc_missing(self, client):
        pid = _create_project(client)
        assert "story-arc" in self._missing(client, pid)

    def test_confirm_empty_rejected(self, client):
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/settings/status/story-arc")
        assert r.status_code == 400
        assert "还未填写" in r.json()["detail"]

    def test_fullstory_only_passes(self, client):
        """只有全景（三问全空）也算有内容——可确认。"""
        pid = _create_project(client)
        client.put(
            f"/api/novels/{pid}/story/arc",
            json={"fullstory": "一段全景", "ending": {}},
        )
        assert "story-arc" not in self._missing(client, pid)
        r = client.put(f"/api/novels/{pid}/settings/status/story-arc")
        assert r.status_code == 200, r.text

    def test_tone_only_passes(self, client):
        """只有基调也判已填。"""
        pid = _create_project(client)
        client.put(
            f"/api/novels/{pid}/story/arc",
            json={"fullstory": "", "ending": {"tone": "苦尽甘来"}},
        )
        assert "story-arc" not in self._missing(client, pid)

    def test_legacy_premise_passes(self, client):
        """legacy premise 书归一为已填。"""
        pid = _create_project(client)
        client.put(
            f"/api/novels/{pid}/story/arc",
            json={"premise": "旧一句话主线", "ending": {}, "volumes": []},
        )
        assert "story-arc" not in self._missing(client, pid)

    def test_tbd_volumes_alone_not_content(self, client):
        """全空主线 + 分卷待定行 → 仍算未填（volumes 不参与判定）。"""
        pid = _create_project(client)
        client.put(
            f"/api/novels/{pid}/story/arc",
            json={
                "fullstory": "",
                "ending": {},
                "volumes": [{"title": "待定", "conflict": "待定", "chapters": "?"}],
            },
        )
        assert "story-arc" in self._missing(client, pid)


# ── 主线 AI 四能力 ─────────────────────────────────────────────────────────


class _FakeAI:
    def __init__(self, text: str):
        self._text = text
        self.calls: list[dict] = []

    async def chat(self, **kw):
        self.calls.append(kw)
        return self._text


@pytest.fixture
def stub_ai(monkeypatch):
    """打桩 AI 客户端；返回 fake 供断言（如模型别名守卫）。"""

    def _stub(text: str):
        import settings.ai_router as air

        fake = _FakeAI(text)

        async def get_client(novel_id=None):
            return fake

        monkeypatch.setattr(air, "get_ai_client_for_novel", get_client)
        return fake

    return _stub


class TestArcAi:
    def test_free_user_403(self, client):
        pid = _create_project(client)
        _set_tier("none", api_key=_FAKE_KEY)
        r = client.post(
            f"/api/novels/{pid}/settings/ai/arc/draft",
            json={"input": "一段想法"},
        )
        assert r.status_code == 403
        assert r.json()["detail"]["reason"] == "member_required"

    def test_draft_happy_path(self, client, stub_ai):
        pid = _create_project(client)
        stub_ai(
            '```json\n{"fullstory": "全景主线", "ending": {"scene": "画面", "hero": "归宿", "tone": "苦尽甘来"}}\n```'
        )
        r = client.post(
            f"/api/novels/{pid}/settings/ai/arc/draft",
            json={"input": "陆征是私家侦探……"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["value"]["fullstory"] == "全景主线"

    def test_calibrate_happy_path(self, client, stub_ai):
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story/arc", json=ARC_FULL)
        stub_ai('{"scene": "画面", "hero": "归宿", "tone": "苦尽甘来", "note": "对齐主线收场"}')
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/calibrate", json={})
        assert r.status_code == 200, r.text
        assert r.json()["value"]["tone"] == "苦尽甘来"

    def test_check_happy_path(self, client, stub_ai):
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story/arc", json=ARC_FULL)
        stub_ai(
            '{"checks": [{"name": "故事连贯", "status": "ok", "note": "一条线到底"},'
            ' {"name": "开头接结局", "status": "ok", "note": "闭环"},'
            ' {"name": "三问对得上", "status": "warn", "note": "基调与画面气质差一点"},'
            ' {"name": "和简介一个方向", "status": "miss", "note": "简介为空，先补再查更准"}],'
            ' "summary": "主线立得住"}'
        )
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/check", json={})
        assert r.status_code == 200, r.text
        checks = r.json()["value"]["checks"]
        assert [c["name"] for c in checks] == [
            "故事连贯", "开头接结局", "三问对得上", "和简介一个方向",
        ]

    def test_tone_happy_path(self, client, stub_ai):
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story/arc", json=ARC_FULL)
        stub_ai('{"tone": "苦尽甘来"}')
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/tone", json={})
        assert r.status_code == 200, r.text
        assert r.json()["value"]["tone"] == "苦尽甘来"

    def test_empty_material_400(self, client):
        """draft 空素材（无 input、无简介、主线全空）→ 400 中文提示。"""
        pid = _create_project(client)
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/draft", json={})
        assert r.status_code == 400
        assert "简介" in r.json()["detail"]

    def test_draft_material_accepts_synopsis(self, client, stub_ai):
        """回归（2026-09-13 实测事故）：起草的主输入是简介——有简介、主线全空时
        必须放行（此前只认 fullstory → 被 400 拦死）。"""
        pid = _create_project(client)
        r = client.put(f"/api/novels/{pid}/story", json={"synopsis": "陆征是私家侦探，姐姐找他查妹妹失踪。"})
        assert r.status_code == 200, r.text
        stub_ai('{"fullstory": "全景", "ending": {}}')
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/draft", json={})
        assert r.status_code == 200, r.text

    def test_arc_ai_uses_supported_model_alias(self, client, stub_ai):
        """回归（2026-09-13 实测事故）：model 必须用客户端支持的别名
        （haiku/sonnet/review → 配置模型）；字面模型名（如 "main"）会透传供应商
        被拒 → 502。四行动逐一守卫。"""
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "有简介"})
        client.put(f"/api/novels/{pid}/story/arc", json=ARC_FULL)
        payloads = {
            "draft": '{"fullstory": "全景", "ending": {}}',
            "calibrate": '{"scene": "画面", "hero": "归宿", "tone": "苦尽甘来"}',
            "check": '{"checks": [], "summary": "ok"}',
            "tone": '{"tone": "苦尽甘来"}',
        }
        for action, text in payloads.items():
            fake = stub_ai(text)
            r = client.post(f"/api/novels/{pid}/settings/ai/arc/{action}", json={})
            assert r.status_code == 200, f"{action}: {r.text}"
            assert fake.calls, f"{action} 未发起模型调用"
            alias = fake.calls[0].get("model")
            assert alias in ("haiku", "sonnet", "review"), (
                f"{action} 使用非法模型别名 {alias!r}——会透传供应商被拒（502）"
            )

    def test_unknown_action_400(self, client):
        pid = _create_project(client)
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/bogus", json={})
        assert r.status_code == 400

    def test_bad_json_502(self, client, stub_ai):
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story/arc", json=ARC_FULL)
        stub_ai("这不是 JSON")
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/check", json={})
        assert r.status_code == 502

    def test_404_project(self, client):
        r = client.post("/api/novels/no-such/settings/ai/arc/draft", json={"input": "x"})
        assert r.status_code == 404


# ── 写章注入（fullstory 进「全书主线」段，唯一裁剪点）────────────────────


class TestArcInjection:
    def test_injection_uses_fullstory_with_clip(self, client):
        """注入层读归一 fullstory 且超 600 字裁剪到句读——存储不截断。"""
        from novels.router import _arc_normalize
        from write.chapter_writer import clip_story_arc

        long_text = "第一幕起。他查了很久。" + "情节推进，一波未平一波又起。" * 80 + "最后收场。"
        assert len(long_text) > 600
        arc = _arc_normalize({"fullstory": long_text})
        clipped = clip_story_arc(arc["fullstory"])
        assert 0 < len(clipped) <= 600
        assert clipped.endswith(("。", "！", "？", "；", "…"))
        # legacy 归一：premise 升位 fullstory 后同样可注入
        arc_legacy = _arc_normalize({"premise": "旧一句话主线"})
        assert clip_story_arc(arc_legacy["fullstory"]) == "旧一句话主线"

    def test_outline_ai_material_uses_mirror(self, client):
        """章纲 AI 素材回归：仅填 fullstory 保存后 _arc_markdown 仍取得到主线（premise 镜像兜底）。"""
        pid = _create_project(client)
        client.put(
            f"/api/novels/{pid}/story/arc",
            json={"fullstory": "全景主线一句话版本", "ending": {}},
        )
        # GET 即 KV 读（同一读路径）；premise 镜像 = _arc_markdown 的 legacy 依赖面
        data = client.get(f"/api/novels/{pid}/story/arc").json()
        story = {"story_arc": {"premise": data["premise"], "ending": data["ending"]}}
        from chapters.ai_draft import _arc_markdown

        md = _arc_markdown(story)
        assert "一句话主线：全景主线一句话版本" in md
