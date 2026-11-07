"""存量数据自愈测试（2026-11-07 走查实锤）：题材双写法归一＋章锚剥除。

病灶钉：
- 题材双写法——「灵异志怪」35 条 ↔ 目录「志怪/民俗灵异」分家（老角色库录入漂移、
  迁移镜像照原样搬）；归一须连 concept_id（{genre}:{concept}）与物化 genre 标签。
- 章锚——拆书 LLM 产物把「（第N章…）」带进 payload 字段（鬼面王案：aliases
  简单形＋plot 嵌套形），条目三源自愈（#1019）不覆盖 summarize 转生链与已归档素材。
"""

import asyncio
import json
import uuid

from sqlalchemy import text as _t

from db import async_session
from kb.migrate_library import (
    backfill_instance_names,
    ensure_legacy_migrated,
    normalize_legacy_genres,
    purge_instances_on_materials,
    repair_chapter_anchors,
)
from kb.summarize import run_summarize
from models.kb import KbEntry, KbEntryTag, KbKnowledgeInstance
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _mk(tag: str) -> str:
    return f"kbdh-{tag}-{uuid.uuid4().hex[:8]}"


async def _seed_user(uid: str):
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="自愈钉"))
        await db.commit()


async def _mk_entry(uid: str, *, genre: str, concept: str = "角色设定",
                    title: str = "", origin: str = "manual",
                    payload: dict | None = None) -> str:
    eid = uuid.uuid4().hex
    async with async_session() as db:
        db.add(KbEntry(
            id=eid, user_id=uid, genre=genre, concept=concept,
            concept_id=f"{genre}:{concept}", title=title or f"条目-{eid[:6]}",
            instruction="写法说明。", payload_json=json.dumps(payload or {}, ensure_ascii=False),
            origin=origin, src_kind="character_library_migration" if origin == "manual" else "deconstruct",
        ))
        await db.commit()
        return eid


async def _mk_tag(uid: str, entry_id: str, dim: str, value: str):
    async with async_session() as db:
        db.add(KbEntryTag(entry_id=entry_id, user_id=uid, dim=dim, value=value))
        await db.commit()


class TestNormalizeLegacyGenres:
    def test_词表外写法归一_连concept_id与genre标签(self):
        uid = _mk("gn")
        _run(_seed_user(uid))
        drift_id = _run(_mk_entry(uid, genre="灵异志怪"))
        themed_id = _run(_mk_entry(uid, genre="志怪/民俗灵异"))
        alien_id = _run(_mk_entry(uid, genre="玛雅文明"))  # normalize 不动的词
        _run(_mk_tag(uid, drift_id, "genre", "灵异志怪"))

        async def _go():
            return await normalize_legacy_genres(user_id=uid)
        fixed = _run(_go())
        assert fixed == 1, f"只应改写漂移词一条：{fixed}"

        async def _check():
            async with async_session() as db:
                rows = (await db.execute(_t(
                    "SELECT genre, concept_id FROM kb_entries WHERE user_id=:u ORDER BY genre"),
                    {"u": uid})).mappings().all()
                tag = (await db.execute(_t(
                    "SELECT value FROM kb_entry_tags WHERE user_id=:u AND dim='genre'"),
                    {"u": uid})).scalar_one()
                return rows, tag
        _rows, tag = _run(_check())
        by_id = {}
        async def _by_id():
            async with async_session() as db:
                for eid in (drift_id, themed_id, alien_id):
                    e = await db.get(KbEntry, eid)
                    by_id[eid] = (e.genre, e.concept_id)
        _run(_by_id())
        assert by_id[drift_id] == ("志怪/民俗灵异", "志怪/民俗灵异:角色设定"), by_id[drift_id]
        assert by_id[themed_id] == ("志怪/民俗灵异", "志怪/民俗灵异:角色设定")
        assert by_id[alien_id] == ("玛雅文明", "玛雅文明:角色设定"), "归不动的词不硬改"
        assert tag == "志怪/民俗灵异", "物化 genre 标签同步改写"

    def test_幂等自熄_二跑零改写(self):
        uid = _mk("gn2")
        _run(_seed_user(uid))
        _run(_mk_entry(uid, genre="灵异志怪"))
        _run(normalize_legacy_genres_hack(uid))

        async def _go():
            return await normalize_legacy_genres(user_id=uid)
        assert _run(_go()) == 0


