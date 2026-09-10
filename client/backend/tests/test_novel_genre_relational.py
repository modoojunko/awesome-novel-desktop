"""本书题材关系化存储契约测试（genre-signup-redesign D19 / tasks 6.0b·6.0e）。

覆盖：
- `PUT/GET /settings/genre` 五字段 JSON ↔ 4 张表往返（tagId→vocab_id、文本→custom_text、sort 保序）
- `resolve_genre_context(root, novel_id)` 读关系表并把 slug 还原为 label（否则注入是裸 slug）
- `build_genre_section` 渲染新五字段（含 cost_ratio 数值）
- `build_chapter_context(novel_id=...)` 端到端注入
- `GET /api/genres/candidates` 三组候选 + 种子幂等
- 约束：cost_ratio 越界 400；空值统一（""/空白＝未填）；`novel_id` FK CASCADE
"""

import asyncio
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_novel_genre.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_novel_genre_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from sqlalchemy import func, select

from auth_local.deps import (
    require_ai_access,
    require_novel_model,
    require_project_limit,
)
from auth_local.middleware import get_current_user
from db import Base, async_session, engine, get_db
from genres.novel_genre_service import (
    custom_vocab_id,
    ensure_custom_vocab,
    ensure_seed_genre_vocab,
    genre_is_filled,
    get_novel_genre,
    put_novel_genre,
)
from genres.service import build_genre_section, resolve_genre_context
from main import app
from models.novel_genre import (
    GenreVocab,
    NovelGenre,
    NovelGenreBattlefield,
    NovelGenreForbidden,
)
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


async def _create_user(user_id: str) -> None:
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


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    _run_async(_create_tables())
    _run_async(_create_user("genreuser"))
    _run_async(ensure_seed_genre_vocab())
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "genreuser"}


async def _override_true():
    return True


@pytest.fixture(autouse=True)
def _setup_overrides():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_ai_access] = _override_true
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = _override_true
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _new_novel(client) -> str:
    name = f"题材关系化-{uuid.uuid4().hex[:8]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


FULL_PAYLOAD = {
    "core_promise": "以弱破强的痛快",
    "promise_note": "读者要看到弱者用脑子翻盘",
    "forbidden_list": [
        {"tagId": "forbidden:no-deus-ex-machina"},
        {"text": "自定义禁项"},
        {"tagId": "forbidden:no-villain-idiot"},
    ],
    "cost_ratio": 7,
    "battlefield": ["battlefield:resources", "家门口的巷子"],
    "track": "从被赶出家门到掌控全城",
}


# ── 五字段 JSON ↔ 4 表往返 ────────────────────────────────────────────────


