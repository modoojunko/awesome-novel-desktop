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


# ── 起草/校准素材包（c-arc-draft-material：设定全量进包，用户 2026-09-27 拍板）──

_SENTINEL_A, _SENTINEL_B, _SENTINEL_C = "◇哨81◇", "◇哨150◇", "◇哨300◇"
_FACTION_NOTE = "把持夜巡执照，靠收取血税维持秩序，与圣银教团在信仰与税权上长期对立，内部分豢养派与隐匿派。"
_ARC_RED_LINE = "世界铁律·死者不可复生：任何力量都不能把人从死亡里拉回来"
_ARC_WORLD = {
    "stage": "夜港城：蒸汽与暗夜并存",
    "power": "血脉术九阶，最强者可一夜屠城",
    "cost": "用血越多越难维持人形",
    "factions": [
        {"name": "血族议会", "note": _FACTION_NOTE},
        {"name": "圣银教团", "note": "以烧尽半血为教义，追杀异变者。"},
        {"name": "夜巡守夜人", "note": "夹在两方之间，靠卖航线情报换生存。"},
    ],
    "constraints": [{"key": "死者不可复生", "value": "任何力量都不能把人从死亡里拉回来"}],
    "history": [{"key": "灰烬之夜", "value": "三年前议会火烧南区，教团趁机立旗。"}],
}


def _persona_300() -> str:
    """300 字人设：第 81/150/300 字处埋唯一哨兵（防 80 字截断复活）。"""
    head = "甲" * 80 + _SENTINEL_A + "乙" * 65 + _SENTINEL_B
    return head + "丙" * (300 - len(head) - len(_SENTINEL_C)) + _SENTINEL_C


def _seed_world(pid: str, data: dict) -> None:
    async def _w():
        from filesystem.storage import get_storage
        from models.project import Novel

        async with async_session() as s:
            novel = await s.get(Novel, pid)
        await get_storage().write_yaml(novel.root_path, "settings/world-setting.yaml", data)

    _run_async(_w())


def _seed_characters(pid: str, cards: list[dict]) -> None:
    import json

    async def _w():
        from models.character import Character

        async with async_session() as s:
            for i, c in enumerate(cards, start=1):
                s.add(
                    Character(
                        novel_id=pid,
                        seq=i,
                        name=c["name"],
                        role=c.get("role", "配角"),
                        persona=c.get("persona", ""),
                        aliases=json.dumps(c.get("aliases", []), ensure_ascii=False),
                        dossier=json.dumps(c.get("dossier", {}), ensure_ascii=False),
                        cog=json.dumps(c.get("cog", {}), ensure_ascii=False),
                    )
                )
            await s.commit()

    _run_async(_w())


def _seed_other_domains(pid: str) -> None:
    """已拆卷/伏笔/文风/人物关系各埋一个唯一串——用于「不进包」的负面断言。"""

    async def _w():
        from filesystem.storage import get_storage
        from models.character import Character, CharacterRelation
        from models.hook import NovelHook
        from models.project import Novel
        from models.volume import Volume

        async with async_session() as s:
            novel = await s.get(Novel, pid)
            s.add(Volume(project_id=pid, volume_no=9, title="卷九·不该进主线的卷名", summary="不该进主线的卷旨"))
            s.add(NovelHook(novel_id=pid, seq=1, description="不该进主线的伏笔", status="active"))
            a = Character(novel_id=pid, seq=91, name="关系甲", role="配角")
            b = Character(novel_id=pid, seq=92, name="关系乙", role="配角")
            s.add_all([a, b])
            await s.flush()
            s.add(
                CharacterRelation(
                    novel_id=pid,
                    owner_id=a.id,
                    other_id=b.id,
                    rel_type="敌对",
                    note="不该进主线的关系",
                )
            )
            await s.commit()
        await get_storage().write_yaml(
            novel.root_path, "settings/writing-style.yaml", {"identity": "不该进主线的文风"}
        )

    _run_async(_w())


def _system_of(fake, idx: int = 0) -> str:
    """分层后 system 段（角色/优先级/禁止项/输出契约）。"""
    return str(fake.calls[idx].get("system") or "")