async def normalize_legacy_genres_hack(uid: str):
    return await normalize_legacy_genres(user_id=uid)


class TestRepairChapterAnchors:
    def test_实例与素材双洗_嵌套形剥净_泛指保留(self):
        uid = _mk("anc")
        _run(_seed_user(uid))
        kid = _run(_mk_entry(uid, genre="都市", title="反派"))
        dirty_fields = {
            "persona": "体型庞大、凶残狡诈。",
            "aliases": "['鬼面人（第26章）', '怪物（泛指）']",
            "plot": "断头不死，鬼面消融凝固（第6章（提及逃脱）/第24章（正面出场））",
        }
        iid = uuid.uuid4().hex

        async def _mk_inst():
            async with async_session() as db:
                db.add(KbKnowledgeInstance(
                    id=iid, knowledge_id=kid, text="实例句。", fields_json=json.dumps(dirty_fields, ensure_ascii=False),
                ))
                await db.commit()
        _run(_mk_inst())
        mat_id = _run(_mk_entry(
            uid, genre="都市", origin="material",
            payload={"aliases": ["鬼面人（第26章）", "怪物（泛指）"],
                     "plot": "断头不死，鬼面消融凝固（第6章（提及逃脱）/第24章（正面出场））"},
        ))
        # 物化投影同病（评审 P3）：payload 剥了、alias 标签不剥＝两套账
        _run(_mk_tag(uid, mat_id, "alias", "鬼面人（第26章）"))
        _run(_mk_tag(uid, mat_id, "alias", "无头鬼面王（第28章）"))
        _run(_mk_tag(uid, mat_id, "alias", "怪物（泛指）"))

        async def _go():
            return await repair_chapter_anchors(user_id=uid)
        fixed = _run(_go())
        assert fixed == 4, f"实例＋素材＋两条锚标签都该洗：{fixed}"

        async def _check():
            async with async_session() as db:
                inst = await db.get(KbKnowledgeInstance, iid)
                mat = await db.get(KbEntry, mat_id)
                return json.loads(inst.fields_json), json.loads(mat.payload_json)
        fields, payload = _run(_check())
        assert fields["aliases"] == "['鬼面人', '怪物（泛指）']", fields["aliases"]
        assert fields["plot"] == "断头不死，鬼面消融凝固"
        assert fields["persona"] == "体型庞大、凶残狡诈。"
        assert payload["aliases"] == ["鬼面人", "怪物（泛指）"], "列表逐项剥、泛指保留"
        assert payload["plot"] == "断头不死，鬼面消融凝固"

        async def _tags():
            async with async_session() as db:
                return (await db.execute(_t(
                    "SELECT value FROM kb_entry_tags WHERE user_id=:u AND dim='alias' ORDER BY value"),
                    {"u": uid})).scalars().all()
        assert sorted(_run(_tags())) == sorted(["鬼面人", "怪物（泛指）", "无头鬼面王"]), \
            "标签投影同步剥锚"

    def test_素材自指实例清掉_正常实例保留(self):
        uid = _mk("purge")
        _run(_seed_user(uid))
        kid = _run(_mk_entry(uid, genre="都市", title="反派"))          # 正常知识
        mat_id = _run(_mk_entry(uid, genre="都市", origin="material"))  # 素材行
        good_iid, bad_iid = uuid.uuid4().hex, uuid.uuid4().hex

        async def _mk_insts():
            async with async_session() as db:
                db.add(KbKnowledgeInstance(id=good_iid, knowledge_id=kid, text="正常实例。"))
                db.add(KbKnowledgeInstance(id=bad_iid, knowledge_id=mat_id, text="自指垃圾。"))
                await db.commit()
        _run(_mk_insts())

        async def _go():
            return await purge_instances_on_materials(user_id=uid)
        assert _run(_go()) == 1

        async def _check():
            async with async_session() as db:
                return (await db.get(KbKnowledgeInstance, good_iid)) is not None, \
                       (await db.get(KbKnowledgeInstance, bad_iid)) is None
        good_ok, bad_gone = _run(_check())
        assert good_ok and bad_gone

    def test_角色实例补名字_按instruction回查素材(self):
        uid = _mk("name")
        _run(_seed_user(uid))
        mat_id = _run(_mk_entry(
            uid, genre="志怪/民俗灵异", origin="material",
            payload={"archetype": "何沉舟", "persona": "嘴贫胆小却重情义。"},
        ))
        async def _archive_mat():
            async with async_session() as db:
                m = await db.get(KbEntry, mat_id)
                m.instruction = "嘴贫胆小却重情义。"  # summarize 转生时 text=素材 instruction
                m.status = "archived"  # summarize 归档口径
                await db.commit()
        _run(_archive_mat())
        iid = uuid.uuid4().hex

        async def _mk_inst():
            async with async_session() as db:
                db.add(KbKnowledgeInstance(
                    id=iid, knowledge_id=mat_id, text="嘴贫胆小却重情义。",  # text=素材 instruction 原样
                    fields_json=json.dumps({"persona": "嘴贫胆小却重情义。"}),  # 无 archetype=病形
                ))
                await db.commit()
        _run(_mk_inst())

        async def _go():
            async with async_session() as db:
                return await backfill_instance_names(user_id=uid)
        assert _run(_go()) == 1

        async def _check():
            async with async_session() as db:
                i = await db.get(KbKnowledgeInstance, iid)
                return json.loads(i.fields_json)
        fields = _run(_check())
        assert fields["archetype"] == "何沉舟", "名字回填进字段"
        assert fields["persona"] == "嘴贫胆小却重情义。"

    def test_无病形自熄(self):
        uid = _mk("anc2")
        _run(_seed_user(uid))
        _run(_mk_entry(uid, genre="都市", origin="material", payload={"plot": "雨夜大战。"}))

        async def _go():
            return await repair_chapter_anchors(user_id=uid)
        assert _run(_go()) == 0