class TestRoundTrip:
    def test_put_get_roundtrip_five_fields(self, client):
        pid = _new_novel(client)
        r = client.put(f"/api/novels/{pid}/settings/genre", json=FULL_PAYLOAD)
        assert r.status_code == 200, r.text

        got = client.get(f"/api/novels/{pid}/settings/genre")
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["core_promise"] == "以弱破强的痛快"
        assert body["promise_note"] == "读者要看到弱者用脑子翻盘"
        assert body["cost_ratio"] == 7
        assert body["track"] == "从被赶出家门到掌控全城"
        assert body["forbidden_list"] == FULL_PAYLOAD["forbidden_list"]
        assert body["battlefield"] == FULL_PAYLOAD["battlefield"]

    def test_relational_rows_and_sort(self, client):
        pid = _new_novel(client)
        client.put(f"/api/novels/{pid}/settings/genre", json=FULL_PAYLOAD)

        async def _read():
            async with async_session() as session:
                forbid = (
                    await session.execute(
                        select(NovelGenreForbidden)
                        .where(NovelGenreForbidden.novel_id == pid)
                        .order_by(NovelGenreForbidden.sort)
                    )
                ).scalars().all()
                bf = (
                    await session.execute(
                        select(NovelGenreBattlefield)
                        .where(NovelGenreBattlefield.novel_id == pid)
                        .order_by(NovelGenreBattlefield.sort)
                    )
                ).scalars().all()
                return forbid, bf

        forbid, bf = _run_async(_read())
        assert [f.vocab_id for f in forbid] == [
            "forbidden:no-deus-ex-machina",
            None,
            "forbidden:no-villain-idiot",
        ]
        assert [f.custom_text for f in forbid] == [None, "自定义禁项", None]
        assert [f.sort for f in forbid] == [0, 1, 2]
        assert [b.vocab_id for b in bf] == ["battlefield:resources", None]
        assert [b.custom_text for b in bf] == [None, "家门口的巷子"]
        assert [b.sort for b in bf] == [0, 1]

    def test_put_replaces_lists_wholesale(self, client):
        pid = _new_novel(client)
        client.put(f"/api/novels/{pid}/settings/genre", json=FULL_PAYLOAD)
        client.put(
            f"/api/novels/{pid}/settings/genre",
            json={**FULL_PAYLOAD, "forbidden_list": [], "battlefield": []},
        )

        async def _count():
            async with async_session() as session:
                f = await session.execute(
                    select(func.count())
                    .select_from(NovelGenreForbidden)
                    .where(NovelGenreForbidden.novel_id == pid)
                )
                b = await session.execute(
                    select(func.count())
                    .select_from(NovelGenreBattlefield)
                    .where(NovelGenreBattlefield.novel_id == pid)
                )
                return f.scalar_one(), b.scalar_one()

        assert _run_async(_count()) == (0, 0)

    def test_empty_values_normalized_to_unfilled(self, client):
        pid = _new_novel(client)
        client.put(
            f"/api/novels/{pid}/settings/genre",
            json={
                "core_promise": "   ",
                "promise_note": "",
                "forbidden_list": [],
                "cost_ratio": None,
                "battlefield": [],
                "track": "",
            },
        )
        body = client.get(f"/api/novels/{pid}/settings/genre").json()
        assert body["core_promise"] == ""
        assert body["track"] == ""
        assert body["cost_ratio"] is None
        assert body["forbidden_list"] == []
        assert body["battlefield"] == []

        async def _filled():
            async with async_session() as session:
                return await genre_is_filled(session, pid)

        assert _run_async(_filled()) is False

    def test_cost_ratio_out_of_range_400(self, client):
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre",
            json={**FULL_PAYLOAD, "cost_ratio": 11},
        )
        assert r.status_code == 400, r.text

    def test_core_promise_over_60_400(self, client):
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre", json={"core_promise": "字" * 61}
        )
        assert r.status_code == 400, r.text

    def test_track_over_300_400(self, client):
        pid = _new_novel(client)
        r = client.put(f"/api/novels/{pid}/settings/genre", json={"track": "字" * 301})
        assert r.status_code == 400, r.text

    def test_forbidden_list_over_50_400(self, client):
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre",
            json={"forbidden_list": [{"text": f"禁项{i}"} for i in range(51)]},
        )
        assert r.status_code == 400, r.text

    def test_battlefield_over_10_400(self, client):
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre",
            json={"battlefield": [f"战场{i}" for i in range(11)]},
        )
        assert r.status_code == 400, r.text

    def test_custom_battlefield_over_20_400(self, client):
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre", json={"battlefield": ["字" * 21]}
        )
        assert r.status_code == 400, r.text

    def test_unknown_keys_ignored_on_replace(self, client):
        """整对象覆盖：旧键（genre_id 等）自动清除，不报错也不落库。"""
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre",
            json={"genre_id": "urban-romance", "core_promise": "以弱破强的痛快"},
        )
        assert r.status_code == 200, r.text
        body = client.get(f"/api/novels/{pid}/settings/genre").json()
        assert body["core_promise"] == "以弱破强的痛快"
        assert "genre_id" not in body

    def test_core_promise_alone_is_filled(self, client):
        pid = _new_novel(client)
        client.put(
            f"/api/novels/{pid}/settings/genre",
            json={"core_promise": "以弱破强的痛快"},
        )

        async def _filled():
            async with async_session() as session:
                return await genre_is_filled(session, pid)

        assert _run_async(_filled()) is True

    def test_novel_delete_cascades(self, client):
        """硬删 novels 行 → novel_genre 与关联表级联清空（FK ON DELETE CASCADE）。

        `DELETE /api/novels/{id}` 是软删（status=deleted），不触发级联；
        此处直接删行验证 FK 契约。
        """
        pid = _new_novel(client)
        client.put(f"/api/novels/{pid}/settings/genre", json=FULL_PAYLOAD)

        async def _hard_delete_and_count():
            async with async_session() as session:
                from models.project import Novel

                row = await session.get(Novel, pid)
                await session.delete(row)
                await session.commit()
                g = await session.get(NovelGenre, pid)
                f = await session.execute(
                    select(func.count())
                    .select_from(NovelGenreForbidden)
                    .where(NovelGenreForbidden.novel_id == pid)
                )
                return g, f.scalar_one()

        row, forbid_count = _run_async(_hard_delete_and_count())
        assert row is None
        assert forbid_count == 0


