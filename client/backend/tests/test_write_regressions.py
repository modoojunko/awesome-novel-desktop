"""ai-prompt-crafting — PR #198 review 三项 major 的回归测试

矩阵：
- major 1：无覆盖直写（POST /write/write 空 body）不得用粗组兜底覆盖已润色的
  write-prompt 存量行；显式 override 仍正常覆盖。
- major 2：阶段机不允许回退（write→prompt 重润色 / archive→write 返工）时，
  polish / write 端点宽容跳过推进，不再 500。
- major 3：validate_polished_prompt 的前情/场景原材料锚词按素材有无条件校验
  （无场景卡且无前情的章，产物不含这两段也合格）。

用法：
    cd client/backend
    python -m pytest tests/test_write_regressions.py -v
"""

import asyncio
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_wr.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_write_regressions_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service  # noqa: E402
import prompt.store as prompt_store  # noqa: E402
from auth_local.deps import require_novel_model, require_project_limit  # noqa: E402
from auth_local.middleware import get_current_user  # noqa: E402
from db import Base, async_session, engine, get_db  # noqa: E402
from main import app  # noqa: E402
from models import Novel  # noqa: E402
from models.user import User  # noqa: E402

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")

USER_ID = "wr_user"


def _set_member():
    _service.CONFIG_FILE = _CFG_PATH
    _service.save_local_config(
        {
            "tier": "monthly",
            "expires_at": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
            "api_key": "sk-test",
        }
    )


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


async def _set_phase(pid: str, phase: str):
    async with async_session() as session:
        proj = await session.get(Novel, pid)
        proj.current_phase = phase
        await session.commit()


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


# 无场景卡时仍合格的润色产物（第 1 章素材包带「无前置章节」前情哨兵，故仍需前情锚）
MINIMAL_VALID = (
    "## 任务指示\n第 1 章，目标字数约 2000 字。\n"
    "## 前情上下文\n无前置章节，开篇直接切入角色当下行动。\n"
    "## 不可违反规则\n红线：本章必须完成——主角进城。\n"
    "## 质感要求\n留 1-2 个细碎生活细节。"
)


class _FakeChatClient:
    """润色路径：client.chat 返回固定文本。"""

    def __init__(self, reply: str = MINIMAL_VALID):
        self._reply = reply
        self.last_kwargs: dict = {}

    async def chat(self, **kwargs):
        self.last_kwargs = kwargs
        return self._reply


class _FakeStreamClient:
    """正文路径：client.chat_stream 吐两段 chunk + done。"""

    def __init__(self, text: str = "雨下了一夜。他把伞收在门后。"):
        self._text = text
        self.last_kwargs: dict = {}

    async def chat_stream(self, **kwargs):
        from ai_client import StreamEvent

        self.last_kwargs = kwargs
        mid = len(self._text) // 2
        yield StreamEvent(text=self._text[:mid])
        yield StreamEvent(text=self._text[mid:])
        yield StreamEvent(is_done=True, tokens=42)


def _create_project_and_chapter(client) -> tuple[str, str]:
    name = f"wr-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    r = client.post(f"/api/novels/{pid}/volumes", json={"vol_num": 1, "title": "第一卷"})
    assert r.status_code in (200, 201)
    r2 = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第1章"})
    assert r2.status_code in (200, 201), r2.text
    return pid, r2.json()["chapter_ref"]


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


def _done_event(resp_text: str) -> dict:
    for line in resp_text.splitlines():
        if line.startswith("data: "):
            body = json.loads(line[6:])
            if body.get("type") == "done":
                return body
    raise AssertionError("no done event in stream")


