"""拆书第三出口测试（c-charlib-deconstruct-exit）：投影单源/候选端点/收录幂等/换名/状态码/exported_at。"""

import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from auth_local.middleware import get_current_user
from db import async_session
from deconstruct.cards import card_to_book_payload, cards_from_products
from library import service as lib_service
from main import app
from models.deconstruct import DeconstructJob
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _products():
    return {
        "characters": {
            "file": "characters.json",
            "data": {
                "characters": [
                    {
                        "name": "沈青崖", "role": "主角", "persona": "",
                        "background": "看山人独子", "gender": "男", "age": "16",
                        "speech": "话少", "faction": "青云峰", "look": "清瘦",
                        "race": "人族", "plot": "下山", "evidence_ch": "第1章",
                        "confidence": "high",
                    },
                    {
                        "name": "秦重霄", "role": "核心反派", "persona": "暴躁记仇",
                        "gender": "男", "age": "42", "confidence": "mid",
                    },
                    # 路人不入清单
                    {"name": "黑风七", "role": "路人", "persona": "探子"},
                    # 同名跨批重复：合并
                    {"name": "秦重霄", "role": "反派", "persona": "", "speech": "骂人",
                     "confidence": "low"},
                ]
            },
        },
        "genre": {"file": "genre.json", "data": {"genre": "古装玄幻"}},
    }


async def _seed(status: str = "completed", with_products: bool = True) -> dict:
    uid = f"dexit-{uuid.uuid4().hex[:8]}"
    tid = str(uuid.uuid4())
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="出口测试"))
        db.add(DeconstructJob(
            id=tid, user_id=uid, status=status, queue_seq=1,
            source_name="剑照山河.txt", source_size=1000, book_name="剑照山河",
            total_chars=1000, chapter_count=5, volume_count=1,
            selected_dims_json=json.dumps(["characters", "genre"]),
            dims_json="{}",
            products_json=json.dumps(_products() if with_products else {"genre": {"data": {}}}, ensure_ascii=False),
        ))
        await db.commit()
    return {"uid": uid, "task_id": tid}


@pytest.fixture
def client():
    seed = _run(_seed())

    async def _override():
        return {"id": seed["uid"]}

    app.dependency_overrides[get_current_user] = _override
    with TestClient(app) as c:
        yield c, seed
    app.dependency_overrides.clear()


class TestProjection:
    def test_projection_single_source_and_payload(self):
        cards = cards_from_products(_products()["characters"]["data"])
        # 路人过滤 + 同名合并（低可信度字段补空）
        assert [c["name"] for c in cards] == ["沈青崖", "秦重霄"]
        qcx = cards[1]
        assert qcx["role"] == "反派"  # 「核心反派」归一
        assert qcx["speech"] == "骂人"  # 低可信度补空格
        # 人设兜底从背景合成；plot 末尾保留 evidence
        assert cards[0]["persona"] == "看山人独子"
        assert "第1章" in cards[0]["plot"]
        # 扁平 → create_character 载荷（建书/收录共用组装）
        payload = card_to_book_payload(qcx, 2)
        assert payload["name"] == "秦重霄" and payload["role"] == "反派"
        assert payload["dossier"]["speech"] == "骂人"
        # 空名兜底
        assert card_to_book_payload({"name": ""}, 3)["name"] == "未命名3"

    def test_apply_reexports_still_work(self):
        from deconstruct.apply import _cards, _role_normalize

        assert _role_normalize("核心反派") == "反派"
        assert callable(_cards)


