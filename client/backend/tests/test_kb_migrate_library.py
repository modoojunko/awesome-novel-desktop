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
    # 证据列不住小说名（住 src_novel_name 专列）；无剧情锚＝证据空
    assert e["evidence"] == ""
    assert e["src_novel_name"] == "剑照山河"
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


def test_映射换轨_剧情锚剥到证据列():
    seed = _run(_seed([{
        "name": "锚哥", "genre": "灵异志怪", "persona": "守钟人，装疯半生。",
        "dossier": {"plot": "装傻吃不明之物、被制服后揭真相。（第159章）", "background": "散打教练出身"},
        "src_novel_name": "13路末班车",
    }]))

    async def _go():
        async with async_session() as db:
            from kb.migrate_library import migrate_character_library

            await migrate_character_library(db, user_id=seed["uid"])
            return (
                await db.execute(KbEntry.__table__.select().where(KbEntry.user_id == seed["uid"]))
            ).mappings().all()

    rows = _run(_go())
    assert len(rows) == 1
    e = rows[0]
    payload = json.loads(e["payload_json"])
    # 锚换轨：证据列＝章，payload.plot＝净文；小说名归专列
    assert e["evidence"] == "第159章"
    assert payload["plot"] == "装傻吃不明之物、被制服后揭真相。"
    assert e["src_novel_name"] == "13路末班车"
    assert payload["background"] == "散打教练出身"  # 其余格零变动


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


# ─── 触达自迁一次性迁移（c-kb-library-once-migration）──────


def test_触达自迁_角色库读面首调即搬入():
    seed = _run(_seed([{"name": "钱七", "genre": "武侠"}, {"name": "孙八", "genre": "都市"}]))

    async def _go():
        from library.service import list_cards

        async with async_session() as db:
            r = await list_cards(db, user_id=seed["uid"])
            rows = (
                await db.execute(KbEntry.__table__.select().where(KbEntry.user_id == seed["uid"]))
            ).mappings().all()
            return r, rows

    r, rows = _run(_go())
    assert r["count"] == 2
    assert len(rows) == 2
    assert {e["src_kind"] for e in rows} == {"character_library_migration"}


def test_触达自迁_知识库条目端点同样生效():
    from fastapi.testclient import TestClient

    from auth_local.middleware import get_current_user
    from main import app

    seed = _run(_seed([{"name": "周九", "genre": "武侠"}]))
    app.dependency_overrides[get_current_user] = lambda: {"id": seed["uid"]}
    try:
        with TestClient(app) as c:
            r = c.get("/api/kb/entries", params={"concept": "角色设定"})
            assert r.status_code == 200
            items = r.json()["data"]["entries"]
            assert len(items) == 1
            assert items[0]["src_kind"] == "character_library_migration"
            assert items[0]["title"] == "周九"
    finally:
        app.dependency_overrides.clear()


def test_二次触达自熄_零重复():
    seed = _run(_seed([{"name": "吴十", "genre": "都市"}]))

    async def _go():
        from library.service import list_cards

        async with async_session() as db:
            await list_cards(db, user_id=seed["uid"])
            await list_cards(db, user_id=seed["uid"])
            rows = (
                await db.execute(KbEntry.__table__.select().where(KbEntry.user_id == seed["uid"]))
            ).mappings().all()
            return rows

    rows = _run(_go())
    assert len(rows) == 1  # 再触达零副本


def test_软删迁移卡再触达不复活():
    seed = _run(_seed([{"name": "郑一", "genre": "武侠"}]))

    async def _go():
        from library.service import list_cards

        async with async_session() as db:
            await list_cards(db, user_id=seed["uid"])
            # 作家在知识库删掉这张迁移卡（软删）
            await db.execute(
                KbEntry.__table__.update()
                .where(KbEntry.user_id == seed["uid"])
                .values(status="deleted")
            )
            await db.commit()
        # 再触达：快路/存在性检查都不许复活软删行
        async with async_session() as db:
            r = await list_cards(db, user_id=seed["uid"])
            rows = (
                await db.execute(KbEntry.__table__.select().where(KbEntry.user_id == seed["uid"]))
            ).mappings().all()
            return r, rows

    r, rows = _run(_go())
    assert r["count"] == 0
    assert len(rows) == 1 and rows[0]["status"] == "deleted"


def test_无存量账号零写入():
    seed = _run(_seed([]))  # 建号但不建 legacy 卡

    async def _go():
        from library.service import list_cards

        async with async_session() as db:
            r = await list_cards(db, user_id=seed["uid"])
            rows = (
                await db.execute(KbEntry.__table__.select().where(KbEntry.user_id == seed["uid"]))
            ).mappings().all()
            return r, rows

    r, rows = _run(_go())
    assert r == {"count": 0, "items": []}
    assert rows == []  # 点查即返，零写入


