"""卷节奏单源与端点（c-volume-pacing）。

覆盖：预设与题材映射 → 归一 clamp → 段表/拍位公式（末段吸收余数、越界 None）
→ 书级默认读写（成对受理/非法 400）→ 卷端点（GET 预填链/PUT 落列/planned
roundtrip）→ 未配置卷拍位查询为 None（注入全关的退化路径）。

用法：
    cd client/backend && python -m pytest tests/test_volume_pacing.py -v
"""

import asyncio
import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_local.middleware import get_current_user
from db import async_session
from filesystem.storage import get_storage
from main import app
from models.project import Novel
from models.volume import Volume
from volumes import pacing as pc

USER_ID = "vp_user"


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _seed_book(theme: str | None = "仙侠/修真") -> tuple[str, str]:
    root = tempfile.mkdtemp(prefix="test_volume_pacing_")
    slug = f"vp-{os.path.basename(root)}"
    async with async_session() as session:
        session.add(
            Novel(
                user_id=USER_ID,
                name="节奏书",
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
    # 题材住 story.yaml（与设定页同键）：genre=大类，sub_genre=子类
    if theme:
        sub = "凡人流" if theme == "仙侠/修真" else ""
        await get_storage().write_yaml(
            root, "story.yaml", {"genre": theme, "sub_genre": sub}
        )
    return root, row.id


async def _seed_volume(novel_id: str, vol_no: int, *, target: int | None = 40,
                       pacing: dict | None = None) -> str:
    async with async_session() as session:
        vol = Volume(
            project_id=novel_id,
            volume_no=vol_no,
            title=f"第{vol_no}卷",
            summary="",
            chapter_target=target,
        )
        if pacing is not None:
            vol.pacing_json = json.dumps(pacing, ensure_ascii=False)
        session.add(vol)
        await session.commit()
        return f"vol-{vol_no}"


def _client():
    c = TestClient(app)
    app.dependency_overrides[get_current_user] = lambda: {"id": USER_ID}
    return c


@pytest.fixture(autouse=True)
def _cleanup_overrides():
    yield
    app.dependency_overrides.pop(get_current_user, None)


# ── 单源：预设 / 映射 / 公式 ────────────────────────────────────────────────


class TestPresets:
    def test_six_presets_shape(self):
        assert set(pc.PACING_PRESETS) == {
            "upgrade", "case", "episodic", "romance", "level", "event"
        }
        for key, p in pc.PACING_PRESETS.items():
            assert p["key"] == key
            assert pc.STEPS_MIN <= len(p["steps"]) <= pc.STEPS_MAX
            assert pc.LEN_MIN <= p["steps_len"] <= pc.LEN_MAX
            assert p["warn_len"] > p["steps_len"]
            assert all(s["n"] and s["t"] for s in p["steps"])
            assert p["ch1_extra"]

    def test_genre_mapping_hits(self):
        assert pc.preset_for_genre("仙侠/修真") == "upgrade"
        assert pc.preset_for_genre("悬疑") == "case"
        assert pc.preset_for_genre("仙侠/修真", "凡人流") == "upgrade"
        assert pc.preset_for_genre("都市", "都市情感") == "romance"

    def test_genre_mapping_fallback(self):
        assert pc.preset_for_genre("未知题材") == pc.DEFAULT_PRESET_KEY
        assert pc.preset_for_genre("") == pc.DEFAULT_PRESET_KEY


class TestFormulas:
    def test_segment_plan_absorbs_remainder(self):
        plan = pc.segment_plan(40, 3)
        assert plan["n"] == 13
        assert plan["last_from"] == 37 and plan["last_to"] == 40

    def test_segment_plan_exact(self):
        plan = pc.segment_plan(40, 4)
        assert plan["n"] == 10 and plan["rem"] == 0

    def test_segment_plan_zero_target(self):
        plan = pc.segment_plan(0, 3)
        assert plan["n"] == 1 and plan["last_to"] == 0

    def test_beat_of_lands_by_formula(self):
        config = pc.build_config("upgrade", 3)
        beat = pc.beat_of(5, config, 40)
        assert beat["seg"] == 2 and beat["step_idx"] == 2
        assert beat["step_name"] == "用金手指解决"

    def test_beat_of_none_cases(self):
        config = pc.build_config("upgrade", 3)
        assert pc.beat_of(5, None, 40) is None  # 未配置
        assert pc.beat_of(5, config, None) is None  # 无章数目标
        assert pc.beat_of(41, config, 40) is None  # 越界

    def test_config_change_recomputes(self):
        config = pc.build_config("upgrade", 3)
        assert pc.beat_of(4, config, 40)["step_idx"] == 1
        config5 = pc.build_config("upgrade", 5)
        assert pc.beat_of(4, config5, 40)["step_idx"] == 4


class TestNormalize:
    def test_none_for_empty_or_invalid(self):
        assert pc.normalize_pacing_config(None) is None
        assert pc.normalize_pacing_config({}) is None
        assert pc.normalize_pacing_config({"preset": "nope"}) is None

    def test_clamps_steps_and_len(self):
        config = pc.normalize_pacing_config(
            {"preset": "upgrade", "steps_len": 99,
             "steps": [{"n": f"步{i}", "t": "x"} for i in range(9)]}
        )
        assert config is not None
        assert config["steps_len"] == pc.LEN_MAX
        assert len(config["steps"]) == pc.STEPS_MAX

    def test_short_steps_fall_back_to_preset(self):
        config = pc.normalize_pacing_config(
            {"preset": "case", "steps_len": 12, "steps": [{"n": "唯一一步", "t": "x"}]}
        )
        assert config is not None
        assert [s["n"] for s in config["steps"]] == [
            s["n"] for s in pc.PACING_PRESETS["case"]["steps"]
        ]


# ── 书级默认（book-prefs 成对受理） ────────────────────────────────────────


class TestBookDefault:
    def test_read_and_effective(self):
        assert pc.book_pacing_default(None) is None
        assert pc.book_pacing_default({}) is None
        assert pc.book_pacing_default({"pacing_preset": "nope"}) is None
        assert pc.book_pacing_default(
            {"pacing_preset": "upgrade", "pacing_steps_len": 4}
        ) == {"preset": "upgrade", "steps_len": 4}
        # 孤段长无意义：读侧不认
        assert pc.book_pacing_default({"pacing_steps_len": 4}) is None

    def test_prefill_chain_order(self):
        mine = pc.build_config("case", 12)
        book = {"preset": "upgrade", "steps_len": 4}
        # 上一卷优先
        assert pc.prefill_chain(mine, book, "悬疑", None)["preset"] == "case"
        # 书默认次之
        assert pc.prefill_chain(None, book, "悬疑", None)["preset"] == "upgrade"
        # 映射兜底
        assert pc.prefill_chain(None, None, "悬疑", None)["preset"] == "case"
        # 终兜底
        assert pc.prefill_chain(None, None, "未知题材", None)["preset"] == "upgrade"


# ── 端点 ───────────────────────────────────────────────────────────────────


class TestEndpoints:
    def test_presets_and_book_default_roundtrip(self):
        _root, novel_id = _run_async(_seed_book())
        c = _client()
        r = c.get(f"/api/novels/{novel_id}/pacing/presets")
        assert r.status_code == 200
        body = r.json()
        assert len(body["presets"]) == 6
        assert body["suggested_key"] == "upgrade"  # 题材映射
        assert body["book_default"] is None

        r = c.put(
            f"/api/novels/{novel_id}/pacing/book-default",
            json={"preset": "upgrade", "steps_len": 4},
        )
        assert r.status_code == 200
        assert r.json() == {"preset": "upgrade", "steps_len": 4}

        r = c.get(f"/api/novels/{novel_id}/pacing/presets")
        assert r.json()["book_default"] == {"preset": "upgrade", "steps_len": 4}

        # 非法套路 400
        r = c.put(
            f"/api/novels/{novel_id}/pacing/book-default",
            json={"preset": "nope", "steps_len": 4},
        )
        assert r.status_code == 400

    def test_volume_pacing_get_put(self):
        _, novel_id = _run_async(_seed_book())
        vol_ref = _run_async(_seed_volume(novel_id, 1))
        c = _client()

        # 未配置：config None，预填链走题材映射
        r = c.get(f"/api/novels/{novel_id}/volumes/{vol_ref}/pacing")
        assert r.status_code == 200
        body = r.json()
        assert body["config"] is None
        assert body["source"] == "genre"
        assert body["prefill"]["preset"] == "upgrade"
        assert body["plan"]["target"] == 40 and body["plan"]["n"] == 13

        # 保存配置（planned 标记排段采纳）
        config = pc.build_config("upgrade", 3, ch1_extra_on=True, planned=True)
        r = c.put(f"/api/novels/{novel_id}/volumes/{vol_ref}/pacing", json=config)
        assert r.status_code == 200
        assert r.json()["config"]["planned"] is True

        # 再读：config 在，source=volume，拍位可查
        r = c.get(f"/api/novels/{novel_id}/volumes/{vol_ref}/pacing")
        body = r.json()
        assert body["source"] == "volume"
        assert body["config"]["preset"] == "upgrade"

        # 非法配置 400
        r = c.put(f"/api/novels/{novel_id}/volumes/{vol_ref}/pacing", json={"preset": "x"})
        assert r.status_code == 400

    def test_prefill_from_prev_volume(self):
        _, novel_id = _run_async(_seed_book())
        prev_pacing = pc.build_config("case", 12)
        _run_async(_seed_volume(novel_id, 1, pacing=prev_pacing))
        vol2 = _run_async(_seed_volume(novel_id, 2))
        c = _client()
        r = c.get(f"/api/novels/{novel_id}/volumes/{vol2}/pacing")
        body = r.json()
        assert body["source"] == "prev"
        assert body["prefill"]["preset"] == "case"

    def test_book_default_beats_genre_when_no_prev(self):
        _, novel_id = _run_async(_seed_book(theme="仙侠/修真"))
        _run_async(_seed_volume(novel_id, 1))  # 卷一无配置
        c = _client()
        c.put(
            f"/api/novels/{novel_id}/pacing/book-default",
            json={"preset": "romance", "steps_len": 5},
        )
        r = c.get(f"/api/novels/{novel_id}/volumes/vol-1/pacing")
        body = r.json()
        assert body["source"] == "book"
        assert body["prefill"]["preset"] == "romance"