class TestEnsureHook:
    def test_读面钩两修齐跑_独立于迁移短路(self):
        uid = _mk("hook")
        _run(_seed_user(uid))
        eid = _run(_mk_entry(uid, genre="灵异志怪"))  # 无 legacy 行也照跑（独立于 stamped 短路）

        mat_id = _run(_mk_entry(uid, genre="灵异志怪", origin="material"))
        bad_iid = uuid.uuid4().hex

        async def _mk_bad():
            async with async_session() as db:
                db.add(KbKnowledgeInstance(id=bad_iid, knowledge_id=mat_id, text="自指垃圾。"))
                await db.commit()
        _run(_mk_bad())

        async def _go():
            async with async_session() as db:
                await ensure_legacy_migrated(db, user_id=uid)  # 钩自带 db 参（迁移仍用调用方会话）
                e = await db.get(KbEntry, eid)
                bad = await db.get(KbKnowledgeInstance, bad_iid)
                return e.genre, bad is None
        genre, bad_gone = _run(_go())
        assert genre == "志怪/民俗灵异" and bad_gone, "归一＋自指清理同钩齐跑"


class TestSummarize接链:
    def test_转生实例字段不再带锚(self):
        uid = _mk("chain")
        _run(_seed_user(uid))
        mat_id = _run(_mk_entry(uid, genre="都市", origin="material"))

        async def _seed_payload():
            async with async_session() as db:
                m = await db.get(KbEntry, mat_id)
                m.payload_json = json.dumps({
                    "archetype": "鬼面王",
                    "aliases": ["鬼面人（第26章）", "（第28章）", "怪物（泛指）"],
                    "plot": "鬼面消融凝固（第6章（提及逃脱）/第24章（正面出场））",
                }, ensure_ascii=False)
                await db.commit()
        _run(_seed_payload())

        async def _go():
            async with async_session() as db:
                return await run_summarize(db, user_id=uid, genre="都市", trigger="manual")
        _r, err = _run(_go())
        assert err == "", f"总结应跑通：{err}"

        async def _check():
            async with async_session() as db:
                row = (await db.execute(_t(
                    "SELECT fields_json FROM kb_knowledge_instances i "
                    "JOIN kb_entries e ON e.id = i.knowledge_id "
                    "WHERE e.user_id=:u LIMIT 1"), {"u": uid})).scalar_one()
                return json.loads(row)
        fields = _run(_check())
        assert "（第" not in json.dumps(fields, ensure_ascii=False), fields
        assert fields["aliases"] == '["鬼面人", "怪物（泛指）"]', fields["aliases"]
        assert "（第28章）" not in fields["aliases"], "整项纯锚剥空项不落（评审 P3）"
        assert fields["plot"] == "鬼面消融凝固"
