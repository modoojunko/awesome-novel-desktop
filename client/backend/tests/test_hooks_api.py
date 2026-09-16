"""伏笔真表 CRUD / 级联 / 卷章树 id 端点测试（foreshadow-settings-v2 tasks 1.2/1.3/2.1/2.2）。

覆盖：
- 表落地与 seq 取号（novels.hook_seq_high 同事务取号、删后新建不复用）
- 条目级 CRUD：列表含 #H-#### 展示号、POST、PATCH 白名单/枚举/长度/trim、
  DELETE 返回 ops token、restore 按原 id 原样恢复（幂等）、越权/跨书拒绝
- 删章/删卷级联：hook 行保留、四个章引用列 SET NULL
- GET /volumes、GET /tree 章条目携带 DB id

用法：
    cd client/backend
    python -m pytest tests/test_hooks_api.py -v
"""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.hook import NovelHook
from models.project import Novel
from models.user import User


async def _seed() -> tuple[str, str]:
    uid = f"hkapi-{uuid.uuid4().hex[:8]}"
    slug = f"hkapi-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name="伏笔接口测试", api_key="", api_base_url="", api_model="",
        ))
        proj = Novel(
            user_id=uid, name="伏笔测试书", slug=slug,
            root_path=f"./data/{slug}", source="manual", current_phase="settings",
        )
        session.add(proj)
        await session.commit()
        return uid, proj.id


async def _seed_chapters(novel_id: str, count: int = 2) -> list[str]:
    """种一卷 N 章，返回章 id 列表。"""
    from models.chapter import Chapter
    from models.volume import Volume

    async with async_session() as session:
        vol = Volume(project_id=novel_id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        ids = []
        for no in range(1, count + 1):
            ch = Chapter(
                project_id=novel_id, volume_id=vol.id, chapter_no=no,
                ref=f"vol-1-ch-{no}", title=f"第{no}章", status="outline",
            )
            session.add(ch)
            await session.flush()
            ids.append(ch.id)
        await session.commit()
        return ids


async def _seed_other_book() -> tuple[str, str, str]:
    """种「别的书」＋其章行，返回 (user_id, novel_id, chapter_id)。"""
    from models.chapter import Chapter
    from models.volume import Volume

    uid = f"hkapi-{uuid.uuid4().hex[:8]}"
    slug = f"hkapi-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{uid}@other.local", password_hash="x",
            display_name="他书", api_key="", api_base_url="", api_model="",
        ))
        proj = Novel(
            user_id=uid, name="别的书", slug=slug,
            root_path=f"./data/{slug}", source="manual", current_phase="settings",
        )
        session.add(proj)
        await session.flush()
        vol = Volume(project_id=proj.id, volume_no=1, title="他书卷")
        session.add(vol)
        await session.flush()
        ch = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref="vol-1-ch-1", title="他书章", status="outline",
        )
        session.add(ch)
        await session.commit()
        return uid, proj.id, ch.id


async def _seed_hook_in(novel_id: str, description: str = "他书的伏笔") -> str:
    async with async_session() as session:
        proj = await session.get(Novel, novel_id)
        proj.hook_seq_high += 1
        h = NovelHook(novel_id=novel_id, seq=proj.hook_seq_high, description=description)
        session.add(h)
        await session.commit()
        return h.id


@pytest.fixture
def client():
    user_id, novel_id = asyncio.run(_seed())
    app.dependency_overrides[get_current_user] = lambda: {"id": user_id}
    with TestClient(app) as c:
        yield c, novel_id
    app.dependency_overrides.clear()


# ── CRUD 全路径（tasks 2.1）───────────────────────────────────────────────


