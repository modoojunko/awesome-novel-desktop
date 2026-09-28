"""故事状态消费链（c-chapter-dossier 6.x）：折叠去重四形态／unarchive 不消费／
stale 跳过＋块头注记／预算硬闸／两路同源 golden／润色条件锚／来源第七处＋缺口标注。

用法：
    cd client/backend
    python -m pytest tests/test_story_state_consumption.py -v
"""

import asyncio
import os
import tempfile

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix="_story_state.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_story_state_")

from sqlalchemy import select  # noqa: E402

from db import Base, async_session, engine  # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _ensure_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _seed_book(n_ch: int = 3) -> tuple[str, str]:
    """建书+卷+N 章（全部 archived 有正文）；返回 (root, nid)。章 ref vol-1-ch-i。"""
    from models.chapter import Chapter, ChapterContent
    from models.project import Novel
    from models.user import User
    from models.volume import Volume

    root = tempfile.mkdtemp(prefix="story_state_")
    uid = f"ss-{os.path.basename(root)[-10:]}"

    async def _go():
        async with async_session() as s:
            s.add(User(id=uid, email=f"{uid}@t.local", password_hash="x",
                       display_name="状态", api_key="", api_base_url="", api_model=""))
            proj = Novel(user_id=uid, name="状态书", slug=f"ss-{os.path.basename(root)}",
                         root_path=root, source="manual", current_phase="write")
            s.add(proj)
            await s.flush()
            vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
            s.add(vol)
            await s.flush()
            for i in range(1, n_ch + 1):
                ch = Chapter(project_id=proj.id, volume_id=vol.id, chapter_no=i,
                             ref=f"vol-1-ch-{i}", title=f"第{i}章", status="archived",
                             has_prose=True)
                s.add(ch)
                await s.flush()
                s.add(ChapterContent(chapter_id=ch.id, prose=f"第{i}章正文。" * 30))
            await s.commit()
            return proj.id, root

    nid, root = _run(_go())
    return root, nid


def _put_rows(nid: str, ch_no: int, *, settings=(), relations=(), items=(), knowledge=(),
              statuses: str = "accepted"):
    """往第 ch_no 章塞章档行（默认全 accepted）。"""
    from chapters.store import save_chapter
    from models.project import Novel

    async def _root():
        async with async_session() as s:
            return (await s.get(Novel, nid)).root_path

    root = _run(_root())
    dossier = {
        "settings": [
            {"area": a, "content": c, "evidence": "", "status": statuses, "flags": ""}
            for a, c in settings
        ],
        "relations": [
            {"owner": o, "other": t, "rel_type": rt, "change_note": cn,
             "evidence": "", "status": statuses, "flags": ""}
            for o, t, rt, cn in relations
        ],
        "items": [
            {"name": n, "change_type": ct, "holder": h, "detail": "",
             "evidence": "", "status": statuses, "flags": ""}
            for n, ct, h in items
        ],
        "knowledge": [
            {"character": ch, "fact": f, "learned": l,
             "evidence": "", "status": statuses, "flags": ""}
            for ch, f, l in knowledge
        ],
    }
    _run(save_chapter(root, f"vol-1-ch-{ch_no}", {"dossier": dossier}))


def _state(nid, ref, **kw):
    from write.story_state import story_state_upto

    return _run(story_state_upto(nid, ref, **kw))


# ── 折叠去重四形态 ──────────────────────────────────────────────────────────


def test_fold_setting_dedupe_and_relation_upsert():
    _run(_ensure_tables())
    _root, nid = _seed_book(3)
    _put_rows(nid, 1, settings=[("势力", "守夜人接管城门")],
              relations=[("林晚", "阿蓟", "戒备", "互不信任")])
    _put_rows(nid, 2, settings=[("势力", "守夜人接管城门")],  # 同事实重复 → 去重
              relations=[("林晚", "阿蓟", "盟友", "并肩")])  # 同对 upsert → 后章覆盖
    st = _state(nid, "vol-1-ch-3")
    assert len(st["settings"]) == 1
    assert st["settings"][0]["ref"] == "vol-1-ch-2"  # 同键重复以后章 last-wins（ref 随之）
    rel = st["relations"][0]
    assert rel["rel_type"] == "盟友" and rel["ref"] == "vol-1-ch-2"


