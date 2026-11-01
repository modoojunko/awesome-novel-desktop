"""角色库迁移测试（c-kb-character-migration 批6）：parity／幂等／题材兜底／端点。"""

import asyncio
import json
import uuid

from db import async_session
from models.character_library import CharacterLibrary
from models.kb import KbEntry
from models.project import Novel
from models.user import User


def _run(coro):
    return asyncio.run(coro)


async def _seed(cards: list[dict]) -> dict:
    uid = f"kbmig-{uuid.uuid4().hex[:8]}"
    slug = f"kbmig-{uuid.uuid4().hex[:8]}"
    async with async_session() as db:
        db.add(User(
            id=uid, email=f"{uid}@t.local", password_hash="x", display_name="迁移测试",
            api_key="", api_base_url="", api_model="",
        ))
        novel = Novel(
            user_id=uid, name="迁移测试书", slug=slug, root_path=f"./data/{slug}",
            source="manual", current_phase="write",
        )
        db.add(novel)
        await db.flush()
        ids = []
        for c in cards:
            card = CharacterLibrary(
                id=c.get("id") or str(uuid.uuid4()),
                user_id=uid,
                name=c["name"],
                role=c.get("role", "配角"),
                genre=c.get("genre", ""),
                kind=c.get("kind", ""),
                persona=c.get("persona", ""),
                dossier=json.dumps(c.get("dossier", {}), ensure_ascii=False),
                cog=json.dumps(c.get("cog", {}), ensure_ascii=False),
                src_kind="book",
                src_novel_name=c.get("src_novel_name", ""),
            )
            db.add(card)
            ids.append(card.id)
        await db.commit()
        return {"uid": uid, "novel_id": novel.id, "card_ids": ids}


def test_字段映射_parity():
    dossier = {
        "gender": "男", "age": "42", "race": "人族", "faction": "黑风寨",
        "look": "虬髯客", "speech": "骂人先问候", "background": "山匪出身", "plot": "中期反派",
    }
    cog = {"w1": "山规即天", "w5": "不知寨主底细", "s1": "大当家", "v1": "守住寨子"}
    seed = _run(_seed([{
        "name": "秦重霄", "persona": "黑风寨大当家，话少刀狠。",
        "genre": "武侠", "dossier": dossier, "cog": cog,
        "src_novel_name": "剑照山河",
    }]))

    async def _go():
        async with async_session() as db:
            from kb.migrate_library import migrate_character_library

            r1 = await migrate_character_library(db, user_id=seed["uid"])
            rows = (
                await db.execute(KbEntry.__table__.select().where(KbEntry.user_id == seed["uid"]))
            )
            entries = rows.mappings().all()
            return r1, entries

    r1, entries = _run(_go())
    assert r1 == {"migrated": 1, "skipped": 0}
    e = entries[0]
    payload = json.loads(e["payload_json"])
    assert e["concept"] == "角色设定"
    assert e["title"] == "秦重霄"
    assert e["genre"] == "武侠"
    assert e["src_kind"] == "character_library_migration"
    assert e["src_ref"] == "character_library"
    assert e["src_key"] == seed["card_ids"][0]
    assert e["evidence"] == "剑照山河"
    assert e["instruction"].endswith("。")
    # parity：档案八格＋认知格逐格
    assert payload["archetype"] == "秦重霄"
    assert payload["persona"] == "黑风寨大当家，话少刀狠。"
    for k, v in dossier.items():
        assert payload[k] == v, f"档案格 {k} 丢失"
    for k, v in cog.items():
        assert payload[k] == v, f"认知格 {k} 丢失"
    # 缺格不落（夹具 cog 只给了 w1/w5/s1/v1；档案格全给）
    assert "p3" not in payload and "e3" not in payload and "s5" not in payload and "p2" not in payload


def test_幂等_重复迁移零副本():
    seed = _run(_seed([
        {"name": "张三", "genre": "都市"},
        {"name": "李四", "genre": "不存在的题材"},
    ]))

    async def _go():
        async with async_session() as db:
            from kb.migrate_library import migrate_character_library

            r1 = await migrate_character_library(db, user_id=seed["uid"])
            r2 = await migrate_character_library(db, user_id=seed["uid"])
            return r1, r2

    r1, r2 = _run(_go())
    assert r1 == {"migrated": 2, "skipped": 0}
    assert r2 == {"migrated": 0, "skipped": 2}

    async def _count():
        async with async_session() as db:
            n = len((
                (await db.execute(KbEntry.__table__.select().where(KbEntry.user_id == seed["uid"])))
            ).mappings().all())
            return n

    assert _run(_count()) == 2


