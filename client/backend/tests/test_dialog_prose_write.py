"""对话框编排生成正文·write 端点测试（c-agent-dialog-prose 批D）。

- kb_picks 键存在＝agent 模式：空数组零命中无块；带条目走 build_block_from_picks
  （selector=agent）；不含键走规则选块旧路（零变化）
- **上下文隔离铁律**（本文件核心钉）：正文模型的 user prompt＝提示词覆盖稿
  ＋写法块＋收尾行，除此之外一字不加——对话框会话内容没有任何通道进来
"""

import asyncio
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select as sel

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_dpw.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_dialog_prose_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service  # noqa: E402
from auth_local.deps import require_novel_model, require_project_limit  # noqa: E402
from auth_local.middleware import get_current_user  # noqa: E402
from db import Base, async_session, engine, get_db  # noqa: E402
from main import app  # noqa: E402
from models.kb import KbMatchRun  # noqa: E402
from models.user import User  # noqa: E402

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")
USER_ID = "dpw_user"


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


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
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

    _run_async(_create())
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
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = _override_true
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_config_after():
    yield
    if os.path.exists(_CFG_PATH):
        os.remove(_CFG_PATH)


class _FakeStreamClient:
    """抓实参假客户端（判例：fake SDK 抓 create kwargs）。"""

    def __init__(self, text: str):
        self._text = text
        self.last_kwargs: dict = {}

    async def chat_stream(self, **kwargs):
        from ai_client import StreamEvent

        self.last_kwargs = kwargs
        yield StreamEvent(text=self._text)
        yield StreamEvent(is_done=True, tokens=10)


def _create_project_and_chapter() -> tuple[str, str]:
    name = f"dpw-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    client.post(f"/api/novels/{pid}/volumes", json={"vol_num": 1, "title": "第一卷"})
    r2 = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第1章"})
    assert r2.status_code in (200, 201), r2.text
    ref = r2.json()["chapter_ref"]

    from models import Novel

    async def _seed():
        async with async_session() as session:
            proj = await session.get(Novel, pid)
            root = proj.root_path
        from chapters.store import save_chapter

        await save_chapter(root, ref, {"title": "第1章", "prose": ""})

    _run_async(_seed())
    return pid, ref


def _events(resp_text: str) -> list[dict]:
    out = []
    for line in resp_text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def _user_content(fake: _FakeStreamClient) -> str:
    msgs = fake.last_kwargs["messages"]
    assert len(msgs) == 1 and msgs[0]["role"] == "user"
    return msgs[0]["content"]


client = TestClient(app)


def test_kb_picks空数组_agent模式_零命中无块_上下文即覆盖稿():
    from write.chapter_writer import WRITE_CLOSING_LINE

    _set_member()
    pid, ref = _create_project_and_chapter()
    fake = _FakeStreamClient("正文内容。")

    import ai_client as ai_client_mod

    async def _get(_novel_id, **_kw):
        return fake

    mp = pytest.MonkeyPatch()
    mp.setattr(ai_client_mod, "get_ai_client_for_novel", _get)
    try:
        override = "【本章剧情走向（分条）】\n- 对话框编排出来的提示词全文"
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/write",
            json={"prompt": override, "kb_picks": []},
        )
        assert r.status_code == 200, r.text
        evs = _events(r.text)
        assert all(e.get("type") != "write_block" for e in evs)  # 零命中＝无块
        assert any(e.get("type") == "done" for e in evs)
    finally:
        mp.undo()
    # 上下文隔离铁律：user prompt＝覆盖稿＋收尾行，一字不多（会话历史没有通道）
    assert _user_content(fake) == f"{override}\n\n{WRITE_CLOSING_LINE}"


def test_kb_picks带条目_块注入_selector_agent():
    from write.chapter_writer import WRITE_CLOSING_LINE

    _set_member()
    pid, ref = _create_project_and_chapter()

    async def _seed_entries():
        async with async_session() as db:
            from kb.service import create_entry

            entry = (await create_entry(
                db, user_id=USER_ID, genre="", concept="手法",
                title="体温计反转",
                payload={"instruction": "体温计反转：物件反应递减泄底。", "scene": "日常"},
                instruction="体温计反转：物件反应递减泄底。",
            ))[0]
            await db.commit()
            return entry.id

    eid = _run_async(_seed_entries())
    fake = _FakeStreamClient("正文内容。")

    import ai_client as ai_client_mod

    async def _get(_novel_id, **_kw):
        return fake

    mp = pytest.MonkeyPatch()
    mp.setattr(ai_client_mod, "get_ai_client_for_novel", _get)
    try:
        override = "对话框编排出来的提示词全文"
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/write",
            json={"prompt": override, "kb_picks": [{"entry_id": eid, "reason": "物件桥段"}]},
        )
        assert r.status_code == 200, r.text
        evs = _events(r.text)
        wb = [e for e in evs if e.get("type") == "write_block"]
        assert len(wb) == 1
        assert "体温计反转" in wb[0]["block"]
        assert wb[0]["items"][0]["reason"] == "物件桥段"
        assert any(e.get("type") == "done" for e in evs)
    finally:
        mp.undo()
    # user prompt＝覆盖稿＋写法块＋收尾行（隔离：除此之外零附加）
    content = _user_content(fake)
    assert content.startswith(f"{override}\n\n【本章写法指引】")
    assert content.endswith(WRITE_CLOSING_LINE)
    # run 落 selector=agent
    async def _runs():
        async with async_session() as db:
            return (
                await db.execute(
                    sel(KbMatchRun).where(
                        KbMatchRun.novel_id == pid, KbMatchRun.chapter_ref == ref
                    )
                )
            ).scalars().all()
    runs = _run_async(_runs())
    assert len(runs) == 1 and runs[0].selector == "agent"


def test_不含kb_picks键_走规则选块旧路_零条目无块():
    from write.chapter_writer import WRITE_CLOSING_LINE

    _set_member()
    pid, ref = _create_project_and_chapter()
    fake = _FakeStreamClient("正文内容。")

    import ai_client as ai_client_mod

    async def _get(_novel_id, **_kw):
        return fake

    mp = pytest.MonkeyPatch()
    mp.setattr(ai_client_mod, "get_ai_client_for_novel", _get)
    try:
        override = "弹窗时代的提示词覆盖"
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/write",
            json={"prompt": override},
        )
        assert r.status_code == 200, r.text
        evs = _events(r.text)
        assert all(e.get("type") != "write_block" for e in evs)  # 无库无条目＝零命中旧路
        assert any(e.get("type") == "done" for e in evs)
    finally:
        mp.undo()
    assert _user_content(fake) == f"{override}\n\n{WRITE_CLOSING_LINE}"


def test_capabilities_端点_缺省开_env_off关():
    _set_member()
    pid, _ref = _create_project_and_chapter()
    r = client.get(f"/api/novels/{pid}/assistant/capabilities")
    assert r.status_code == 200
    assert r.json()["dialog_prose"] is True

    os.environ["ASSISTANT_PROSE_FLOW"] = "off"
    try:
        r = client.get(f"/api/novels/{pid}/assistant/capabilities")
        assert r.json()["dialog_prose"] is False
    finally:
        os.environ.pop("ASSISTANT_PROSE_FLOW", None)