def test_fold_item_latest_holder_and_knowledge_flip():
    _run(_ensure_tables())
    _root, nid = _seed_book(3)
    _put_rows(nid, 1, items=[("旧刀", "obtain", "林晚")],
              knowledge=[("阿蓟", "林晚的身份", False)])
    _put_rows(nid, 2, items=[("旧刀", "transfer", "阿蓟")],
              knowledge=[("阿蓟", "林晚的身份", True)])  # 不知 → 已知 翻转覆盖
    st = _state(nid, "vol-1-ch-3")
    assert st["items"][0]["holder"] == "阿蓟"
    assert st["knowledge"][0]["learned"] is True


def test_exclusive_window_and_pending_not_consumed():
    _run(_ensure_tables())
    _root, nid = _seed_book(3)
    _put_rows(nid, 1, settings=[("势力", "第一章事实")])
    _put_rows(nid, 2, settings=[("势力", "第二章事实")])
    # 第三章自己有已采纳行——exclusive 窗口不含本章
    _put_rows(nid, 3, settings=[("势力", "第三章事实")])
    st = _state(nid, "vol-1-ch-3", exclusive=True)
    assert {s["content"] for s in st["settings"]} == {"第一章事实", "第二章事实"}
    # pending 行不进消费
    _put_rows(nid, 2, settings=[("势力", "第二章待确认事实")], statuses="pending")
    st2 = _state(nid, "vol-1-ch-3", exclusive=True)
    assert all("待确认" not in s["content"] for s in st2["settings"])


def test_unarchived_chapter_excluded():
    _run(_ensure_tables())
    _root, nid = _seed_book(3)

    from models.chapter import Chapter

    async def _unarchive():
        async with async_session() as s:
            ch = (await s.scalars(select(Chapter).where(
                Chapter.project_id == nid, Chapter.ref == "vol-1-ch-2"))).one()
            ch.status = "draft"
            await s.commit()

    _put_rows(nid, 1, settings=[("势力", "第一章事实")])
    _put_rows(nid, 2, settings=[("势力", "第二章事实")])
    _run(_unarchive())
    st = _state(nid, "vol-1-ch-3", exclusive=True)
    assert {s["content"] for s in st["settings"]} == {"第一章事实"}


def test_stale_chapter_skipped_and_noted():
    _run(_ensure_tables())
    _root, nid = _seed_book(3)
    _put_rows(nid, 2, settings=[("势力", "第二章旧事实")])

    from models.chapter import Chapter

    async def _mark_stale():
        async with async_session() as s:
            ch = (await s.scalars(select(Chapter).where(
                Chapter.project_id == nid, Chapter.ref == "vol-1-ch-2"))).one()
            ch.dossier_stale = True
            await s.commit()

    _run(_mark_stale())
    st = _state(nid, "vol-1-ch-3", exclusive=True)
    assert st["settings"] == []
    assert st["skipped_stale_refs"] == ["vol-1-ch-2"]


# ── 渲染：单源、golden、锚 ──────────────────────────────────────────────────


def test_block_render_two_paths_identical_and_empty_absent():
    from write.chapter_writer import ChapterContext, _story_state_block

    # 空态：块缺席
    ctx = ChapterContext()
    assert _story_state_block(ctx.story_state) == ""
    ctx.material_markdown()
    assert "故事状态" not in ctx.material_markdown() and "故事状态" not in ctx.to_user_material()

    ctx.story_state = {
        "settings": [{"area": "势力", "content": "守夜人接管城门", "ref": "vol-1-ch-1"}],
        "relations": [{"owner": "林晚", "other": "阿蓟", "rel_type": "盟友",
                       "change_note": "并肩", "ref": "vol-1-ch-2"}],
        "items": [{"name": "旧刀", "change_type": "transfer", "holder": "阿蓟",
                   "detail": "", "ref": "vol-1-ch-2"}],
        "knowledge": [{"character": "阿蓟", "fact": "林晚的身份", "learned": False,
                       "ref": "vol-1-ch-1"}],
        "skipped_stale_refs": [],
    }
    block = _story_state_block(ctx.story_state)
    assert block.startswith("【故事状态（截至上章）】")
    assert "- 势力：守夜人接管城门" in block
    assert "- 林晚→阿蓟：盟友（并肩）" in block
    assert "- 旧刀：在阿蓟手中" in block
    assert "阿蓟仍不知道「林晚的身份」（阿蓟不知）" in block
    assert "不得表现出知情" in block
    # 两路同源同字
    assert block in ctx.material_markdown()
    assert block in ctx.to_user_material()
    # 证据句不进消费段（本例无 evidence——形状断言：块内不出现 ref）
    assert "vol-1-ch-1" not in block


