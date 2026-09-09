"""ai-prompt-crafting — 正文三工序（铁律注入 / 字数校验 / 叙事自查）

单元：run_narrative_self_check 各规则命中与干净正文空清单；铁律常量要素齐全。
契约：POST /write/write 流式生成——system 含铁律；done 事件含 word_check
（不足 <90% 带文案 / 达标无警告）与 self_check；正文照常落库。

用法：
    cd client/backend
    python -m pytest tests/test_prose_pipeline.py -v
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
_tmp_db = tempfile.NamedTemporaryFile(suffix="_pp.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_prose_pipeline_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service  # noqa: E402
from auth_local.deps import require_novel_model, require_project_limit  # noqa: E402
from auth_local.middleware import get_current_user  # noqa: E402
from db import Base, async_session, engine, get_db  # noqa: E402
from filesystem.storage import get_storage  # noqa: E402
from main import app  # noqa: E402
from models.user import User  # noqa: E402
from write.chapter_writer import WRITING_IRON_RULES  # noqa: E402
from write.quality import run_narrative_self_check  # noqa: E402

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")
USER_ID = "pp_user"


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


# ── 单元：叙事自查 ───────────────────────────────────────────────────────


def test_self_check_clean_text_empty():
    text = (
        "雨点砸在铁皮棚上，他没有抬头。\n"
        "杯子里的茶凉了半截，他捏着杯沿转了半圈。\n"
        "「人呢？」掌柜的抹布停在柜台上。\n"
        "「走了。」他说，「天黑前走的。」"
    )
    assert run_narrative_self_check(text) == []


def test_self_check_cognitive_verbs_dense():
    text = (
        "他意识到酒里有问题。\n"
        "他感觉到背后有人盯着。\n"
        "他察觉到掌柜的手在抖。\n"
        "门外的雨还没停。"
    )
    issues = run_narrative_self_check(text)
    rules = [i["rule"] for i in issues]
    assert any("认知动词节制" in r for r in rules)
    entry = next(i for i in issues if "认知动词节制" in i["rule"])
    assert entry["excerpts"]


def test_self_check_perception_lead():
    text = "他看到远处的灯塔亮了。\n再无别的动静。"
    issues = run_narrative_self_check(text)
    assert any("先出感知信号" in i["rule"] for i in issues)


def test_self_check_causal_density():
    text = (
        "因为起雾，所以船停了。\n因为停电，因此灯灭了。\n"
        "由于下雨，于是他留下。\n夜深了。"
    )
    issues = run_narrative_self_check(text)
    assert any("因果自然呈现" in i["rule"] for i in issues)


def test_self_check_label_words():
    text = "门外传来一股强大的气息。\n他退了半步。"
    issues = run_narrative_self_check(text)
    assert any("泛化标签词" in i["rule"] for i in issues)


def test_self_check_markdown_residue():
    text = "以下是本章正文：\n# 第一章\n他推门进去。"
    issues = run_narrative_self_check(text)
    assert any("Markdown/引导语残留" in i["rule"] for i in issues)


def test_self_check_ledger_structure():
    text = "然后他起床。\n接着他洗脸。\n随后他出门。\n街上的灯还亮着。"
    issues = run_narrative_self_check(text)
    assert any("流水账" in i["rule"] for i in issues)


def test_iron_rules_cover_three_clauses():
    assert "不写章节标题" in WRITING_IRON_RULES
    assert "不自行添加" in WRITING_IRON_RULES
    assert "不擅自命名" in WRITING_IRON_RULES
    assert "Markdown" in WRITING_IRON_RULES


# ── 契约：流式生成三工序 ─────────────────────────────────────────────────


class _FakeStreamClient:
    def __init__(self, text: str):
        self._text = text
        self.last_kwargs: dict = {}

    async def chat_stream(self, **kwargs):
        from ai_client import StreamEvent

        self.last_kwargs = kwargs
        mid = len(self._text) // 2
        yield StreamEvent(text=self._text[:mid])
        yield StreamEvent(text=self._text[mid:])
        yield StreamEvent(is_done=True, tokens=99)


def _create_project_and_chapter(client, word_target=None) -> tuple[str, str, str]:
    name = f"pp-{uuid.uuid4().hex[:6]}"
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
        await get_storage().write_yaml(root, "settings/anti-ai.yaml", {})
        data = {"title": "第1章", "prose": ""}
        if word_target:
            data["word_target"] = word_target
        from chapters.store import save_chapter

        await save_chapter(root, ref, data)

    _run_async(_seed())
    return pid, ref, name


def _done_event(resp_text: str) -> dict:
    for line in resp_text.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            if payload.get("type") == "done":
                return payload
    raise AssertionError("no done event in SSE stream")


CLEAN_PROSE = (
    "雨下了一夜。\n"
    "他把伞收在门后，水顺着伞尖在地上积了一小滩。\n"
    "「人呢？」掌柜的抹布停在半空。\n"
    "「走了。」他捏着杯沿转了半圈，「天黑前走的。」\n"
    "灯芯爆了个火星。"
) * 3  # ~ 660 字


class TestWritePipeline:
    def test_iron_rules_injected_and_word_check_ok(self, client, monkeypatch):
        _set_member()
        pid, ref, _ = _create_project_and_chapter(client)  # 无 word_target → 2500
        fake = _FakeStreamClient(CLEAN_PROSE)

        async def _fake_get_ai_client(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake_get_ai_client)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write/write", json={})
        assert r.status_code == 200, r.text
        # 工序①：system 含铁律
        assert "写作铁律" in fake.last_kwargs["system"]
        assert "不擅自命名" in fake.last_kwargs["system"]
        # 工序②：字数达标（660 ≥ 2500*0.9? 不 —— 无目标是 2500，660 字必不足）
        done = _done_event(r.text)
        assert "word_check" in done and "self_check" in done

    def test_word_check_below_limit_with_message(self, client, monkeypatch):
        _set_member()
        pid, ref, _ = _create_project_and_chapter(client, word_target=3000)
        fake = _FakeStreamClient(CLEAN_PROSE)  # ~660 字 < 3000*90%

        async def _fake_get_ai_client(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake_get_ai_client)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write/write", json={})
        assert r.status_code == 200, r.text
        done = _done_event(r.text)
        wc = done["word_check"]
        assert wc["target"] == 3000
        assert wc["below_limit"] is True
        assert wc["message"].startswith("字数不足：目标 3000")
        # 正文照常落库
        from chapters.store import load_chapter
        from models import Novel

        async def _check():
            async with async_session() as session:
                proj = await session.get(Novel, pid)
            loaded = await load_chapter(proj.root_path, ref)
            assert loaded["prose"] == CLEAN_PROSE

        _run_async(_check())

    def test_word_check_within_limit_no_warning(self, client, monkeypatch):
        _set_member()
        # 正文 ×10（~730 字），目标取实长 → 恰在 ±10% 内，无警告
        prose = CLEAN_PROSE * 10
        pid, ref, _ = _create_project_and_chapter(client, word_target=len(prose))
        fake = _FakeStreamClient(prose)

        async def _fake_get_ai_client(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake_get_ai_client)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write/write", json={})
        assert r.status_code == 200, r.text
        done = _done_event(r.text)
        wc = done["word_check"]
        assert wc["below_limit"] is False
        assert "message" not in wc
        # 干净正文 → 自查清单为空
        assert done["self_check"] == []

    def test_self_check_in_done_event_when_issues(self, client, monkeypatch):
        _set_member()
        messy = (
            "以下是本章正文：\n"
            "他意识到事情不对。\n他感觉到背后发凉。\n他察觉到门缝里有风。\n"
            "然后他起身。\n接着他披衣。\n随后他推门。\n"
            "门外是一股强大的气息。"
        ) * 10
        pid, ref, _ = _create_project_and_chapter(client, word_target=600)
        fake = _FakeStreamClient(messy)

        async def _fake_get_ai_client(novel_id=None):
            return fake

        import ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "get_ai_client_for_novel", _fake_get_ai_client)

        r = client.post(f"/api/novels/{pid}/chapters/{ref}/write/write", json={})
        assert r.status_code == 200, r.text
        done = _done_event(r.text)
        rules = " ".join(i["rule"] for i in done["self_check"])
        assert "认知动词节制" in rules
        assert "Markdown/引导语残留" in rules
        assert "泛化标签词" in rules
