"""outline-ai-draft — 章纲 AI 起草端点契约

矩阵：
- 成功：返回结构化草稿，章数据/status 不变（不落库），计量入账；
- 无主线卡：422 提示先完成主线，AI 不被触达、不计量；
- 免费用户：403，AI 不被触达；
- 模型输出非法 JSON / 骨架缺失：502 可重试；
- 枚举非法回落、word_target clamp、无前情段（首章）。

用法：
    cd client/backend
    python -m pytest tests/test_outline_ai_draft.py -v
"""

import asyncio
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_oad.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_outline_ai_draft_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from sqlalchemy import select  # noqa: E402

import auth_local.service as _service  # noqa: E402
import chapters.store as chapters_store  # noqa: E402
from auth_local.deps import require_novel_model, require_project_limit  # noqa: E402
from auth_local.middleware import get_current_user  # noqa: E402
from chapters import ai_draft  # noqa: E402
from db import Base, async_session, engine, get_db  # noqa: E402
from filesystem.storage import get_storage  # noqa: E402
from main import app  # noqa: E402
from models import Novel  # noqa: E402
from models.token_log import TokenLog  # noqa: E402
from models.user import User  # noqa: E402


def _layered_prompt(kwargs) -> str:
    """分层协议下的全文（system＋user 合并读——内容断言不关心落在哪一段）。"""
    return str(kwargs.get("system") or "") + "\n" + str(kwargs["messages"][0]["content"])


_CFG_PATH = os.path.join(_tmp_data_root, "config.json")

USER_ID = "oad_user"


def _set_tier(tier: str, api_key: str = "sk-test"):
    _service.CONFIG_FILE = _CFG_PATH
    _service.save_local_config(
        {"tier": tier, "expires_at": _future_iso() if tier != "none" else "", "api_key": api_key}
    )