# ── resolve_genre_context / build_genre_section ───────────────────────────


class TestInjection:
    def test_resolve_reads_relational_and_labels(self, client):
        pid = _new_novel(client)
        client.put(f"/api/novels/{pid}/settings/genre", json=FULL_PAYLOAD)
        ctx = _run_async(resolve_genre_context("", pid))
        assert ctx is not None
        assert ctx["core_promise"] == "以弱破强的痛快"
        assert ctx["cost_ratio"] == 7
        # slug 还原为可读 label（裸 slug 注入等于没注入）
        assert ctx["forbidden"] == ["禁天降外援", "自定义禁项", "禁反派降智"]
        assert ctx["battlefield"] == ["抢资源", "家门口的巷子"]

    def test_resolve_empty_returns_none(self, client):
        pid = _new_novel(client)
        assert _run_async(resolve_genre_context("", pid)) is None

    def test_build_section_renders_new_fields(self):
        section = build_genre_section(
            {
                "core_promise": "以弱破强的痛快",
                "promise_note": "读者要看到弱者用脑子翻盘",
                "cost_ratio": 7,
                "track": "从被赶出家门到掌控全城",
                "forbidden": ["禁天降外援"],
                "battlefield": ["抢资源"],
            }
        )
        assert "## 题材设定" in section
        assert "核心承诺：以弱破强的痛快" in section
        assert "读者预期：读者要看到弱者用脑子翻盘" in section
        assert "吃苦指数：7" in section
        assert "剧情轨道：从被赶出家门到掌控全城" in section
        assert "绝对禁止：禁天降外援" in section
        assert "主线战场：抢资源" in section

    def test_chapter_context_injects_new_section(self, client):
        from write.chapter_writer import build_chapter_context

        pid = _new_novel(client)
        client.put(f"/api/novels/{pid}/settings/genre", json=FULL_PAYLOAD)

        async def _ctx():
            async with async_session() as session:
                novel = await session.get(NovelGenre, pid)
                return novel.novel_id

        novel_id = _run_async(_ctx())
        # 直接以 novel_id 组装上下文（章节不存在时其余素材为空，题材块仍注入）
        root = _run_async(_root_of(pid))
        ctx = _run_async(build_chapter_context(root, "vol-1-ch-1", "题材注入", novel_id))
        assert "核心承诺：以弱破强的痛快" in ctx.genre_section
        assert "核心承诺" in ctx.to_prompt()


async def _root_of(novel_id: str) -> str:
    from novels.service import get_novel

    async with async_session() as session:
        novel = await get_novel(session, novel_id, "genreuser")
        return novel.root_path


# ── 候选源 ────────────────────────────────────────────────────────────────


class TestCandidates:
    def test_candidates_three_groups(self, client):
        r = client.get("/api/genres/candidates")
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) >= {"promise", "forbidden", "battlefield"}
        assert {"id": "promise:comeback", "label": "以弱破强的痛快", "is_preset": True} in body[
            "promise"
        ]
        assert any(x["id"] == "forbidden:no-deus-ex-machina" for x in body["forbidden"])
        assert any(x["id"] == "battlefield:resources" for x in body["battlefield"])

    def test_candidates_not_shadowed_by_genre_id_route(self, client):
        """`/candidates` 必须优先于 `/{genre_id}` 匹配。"""
        r = client.get("/api/genres/candidates")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_seed_is_idempotent(self):
        _run_async(ensure_seed_genre_vocab())

        async def _count():
            async with async_session() as session:
                res = await session.execute(select(func.count()).select_from(GenreVocab))
                return res.scalar_one()

        from genres.vocab_presets import VOCAB_PRESETS

        assert _run_async(_count()) == len(VOCAB_PRESETS)


