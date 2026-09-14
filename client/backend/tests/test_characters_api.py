"""角色 CRUD / 关系 / 删除合并撤销 端点测试（tasks 2.3-2.5）。"""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.character import Character
from models.project import Novel
from models.user import User


async def _seed() -> tuple[str, str]:
    uid = f"chapi-{uuid.uuid4().hex[:8]}"
    slug = f"chapi-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name="接口测试", api_key="", api_base_url="", api_model="",
        ))
        proj = Novel(
            user_id=uid, name="接口测试书", slug=slug,
            root_path=f"./data/{slug}", source="manual", current_phase="write",
        )
        session.add(proj)
        await session.commit()
        return uid, proj.id


@pytest.fixture
def client():
    user_id, novel_id = asyncio.run(_seed())

    async def _override():
        return {"id": user_id}

    app.dependency_overrides[get_current_user] = _override
    with TestClient(app) as c:
        yield c, novel_id
    app.dependency_overrides.clear()


class TestFirstChapter:
    def test_list_and_card_carry_first_chapter(self, client):
        """spec：列表聚合 SHALL 含首次出场（出场章最小阅读序的章号）。"""
        from models.chapter import Chapter, ChapterCharacter
        from models.volume import Volume

        c, nid = client
        r = c.post(f"/api/novels/{nid}/characters", json={"name": "林拾", "role": "主角"})
        cid = r.json()["data"]["id"]

        async def _seed_chapters() -> None:
            async with async_session() as session:
                vol = Volume(id=str(uuid.uuid4()), project_id=nid, volume_no=1, title="V1")
                session.add(vol)
                await session.flush()
                ch2 = Chapter(
                    project_id=nid, volume_id=vol.id, chapter_no=2,
                    ref="v1-c2", title="二", status="outline",
                )
                ch5 = Chapter(
                    project_id=nid, volume_id=vol.id, chapter_no=5,
                    ref="v1-c5", title="五", status="outline",
                )
                session.add_all([ch2, ch5])
                await session.flush()
                session.add_all([
                    ChapterCharacter(chapter_id=ch5.id, sort_order=0, character_id=cid, character_name="林拾"),
                    ChapterCharacter(chapter_id=ch2.id, sort_order=0, character_id=cid, character_name="林拾"),
                ])
                await session.commit()

        asyncio.run(_seed_chapters())

        data = c.get(f"/api/novels/{nid}/characters").json()["data"]
        assert data["items"][0]["first_chapter"] == 2  # 出场在 5 和 2 → 取 2
        card = c.get(f"/api/novels/{nid}/characters/{cid}").json()["data"]
        assert card["first_chapter"] == 2

        # 未出场角色 → None
        c.post(f"/api/novels/{nid}/characters", json={"name": "路人甲"})
        data = c.get(f"/api/novels/{nid}/characters").json()["data"]
        by_name = {x["name"]: x["first_chapter"] for x in data["items"]}
        assert by_name["路人甲"] is None


    def test_create_list_get_patch_flow(self, client):
        c, nid = client
        r = c.post(f"/api/novels/{nid}/characters", json={"name": "林拾", "role": "主角"})
        assert r.status_code == 200, r.text
        card = r.json()["data"]
        assert card["seq"] == 1 and card["code"] == "C-0001" and card["role"] == "主角"

        # 列表一次给全
        r = c.get(f"/api/novels/{nid}/characters")
        data = r.json()["data"]
        assert data["count"] == 1 and data["protagonist_id"] == card["id"]
        assert data["items"][0]["gaps"]  # 空卡有缺口提示

        # 单格 PATCH：dossier.plot
        r = c.patch(f"/api/novels/{nid}/characters/{card['id']}", json={
            "path": "dossier.plot", "value": "以弱破强", "base_rev": card["rev"],
        })
        assert r.status_code == 200, r.text
        assert r.json()["data"]["rev"] == card["rev"] + 1

        # 旧 rev → 409 且带当前值
        r = c.patch(f"/api/novels/{nid}/characters/{card['id']}", json={
            "path": "dossier.plot", "value": "另一句", "base_rev": card["rev"],
        })
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["code"] == "rev_conflict"
        assert detail["current"] == "以弱破强"
        assert detail["field"] == "dossier.plot"

        # 未知格 → 400
        r = c.patch(f"/api/novels/{nid}/characters/{card['id']}", json={
            "path": "cog.nope", "value": "x", "base_rev": card["rev"] + 1,
        })
        assert r.status_code == 400

    def test_empty_name_gets_placeholder_unique(self, client):
        c, nid = client
        r1 = c.post(f"/api/novels/{nid}/characters", json={"name": ""})
        r2 = c.post(f"/api/novels/{nid}/characters", json={"name": ""})
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["data"]["name"] != r2.json()["data"]["name"]

    def test_set_protagonist_demotes_old(self, client):
        c, nid = client
        a = c.post(f"/api/novels/{nid}/characters", json={"name": "甲", "role": "主角"}).json()["data"]
        b = c.post(f"/api/novels/{nid}/characters", json={"name": "乙"}).json()["data"]
        r = c.patch(f"/api/novels/{nid}/characters/{b['id']}", json={
            "path": "role", "value": "主角", "base_rev": b["rev"],
        })
        assert r.status_code == 200, r.text
        roles = {
            item["name"]: item["role"]
            for item in c.get(f"/api/novels/{nid}/characters").json()["data"]["items"]
        }
        assert roles == {"甲": "配角", "乙": "主角"}

    def test_rename_to_conflict_name_rejected(self, client):
        c, nid = client
        c.post(f"/api/novels/{nid}/characters", json={"name": "林拾"})
        b = c.post(f"/api/novels/{nid}/characters", json={"name": "乙"}).json()["data"]
        r = c.patch(f"/api/novels/{nid}/characters/{b['id']}", json={
            "path": "name", "value": "林拾", "base_rev": b["rev"],
        })
        assert r.status_code in (400, 409, 500)  # DB 唯一约束（服务层预检在 name 非空时先行）
        # 服务层预检（更友好）：
        c2 = c.post(f"/api/novels/{nid}/characters", json={"name": "林拾"})
        assert c2.status_code == 409


