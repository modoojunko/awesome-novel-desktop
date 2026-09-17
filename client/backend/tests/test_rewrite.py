"""重写这一章（chapter-rewrite）后端行为测试。

覆盖：frontier 不被旧稿抢占（P0 前置）／rewrite 合成端点（快照内容寻址 ref、
归档章解锁、下游 stale 置位、幂等、409 族）／stale 单写入口清除／
契约字段（卷章树 stale、ghosts origin+created_at）。
"""

import asyncio
import os
import re
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

GHOST_RE = re.compile(r"^vol-1-ch-2-r[0-9a-f]{8}$")


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
    def test_rewrite_full_chain(self):
        _root, nid = asyncio.run(_seed())
        try:
            r = _post(nid, "/chapters/vol-1-ch-2/rewrite")
            assert r.status_code == 200, r.text
            d = r.json()
            assert GHOST_RE.match(d["ghost_ref"]), d["ghost_ref"]
            assert d["ghost_created"] is True
            assert d["unarchived"] is True
            assert d["stale_marked"] == 1  # 仅第 3 章（有正文的下游）

            # 快照：旧稿章只读、正文原文、ghost_of 指向源章
            g = _get(nid, f"/chapters/{d['ghost_ref']}")
            assert g.status_code == 200, g.text
            gd = g.json()
            assert gd["prose"] == "第2章的正文内容。"
            assert gd["ghost_of"] == "vol-1-ch-2"

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

            # ghosts 契约：origin=rewrite + created_at
            ghosts = _get(nid, "/ghosts").json()
            hit = next(x for x in ghosts if x["ref"] == d["ghost_ref"])
            assert hit["origin"] == "rewrite"
            assert hit["created_at"]
        finally:
            _cleanup()

    def test_rewrite_idempotent(self):
        _root, nid = asyncio.run(_seed())
        try:
            r1 = _post(nid, "/chapters/vol-1-ch-2/rewrite").json()
            r2 = _post(nid, "/chapters/vol-1-ch-2/rewrite")
            assert r2.status_code == 200, r2.text
            d2 = r2.json()
            assert d2["ghost_ref"] == r1["ghost_ref"]
            assert d2["ghost_created"] is False
            # 旧稿不重复
            ghosts = _get(nid, "/ghosts").json()
            assert sum(1 for x in ghosts if x["ref"].endswith(r1["ghost_ref"][-9:])) == 1
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

            # ghost 源 409
            g = _post(nid, "/chapters/vol-1-ch-2/rewrite").json()["ghost_ref"]
            r2 = _post(nid, f"/chapters/{g}/rewrite")
            assert r2.status_code == 409
            assert "旧稿" in r2.json()["detail"]
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
    def test_ghost_snapshot_does_not_take_frontier(self):
        """P0 回归：重写已归档章后，旧稿快照不得抢占 frontier（否则真端点章 409）。"""
        _root, nid = asyncio.run(_seed())
        try:
            # 第 1、2 章已归档 → frontier 应为第 3 章
            f0 = _get(nid, "/frontier").json()["frontier"]
            assert f0["ref"] == "vol-1-ch-3"
            # 重写第 2 章（产生未归档 ghost，同章号）
            _post(nid, "/chapters/vol-1-ch-2/rewrite")
            f1 = _get(nid, "/frontier").json()["frontier"]
            assert f1["ref"] == "vol-1-ch-2"  # 源章解锁成可写端点
            assert "-r" not in f1["ref"]
            # ghost 仍只读
            g = _get(nid, "/ghosts").json()[0]["ref"]
            r = _put(nid, f"/chapters/{g}/prose", {"prose": "x"})
            assert r.status_code == 409
        finally:
            _cleanup()
