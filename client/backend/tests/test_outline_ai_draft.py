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
        # 骨架完整
        assert d["memo"]["current_task"] == "拿到亏空证据并全身而退"
        assert len(d["segments"]) == 2
        # 枚举非法回落（weight/focus 清空键、kind 回落 clue、location 清空键）
        sc = d["scene_cards"][0]
        assert sc["scene_name"] == "账房" and "weight" not in sc and "focus" not in sc
        mp = d["micro_payoffs"][0]
        assert mp["kind"] == "clue" and "location" not in mp
        # word_target clamp 到 6000
        assert d["word_target"] == 6000
        # 不落库：章数据与 status 不变
        assert _read_chapter(pid, ref) == before
        # 素材包含主线卡与改写基底提示
        assert "林昭要查清父亲冤案" in fake.last_kwargs["system"]
        assert "无现有章纲，从零起草" in fake.last_kwargs["system"]
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
                root, ref, {"memo": {"current_task": "作者已定的任务"}}
            )

        _run_async(_seed())
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 200
        assert "作者已定的任务" in fake.last_kwargs["system"]
        assert "无现有章纲" not in fake.last_kwargs["system"]
        # 首章（前情=哨兵）：素材包不含前情段
        assert "【前情" not in fake.last_kwargs["system"]

    def test_segments_only_counts_as_rewrite_base(self, client, monkeypatch):
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
                    "segments": [{"summary": "既定段落", "target_words": 900}],
                    "scene_cards": [{"scene_name": "渡口", "goal": "出城"}],
                },
            )

        _run_async(_seed())
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 200
        assert "既定段落" in fake.last_kwargs["system"]
        assert "无现有章纲" not in fake.last_kwargs["system"]


class TestAiDraftGuarded:
    def test_seg_target_words_coerced(self, client, monkeypatch):
        """段落字数规整：字符串转 int，非法/缺省回落 800（hardening）。"""
        _set_tier("trial")
        calls: list = []
        reply = VALID_DRAFT.replace(
            '"segments": [{"summary": "潜入", "target_words": 800}, {"summary": "翻账", "target_words": 1000}]',
            '"segments": [{"summary": "潜入", "target_words": "800"},'
            ' {"summary": "翻账", "target_words": "很多"}, {"summary": "收尾"}]',
        )
        _setup_ai(monkeypatch, calls, reply=reply)
        pid, ref = _create_project_and_chapter(client)
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 200, r.text
        assert [s["target_words"] for s in r.json()["segments"]] == [800, 800, 800]

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
        assert _token_log_count(pid) == 0  # 失败不计量

    def test_missing_skeleton_502(self, client, monkeypatch):
        _set_tier("trial")
        calls: list = []
        reply = '{"outline": {"summary": "s"}, "memo": {"current_task": "t"}, "segments": []}'
        _setup_ai(monkeypatch, calls, reply=reply)
        pid, ref = _create_project_and_chapter(client)
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/outline/ai-draft")
        assert r.status_code == 502

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