class TestRelations:
    def test_upsert_idempotent_and_directional(self, client):
        c, nid = client
        a = c.post(f"/api/novels/{nid}/characters", json={"name": "甲"}).json()["data"]
        b = c.post(f"/api/novels/{nid}/characters", json={"name": "乙"}).json()["data"]
        url = f"/api/novels/{nid}/characters/{a['id']}/relations/{b['id']}"
        r1 = c.put(url, json={"rel_type": "同盟", "stance": "试探"})
        assert r1.status_code == 200, r1.text
        r2 = c.put(url, json={"rel_type": "敌对", "stance": "转明"})
        assert r2.status_code == 200
        rels = c.get(url.rsplit("/", 1)[0]).json()["data"]
        assert len(rels) == 1  # 幂等：仍一条
        assert rels[0]["rel_type"] == "敌对"

        # 反向是另一条（单向）
        r3 = c.put(
            f"/api/novels/{nid}/characters/{b['id']}/relations/{a['id']}",
            json={"rel_type": "同盟", "stance": "各留一手"},
        )
        assert r3.status_code == 200
        rels_a = c.get(f"/api/novels/{nid}/characters/{a['id']}/relations").json()["data"]
        assert len(rels_a) == 1  # 甲的视角里只有他对乙的那条

        # 自环 400
        r4 = c.put(
            f"/api/novels/{nid}/characters/{a['id']}/relations/{a['id']}",
            json={"rel_type": "同盟"},
        )
        assert r4.status_code == 400

    def test_relation_delete_and_undo(self, client):
        c, nid = client
        a = c.post(f"/api/novels/{nid}/characters", json={"name": "甲"}).json()["data"]
        b = c.post(f"/api/novels/{nid}/characters", json={"name": "乙"}).json()["data"]
        url = f"/api/novels/{nid}/characters/{a['id']}/relations/{b['id']}"
        c.put(url, json={"rel_type": "同盟", "stance": "试探", "note": "互换线索"})
        r = c.delete(url)
        assert r.status_code == 200, r.text
        token = r.json()["data"]["undo"]["op_id"]
        assert c.get(f"/api/novels/{nid}/characters/{a['id']}/relations").json()["data"] == []

        undo = c.post(f"/api/novels/{nid}/characters/ops/{token}/undo")
        assert undo.status_code == 200, undo.text
        rels = c.get(f"/api/novels/{nid}/characters/{a['id']}/relations").json()["data"]
        assert rels and rels[0]["stance"] == "试探"

        # 二次撤销 → 409 already_undone
        again = c.post(f"/api/novels/{nid}/characters/ops/{token}/undo")
        assert again.status_code == 409
        assert again.json()["detail"]["code"] == "already_undone"

        # 无此 token → 400（not_found 走 Unprocessable）
        missing = c.post(f"/api/novels/{nid}/characters/ops/nope/undo")
        assert missing.status_code == 400