# ── 服务层单测 ────────────────────────────────────────────────────────────


class TestService:
    def test_get_returns_empty_shape_without_row(self, client):
        pid = _new_novel(client)

        async def _get():
            async with async_session() as session:
                return await get_novel_genre(session, pid)

        body = _run_async(_get())
        assert body == {
            "core_promise": "",
            "promise_note": "",
            "forbidden_list": [],
            "cost_ratio": None,
            "battlefield": [],
            "track": "",
        }

    def test_put_ignores_malformed_forbidden_item(self, client):
        pid = _new_novel(client)

        async def _put():
            async with async_session() as session:
                await put_novel_genre(
                    session,
                    pid,
                    {
                        "forbidden_list": ["裸字符串", {"tagId": "forbidden:no-free-powerup"}],
                        "battlefield": ["", "  "],
                    },
                )

        _run_async(_put())
        body = client.get(f"/api/novels/{pid}/settings/genre").json()
        assert body["forbidden_list"] == [{"tagId": "forbidden:no-free-powerup"}]
        assert body["battlefield"] == []


class TestCustomVocab:
    def test_custom_vocab_id_slug(self):
        assert custom_vocab_id("forbidden", "禁 老套 桥段") == "custom:forbidden:禁-老套-桥段"
        assert custom_vocab_id("forbidden", "!!!") == "custom:forbidden:item"

    def test_custom_vocab_id_dedup_suffix(self):
        taken = {"custom:forbidden:x", "custom:forbidden:x-2"}
        assert custom_vocab_id("forbidden", "x", taken) == "custom:forbidden:x-3"

    def test_ensure_custom_vocab_idempotent(self, client):
        async def _two_calls():
            async with async_session() as session:
                first = await ensure_custom_vocab(session, "battlefield", "抢地盘")
            async with async_session() as session:
                second = await ensure_custom_vocab(session, "battlefield", "抢地盘")
            async with async_session() as session:
                res = await session.execute(
                    select(func.count())
                    .select_from(GenreVocab)
                    .where(GenreVocab.label == "抢地盘")
                )
                return first, second, res.scalar_one()

        first, second, count = _run_async(_two_calls())
        assert first == second == "custom:battlefield:抢地盘"
        assert count == 1

    def test_ensure_custom_vocab_blank_returns_none(self, client):
        async def _call():
            async with async_session() as session:
                return await ensure_custom_vocab(session, "forbidden", "   ")

        assert _run_async(_call()) is None

    def test_custom_vocab_appears_in_candidates(self, client):
        async def _seed():
            async with async_session() as session:
                return await ensure_custom_vocab(session, "forbidden", "禁 无脑装逼")

        vid = _run_async(_seed())
        body = client.get("/api/genres/candidates").json()
        assert {"id": vid, "label": "禁 无脑装逼", "is_preset": False} in body["forbidden"]


# ── 边界值（tasks 9.2.15）────────────────────────────────────────────────


class TestBoundaries:
    @pytest.mark.parametrize("value", [0, 11, -1, 100])
    def test_cost_ratio_out_of_range(self, client, value):
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre", json={"cost_ratio": value}
        )
        assert r.status_code == 400, r.text

    @pytest.mark.parametrize("value", [1, 10])
    def test_cost_ratio_bounds_accepted(self, client, value):
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre", json={"cost_ratio": value}
        )
        assert r.status_code == 200, r.text
        assert client.get(f"/api/novels/{pid}/settings/genre").json()["cost_ratio"] == value

    def test_battlefield_at_limit_accepted(self, client):
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre",
            json={"battlefield": [f"战场{i}" for i in range(10)]},
        )
        assert r.status_code == 200, r.text

    def test_battlefield_custom_at_20_chars(self, client):
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre", json={"battlefield": ["字" * 20]}
        )
        assert r.status_code == 200, r.text

    def test_forbidden_at_limit_accepted(self, client):
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre",
            json={"forbidden_list": [{"text": f"禁{i}"} for i in range(50)]},
        )
        assert r.status_code == 200, r.text


