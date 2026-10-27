"""重写这一章（chapter-rewrite）后端行为测试。

覆盖：rewrite 合成端点（归档章解锁、下游 stale 置位、409 族）／
stale 单写入口清除／旧稿不再转存支线（重写后 /ghosts 不出新条目；
存量重写旧稿行不列、回退支线照列且只读）／frontier 不被抢占（P0 前置）。
"""

import asyncio
import os
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.chapter import Chapter, ChapterContent
from models.project import Novel
from models.user import User
from models.volume import Volume


async def _seed() -> tuple[str, str]:
    """3 章 + 各有正文（直接落库绕开排队门禁）；第 1、2 章归档。"""
    root = tempfile.mkdtemp(prefix="test_rewrite_")
    slug = f"rw-{os.path.basename(root)}"
    uid = f"rw-{os.path.basename(root)[-12:]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{slug}@test.local", password_hash="x",
            display_name="重写测试", api_key="", api_base_url="", api_model="",
        ))
        session.add(Novel(
            user_id=uid, name="重写书", slug=slug,
            root_path=root, source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(
            select(Novel).where(Novel.root_path == root)
        )).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        for no in (1, 2, 3):
            ch = Chapter(
                project_id=proj.id, volume_id=vol.id, chapter_no=no,
                ref=f"vol-1-ch-{no}", title=f"第{no}章",
                status="archived" if no <= 2 else "writing",
                word_count=0, has_prose=True,
            )
            session.add(ch)
            await session.flush()
            prose = f"第{no}章的正文内容。"
            session.add(ChapterContent(chapter_id=ch.id, prose=prose))
            ch.word_count = len(prose)
        await session.commit()
        return root, proj.id


async def _seed_ghost(nid: str, *, ref: str, ghost_of: str, chapter_no: int,
                      prose: str = "旧稿正文。"):
    """直接落库一支线章（模拟存量）：ref 带 -r{8hex}＝重写旧稿旧形态，否则回退转入。"""
    async with async_session() as session:
        vol = (await session.scalars(
            select(Volume).where(Volume.project_id == nid)
        )).first()
        ch = Chapter(
            project_id=nid, volume_id=vol.id, chapter_no=chapter_no,
            ref=ref, title=f"第{chapter_no}章", status="archived",
            word_count=len(prose), has_prose=True,
        )
        session.add(ch)
        await session.flush()
        session.add(ChapterContent(chapter_id=ch.id, prose=prose))
        ch.ghost_of = ghost_of
        await session.commit()


def _client(uid_nid: tuple[str, str]):
    _root, nid = uid_nid
    c = TestClient(app)
    c.__enter__()

    async def _uid():
        async with async_session() as s:
            p = await s.get(Novel, nid)
            return {"id": p.user_id}

    # 依赖 override 需要同步返回：先取一次 uid
    loop = asyncio.new_event_loop()
    uid = loop.run_until_complete(_uid())["id"]
    loop.close()
    app.dependency_overrides[get_current_user] = lambda: {"id": uid}
    return c


def _get(nid: str, path: str):
    c = _client((None, nid))  # type: ignore[arg-type]
    r = c.get(f"/api/novels/{nid}{path}")
    return r


def _post(nid: str, path: str):
    c = _client((None, nid))  # type: ignore[arg-type]
    r = c.post(f"/api/novels/{nid}{path}")
    return r


def _put(nid: str, path: str, body: dict):
    c = _client((None, nid))  # type: ignore[arg-type]
    r = c.put(f"/api/novels/{nid}{path}", json=body)
    return r


def _cleanup():
    app.dependency_overrides.clear()


class TestRewrite:
    def test_rewrite_unlocks_and_marks_stale_without_ghost(self):
        _root, nid = asyncio.run(_seed())
        try:
            r = _post(nid, "/chapters/vol-1-ch-2/rewrite")
            assert r.status_code == 200, r.text
            d = r.json()
            # 契约收紧：不再产出旧稿字段（旧稿由版本历史承接）
            assert "ghost_ref" not in d, d
            assert "ghost_created" not in d, d
            assert d["unarchived"] is True
            assert d["stale_marked"] == 1  # 仅第 3 章（有正文的下游）

            # 源章解锁回可写
            src = _get(nid, "/chapters/vol-1-ch-2").json()
            assert src["status"] != "archived"

            # 下游 stale 置位（章详情 + 卷章树两处契约）
            ch3 = _get(nid, "/chapters/vol-1-ch-3").json()
            assert ch3.get("stale") is True
            vols = _get(nid, "/volumes").json()
            entries = {c["ref"]: c for c in vols[0]["chapters"]}
            assert entries["vol-1-ch-3"]["stale"] is True
            assert entries["vol-1-ch-2"]["stale"] is False

            # 重写不产支线：/ghosts 保持空
            assert _get(nid, "/ghosts").json() == []
        finally:
            _cleanup()

    def test_rewrite_twice_stays_safe(self):
        """连看重写不炸不重复：二次重写幂等（已解锁不重复解锁、stale 不重复计）。"""
        _root, nid = asyncio.run(_seed())
        try:
            r1 = _post(nid, "/chapters/vol-1-ch-2/rewrite").json()
            assert r1["unarchived"] is True
            # 源章改写为新内容后再重写
            r = _put(nid, "/chapters/vol-1-ch-2/prose",
                     {"prose": "第2章重写后的新正文。"})
            assert r.status_code == 200, r.text
            r2 = _post(nid, "/chapters/vol-1-ch-2/rewrite")
            assert r2.status_code == 200, r2.text
            d2 = r2.json()
            assert d2["unarchived"] is False  # 已处于可写态
            assert d2["stale_marked"] == 0  # 下游已置过，不重复计
            # 依旧不产支线
            assert _get(nid, "/ghosts").json() == []
        finally:
            _cleanup()

    def test_rewrite_409_no_prose_and_ghost_source(self):
        _root, nid = asyncio.run(_seed())
        try:
            # 造一个无正文章
            loop = asyncio.new_event_loop()

            async def _add_empty():
                async with async_session() as s:
                    p = (await s.scalars(select(Novel).where(Novel.id == nid))).one()
                    vol = (await s.scalars(
                        select(Volume).where(Volume.project_id == nid)
                    )).first()
                    s.add(Chapter(
                        project_id=p.id, volume_id=vol.id, chapter_no=9,
                        ref="vol-1-ch-9", title="第9章", status="outline",
                        word_count=0, has_prose=False,
                    ))
                    await s.commit()

            loop.run_until_complete(_add_empty())
            loop.close()
            r = _post(nid, "/chapters/vol-1-ch-9/rewrite")
            assert r.status_code == 409

            # ghost 源 409（回退支线章不可重写）
            asyncio.run(_seed_ghost(
                nid, ref="vol-1-ch-4", ghost_of="vol-1-ch-1", chapter_no=4,
            ))
            r2 = _post(nid, "/chapters/vol-1-ch-4/rewrite")
            assert r2.status_code == 409
            assert "旧稿" in r2.json()["detail"]
        finally:
            _cleanup()

    def test_legacy_rewrite_ghost_filtered_revert_ghost_listed(self):
        """存量重写旧稿行（-r{8hex}）不列；回退支线照列；两者都只读。"""
        _root, nid = asyncio.run(_seed())
        try:
            asyncio.run(_seed_ghost(
                nid, ref="vol-1-ch-2-rdeadbeef", ghost_of="vol-1-ch-2",
                chapter_no=2, prose="重写前的旧稿。",
            ))
            asyncio.run(_seed_ghost(
                nid, ref="vol-1-ch-4", ghost_of="vol-1-ch-1", chapter_no=4,
            ))

            ghosts = _get(nid, "/ghosts").json()
            assert [x["ref"] for x in ghosts] == ["vol-1-ch-4"]
            # 契约收紧：origin 派生字段随重写支线退役
            assert "origin" not in ghosts[0], ghosts[0]
            assert ghosts[0]["ghost_of"] == "vol-1-ch-1"
            assert ghosts[0]["created_at"]

            # 存量重写旧稿行依旧只读（只是不再列出让用户看见）
            r = _put(nid, "/chapters/vol-1-ch-2-rdeadbeef/prose", {"prose": "x"})
            assert r.status_code == 409
            assert "只读" in r.json()["detail"]
            r2 = _put(nid, "/chapters/vol-1-ch-4/prose", {"prose": "x"})
            assert r2.status_code == 409
        finally:
            _cleanup()

    def test_stale_cleared_on_own_save(self):
        _root, nid = asyncio.run(_seed())
        try:
            _post(nid, "/chapters/vol-1-ch-2/rewrite")
            assert _get(nid, "/chapters/vol-1-ch-3").json().get("stale") is True
            # 第 3 章自身被写（PUT prose 走单写入口）
            r = _put(nid, "/chapters/vol-1-ch-3/prose", {"prose": "第3章改写后的正文。"})
            assert r.status_code == 200, r.text
            assert _get(nid, "/chapters/vol-1-ch-3").json().get("stale") in (None, False)
        finally:
            _cleanup()


class TestFrontierNotHijacked:
    def test_rewrite_moves_frontier_without_ghost(self):
        """P0 回归：重写已归档章后，frontier 移回源章；无旧稿快照可抢占。"""
        _root, nid = asyncio.run(_seed())
        try:
            # 第 1、2 章已归档 → frontier 应为第 3 章
            f0 = _get(nid, "/frontier").json()["frontier"]
            assert f0["ref"] == "vol-1-ch-3"
            # 重写第 2 章（解锁成可写端点）
            _post(nid, "/chapters/vol-1-ch-2/rewrite")
            f1 = _get(nid, "/frontier").json()["frontier"]
            assert f1["ref"] == "vol-1-ch-2"
            assert "-r" not in f1["ref"]
            # 重写不产支线；存量回退支线仍只读
            assert _get(nid, "/ghosts").json() == []
            asyncio.run(_seed_ghost(
                nid, ref="vol-1-ch-4", ghost_of="vol-1-ch-1", chapter_no=4,
            ))
            g = _get(nid, "/ghosts").json()[0]["ref"]
            r = _put(nid, f"/chapters/{g}/prose", {"prose": "x"})
            assert r.status_code == 409
        finally:
            _cleanup()