class TestDeleteMergeUndo:
    def _seed_cards(self, c, nid: str):
        prot = c.post(f"/api/novels/{nid}/characters", json={"name": "林拾", "role": "主角"}).json()["data"]
        side = c.post(f"/api/novels/{nid}/characters", json={"name": "苏晚芜"}).json()["data"]
        c.patch(f"/api/novels/{nid}/characters/{side['id']}", json={
            "path": "cog.w5", "value": "以为旧案只是丹阁的事", "base_rev": side["rev"],
        })
        c.put(
            f"/api/novels/{nid}/characters/{prot['id']}/relations/{side['id']}",
            json={"rel_type": "同盟", "stance": "试探", "note": "互换线索"},
        )
        return prot, side

    def test_delete_with_undo_restores_everything(self, client):
        c, nid = client
        prot, side = self._seed_cards(c, nid)
        r = c.delete(f"/api/novels/{nid}/characters/{side['id']}")
        assert r.status_code == 200, r.text
        token = r.json()["data"]["undo"]["op_id"]
        items = c.get(f"/api/novels/{nid}/characters").json()["data"]["items"]
        assert len(items) == 1

        undo = c.post(f"/api/novels/{nid}/characters/ops/{token}/undo")
        assert undo.status_code == 200, undo.text
        items = c.get(f"/api/novels/{nid}/characters").json()["data"]["items"]
        assert len(items) == 2
        restored = next(i for i in items if i["name"] == "苏晚芜")
        assert restored["cog"]["w5"] == "以为旧案只是丹阁的事"  # 格内容逐字回来
        rels = c.get(f"/api/novels/{nid}/characters/{prot['id']}/relations").json()["data"]
        assert rels and rels[0]["other_name"] == "苏晚芜"

    def test_merge_fills_and_dedups_then_undo(self, client):
        c, nid = client
        prot = c.post(f"/api/novels/{nid}/characters", json={"name": "林拾", "role": "主角"}).json()["data"]
        src = c.post(f"/api/novels/{nid}/characters", json={"name": "苏晚芜"}).json()["data"]
        tgt = c.post(f"/api/novels/{nid}/characters", json={"name": "林十一"}).json()["data"]
        # 源卡：写一句认知 + 一条对林拾的关系
        c.patch(f"/api/novels/{nid}/characters/{src['id']}", json={
            "path": "cog.w5", "value": "以为旧案只是丹阁的事", "base_rev": src["rev"],
        })
        c.put(
            f"/api/novels/{nid}/characters/{src['id']}/relations/{prot['id']}",
            json={"rel_type": "仇人", "stance": "家案"},
        )
        # 目标卡：也对林拾有一条（合并时应去重成一条，且目标已有字不动）
        c.put(
            f"/api/novels/{nid}/characters/{tgt['id']}/relations/{prot['id']}",
            json={"rel_type": "同盟", "stance": "同门"},
        )

        r = c.post(f"/api/novels/{nid}/characters/{src['id']}/merge", json={"target_id": tgt["id"]})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["target"]["name"] == "林十一"
        assert "苏晚芜" in data["target"]["aliases"]  # 名字并入别名
        assert data["target"]["cog"]["w5"] == "以为旧案只是丹阁的事"  # 空格被补
        rels = c.get(f"/api/novels/{nid}/characters/{tgt['id']}/relations").json()["data"]
        to_prot = [x for x in rels if x["other_id"] == prot["id"]]
        assert len(to_prot) == 1  # 同对端去重
        assert to_prot[0]["rel_type"] == "同盟"  # 目标已有字不动（先见者赢）

        token = data["undo"]["op_id"]
        undo = c.post(f"/api/novels/{nid}/characters/ops/{token}/undo")
        assert undo.status_code == 200, undo.text
        items = {i["name"]: i for i in c.get(f"/api/novels/{nid}/characters").json()["data"]["items"]}
        assert "苏晚芜" in items  # 源卡回来了
        assert items["林十一"]["cog"].get("w5", "") in ("", None)  # 目标卡的补格被还原
        rels_src = c.get(f"/api/novels/{nid}/characters/{src['id']}/relations").json()["data"]
        assert rels_src and rels_src[0]["rel_type"] == "仇人"  # 关系改回

    def test_gate_confirm_two_tiers_and_stale(self, client):
        c, nid = client
        prot = c.post(f"/api/novels/{nid}/characters", json={"name": "林拾", "role": "主角"}).json()["data"]
        c.patch(f"/api/novels/{nid}/characters/{prot['id']}", json={
            "path": "persona", "value": "杂役弟子，记性过人", "base_rev": prot["rev"],
        })
        # 首次档：只查主角卡名称+人设
        r = c.post(f"/api/novels/{nid}/characters/confirm", json={"first": True})
        assert r.status_code == 200, r.text

        # 此后档：六项缺 → 400 点名
        r2 = c.post(f"/api/novels/{nid}/characters/confirm", json={})
        assert r2.status_code == 400
        assert "林拾" in r2.json()["detail"]["message"]

        # 补齐主角六项
        card = c.get(f"/api/novels/{nid}/characters").json()["data"]["items"][0]
        for path, value in [
            ("dossier.plot", "以弱破强"),
            ("cog.w5", "盲区"), ("cog.p3", "上限"), ("cog.p4", "代价"),
        ]:
            c.patch(f"/api/novels/{nid}/characters/{card['id']}", json={
                "path": path, "value": value, "base_rev": card["rev"],
            })
            card = c.get(f"/api/novels/{nid}/characters").json()["data"]["items"][0]
        r3 = c.post(f"/api/novels/{nid}/characters/confirm", json={})
        assert r3.status_code == 200, r3.text

        # 状态：已确认、未 stale
        status = c.get(f"/api/novels/{nid}/characters/gate/status").json()["data"]
        assert status["confirmed"] is True and status["stale"] is False

        # 清空必填 → stale
        c.patch(f"/api/novels/{nid}/characters/{card['id']}", json={
            "path": "cog.w5", "value": "", "base_rev": card["rev"],
        })
        status2 = c.get(f"/api/novels/{nid}/characters/gate/status").json()["data"]
        assert status2["stale"] is True

    def test_patch_unknown_character_404ish(self, client):
        c, nid = client
        r = c.patch(f"/api/novels/{nid}/characters/nope", json={
            "path": "name", "value": "x", "base_rev": 1,
        })
        assert r.status_code == 400