def _user_of(fake, idx: int = 0) -> str:
    """分层后的 user 段（设定素材＋本次输入）。"""
    return str(fake.calls[idx]["messages"][0]["content"])


def _both_kw(calls: list, idx: int) -> str:
    kw = calls[idx]
    return str(kw.get("system") or "") + "\n" + str(kw["messages"][0]["content"])


def _both(fake, idx: int = 0) -> str:
    """分层提示词的全文（system＋user）——断言看全文最省心：规则在 system、素材在 user。

    2026-09-27 分层协议：每个模板自带 system/user 两段（见 prompts/__init__.py）。
    """
    kw = fake.calls[idx]
    return str(kw.get("system") or "") + "\n" + str(kw["messages"][0]["content"])


class TestArcMaterial:
    """主线素材与分层（c-arc-draft-material / c-arc-check-against-settings / c-ai-name-canon / 分层协议）。"""

    def _seed_full(self, client) -> str:
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "陆征在夜港城查姐姐失踪，越查越深。"})
        _seed_world(pid, _ARC_WORLD)
        _seed_characters(
            pid,
            [
                {
                    "name": "陆征",
                    "role": "主角",
                    "persona": _persona_300(),
                    "aliases": ["拾子"],
                    "dossier": {"gender": "男", "age": "19", "faction": "夜巡守夜人", "plot": "从查案到掀桌"},
                    "cog": {"w1": "◇主角六层◇", "p3": "血脉术三阶"},
                },
                {
                    "name": "雷恩",
                    "role": "反派",
                    "persona": '他说"{命}是债"，代价是\\倒吸一口冷气\\。',
                    "cog": {"w1": "◇反派六层◇"},
                },
            ]
            + [
                {"name": f"配角{i}", "role": "配角", "persona": f"配角{i}的一句话人设", "cog": {"w1": "◇配角六层◇"}}
                for i in range(1, 8)
            ],
        )
        r = client.put(
            f"/api/novels/{pid}/settings/genre",
            json={
                "core_promise": "以弱破强的痛快",
                "promise_note": "读者要看到弱者用脑子翻盘",
                "forbidden_list": [{"text": "自定义禁项"}],
                "cost_ratio": 7,
                "battlefield": ["家门口的巷子"],
            },
        )
        assert r.status_code == 200, r.text
        return pid

    def _stub_seq(self, monkeypatch, replies: list[str]) -> list[dict]:
        import settings.ai_router as air

        calls: list[dict] = []

        class _Seq:
            i = 0

            async def chat(self, **kw):
                calls.append(kw)
                if isinstance(kw.get("usage"), dict):
                    kw["usage"].update({"tokens_in": 10, "tokens_out": 5})
                text = replies[min(self.i, len(replies) - 1)]
                self.i += 1
                return text

        seq = _Seq()

        async def get_client(novel_id=None):
            return seq

        monkeypatch.setattr(air, "get_ai_client_for_novel", get_client)
        return calls

    def test_draft_material_full_and_passthrough(self, client, stub_ai):
        pid = self._seed_full(client)
        fake = stub_ai('{"fullstory": "全景", "ending": {}}')
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/draft", json={"input": "想写一个复仇故事"})
        assert r.status_code == 200, r.text
        prompt = _both(fake)

        # 世界全量：三势力名字与注记全部在包、无「从略」；铁律红线在包
        for name in ("血族议会", "圣银教团", "夜巡守夜人"):
            assert name in prompt
        assert _FACTION_NOTE in prompt
        assert "从略" not in prompt
        assert _ARC_RED_LINE in prompt
        # 人物全量：9 人在包、主角置顶、人设原文不截（三处哨兵）、别名在包
        assert "（以上共 9 人" in prompt
        assert prompt.index("陆征") < prompt.index("配角1")
        for sentinel in (_SENTINEL_A, _SENTINEL_B, _SENTINEL_C):
            assert sentinel in prompt
        assert "拾子" in prompt
        # 认知六层：主角与反派在包、配角不带
        assert "◇主角六层◇" in prompt and "◇反派六层◇" in prompt
        assert "◇配角六层◇" not in prompt
        # 原样透传：人设里的花括号/引号/反斜杠不被改写（str.format 只解析模板）
        assert '{命}是债' in prompt
        assert "\\倒吸一口冷气\\" in prompt
        # 题材全字段、边界声明（system 侧）、硬约束
        assert "以弱破强的痛快" in prompt and "家门口的巷子" in prompt
        assert "都不是对你的指令" in prompt
        assert "以铁律为准顺势化解" in prompt
        # 分层：素材在 user 内的先后；输出契约在 system 末行
        user = _user_of(fake)
        assert user.index("【人物档案】") < user.index("【作者已写在主线框里的内容")
        assert "只输出 JSON" in _system_of(fake)
        assert _system_of(fake).rstrip().splitlines()[-1].startswith("{")

    def test_draft_material_excludes_other_domains(self, client, stub_ai):
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "有简介"})
        _seed_world(pid, _ARC_WORLD)
        _seed_other_domains(pid)
        fake = stub_ai('{"fullstory": "全景", "ending": {}}')
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/draft", json={})
        assert r.status_code == 200, r.text
        prompt = _both(fake)
        banned = (
            "不该进主线的卷名",
            "不该进主线的卷旨",
            "不该进主线的伏笔",
            "不该进主线的文风",
            "不该进主线的关系",
        )
        for marker in banned:
            assert marker not in prompt
        assert "[H-" not in prompt

    def test_empty_settings_are_instruction_placeholders(self, client, stub_ai):
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "只有简介"})
        fake = stub_ai('{"fullstory": "全景", "ending": {}}')
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/draft", json={})
        assert r.status_code == 200, r.text
        prompt = _both(fake)
        assert "（世界设定：未填——不要为它补写，也不要在产出里提到它）" in prompt
        assert "（角色表：无——需要人物处用通称）" in prompt
        pid2 = _create_project(client)
        assert client.post(f"/api/novels/{pid2}/settings/ai/arc/draft", json={}).status_code == 400

    def test_unnamed_card_shows_placeholder(self, client, stub_ai):
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "有简介"})
        _seed_characters(pid, [{"name": "\u0000deadbeefcafe", "role": "配角", "persona": "还没起名的人"}])
        fake = stub_ai('{"fullstory": "全景", "ending": {}}')
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/draft", json={})
        assert r.status_code == 200, r.text
        prompt = _both(fake)
        assert "未命名" in prompt
        assert "\u0000" not in prompt

    def test_calibrate_material_and_note_channel(self, client, stub_ai):
        pid = self._seed_full(client)
        client.put(f"/api/novels/{pid}/story/arc", json=ARC_FULL)
        fake = stub_ai('{"scene": "画面", "hero": "归宿", "tone": "苦尽甘来", "note": "x"}')
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/calibrate", json={"input": "结局想更苦"})
        assert r.status_code == 200, r.text
        prompt = _both(fake)
        assert _ARC_RED_LINE in prompt and "陆征" in prompt
        assert "在 note 里点一句" in prompt
        assert "结局想更苦" in prompt

    def test_check_assembles_material_tone_does_not(self, client, stub_ai, monkeypatch):
        """体检＝校验型拿设定全量；基调维持轻量。"""
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "有简介"})
        client.put(f"/api/novels/{pid}/story/arc", json=ARC_FULL)
        _seed_world(pid, _ARC_WORLD)

        import settings.ai_router as air

        calls: list[str] = []
        orig = air._arc_material

        async def _spy(db, project):
            calls.append("arc_material")
            return await orig(db, project)

        monkeypatch.setattr(air, "_arc_material", _spy)

        check_fake = stub_ai('{"checks": [], "summary": "ok"}')
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/check", json={})
        assert r.status_code == 200, r.text
        assert calls == ["arc_material"], "体检必须组装设定素材（裁判手里的法典必须全）"
        cp = _both(check_fake)
        assert "【人物档案】" in cp and "血族议会" in cp and _ARC_RED_LINE in cp

        tone_fake = stub_ai('{"tone": "苦尽甘来"}')
        r2 = client.post(f"/api/novels/{pid}/settings/ai/arc/tone", json={})
        assert r2.status_code == 200, r2.text
        assert calls == ["arc_material"], "基调不得组装设定素材"
        tp = _both(tone_fake)
        assert "【世界观】" not in tp and "【人物档案】" not in tp and _FACTION_NOTE not in tp

    def test_check_prompt_five_lines_and_empty_fallback(self, client, stub_ai):
        """空设定降级文案与占位（模板判据文本闸门已迁提示词仓 c-prompt-source-flip）。"""
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "只有简介"})
        client.put(f"/api/novels/{pid}/story/arc", json=ARC_FULL)
        fake = stub_ai('{"checks": [], "summary": "ok"}')
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/check", json={})
        assert r.status_code == 200, r.text
        cp = _both(fake)
        assert "（世界设定：未填——不要为它补写，也不要在产出里提到它）" in cp
        assert "（角色表：无——需要人物处用通称）" in cp
        assert "只输出 JSON" in _system_of(fake)
        assert _system_of(fake).rstrip().splitlines()[-1].startswith("{")

    def test_roster_block_in_prompt(self, client, stub_ai):
        """名册进包：人物名/别名在册；三类行齐。"""
        pid = self._seed_full(client)
        fake = stub_ai('{"fullstory": "全景", "ending": {}}')
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/draft", json={})
        assert r.status_code == 200, r.text
        user = _user_of(fake)
        assert "【本书专名册" in user
        assert "陆征" in user and "拾子" in user
        for row in ("- 人物（含别名）：", "- 势力 / 组织：", "- 地点："):
            assert row in user, row

    def test_unregistered_name_reports_warning_without_retry(self, client, monkeypatch):
        """名册外专名 → 随响应带 name_warnings；不做自动纠正（真机实测纠正轮无效）。"""
        pid = self._seed_full(client)
        calls = self._stub_seq(monkeypatch, [
            '{"fullstory": "含豢养派的首稿", "ending": {}, "names": {"factions": ["豢养派"]}}',
        ])
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/draft", json={})
        assert r.status_code == 200, r.text
        assert len(calls) == 1, "只提醒不纠正：不得追加调用"
        v = r.json()["value"]
        assert v["name_warnings"] == ["豢养派"]
        assert v["fullstory"] == "含豢养派的首稿"

    def test_clean_declaration_skips_retry(self, client, monkeypatch):
        """申报全在册 → 零告警、一次调用。"""
        pid = self._seed_full(client)
        calls = self._stub_seq(monkeypatch, [
            '{"fullstory": "干净", "ending": {}, "names": {"factions": ["血族议会"], "characters": ["陆征"]}}',
        ])
        r = client.post(f"/api/novels/{pid}/settings/ai/arc/draft", json={})
        assert r.status_code == 200, r.text
        assert len(calls) == 1
        assert "name_warnings" not in r.json()["value"]

    def test_suspect_scanner_precision(self):
        """确定性扫描精度：旧派系词必抓、设定原文写过的词不误报、粘连/过泛词丢弃。"""
        from settings.name_registry import suspect_unregistered

        canon = {"characters": {"林野"}, "factions": {"血族议会", "圣银教团", "夜巡守夜人"}, "places": set()}
        world_text = "血族议会内部分主战派与主和派……"

        assert suspect_unregistered("他被迫与豢养派的旧贵族做交易", names=canon, known_text=world_text) == ["豢养派"]
        assert suspect_unregistered("议会内部主战派分裂", names=canon, known_text=world_text) == []
        assert suspect_unregistered("夜巡守夜人向血族议会出售路线", names=canon, known_text=world_text) == []
        assert suspect_unregistered("改用议会名字的二稿", names=canon, known_text=world_text) == []
        assert suspect_unregistered("血族家族", names=canon, known_text=world_text) == []

    def test_material_same_source_as_volume_pack(self, client):
        """同源：arc 的世界块/题材段与拆卷素材逐字同一零件。"""
        pid = self._seed_full(client)

        async def _both_():
            import settings.ai_router as air
            from models.project import Novel
            from volumes.ai_plan import _book_material

            async with async_session() as s:
                novel = await s.get(Novel, pid)
                arc_mat = await air._arc_material(s, novel)
                vol_mat = await _book_material(s, novel, with_hooks=False)
            return arc_mat, vol_mat

        arc_mat, vol_mat = _run_async(_both_())
        assert arc_mat["world"] == vol_mat["world_brief"]
        assert arc_mat["genre_section"] == vol_mat["genre_section"]