class TestHooksCrud:
    def test_post_list_code_seq(self, client):
        c, nid = client
        r = c.post(f"/api/novels/{nid}/hooks", json={"description": "主角妹妹失踪的真相"})
        assert r.status_code == 200, r.text
        h1 = r.json()["data"]
        assert h1["seq"] == 1 and h1["code"] == "#H-0001"
        assert h1["status"] == "active" and h1["type"] == "mystery" and h1["priority"] == 2

        r = c.post(f"/api/novels/{nid}/hooks", json={
            "description": "半张地图", "type": "clue", "priority": "high", "status": "active",
        })
        h2 = r.json()["data"]
        assert h2["seq"] == 2 and h2["code"] == "#H-0002" and h2["priority"] == 1

        r = c.get(f"/api/novels/{nid}/hooks")
        data = r.json()["data"]
        assert data["count"] == 2
        assert [i["code"] for i in data["items"]] == ["#H-0001", "#H-0002"]

    def test_patch_partial_fields(self, client):
        c, nid = client
        hid = c.post(f"/api/novels/{nid}/hooks", json={"description": "旧描述"}).json()["data"]["id"]
        r = c.patch(f"/api/novels/{nid}/hooks/{hid}", json={
            "description": "  新描述  ", "type": "threat", "priority": 3, "status": "resolved",
            "payoff_note": "用假死收束",
        })
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["description"] == "新描述"  # trim
        assert data["type"] == "threat" and data["priority"] == 3 and data["status"] == "resolved"
        assert data["payoff_note"] == "用假死收束"

    def test_patch_rejects_bad_enum_length_unknown(self, client):
        c, nid = client
        hid = c.post(f"/api/novels/{nid}/hooks", json={"description": "x"}).json()["data"]["id"]
        # type 非白名单
        r = c.patch(f"/api/novels/{nid}/hooks/{hid}", json={"type": "bogus"})
        assert r.status_code == 400
        # status 非白名单（mentioned 不是状态）
        r = c.patch(f"/api/novels/{nid}/hooks/{hid}", json={"status": "mentioned"})
        assert r.status_code == 400
        # priority 混形非法
        r = c.patch(f"/api/novels/{nid}/hooks/{hid}", json={"priority": "highest"})
        assert r.status_code == 400
        # 超长
        r = c.patch(f"/api/novels/{nid}/hooks/{hid}", json={"description": "长" * 301})
        assert r.status_code == 400
        r = c.patch(f"/api/novels/{nid}/hooks/{hid}", json={"payoff_note": "长" * 301})
        assert r.status_code == 400
        # 未知格
        r = c.patch(f"/api/novels/{nid}/hooks/{hid}", json={"nope": "x"})
        assert r.status_code == 400
        # mentioned_chapter_id 是归档专属列，手写拒绝
        r = c.patch(f"/api/novels/{nid}/hooks/{hid}", json={"mentioned_chapter_id": "whatever"})
        assert r.status_code == 400

    def test_status_switch_keeps_payoff_record(self, client):
        """resolved→active 回切保留收束记录（spec：收束章节与怎么收的不清）。"""
        c, nid = client
        hid = c.post(f"/api/novels/{nid}/hooks", json={"description": "x"}).json()["data"]["id"]
        ch_ids = asyncio.run(_seed_chapters(nid, 1))
        c.patch(f"/api/novels/{nid}/hooks/{hid}", json={
            "status": "resolved", "resolved_chapter_id": ch_ids[0], "payoff_note": "怎么收的",
        })
        r = c.patch(f"/api/novels/{nid}/hooks/{hid}", json={"status": "active"})
        data = r.json()["data"]
        assert data["status"] == "active"
        assert data["resolved_chapter_id"] == ch_ids[0]
        assert data["payoff_note"] == "怎么收的"

    def test_chapter_refs_validated_same_novel(self, client):
        """章引用只认同书章 id：跨书/不存在拒绝（tasks 2.1）。"""
        c, nid = client
        _ouid, _onid, other_ch = asyncio.run(_seed_other_book())
        hid = c.post(f"/api/novels/{nid}/hooks", json={"description": "x"}).json()["data"]["id"]

        r = c.patch(f"/api/novels/{nid}/hooks/{hid}", json={"introduced_chapter_id": other_ch})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_chapter_ref"
        r = c.patch(f"/api/novels/{nid}/hooks/{hid}", json={"planned_chapter_id": "no-such-id"})
        assert r.status_code == 400

        # 同书章 id：合法引用落库
        ch_ids = asyncio.run(_seed_chapters(nid, 1))
        r = c.patch(f"/api/novels/{nid}/hooks/{hid}", json={"introduced_chapter_id": ch_ids[0]})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["introduced_chapter_id"] == ch_ids[0]

    def test_delete_returns_token_and_restore_by_original_id(self, client):
        c, nid = client
        h = c.post(f"/api/novels/{nid}/hooks", json={
            "description": "被删的钩子", "type": "promise", "priority": 1,
        }).json()["data"]
        r = c.delete(f"/api/novels/{nid}/hooks/{h['id']}")
        assert r.status_code == 200, r.text
        token = r.json()["data"]["undo"]["token"]
        assert token

        # 列表空了
        assert c.get(f"/api/novels/{nid}/hooks").json()["data"]["count"] == 0

        # restore：原 id 原样恢复
        r = c.post(f"/api/novels/{nid}/hooks/{h['id']}/restore", json={"token": token})
        assert r.status_code == 200, r.text
        restored = r.json()["data"]
        assert restored["id"] == h["id"]
        assert restored["seq"] == h["seq"] and restored["code"] == h["code"]
        assert restored["description"] == "被删的钩子"
        assert restored["type"] == "promise" and restored["priority"] == 1

    def test_restore_idempotent(self, client):
        c, nid = client
        h = c.post(f"/api/novels/{nid}/hooks", json={"description": "幂等恢复"}).json()["data"]
        token = c.delete(f"/api/novels/{nid}/hooks/{h['id']}").json()["data"]["undo"]["token"]
        for _ in range(2):
            r = c.post(f"/api/novels/{nid}/hooks/{h['id']}/restore", json={"token": token})
            assert r.status_code == 200, r.text
        r = c.get(f"/api/novels/{nid}/hooks")
        assert r.json()["data"]["count"] == 1  # 不重复插行
        assert r.json()["data"]["items"][0]["id"] == h["id"]

    def test_token_mismatch_and_missing_op_rejected(self, client):
        c, nid = client
        h = c.post(f"/api/novels/{nid}/hooks", json={"description": "x"}).json()["data"]
        c.delete(f"/api/novels/{nid}/hooks/{h['id']}")
        # 无 op 的 hid
        r = c.post(f"/api/novels/{nid}/hooks/does-not-exist/restore", json={})
        assert r.status_code == 400
        # token 不匹配
        r = c.post(f"/api/novels/{nid}/hooks/{h['id']}/restore", json={"token": "wrong"})
        assert r.status_code == 409

    def test_new_delete_invalidates_previous_token(self, client):
        """单槽撤销：token 有效期到「下次操作」（design.md D4）。"""
        c, nid = client
        h1 = c.post(f"/api/novels/{nid}/hooks", json={"description": "第一条"}).json()["data"]
        h2 = c.post(f"/api/novels/{nid}/hooks", json={"description": "第二条"}).json()["data"]
        t1 = c.delete(f"/api/novels/{nid}/hooks/{h1['id']}").json()["data"]["undo"]["token"]
        c.delete(f"/api/novels/{nid}/hooks/{h2['id']}")  # 第二次操作 → t1 失效
        r = c.post(f"/api/novels/{nid}/hooks/{h1['id']}/restore", json={"token": t1})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "undo_expired"

    def test_seq_never_reused_after_delete(self, client):
        """删除编号最大的伏笔后再新建：新 seq 大于所有历史 seq（spec Scenario）。"""
        c, nid = client
        h1 = c.post(f"/api/novels/{nid}/hooks", json={"description": "一"}).json()["data"]
        h2 = c.post(f"/api/novels/{nid}/hooks", json={"description": "二"}).json()["data"]
        c.delete(f"/api/novels/{nid}/hooks/{h2['id']}")
        h3 = c.post(f"/api/novels/{nid}/hooks", json={"description": "三"}).json()["data"]
        assert h3["seq"] > h1["seq"] and h3["seq"] > h2["seq"]
        assert h3["code"] == "#H-0003"

        # restore 不占新号：原 seq 原样恢复（在单槽撤销窗口内恢复 h2）
        r = c.post(f"/api/novels/{nid}/hooks/{h2['id']}/restore")
        assert r.status_code == 200
        assert r.json()["data"]["seq"] == h2["seq"]
        # 台账回到 h1/h2/h3 三条，编号 1/2/3 连续（无新号被占用）
        assert c.get(f"/api/novels/{nid}/hooks").json()["data"]["count"] == 3

    def test_cross_novel_access_rejected(self, client):
        """越权：别的书的 hook id → 400 not_found（读/改/删/撤全路径）。"""
        c, nid = client
        _ouid, onid = asyncio.run(_seed_other_book())[:2]
        other_hid = asyncio.run(_seed_hook_in(onid))

        r = c.patch(f"/api/novels/{nid}/hooks/{other_hid}", json={"description": "越权"})
        assert r.status_code == 400
        r = c.delete(f"/api/novels/{nid}/hooks/{other_hid}")
        assert r.status_code == 400
        r = c.post(f"/api/novels/{nid}/hooks/{other_hid}/restore")
        assert r.status_code == 400

    def test_post_unknown_novel_rejected(self, client):
        c, _nid = client
        r = c.post("/api/novels/no-such-novel/hooks", json={"description": "x"})
        assert r.status_code == 400