def test_题材不在21目录_落跨题材通用():
    seed = _run(_seed([{"name": "王五", "genre": "玄幻修真乱写"}]))

    async def _go():
        async with async_session() as db:
            from kb.migrate_library import migrate_character_library

            await migrate_character_library(db, user_id=seed["uid"])
            rows = (
                await db.execute(KbEntry.__table__.select().where(KbEntry.user_id == seed["uid"]))
            ).mappings().all()
            return rows[0]

    e = _run(_go())
    # 自由文本题材不硬塞词表——落 ""（跨题材通用），概念 id 同步兜底
    assert e["genre"] == "玄幻修真乱写"  # 原样保留（消费端按 21 目录过滤时自然归通用组）
    assert e["concept_id"].endswith(":角色设定")


def test_迁移端点_信封与鉴权():
    from fastapi.testclient import TestClient

    from auth_local.middleware import get_current_user
    from main import app

    seed = _run(_seed([{"name": "赵六"}]))
    app.dependency_overrides[get_current_user] = lambda: {"id": seed["uid"]}
    try:
        with TestClient(app) as c:
            r = c.post("/api/kb/migrate-library")
            assert r.status_code == 200
            assert r.json()["data"] == {"migrated": 1, "skipped": 0}
            r = c.post("/api/kb/migrate-library")
            assert r.json()["data"] == {"migrated": 0, "skipped": 1}
    finally:
        app.dependency_overrides.clear()


# ─── 双向映射单源（c-kb-character-migration 刀2b 地基）──────


def test_卡payload卡_往返parity():
    from kb.migrate_library import card_to_payload, payload_to_card
    from models.kb import KbEntry

    dossier = {"gender": "男", "age": "42", "race": "人族", "faction": "黑风寨",
               "look": "虬髯", "speech": "骂人", "background": "山匪", "plot": "反派"}
    cog = {"w1": "山规", "b1": "暴躁"}
    card_id = str(uuid.uuid4())

    async def _mk():
        async with async_session() as db:
            card = CharacterLibrary(
                id=card_id, user_id="parity-user", name="秦重霄",
                aliases=json.dumps(["大当家", "老爷子"], ensure_ascii=False),
                role="反派", genre="武侠", kind="敌人",
                persona="黑风寨大当家，话少刀狠。",
                dossier=json.dumps(dossier, ensure_ascii=False),
                cog=json.dumps(cog, ensure_ascii=False),
                src_kind="book", src_novel_name="剑照山河",
            )
            db.add(card)
            payload = card_to_payload(card)
            entry = KbEntry(
                id=str(uuid.uuid4()), user_id="parity-user", genre="武侠",
                concept="角色设定", concept_id="武侠:角色设定", title="秦重霄",
                payload_json=json.dumps(payload, ensure_ascii=False),
                instruction="x。", when_json="{}",
                src_kind="character_library_migration", src_ref="character_library",
                src_key=card_id, src_novel_name="剑照山河",
                rev=3,
            )
            return payload, payload_to_card(entry)

    payload, back = _run(_mk())
    # 正向：分类字段进 payload
    assert payload["aliases"] == ["大当家", "老爷子"]
    assert payload["role"] == "反派"
    assert payload["kind"] == "敌人"
    # 反向：卡形状全量还原
    assert back["name"] == "秦重霄"
    assert back["aliases"] == ["大当家", "老爷子"]
    assert back["role"] == "反派"
    assert back["kind"] == "敌人"
    assert back["persona"] == "黑风寨大当家，话少刀狠。"
    assert back["dossier"] == dossier
    assert back["cog"] == cog
    assert back["genre"] == "武侠"
    assert back["rev"] == 3
    assert back["src_character_id"] == card_id
    assert back["src_novel_name"] == "剑照山河"


def test_反向映射_空payload兜底():
    from kb.migrate_library import payload_to_card
    from models.kb import KbEntry

    async def _mk():
        e = KbEntry(
            id="e1", user_id="u", genre="", concept="角色设定",
            payload_json="not-json{", instruction="x。",
        )
        return payload_to_card(e)

    card = _run(_mk())
    assert card["name"] == ""  # 坏 json 兜底空卡形状
    assert card["dossier"] == {} and card["cog"] == {}
    assert card["role"] == "配角"  # role 缺省
