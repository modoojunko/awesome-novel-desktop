"""ai-prompt-crafting — PR #198 review 三项 major 的回归测试

矩阵：
- major 1：无覆盖直写（POST /write 空 body）不得用粗组兜底覆盖存量的
  write-prompt 行；显式 override 仍正常覆盖。
- major 2：阶段机不允许回退（archive→write 返工）时，write 端点宽容跳过推进，
  不再 500。原「write→prompt 重润色」用例随 c-retire-prompt-polish 退役
  （润色端点已下线，阶段宽容口径由 /write 返工用例继续钉住）。
- major 3（已随 c-retire-prompt-polish 退役）：validate_polished_prompt 的
  条件锚校验随润色链删除。

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
            "tier": "max",
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


def _create_two_chapters(client) -> tuple[str, str]:
    """建书＋卷＋两章，返回 (pid, ch2_ref)——ch-2 有上一章可落正文。"""
    name = f"wr2-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    r = client.post(f"/api/novels/{pid}/volumes", json={"vol_num": 1, "title": "第一卷"})
    assert r.status_code in (200, 201)
    r1 = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第1章"})
    assert r1.status_code in (200, 201), r1.text
    r2 = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第2章"})
    assert r2.status_code in (200, 201), r2.text
    return pid, r2.json()["chapter_ref"]


def _seed_prev_prose(pid: str):
    """给 vol-1-ch-1 落正文并置 archived（ch-2 素材含尾块且过主线门禁）。"""
    from sqlalchemy import update

    from chapters.store import save_chapter
    from models.chapter import Chapter

    async def _seed():
        root = await _get_root(pid)
        await save_chapter(
            root, "vol-1-ch-1", {"prose": "上一章的正文。\n雨衣人回过头，便签烫起来。"}
        )
        async with async_session() as session:
            await session.execute(
                update(Chapter)
                .where(Chapter.project_id == pid, Chapter.ref == "vol-1-ch-1")
                .values(status="archived", has_prose=True)
            )
            await session.commit()

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

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write", json={})
        assert r.status_code == 200, r.text
        assert _done_event(r.text)["type"] == "done"
        # 发给模型的就是存量润色版＋收尾重申行（c-write-prompt-layering：两路径同样生效）
        from write.chapter_writer import WRITE_CLOSING_LINE

        content = fake.last_kwargs["messages"][0]["content"]
        assert "已润色版本" in content
        assert content.endswith(WRITE_CLOSING_LINE)
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

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write", json={})
        assert r.status_code == 200, r.text
        # 无存量 → 章级素材组装并落库（c-write-prompt-layering：恒定块在 system 层）
        stored = _read_stored_prompt(pid, ref)
        assert stored.startswith("## 当前章节")
        assert "## 角色定位" not in stored

    def test_stale_draft_without_tail_block_refreshes(self, client, monkeypatch):
        """c-chapter-seam-hardcut：存量粗组稿缺「上章结尾」块且本轮素材含该块
        → 生成回落重组（升级后的重生成吃到新素材），落库行被回落稿更新。"""
        _set_member()
        pid, ref = _create_two_chapters(client)
        _seed_prev_prose(pid)
        _seed_stored_prompt(pid, ref, "## 当前章节\n章纲：旧版组装的粗组稿")
        fake = _FakeStreamClient()

        async def _fake(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write", json={})
        assert r.status_code == 200, r.text
        assert _done_event(r.text)["type"] == "done"
        content = fake.last_kwargs["messages"][0]["content"]
        assert "上章结尾（原文）" in content
        # 落库行被回落稿更新（旧粗组稿无作者内容，覆盖无损失）
        assert "上章结尾（原文）" in _read_stored_prompt(pid, ref)

    def test_polished_without_tail_block_stays(self, client, monkeypatch):
        """c-chapter-seam-hardcut：润色稿（三锚）缺「上章结尾」段也不回落——
        作者资产 SHALL NOT 被重组稿覆盖。"""
        _set_member()
        pid, ref = _create_two_chapters(client)
        polished = "## 任务指示\n旧素材下润色的稿。\n## 红线\n无。\n## 质感\n细节。"
        _seed_stored_prompt(pid, ref, polished)
        _seed_prev_prose(pid)
        fake = _FakeStreamClient()

        async def _fake(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write", json={})
        assert r.status_code == 200, r.text
        assert _done_event(r.text)["type"] == "done"
        content = fake.last_kwargs["messages"][0]["content"]
        assert "旧素材下润色的稿" in content
        assert "上章结尾（原文）" not in content
        assert _read_stored_prompt(pid, ref) == polished

    def test_no_tail_block_keeps_stored(self, client, monkeypatch):
        """c-chapter-seam-hardcut：素材无尾块（首章/上章无正文）时守卫不触发，
        存量稿照旧复用。"""
        _set_member()
        pid, ref = _create_project_and_chapter(client)
        _seed_stored_prompt(pid, ref, "## 当前章节\n章纲：首章旧稿")
        fake = _FakeStreamClient()

        async def _fake(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write", json={})
        assert r.status_code == 200, r.text
        content = fake.last_kwargs["messages"][0]["content"]
        assert "首章旧稿" in content
        assert "上章结尾（原文）" not in content

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write", json={})
        assert r.status_code == 200, r.text
        content = fake.last_kwargs["messages"][0]["content"]
        assert "首章旧稿" in content
        assert "上章结尾（原文）" not in content

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
            f"/api/novels/{pid}/chapters/{ref}/write",
            json={"prompt": "作家手动编辑版"},
        )
        assert r.status_code == 200, r.text
        # c-write-prompt-layering：收尾重申行在发送前追加，落库行不含
        from write.chapter_writer import WRITE_CLOSING_LINE

        assert fake.last_kwargs["messages"][0]["content"] == (
            "作家手动编辑版\n\n" + WRITE_CLOSING_LINE
        )
        assert _read_stored_prompt(pid, ref) == "作家手动编辑版"


class TestPhaseRegressionsTolerated:
    """major 2：阶段回退不再 500。"""

    def test_write_from_archive_phase_returns_200(self, client, monkeypatch):
        _set_member()
        pid, ref = _create_project_and_chapter(client)
        _run_async(_set_phase(pid, "archive"))
        fake = _FakeStreamClient()

        async def _fake(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write", json={})
        assert r.status_code == 200, r.text
        assert _done_event(r.text)["type"] == "done"