class TestDirectWriteKeepsStoredPrompt:
    """major 1：无覆盖直写不得摧毁已润色提示词。"""

    def test_no_override_reuses_stored_polished(self, client, monkeypatch):
        _set_member()
        pid, ref = _create_project_and_chapter(client)
        _seed_stored_prompt(pid, ref, "已润色版本：任务指示/红线/质感齐备")
        fake = _FakeStreamClient()

        async def _fake(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write/write", json={})
        assert r.status_code == 200, r.text
        assert _done_event(r.text)["type"] == "done"
        # 发给模型的就是存量润色版，而非粗组兜底
        assert "已润色版本" in fake.last_kwargs["messages"][0]["content"]
        # 存量行未被覆盖
        assert _read_stored_prompt(pid, ref) == "已润色版本：任务指示/红线/质感齐备"

    def test_no_stored_falls_back_to_assembly(self, client, monkeypatch):
        _set_member()
        pid, ref = _create_project_and_chapter(client)
        fake = _FakeStreamClient()

        async def _fake(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write/write", json={})
        assert r.status_code == 200, r.text
        # 无存量 → 粗组组装并落库（粗组草稿以角色定位开头，非润色锚词形态）
        assert _read_stored_prompt(pid, ref).startswith("## 角色定位")

    def test_override_still_wins(self, client, monkeypatch):
        _set_member()
        pid, ref = _create_project_and_chapter(client)
        _seed_stored_prompt(pid, ref, "旧存量")
        fake = _FakeStreamClient()

        async def _fake(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake)

        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/write/write",
            json={"prompt": "作家手动编辑版"},
        )
        assert r.status_code == 200, r.text
        assert fake.last_kwargs["messages"][0]["content"] == "作家手动编辑版"
        assert _read_stored_prompt(pid, ref) == "作家手动编辑版"


class TestPhaseRegressionsTolerated:
    """major 2：阶段回退不再 500。"""

    def test_polish_from_write_phase_returns_200(self, client, monkeypatch):
        _set_member()
        pid, ref = _create_project_and_chapter(client)
        _run_async(_set_phase(pid, "write"))
        fake = _FakeChatClient()

        async def _fake(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write/prompt/polish")
        assert r.status_code == 200, r.text
        assert r.json()["polished"] is True
        assert _read_stored_prompt(pid, ref) == MINIMAL_VALID

    def test_write_from_archive_phase_returns_200(self, client, monkeypatch):
        _set_member()
        pid, ref = _create_project_and_chapter(client)
        _run_async(_set_phase(pid, "archive"))
        fake = _FakeStreamClient()

        async def _fake(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write/write", json={})
        assert r.status_code == 200, r.text
        assert _done_event(r.text)["type"] == "done"


class TestAnchorValidationConditional:
    """major 3：前情/场景原材料锚词按素材有无条件校验。"""

    def _ctx(self, **kw):
        from write.chapter_writer import ChapterContext

        ctx = ChapterContext()
        for k, v in kw.items():
            setattr(ctx, k, v)
        return ctx

    def test_sparse_material_passes_without_scene_or_recap(self):
        from write.chapter_writer import validate_polished_prompt

        no_recap_text = MINIMAL_VALID.replace(
            "## 前情上下文\n无前置章节，开篇直接切入角色当下行动。\n", ""
        )
        ctx = self._ctx()  # 无场景卡、无前情、无爽点
        assert validate_polished_prompt(no_recap_text, ctx) == []

    def test_scene_cards_require_scene_anchor(self):
        from write.chapter_writer import validate_polished_prompt

        ctx = self._ctx(scene_cards=[{"scene_name": "城门对峙"}])
        missing = validate_polished_prompt(MINIMAL_VALID, ctx)
        assert "场景原材料" in missing

    def test_prev_recap_requires_recap_anchor(self):
        from write.chapter_writer import validate_polished_prompt

        no_recap_text = MINIMAL_VALID.replace(
            "## 前情上下文\n无前置章节，开篇直接切入角色当下行动。\n", ""
        )
        ctx = self._ctx(previous_chapter_recap="上一章主角进城。")
        missing = validate_polished_prompt(no_recap_text, ctx)
        assert "前情" in missing

    def test_full_still_passes_with_all_anchors(self):
        from write.chapter_writer import validate_polished_prompt

        full = MINIMAL_VALID + "\n## 前情上下文\n上章摘要。\n## 场景原材料\n场景1｜城门。"
        ctx = self._ctx(
            scene_cards=[{"scene_name": "城门对峙"}],
            previous_chapter_recap="上一章摘要",
        )
        assert validate_polished_prompt(full, ctx) == []
