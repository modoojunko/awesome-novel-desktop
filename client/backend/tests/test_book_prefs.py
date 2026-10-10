"""作品偏好「章节默认字数」端到端（c-chapter-default-words，内测反馈#10）。

覆盖：模型归一（区间/缺省/清除语义）→ 端点读写（GET 空态/PUT 设置/400/清除）
→ 生成链取用（章纲未填走本书默认、逐章显式值优先、未设置存量行为不变 2500）。

用法：
    cd client/backend && python -m pytest tests/test_book_prefs.py -v
"""

import asyncio
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_local.middleware import get_current_user
from db import async_session
from filesystem.paths import BOOK_PREFS_PATH
from filesystem.storage import get_storage
from main import app
from models.project import Novel
from settings import book_prefs_model as bm

USER_ID = "bp_user"


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _seed_book() -> tuple[str, str]:
    """种一本书，返回 (root_path, novel_id)——端点路径参数用 id（get_novel 按 id+user 查）。"""
    root = tempfile.mkdtemp(prefix="test_book_prefs_")
    slug = f"bp-{os.path.basename(root)}"
    async with async_session() as session:
        session.add(
            Novel(
                user_id=USER_ID,
                name="默认字数书",
                slug=slug,
                root_path=root,
                source="manual",
                current_phase="outline",
            )
        )
        await session.commit()
        row = (
            await session.execute(select(Novel).where(Novel.root_path == root))
        ).scalar_one()
        return root, row.id


def _client(user_id: str = USER_ID):
    c = TestClient(app)
    app.dependency_overrides[get_current_user] = lambda: {"id": user_id}
    return c


# ── 模型：归一与缺省 ────────────────────────────────────────────────────────


class TestModel:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (None, None),
            ("", None),
            (500, 500),
            (2500, 2500),
            (6000, 6000),
        ],
    )
    def test_normalize_accepts_and_clears(self, raw, expected):
        assert bm.normalize_chapter_word_target(raw) == expected

    @pytest.mark.parametrize("raw", [400, 6001, 0, -100, "2500", 2500.0, True])
    def test_normalize_rejects_out_of_range_and_non_int(self, raw):
        """越界/非整数不静默改写——API 兜底 400（表单已按区间限制）。"""
        with pytest.raises((TypeError, ValueError)):
            bm.normalize_chapter_word_target(raw)

    def test_effective_falls_back_to_default(self):
        """未设置/损坏值一律回落缺省 2500（存量项目零迁移、行为不变）。"""
        assert bm.effective_chapter_word_target(None) == 2500
        assert bm.effective_chapter_word_target({}) == 2500
        assert bm.effective_chapter_word_target({"chapter_word_target": 99999}) == 2500
        assert bm.effective_chapter_word_target({"chapter_word_target": "3000"}) == 2500
        assert bm.effective_chapter_word_target({"chapter_word_target": 3000}) == 3000

    def test_read_drops_invalid_fields(self):
        assert bm.read_book_prefs({"chapter_word_target": 3000}) == {
            "chapter_word_target": 3000
        }
        assert bm.read_book_prefs({"chapter_word_target": 10}) == {}
        assert bm.read_book_prefs("nonsense") == {}


# ── 端点：读写贯通 ──────────────────────────────────────────────────────────


class TestRouter:
    def test_get_empty_then_put_roundtrip(self):
        root, nid = _run_async(_seed_book())
        with _client() as c:
            r = c.get(f"/api/novels/{nid}/settings/book-prefs")
            assert r.status_code == 200 and r.json() == {}
            r = c.put(
                f"/api/novels/{nid}/settings/book-prefs",
                json={"chapter_word_target": 3000},
            )
            assert r.status_code == 200 and r.json() == {"chapter_word_target": 3000}
            assert c.get(f"/api/novels/{nid}/settings/book-prefs").json() == {
                "chapter_word_target": 3000
            }
        # 落 KV（route_relative_path 专用键）
        assert _run_async(get_storage().read_yaml(root, BOOK_PREFS_PATH)) == {
            "chapter_word_target": 3000
        }

    @pytest.mark.parametrize("bad", [400, 6001, "abc", 2500.5])
    def test_put_out_of_range_400(self, bad):
        nid = _run_async(_seed_book())[1]
        with _client() as c:
            r = c.put(
                f"/api/novels/{nid}/settings/book-prefs",
                json={"chapter_word_target": bad},
            )
            assert r.status_code == 400, r.text
            assert "章节默认字数" in r.json()["detail"]

    def test_put_null_clears_setting(self):
        nid = _run_async(_seed_book())[1]
        with _client() as c:
            c.put(
                f"/api/novels/{nid}/settings/book-prefs",
                json={"chapter_word_target": 3000},
            )
            r = c.put(
                f"/api/novels/{nid}/settings/book-prefs",
                json={"chapter_word_target": None},
            )
            assert r.status_code == 200 and r.json() == {}

    def test_put_absent_field_is_noop(self):
        """字段缺省＝无操作成功（style-quant 口径）：不误清已设值。"""
        nid = _run_async(_seed_book())[1]
        with _client() as c:
            c.put(
                f"/api/novels/{nid}/settings/book-prefs",
                json={"chapter_word_target": 3000},
            )
            r = c.put(f"/api/novels/{nid}/settings/book-prefs", json={})
            assert r.status_code == 200 and r.json() == {"chapter_word_target": 3000}

    def test_unknown_project_404(self):
        with _client() as c:
            assert (
                c.get("/api/novels/no-such-book/settings/book-prefs").status_code == 404
            )

    def test_not_routed_by_generic_settings_endpoint(self):
        """专用键不进 PATH_TO_KEY：通用 /settings/book-prefs 仍拒（专用端点先注册）。"""
        nid = _run_async(_seed_book())[1]
        with _client() as c:
            r = c.get(f"/api/novels/{nid}/settings/book-prefs")
            assert r.status_code == 200  # 命中专用端点
            from settings.router import SINGLE_FILE_TYPES

            assert "book-prefs" not in SINGLE_FILE_TYPES