class TestCandidates:
    def test_candidates_list(self, client):
        c, seed = client
        r = c.get(f"/api/deconstruct/tasks/{seed['task_id']}/library-candidates")
        assert r.status_code == 200
        data = r.json()
        assert data["can_import"] is True
        assert [i["key"] for i in data["items"]] == ["沈青崖", "秦重霄"]
        assert all(i["collected"] is False for i in data["items"])

    def test_not_completed_and_missing_products(self, client):
        c, seed = client
        async def _set(status, products):
            async with async_session() as db:
                job = await db.get(DeconstructJob, seed["task_id"])
                job.status = status
                if products is not None:
                    job.products_json = products
                await db.commit()
        _run(_set("running", None))
        r = c.get(f"/api/deconstruct/tasks/{seed['task_id']}/library-candidates")
        assert r.json()["can_import"] is False and "没拆完" in r.json()["reason"]
        _run(_set("completed", json.dumps({"genre": {"data": {}}})))
        r2 = c.get(f"/api/deconstruct/tasks/{seed['task_id']}/library-candidates")
        assert r2.json()["can_import"] is False and "没有角色" in r2.json()["reason"]


class TestToLibrary:
    def test_import_idempotent_and_collected_flag(self, client):
        c, seed = client
        body = {"picks": ["沈青崖", "秦重霄"], "rename": False}
        r = c.post(f"/api/deconstruct/tasks/{seed['task_id']}/to-library", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] == 2 and data["skipped"] == 0

        listed = c.get("/api/character-library").json()["data"]
        assert listed["count"] == 2
        names = {i["name"] for i in listed["items"]}
        assert names == {"沈青崖", "秦重霄"}
        qcx = next(i for i in listed["items"] if i["name"] == "秦重霄")
        assert qcx["genre"] == "玄幻" and qcx["src"]["kind"] == "deconstruct"  # 自由文本经目录归一

        # 幂等：重复提交同一批
        again = c.post(f"/api/deconstruct/tasks/{seed['task_id']}/to-library", json=body).json()
        assert again["created"] == 0 and again["skipped"] == 2
        assert c.get("/api/character-library").json()["data"]["count"] == 2

        # 已收录态
        items = c.get(f"/api/deconstruct/tasks/{seed['task_id']}/library-candidates").json()["items"]
        assert all(i["collected"] for i in items)

    def test_rename_only_name_and_age(self, client):
        c, seed = client
        r = c.post(f"/api/deconstruct/tasks/{seed['task_id']}/to-library",
                   json={"picks": ["秦重霄"], "rename": True})
        assert r.status_code == 200
        card = c.get("/api/character-library").json()["data"]["items"][0]
        assert card["name"] != "秦重霄"
        assert 16 <= int(card["dossier"]["age"]) <= 55
        assert card["persona"] == "暴躁记仇"  # 其余格不动

    def test_status_codes(self, client):
        c, seed = client
        assert c.post(f"/api/deconstruct/tasks/{seed['task_id']}/to-library",
                      json={"picks": []}).status_code == 400
        async def _running():
            async with async_session() as db:
                job = await db.get(DeconstructJob, seed["task_id"])
                job.status = "running"
                await db.commit()
        _run(_running())
        assert c.post(f"/api/deconstruct/tasks/{seed['task_id']}/to-library",
                      json={"picks": ["沈青崖"]}).status_code == 409
        async def _noprod():
            async with async_session() as db:
                job = await db.get(DeconstructJob, seed["task_id"])
                job.status = "completed"
                job.products_json = json.dumps({"genre": {"data": {}}})
                await db.commit()
        _run(_noprod())
        assert c.post(f"/api/deconstruct/tasks/{seed['task_id']}/to-library",
                      json={"picks": ["沈青崖"]}).status_code == 422

    def test_exported_at_and_badge(self, client):
        c, seed = client
        before = c.get("/api/deconstruct/tasks").json()["badge"]
        assert before >= 1
        c.post(f"/api/deconstruct/tasks/{seed['task_id']}/to-library",
               json={"picks": ["沈青崖"]})
        after = c.get("/api/deconstruct/tasks").json()["badge"]
        assert after == before - 1  # 已取结果：徽标不再计数
        async def _exported():
            async with async_session() as db:
                job = await db.get(DeconstructJob, seed["task_id"])
                return job.exported_at
        assert _run(_exported()) is not None


class TestLibrarySideKeys:
    def test_source_key_fallback(self):
        assert lib_service.deconstruct_source_key({"name": "  "}, 4) == "未命名#4"
        assert lib_service.deconstruct_source_key({"name": " 甲 "}, 1) == "甲"
