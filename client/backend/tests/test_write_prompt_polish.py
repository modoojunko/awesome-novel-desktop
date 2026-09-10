"""ai-prompt-crafting — 润色端点与 GET /write/prompt 存量优先契约

矩阵：
- GET /write/prompt：无存量 → 粗组 + polished:false；润色落库后 → 存量 + polished:true
- POST /write/prompt/polish：会员成功（校验锚词 + 落库 + system 为 prompt_crafting 模板）；
  免费用户 403（AI 不被触达）；校验不合格 502 且既有行不清空；模型错误 502 且不清空。

用法：
    cd client/backend
    python -m pytest tests/test_write_prompt_polish.py -v
"""

import asyncio
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_wpp.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_write_prompt_polish_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service  # noqa: E402
import chapters.store as chapters_store  # noqa: E402
import prompt.store as prompt_store  # noqa: E402
from auth_local.deps import require_novel_model, require_project_limit  # noqa: E402
from auth_local.middleware import get_current_user  # noqa: E402
from db import Base, async_session, engine, get_db  # noqa: E402
from main import app  # noqa: E402
from models import Novel  # noqa: E402
from models.user import User  # noqa: E402

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")

USER_ID = "wpp_user"


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


async def _get_root(pid: str) -> str:
    async with async_session() as session:
        proj = await session.get(Novel, pid)
        return proj.root_path


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


VALID_POLISHED = (
    "## 任务指示\n第 1 章，目标字数约 1800 字（±10%）。\n"
    "## 前情上下文\n无前置章节，开篇直接切入角色当下行动。\n"
    "## 场景原材料\n场景1｜酒馆对峙｜权重：高｜焦点：核心冲突。\n"
    "爽点设计：clue·半块玉佩（中段）。\n"
    "## 不可违反规则\n红线：本章必须完成——主角与师父决裂。\n"
    "## 质感要求\n留 1-2 个不服务主线的细碎生活细节。"
)


class _FakeAIClient:
    def __init__(self, calls: list, reply=VALID_POLISHED, error: Exception | None = None):
        self._calls = calls
        self._reply = reply
        self._error = error
        self.last_kwargs: dict = {}

    async def chat(self, **kwargs):
        self._calls.append("chat")
        self.last_kwargs = kwargs
        if self._error:
            raise self._error
        return self._reply


def _create_project_and_chapter(client) -> tuple[str, str]:
    name = f"wpp-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    r = client.post(f"/api/novels/{pid}/volumes", json={"vol_num": 1, "title": "第一卷"})
    assert r.status_code in (200, 201)
    r2 = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第1章"})
    assert r2.status_code in (200, 201), r2.text
    ref = r2.json()["chapter_ref"]
    # 章纲素材：场景卡 + 爽点 + 字数目标（直接走 store 写全量章数据）

    async def _seed():
        root = await _get_root(pid)
        await chapters_store.save_chapter(
            root,
            ref,
            {
                "title": "第1章",
                "word_target": 1800,
                "scene_cards": [
                    {
                        "scene_name": "酒馆对峙",
                        "goal": "问出货源",
                        "obstacle": "掌柜装傻",
                        "weight": "high",
                        "focus": "核心冲突",
                    }
                ],
                "micro_payoffs": [
                    {"kind": "clue", "description": "半块玉佩", "location": "中段"}
                ],
                "memo": {"required_changes": ["主角与师父决裂"]},
            },
        )

    _run_async(_seed())
    return pid, ref


def _read_stored_prompt(pid: str, ref: str) -> str:
    async def _read():
        root = await _get_root(pid)
        return await prompt_store.load_prompt(root, ref, "write-prompt")

    return _run_async(_read())


def _seed_stored_prompt(pid: str, ref: str, content: str):
    async def _seed():
        root = await _get_root(pid)
        await prompt_store.save_prompt(root, ref, "write-prompt", content)

    _run_async(_seed())


class TestGetWritePrompt:
    def test_no_stored_prompt_returns_draft(self, client):
        _set_tier("monthly")
        pid, ref = _create_project_and_chapter(client)
        r = client.get(f"/api/novels/{pid}/chapters/{ref}/write/prompt")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["polished"] is False
        assert "## 角色定位" in body["prompt"]
        assert "has_outline" in body

    def test_stored_prompt_wins_over_draft(self, client):
        _set_tier("monthly")
        pid, ref = _create_project_and_chapter(client)
        _seed_stored_prompt(pid, ref, "既有润色行")
        r = client.get(f"/api/novels/{pid}/chapters/{ref}/write/prompt")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["polished"] is True
        assert body["prompt"] == "既有润色行"


class TestPolishPrompt:
    def test_member_polish_success(self, client, monkeypatch):
        _set_tier("monthly")
        calls: list = []
        fake = _FakeAIClient(calls)

        async def _fake_get_ai_client(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake_get_ai_client)

        pid, ref = _create_project_and_chapter(client)
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write/prompt/polish")
        assert r.status_code == 200, r.text
        assert calls == ["chat"]
        body = r.json()
        assert body["polished"] is True
        assert "任务指示" in body["prompt"]
        # system 用 prompt_crafting 模板（九段骨架清单特征）
        assert "九段要素" in fake.last_kwargs["system"]
        # user 内容是素材包（带场景原材料原料 + 约束红线）
        assert "【场景原材料】" in fake.last_kwargs["messages"][0]["content"]
        assert "【约束红线" in fake.last_kwargs["messages"][0]["content"]
        # 落库为 write-prompt 行
        stored = _read_stored_prompt(pid, ref)
        assert stored == body["prompt"]

    def test_free_tier_blocked_403(self, client, monkeypatch):
        _set_tier("none", api_key="sk-test")
        calls: list = []

        async def _fake_get_ai_client(novel_id=None):
            return _FakeAIClient(calls)

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake_get_ai_client)

        pid, ref = _create_project_and_chapter(client)
        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write/prompt/polish")
        assert r.status_code == 403
        assert calls == [], "free tier must not reach AI client"
        assert _read_stored_prompt(pid, ref) == ""

    def test_validation_failure_keeps_existing_row(self, client, monkeypatch):
        _set_tier("monthly")
        pid, ref = _create_project_and_chapter(client)
        _seed_stored_prompt(pid, ref, "既有润色行")

        calls: list = []

        async def _fake_get_ai_client(novel_id=None):
            # 缺全部锚词的产物
            return _FakeAIClient(calls, reply="写作提示词如下，请查收。")

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake_get_ai_client)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write/prompt/polish")
        assert r.status_code == 502, r.text
        assert "必备段" in r.text
        # 失败不清空既有行
        assert _read_stored_prompt(pid, ref) == "既有润色行"

    def test_model_error_502_keeps_existing_row(self, client, monkeypatch):
        _set_tier("monthly")
        pid, ref = _create_project_and_chapter(client)

        calls: list = []

        async def _fake_get_ai_client(novel_id=None):
            return _FakeAIClient(calls, error=RuntimeError("upstream down"))

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake_get_ai_client)

        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/write/prompt/polish",
        )
        assert r.status_code == 502, r.text
        assert "润色调用失败" in r.text
        assert _read_stored_prompt(pid, ref) == ""