# ── 参数等价类（tasks 9.2.14）──────────────────────────────────────────────


class TestEquivalenceClasses:
    """逐入参划分合法/非法/空等价类（同一行为类只测代表值）。"""

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_core_promise_blank_equivalents(self, client, value):
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre", json={"core_promise": value}
        )
        assert r.status_code == 200, r.text
        assert client.get(f"/api/novels/{pid}/settings/genre").json()["core_promise"] == ""

    def test_core_promise_special_chars_accepted(self, client):
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre",
            json={"core_promise": "<>{}'\"` 特殊字符"},
        )
        assert r.status_code == 200, r.text

    def test_emoji_accepted_and_roundtrips(self, client):
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre", json={"core_promise": "爽点🔥到炸"}
        )
        assert r.status_code == 200, r.text
        assert (
            client.get(f"/api/novels/{pid}/settings/genre").json()["core_promise"]
            == "爽点🔥到炸"
        )

    def test_forbidden_item_both_keys_present_prefers_tag(self, client):
        """同时给 tagId 与 text → 按 tagId 落（恰一非空的 DB 约束不破）。"""
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre",
            json={
                "forbidden_list": [
                    {"tagId": "forbidden:no-foresight", "text": "被忽略的自定义"}
                ]
            },
        )
        assert r.status_code == 200, r.text
        assert client.get(f"/api/novels/{pid}/settings/genre").json()["forbidden_list"] == [
            {"tagId": "forbidden:no-foresight"}
        ]

    def test_unknown_tag_id_400_not_500(self, client):
        """未知 tagId（词汇已删/拼错）→ 400 可读错误，不得 FK 炸 500。"""
        pid = _new_novel(client)
        r = client.put(
            f"/api/novels/{pid}/settings/genre",
            json={"forbidden_list": [{"tagId": "forbidden:ghost"}]},
        )
        assert r.status_code == 400, r.text
        assert "未知的候选词汇" in r.text

    def test_cost_ratio_string_numeric_coerced(self, client):
        pid = _new_novel(client)
        r = client.put(f"/api/novels/{pid}/settings/genre", json={"cost_ratio": "7"})
        assert r.status_code == 200, r.text
        assert client.get(f"/api/novels/{pid}/settings/genre").json()["cost_ratio"] == 7

    def test_cost_ratio_non_numeric_400(self, client):
        pid = _new_novel(client)
        r = client.put(f"/api/novels/{pid}/settings/genre", json={"cost_ratio": "高"})
        assert r.status_code == 400, r.text


# ── total_archives 语义＝已归档章节数（书架卡片阶段判据，必须先准）──────────────