def test_迁移失败_读面降级不红():
    seed = _run(_seed([{"name": "王二", "genre": "武侠"}]))

    async def _go():
        from library.service import list_cards

        async with async_session() as db:
            return await list_cards(db, user_id=seed["uid"])

    import kb.migrate_library as mig

    def _boom(db, *, user_id):
        raise RuntimeError("迁移炸了")

    real = mig.migrate_character_library
    mig.migrate_character_library = _boom
    try:
        r = _run(_go())  # 不抛＝降级成立
    finally:
        mig.migrate_character_library = real
    assert r == {"count": 0, "items": []}


# ─── 证据列存量自愈（c-kb-char-evidence：老迁移把小说名写进证据列）──────


def _seed_kb_rows(uid: str, specs: list[dict]) -> None:
    async def _go():
        async with async_session() as db:
            for s in specs:
                db.add(KbEntry(
                    id=str(uuid.uuid4()), user_id=uid,
                    genre=s.get("genre", ""), concept=s["concept"],
                    concept_id=f"{s.get('genre', '')}:{s['concept']}",
                    title=s["title"],
                    payload_json=json.dumps(s["payload"], ensure_ascii=False),
                    instruction="x。", when_json="{}",
                    evidence=s["evidence"],
                    src_kind="character_library_migration",
                    src_ref="character_library", src_key=str(uuid.uuid4()),
                    src_novel_name=s["src_novel_name"],
                ))
            await db.commit()

    _run(_go())


def test_证据自愈_病形换轨_自熄():
    uid = f"kbrep-{uuid.uuid4().hex[:8]}"
    _seed_kb_rows(uid, [
        # 病形＋有锚：锚换轨成证据，plot 落净文
        {"concept": "角色设定", "title": "甲",
         "payload": {"archetype": "甲", "plot": "中期反派。（第45章）", "background": "山匪"},
         "evidence": "剑照山河", "src_novel_name": "剑照山河"},
        # 病形＋无锚：只清空证据（证据列不该住小说名）
        {"concept": "角色设定", "title": "乙",
         "payload": {"archetype": "乙", "plot": "无锚条目"},
         "evidence": "剑照山河", "src_novel_name": "剑照山河"},
        # 健康条目（新映射形状）：不动
        {"concept": "角色设定", "title": "丙",
         "payload": {"archetype": "丙", "plot": "健康。（第7章）"},
         "evidence": "第7章", "src_novel_name": "剑照山河"},
        # 非角色概念：不动（concept 过滤）
        {"concept": "手法", "genre": "武侠", "title": "丁",
         "payload": {"instruction": "打压后反转"},
         "evidence": "剑照山河", "src_novel_name": "剑照山河"},
    ])

    async def _go():
        async with async_session() as db:
            from kb.migrate_library import repair_character_evidence

            n1 = await repair_character_evidence(db, user_id=uid)
            n2 = await repair_character_evidence(db, user_id=uid)  # 自熄
            rows = (
                await db.execute(KbEntry.__table__.select().where(KbEntry.user_id == uid))
            ).mappings().all()
            return n1, n2, {r["title"]: r for r in rows}

    n1, n2, by_title = _run(_go())
    assert n1 == 2 and n2 == 0
    jia = json.loads(by_title["甲"]["payload_json"])
    assert by_title["甲"]["evidence"] == "第45章"
    assert jia["plot"] == "中期反派。" and jia["background"] == "山匪"  # 其余格零变动
    assert by_title["乙"]["evidence"] == ""
    assert json.loads(by_title["乙"]["payload_json"])["plot"] == "无锚条目"
    assert by_title["丙"]["evidence"] == "第7章"
    assert by_title["丁"]["evidence"] == "剑照山河"


def test_证据自愈_读面触达即修():
    uid = f"kbrep-{uuid.uuid4().hex[:8]}"
    _seed_kb_rows(uid, [
        {"concept": "角色设定", "title": "甲",
         "payload": {"archetype": "甲", "plot": "装傻半生。（第11章）"},
         "evidence": "13路末班车", "src_novel_name": "13路末班车"},
    ])

    async def _go():
        from library.service import list_cards

        async with async_session() as db:
            await list_cards(db, user_id=uid)  # 读面触达：自愈挂点在 ensure_legacy_migrated 前段
            rows = (
                await db.execute(KbEntry.__table__.select().where(KbEntry.user_id == uid))
            ).mappings().all()
            return rows

    rows = _run(_go())
    assert len(rows) == 1
    assert rows[0]["evidence"] == "第11章"