def test_block_quota_and_hard_gate():
    from write.chapter_writer import _story_state_block

    state = {
        "settings": [{"area": "a", "content": f"事实{i}", "ref": "r"} for i in range(20)],
        "relations": [], "items": [], "knowledge": [],
    }
    block = _story_state_block(state)
    assert block.count("- a：") == 6  # 每域 ≤6（尾部＝章近优先）
    assert "事实19" in block and "事实0" not in block

    huge = {
        "settings": [{"area": "a", "content": "字" * 39, "ref": "r"} for i in range(50)],
        "relations": [], "items": [], "knowledge": [],
    }
    gated = _story_state_block(huge)
    assert len(gated) <= 1500 + 200  # 标题/锚/规则行余量


def test_polish_anchor_requires_story_state_title():
    from write.chapter_writer import ChapterContext, validate_polished_prompt

    ctx = ChapterContext()
    ctx.story_state = {"settings": [{"area": "a", "content": "x", "ref": "r"}]}
    # 有状态块但润色产物丢了段标题 → 缺失项含「故事状态」；标题在 → 不缺
    assert "故事状态" in validate_polished_prompt("前情 章纲概要", ctx)
    assert "故事状态" not in validate_polished_prompt("前情 章纲概要 故事状态", ctx)
    # 无状态块 → 不要求该锚
    empty = ChapterContext()
    assert "故事状态" not in validate_polished_prompt("前情", empty)


# ── 来源第七处＋缺口标注 ────────────────────────────────────────────────────


def test_prompt_sources_seventh_source_and_gap():
    _run(_ensure_tables())
    from fastapi.testclient import TestClient

    from auth_local.middleware import get_current_user
    from main import app
    from models.project import Novel

    _root, nid = _seed_book(3)
    # 第一章全采纳；第二章 1 采纳 1 待确认；当前写第三章
    _put_rows(nid, 1, settings=[("势力", "第一章事实")])
    _put_rows(nid, 2, settings=[("势力", "第二章事实")])
    _put_rows(nid, 2, items=[("铜哨", "obtain", "林晚")], statuses="pending")

    # 第三章切回 writing（当前章）
    from models.chapter import Chapter

    async def _cur():
        async with async_session() as s:
            ch = (await s.scalars(select(Chapter).where(
                Chapter.project_id == nid, Chapter.ref == "vol-1-ch-3"))).one()
            ch.status = "writing"

    _run(_cur())

    async def _uid():
        async with async_session() as s:
            return (await s.get(Novel, nid)).user_id

    uid = _run(_uid())
    app.dependency_overrides[get_current_user] = lambda: {"id": uid}
    try:
        with TestClient(app) as c:
            r = c.get(f"/api/novels/{nid}/chapters/vol-1-ch-3/prompt-sources")
        assert r.status_code == 200, r.text
        srcs = {s["key"]: s for s in r.json()["sources"]}
        assert set(srcs) == {
            "book", "volume", "outline", "style", "hooks", "cast", "story_state",
        }
        ss = srcs["story_state"]
        assert ss["empty"] is False
        assert "第一章事实" in ss["preview"] + (ss["preview"] and "")
        assert ss["note"] == "缺 1 条未确认"
    finally:
        app.dependency_overrides.clear()