class TestArchiveCounter:
    """归档 +1（幂等）、取消归档 −1（对称）——卡片阶段判据依赖它。"""

    def _setup(self, client):
        pid = _new_novel(client)
        r = client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷"})
        assert r.status_code in (200, 201), r.text
        vol_ref = r.json().get("ref") or "vol-1"
        r2 = client.post(f"/api/novels/{pid}/volumes/{vol_ref}/chapters", json={"title": "第一章"})
        assert r2.status_code in (200, 201), r2.text
        ref = r2.json().get("ref") or f"{vol_ref}-ch-1"
        return pid, ref

    def _archives(self, pid) -> int:
        import sqlite3

        from config import DATABASE_URL

        path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return con.execute(
                "SELECT total_archives FROM novels WHERE id = ?", (pid,)
            ).fetchone()[0]
        finally:
            con.close()

    def test_archive_then_unarchive_is_symmetric(self, client):
        pid, ref = self._setup(client)
        text = "第一章正文。" + "内容。" * 60

        assert client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive",
            json={"full_text": text, "ai_summary": False},
        ).status_code == 200
        assert self._archives(pid) == 1

        assert client.post(f"/api/novels/{pid}/chapters/{ref}/unarchive").status_code == 200
        assert self._archives(pid) == 0, "取消归档必须回减，否则卡片会误判写完"

    def test_rearchive_is_idempotent(self, client):
        pid, ref = self._setup(client)
        text = "第一章正文。" + "内容。" * 60
        for _ in range(2):
            client.post(
                f"/api/novels/{pid}/chapters/{ref}/archive",
                json={"full_text": text, "ai_summary": False},
            )
        assert self._archives(pid) == 1, "重复归档同一章不得重复计数"

    def test_unarchive_when_not_archived_never_goes_negative(self, client):
        pid, ref = self._setup(client)
        assert client.post(f"/api/novels/{pid}/chapters/{ref}/unarchive").status_code == 200
        assert self._archives(pid) == 0

    def _shelf_item(self, client, pid) -> dict:
        items = client.get("/api/novels").json()
        rows = items if isinstance(items, list) else items.get("items", [])
        return next(r for r in rows if r["id"] == pid)

    def test_shelf_counters_come_from_chapter_table(self, client):
        """书架下发口径＝章表聚合（卡片阶段判据），且自愈列上的漂移计数。"""
        pid, ref = self._setup(client)
        text = "第一章正文。" + "内容。" * 60

        before = self._shelf_item(client, pid)
        assert (before["total_chapters"], before["total_archives"]) == (1, 0)

        client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive",
            json={"full_text": text, "ai_summary": False},
        )
        after = self._shelf_item(client, pid)
        assert (after["total_chapters"], after["total_archives"]) == (1, 1)

        # 人为把列上的计数改脏（模拟历史库/旧版本漏减）→ 下发值仍以章表为准
        import sqlite3

        from config import DATABASE_URL

        path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        con = sqlite3.connect(path)
        try:
            con.execute("UPDATE novels SET total_archives = 7 WHERE id = ?", (pid,))
            con.commit()
        finally:
            con.close()
        healthy = self._shelf_item(client, pid)
        assert healthy["total_archives"] == 1, "卡片不得读列上的漂移计数"

        client.post(f"/api/novels/{pid}/chapters/{ref}/unarchive")
        back = self._shelf_item(client, pid)
        assert (back["total_chapters"], back["total_archives"]) == (1, 0)


# ── 题材展示名（书卡胶囊 / 书内标签）单源：新契约核心承诺优先 ─────────────


class TestGenreDisplaySource:
    """题材胶囊/标签取值来自题材（core_promise）；空值＝未设定（前端以占位呈现）。"""

    def test_shelf_genre_comes_from_core_promise(self, client):
        pid = _new_novel(client)
        before = client.get("/api/novels").json()
        item = next(r for r in before if r["id"] == pid)
        assert not item["genre"], "未设定题材时不下发题材名（前端占位）"

        client.put(
            f"/api/novels/{pid}/settings/genre",
            json={"core_promise": "以弱破强的痛快"},
        )
        after = client.get("/api/novels").json()
        item = next(r for r in after if r["id"] == pid)
        assert item["genre"] == "以弱破强的痛快"

    def test_detail_genre_label_matches_shelf(self, client):
        pid = _new_novel(client)
        client.put(
            f"/api/novels/{pid}/settings/genre",
            json={"core_promise": "层层反转的智力快感", "cost_ratio": 5},
        )
        detail = client.get(f"/api/novels/{pid}").json()
        assert detail["genre_label"] == "层层反转的智力快感"
        # 旧字段保留（老书 / 外部消费者兼容）：题材核心承诺不进 genre（那是历史 KV 口径）
        assert detail["genre"] in (None, "")
        assert detail["genre_name"] in (None, "")

    def test_core_promise_blank_falls_back_to_none(self, client):
        """只有 03/04 等非核心承诺字段时，展示名仍为空（胶囊走占位，不编造题材名）。"""
        pid = _new_novel(client)
        client.put(f"/api/novels/{pid}/settings/genre", json={"cost_ratio": 8})
        item = next(r for r in client.get("/api/novels").json() if r["id"] == pid)
        assert not item["genre"]
        detail = client.get(f"/api/novels/{pid}").json()
        assert not detail["genre_label"]