def _future_iso(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


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


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    _run_async(_create_tables())

    async def _create_user():
        async with async_session() as session:
            session.add(
                User(
                    id=USER_ID,
                    email=f"{USER_ID}@test.com",
                    password_hash="*",
                    display_name=USER_ID,
                )
            )
            await session.commit()

    _run_async(_create_user())
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": USER_ID}


async def _override_true():
    return True


@pytest.fixture(autouse=True)
def _setup_overrides():
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


VALID_DRAFT = """```json
{
  "outline": {"summary": "林昭夜探账房", "key_points": ["发现亏空"], "characters": ["林昭"],
              "location": "账房", "time": "深夜", "narrative_pov": "第三人称限知",
              "perspective_guidance": ""},
  "memo": {"current_task": "拿到亏空证据并全身而退",
           "reader_expectation": {"state": "怀疑管家", "strategy": "证实怀疑", "detail": ""},
           "payoff_plan": {"must_resolve": ["账本去向"], "must_hold": ["幕后主使"], "partial_advance": []},
           "required_changes": ["林昭掌握实证"], "prohibitions": ["不得动武"]},
  "emotional_design": {"primary_mood": "紧张", "mood_progression": "", "emotional_hook": "脚步声逼近"},
  "segments": [{"summary": "潜入", "target_words": 800}, {"summary": "翻账", "target_words": 1000}],
  "scene_cards": [{"scene_name": "账房", "goal": "取证", "obstacle": "守夜", "hook": "暗格",
                   "weight": "超高", "focus": "不知道"}],
  "micro_payoffs": [{"kind": "unknown", "description": "账本缺页", "location": "结尾"}],
  "challenge": "船家改口要加钱",
  "plot_stage": "重要转折",
  "ladder_exit": "带着半本账册越墙而出",
  "word_target": 99999
}
```"""


class _FakeAIClient:
    def __init__(self, calls: list, reply: str = VALID_DRAFT, error: Exception | None = None):
        self._calls = calls
        self._reply = reply
        self._error = error
        self.last_kwargs: dict = {}

    async def chat(self, **kwargs):
        self._calls.append("chat")
        self.last_kwargs = kwargs
        if isinstance(kwargs.get("usage"), dict):
            kwargs["usage"].update({"tokens_in": 100, "tokens_out": 200})
        if self._error:
            raise self._error
        return self._reply


def _create_project_and_chapter(client, with_arc: bool = True) -> tuple[str, str]:
    name = f"oad-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    r = client.post(f"/api/novels/{pid}/volumes", json={"vol_num": 1, "title": "第一卷"})
    assert r.status_code in (200, 201)
    r2 = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第1章"})
    assert r2.status_code in (200, 201), r2.text
    ref = r2.json()["chapter_ref"]

    async def _seed():
        session = async_session()
        proj = await session.get(Novel, pid)
        root = proj.root_path
        await session.close()
        if with_arc:
            story = await get_storage().read_yaml(root, "story.yaml") or {}
            story["story_arc"] = {
                "premise": "林昭要查清父亲冤案，对抗遮天的旧党",
                "ending": {"scene": "金殿对质", "hero": "沉冤得雪", "tone": "悲壮"},
                "volumes": [{"title": "第一卷", "conflict": "府内暗流", "chapters": "1-10"}],
            }
            await get_storage().write_yaml(root, "story.yaml", story)

    _run_async(_seed())
    return pid, ref


def _read_chapter(pid: str, ref: str) -> dict:
    async def _read():
        session = async_session()
        proj = await session.get(Novel, pid)
        root = proj.root_path
        await session.close()
        return await chapters_store.load_chapter(root, ref)

    return _run_async(_read())


def _token_log_count(pid: str) -> int:
    async def _count():
        async with async_session() as session:
            rows = await session.scalars(
                select(TokenLog).where(
                    TokenLog.user_id == USER_ID, TokenLog.project_id == pid
                )
            )
            return len(list(rows))

    return _run_async(_count())


def _setup_ai(monkeypatch, calls: list, **kw):
    fake = _FakeAIClient(calls, **kw)

    async def _factory(novel_id=None):
        return fake

    monkeypatch.setattr(ai_draft, "get_ai_client_for_novel", _factory)
    return fake


class TestAiDraftSuccess:
    def test_draft_returns_sanitized_payload_and_not_persisted(self, client, monkeypatch):
        _set_tier("trial")
        calls: list = []
        fake = _setup_ai(monkeypatch, calls)
        pid, ref = _create_project_and_chapter(client)
        before = _read_chapter(pid, ref)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 200, r.text
        d = r.json()
        # 骨架完整（c-og-slim-v2：段落规划/场景卡/读者预期/关键事件等退役键一律丢弃）
        for dead in ("current_task", "reader_expectation"):
            assert dead not in d["memo"]
        assert "partial_advance" not in d["memo"]["payoff_plan"]
        for dead in ("segments", "scene_cards", "chapter_acts", "key_points"):
            assert dead not in d
        for dead in ("location", "time", "narrative_pov", "perspective_guidance"):
            assert dead not in d["outline"]
        for dead in ("mood_progression", "emotional_hook"):
            assert dead not in d["emotional_design"]
        # 枚举非法回落（kind 回落 clue；位置档退役）
        mp = d["micro_payoffs"][0]
        assert mp["kind"] == "clue" and "location" not in mp
        # 拆章两格随草稿返回
        assert d["challenge"] == "船家改口要加钱"
        assert d["plot_stage"] == "重要转折"
        # word_target clamp 到 6000
        assert d["word_target"] == 6000
        # 不落库：章数据与 status 不变
        assert _read_chapter(pid, ref) == before
        # 素材包含主线卡与改写基底提示
        assert "林昭要查清父亲冤案" in _layered_prompt(fake.last_kwargs)
        assert "无现有章纲，从零起草" in _layered_prompt(fake.last_kwargs)
        # 计量入账
        assert _token_log_count(pid) >= 1

    def test_existing_outline_used_as_rewrite_base(self, client, monkeypatch):
        _set_tier("trial")
        calls: list = []
        fake = _setup_ai(monkeypatch, calls)
        pid, ref = _create_project_and_chapter(client)

        async def _seed():
            session = async_session()
            proj = await session.get(Novel, pid)
            root = proj.root_path
            await session.close()
            await chapters_store.save_chapter(
                root, ref,
                {"outline": {"summary": "作者已定的开场"},
                 "memo": {"prohibitions": ["不得惊动管家"]}},
            )

        _run_async(_seed())
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 200
        # c-og-fields-slim：核心任务退役——重写底稿用在册字段（禁令）证明素材携带
        assert "不得惊动管家" in _layered_prompt(fake.last_kwargs)
        assert "无现有章纲" not in _layered_prompt(fake.last_kwargs)
        # 首章（前情=哨兵）：素材包不含前情段
        assert "【前情" not in _layered_prompt(fake.last_kwargs)

    def test_retired_field_only_does_not_count_as_rewrite_base(self, client, monkeypatch):
        """hardening：只填段落/场景卡的章不再被判「无现有章纲」（review P3）。"""
        _set_tier("trial")
        calls: list = []
        fake = _setup_ai(monkeypatch, calls)
        pid, ref = _create_project_and_chapter(client)

        async def _seed():
            session = async_session()
            proj = await session.get(Novel, pid)
            root = proj.root_path
            await session.close()
            await chapters_store.save_chapter(
                root,
                ref,
                {
                    # c-og-slim-v2：拆章格子计入「有现有章纲」（原口径用段落规划）
                    "challenge": "渡口封航，出不了城",
                },
            )

        _run_async(_seed())
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 200
        assert "渡口封航" in _layered_prompt(fake.last_kwargs)
        assert "无现有章纲" not in _layered_prompt(fake.last_kwargs)


class TestAiDraftGuarded:
    def test_retired_draft_keys_dropped(self, client, monkeypatch):
        """c-og-slim-v2：模型返回段落规划/场景卡/关键事件等退役键 → 整体丢弃、不落草稿。"""
        _set_tier("trial")
        calls: list = []
        reply = VALID_DRAFT.replace(
            '"micro_payoffs": [',
            '"segments": [{"summary": "潜入", "target_words": "800"}],'
            ' "scene_cards": [{"scene_name": "渡口"}],'
            ' "outline_extra": 1, "micro_payoffs": [',
        )
        _setup_ai(monkeypatch, calls, reply=reply)
        pid, ref = _create_project_and_chapter(client)
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 200, r.text
        d = r.json()
        for dead in ("segments", "scene_cards", "outline_extra"):
            assert dead not in d

    def test_no_story_arc_422_and_ai_not_called(self, client, monkeypatch):
        _set_tier("trial")
        calls: list = []
        _setup_ai(monkeypatch, calls)
        pid, ref = _create_project_and_chapter(client, with_arc=False)
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 422
        assert "主线" in r.json()["detail"]
        assert calls == []  # AI 未被触达
        assert _token_log_count(pid) == 0

    def test_free_tier_403_ai_not_called(self, client, monkeypatch):
        _set_tier("none")
        calls: list = []
        _setup_ai(monkeypatch, calls)
        pid, ref = _create_project_and_chapter(client)
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 403
        assert calls == []

    def test_invalid_json_502(self, client, monkeypatch):
        _set_tier("trial")
        calls: list = []
        _setup_ai(monkeypatch, calls, reply="这不是 JSON")
        pid, ref = _create_project_and_chapter(client)
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 502
        # ai-client-timeout-and-usage-accounting 新口径：调用已完成（钱已花），
        # 产物不合格也要留痕（成功名记账，与 characters_ai 空结果口径一致）
        assert _token_log_count(pid) == 1

    def test_missing_skeleton_502(self, client, monkeypatch):
        """c-og-slim-v2：必备骨架只剩「章纲概要」——概要为空才 502。"""
        _set_tier("trial")
        calls: list = []
        _setup_ai(monkeypatch, calls, reply='{"outline": {"summary": ""}, "memo": {}}')
        pid, ref = _create_project_and_chapter(client)
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 502

    def test_summary_only_counts_as_skeleton(self, client, monkeypatch):
        """概要非空即合格（段落规划退役后不再作骨架）。"""
        _set_tier("trial")
        calls: list = []
        _setup_ai(
            monkeypatch, calls,
            reply='{"outline": {"summary": "s"}, "memo": {"current_task": "t"}}',
        )
        pid, ref = _create_project_and_chapter(client)
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 200, r.text
        assert r.json()["outline"]["summary"] == "s"

    def test_model_error_502(self, client, monkeypatch):
        _set_tier("trial")
        calls: list = []
        _setup_ai(monkeypatch, calls, error=RuntimeError("网络炸了"))
        pid, ref = _create_project_and_chapter(client)
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 502

    def test_chapter_not_found_404(self, client, monkeypatch):
        _set_tier("trial")
        calls: list = []
        _setup_ai(monkeypatch, calls)
        pid, _ = _create_project_and_chapter(client)
        r = client.post(f"/api/novels/{pid}/chapters/ch-999/outline/ai-draft")
        assert r.status_code == 404
        assert calls == []

    def test_draft_material_includes_settings(self, client, monkeypatch):
        """回归（c-ai-material-audit）：章纲起草素材曾零世界/铁律/题材/人物——三块必须进包。"""
        _set_tier("trial")
        calls: list = []
        fake = _setup_ai(monkeypatch, calls)
        pid, ref = _create_project_and_chapter(client)

        async def _seed():
            from models.character import Character

            session = async_session()
            proj = await session.get(Novel, pid)
            root = proj.root_path
            await get_storage().write_yaml(root, "settings/world-setting.yaml", {
                "stage": "灰港旧街区",
                "factions": [{"name": "血族议会", "note": "把持夜巡执照"}],
                "constraints": [{"key": "死者不可复生", "value": "任何力量都不能把人从死亡里拉回来"}],
            })
            session.add(Character(novel_id=pid, seq=1, name="林野", role="主角", persona="夜班巡护者"))
            await session.commit()
            await session.close()

        _run_async(_seed())
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 200, r.text
        system = _layered_prompt(fake.last_kwargs)
        assert "【世界观】" in system
        assert "世界铁律·死者不可复生：任何力量都不能把人从死亡里拉回来" in system
        assert "血族议会" in system
        assert "【题材与节奏】" in system
        assert "【人物】" in system and "林野（主角）：夜班巡护者" in system

    def test_draft_material_hooks_carry_due_signal(self, client, monkeypatch):
        """c-og-hooks-projection：活跃伏笔块与写作素材包同口径——
        编号＋优先级/类型＋「建议本章收束」；不给计划收信号则 must_resolve 判断无从谈起。"""
        _set_tier("trial")
        calls: list = []
        fake = _setup_ai(monkeypatch, calls)
        pid, ref = _create_project_and_chapter(client)

        async def _seed():
            from models.hook import NovelHook

            session = async_session()
            proj = await session.get(Novel, pid)
            root = proj.root_path
            ch_row = await chapters_store._get_chapter_by_root(session, root, ref)
            ch_id = ch_row.id
            await session.close()
            session.add_all(
                [
                    # 开书埋点＋计划收=本章 → due：素材应带「建议本章收束」
                    NovelHook(
                        novel_id=pid, seq=1, description="猎血短刃的异常威力",
                        type="mystery", priority=1, status="active",
                        planned_chapter_id=ch_id,
                    ),
                    # 未设计划收 → 只带编号/标注，不带收束信号
                    NovelHook(
                        novel_id=pid, seq=2, description="屋顶黑影的身份",
                        type="mystery", priority=2, status="active",
                    ),
                ]
            )
            await session.commit()
            await session.close()
            return ch_id

        ch_id = _run_async(_seed())
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 200, r.text
        system = _layered_prompt(fake.last_kwargs)
        assert "【活跃伏笔】" in system
        assert "[H-0001] 猎血短刃的异常威力（优先级：高，类型：悬念，建议本章收束）" in system, system
        assert "[H-0002] 屋顶黑影的身份（优先级：中，类型：悬念）" in system
        # 本章引入的伏笔不进素材（与写作注入「排除本章引入」同口径）
        async def _seed2():
            from models.hook import NovelHook

            session = async_session()
            session.add(
                NovelHook(
                    novel_id=pid, seq=3, description="本章才埋的钩子",
                    type="clue", priority=2, status="active",
                    introduced_chapter_id=ch_id,
                )
            )
            await session.commit()
            await session.close()

        _run_async(_seed2())
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 200
        assert "本章才埋的钩子" not in _layered_prompt(fake.last_kwargs)