# ── 重写级联（c-chapter-dossier 7.x）────────────────────────────────────────


def test_rewrite_cascade_clears_source_and_marks_downstream():
    _run(_ensure_tables())
    _root, nid = _seed_book(3)
    _put_rows(nid, 1, settings=[("势力", "第一章事实")])
    _put_rows(nid, 2, settings=[("势力", "第二章事实")])
    # 第三章无章档行——重写下游时不应被标 dossier_stale（无档可旧）

    from chapters.rewrite import rewrite_chapter
    from models.project import Novel

    async def _rewrite():
        async with async_session() as s:
            proj = await s.get(Novel, nid)
            return await rewrite_chapter(s, proj, "vol-1-ch-1")

    got = _run(_rewrite())
    assert got["dossier_rows_cleared"] == 1
    assert got["dossier_stale_marked"] == 1

    from models.chapter import Chapter, ChapterSettingChange

    async def _check():
        async with async_session() as s:
            ch1 = (await s.scalars(select(Chapter).where(
                Chapter.project_id == nid, Chapter.ref == "vol-1-ch-1"))).one()
            ch2 = (await s.scalars(select(Chapter).where(
                Chapter.project_id == nid, Chapter.ref == "vol-1-ch-2"))).one()
            ch3 = (await s.scalars(select(Chapter).where(
                Chapter.project_id == nid, Chapter.ref == "vol-1-ch-3"))).one()
            ch1_rows = (await s.scalars(select(ChapterSettingChange).where(
                ChapterSettingChange.chapter_id == ch1.id))).all()
            return ch1, ch2, ch3, ch1_rows

    ch1, ch2, ch3, ch1_rows = _run(_check())
    assert ch1_rows == [] and ch1.dossier_stale is False
    assert ch2.dossier_stale is True and ch2.stale is True
    assert ch3.dossier_stale is False  # 无章档行不标

    # 消费侧：ch2 被跳过并注记
    st = _state(nid, "vol-1-ch-3", exclusive=True)
    assert st["settings"] == []
    assert st["skipped_stale_refs"] == ["vol-1-ch-2"]


def test_reextract_clears_dossier_stale(monkeypatch):
    """补提取成功（rows_only）清 dossier_stale——角标随重提消失。"""
    _run(_ensure_tables())
    _root, nid = _seed_book(2)
    _put_rows(nid, 2, settings=[("势力", "第二章事实")])

    from models.chapter import Chapter

    async def _mark():
        async with async_session() as s:
            ch = (await s.scalars(select(Chapter).where(
                Chapter.project_id == nid, Chapter.ref == "vol-1-ch-2"))).one()
            ch.dossier_stale = True
            await s.commit()

    _run(_mark())

    import json as _json

    replies = [_json.dumps({"settings": [], "relations": [], "items": [], "knowledge": []})]
    from tests.test_dossier_pipeline import _mock_ai  # 复用假客户端

    _mock_ai(monkeypatch, replies)

    from archive.dossier import accept_extraction, prose_sha256
    from models.chapter import ChapterContent

    async def _go():
        async with async_session() as s:
            ch = (await s.scalars(select(Chapter).where(
                Chapter.project_id == nid, Chapter.ref == "vol-1-ch-2"))).one()
            content = (await s.scalars(select(ChapterContent).where(
                ChapterContent.chapter_id == ch.id))).first()
            await accept_extraction(
                nid, _root, "vol-1-ch-2", ch.id, prose_sha256(content.prose),
                rows_only=True,
            )

    _run(_go())
    from archive.dossier import get_job_state
    from tests.test_dossier_pipeline import _wait_job

    async def _cid():
        async with async_session() as s:
            ch = (await s.scalars(select(Chapter).where(
                Chapter.project_id == nid, Chapter.ref == "vol-1-ch-2"))).one()
            return ch.id

    ch_id = _run(_cid())
    assert _wait_job(ch_id, "ok")["state"] == "ok"

    async def _stale():
        async with async_session() as s:
            ch = await s.get(Chapter, ch_id)
            return ch.dossier_stale

    assert _run(_stale()) is False