# ── 级联（tasks 1.2 / 2.2）────────────────────────────────────────────────


class TestCascadeRules:
    def test_delete_chapter_sets_four_refs_null(self):
        async def _run():
            _uid, nid = await _seed()
            ch_ids = await _seed_chapters(nid, 1)
            async with async_session() as session:
                session.add(NovelHook(
                    novel_id=nid, seq=1, description="引用将被删的章",
                    introduced_chapter_id=ch_ids[0], planned_chapter_id=ch_ids[0],
                    resolved_chapter_id=ch_ids[0], mentioned_chapter_id=ch_ids[0],
                ))
                await session.commit()

            # 删章（DB 行直删，等价于删章端点最终触发的行删除）
            from models.chapter import Chapter

            async with async_session() as session:
                row = await session.get(Chapter, ch_ids[0])
                await session.delete(row)
                await session.commit()

            async with async_session() as session:
                h = (await session.scalars(
                    select(NovelHook).where(NovelHook.novel_id == nid)
                )).one()
                assert h.description == "引用将被删的章"  # 行保留
                assert h.introduced_chapter_id is None
                assert h.planned_chapter_id is None
                assert h.resolved_chapter_id is None
                assert h.mentioned_chapter_id is None

        asyncio.run(_run())

    def test_delete_volume_cascades_chapters_and_nulls_refs(self):
        async def _run():
            _uid, nid = await _seed()
            ch_ids = await _seed_chapters(nid, 1)
            async with async_session() as session:
                session.add(NovelHook(
                    novel_id=nid, seq=1, description="卷删章也被删",
                    introduced_chapter_id=ch_ids[0], planned_chapter_id=ch_ids[0],
                ))
                await session.commit()

            from models.volume import Volume

            async with async_session() as session:
                vol = (await session.scalars(
                    select(Volume).where(Volume.project_id == nid)
                )).one()
                await session.delete(vol)  # 卷 CASCADE 删章 → hook 引用 SET NULL
                await session.commit()

            async with async_session() as session:
                h = (await session.scalars(
                    select(NovelHook).where(NovelHook.novel_id == nid)
                )).one()
                assert h.introduced_chapter_id is None
                assert h.planned_chapter_id is None

        asyncio.run(_run())

    def test_delete_novel_cascades_hooks(self):
        async def _run():
            _uid, nid = await _seed()
            async with async_session() as session:
                session.add(NovelHook(novel_id=nid, seq=1, description="随书删"))
                await session.commit()

            async with async_session() as session:
                proj = await session.get(Novel, nid)
                await session.delete(proj)
                await session.commit()

            async with async_session() as session:
                count = await session.scalar(
                    select(func.count()).select_from(NovelHook).where(NovelHook.novel_id == nid)
                )
                assert count == 0

        asyncio.run(_run())


# ── 卷章树补 chapter id（tasks 1.3）───────────────────────────────────────


class TestTreeCarriesChapterId:
    def test_volumes_and_tree_chapter_entries_carry_db_id(self, client):
        c, nid = client
        asyncio.run(_seed_chapters(nid, 2))

        async def _db_ids():
            from models.chapter import Chapter

            async with async_session() as session:
                rows = (await session.scalars(
                    select(Chapter).where(Chapter.project_id == nid).order_by(Chapter.chapter_no)
                )).all()
                return [row.id for row in rows]

        db_ids = asyncio.run(_db_ids())

        r = c.get(f"/api/novels/{nid}/volumes")
        assert r.status_code == 200, r.text
        entries = r.json()[0]["chapters"]
        assert [e["id"] for e in entries] == db_ids

        r = c.get(f"/api/novels/{nid}/tree")
        assert r.status_code == 200, r.text
        tree_entries = r.json()["volumes"][0]["chapters"]
        assert [e["id"] for e in tree_entries] == db_ids
