"""拆书版本收敛测试（c-kb-collect-dims）：同书以全本为准重收＋四维扩收。

钉的口径：
- 试拆版素材/实例退役，canonical（章数最大）重收为唯一版本；
- 重收走现行四维映射——文风/文笔/手法/世界素材入库并经总结转实例；
- 同题材他书共用的知识点不被单书拆除误删；
- app_meta 标记幂等：二跑零改写。
"""

import asyncio
import json
import uuid

from sqlalchemy import text as _t

from db import async_session
from kb.version_reconcile import reconcile_deconstruct_versions
from models.deconstruct import DeconstructJob
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _mk(tag: str) -> str:
    return f"kbvr-{tag}-{uuid.uuid4().hex[:8]}"


async def _seed_user(uid: str):
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="版本收敛钉"))
        await db.commit()


def _products(chars: list[dict], *, style_rule=None, technique=None) -> dict:
    p: dict = {
        "genre": {"file": "genre.json", "data": {"genre": "都市"}},
        "characters": {"file": "characters.json", "data": {"characters": chars}},
    }
    if style_rule:
        p["style"] = {"file": "style.json", "data": {"role": "第三人称限知", "rules": [style_rule]}}
    if technique:
        p["techniques"] = {"file": "techniques.json", "data": {"techniques": [technique]}}
    return p


async def _mk_job(uid: str, book: str, chapters: int, products: dict) -> str:
    jid = uuid.uuid4().hex
    async with async_session() as db:
        db.add(DeconstructJob(
            id=jid, user_id=uid, status="completed", queue_seq=0,
            source_name=f"{book}.txt", source_size=1000, source_path="", encoding="",
            book_name=book, total_chars=1000, chapter_count=chapters, volume_count=1,
            parse_warnings_json="[]", api_config_id="", ai_model="test", mode="smart",
            selected_chapters_json="[]", rhythm_json="{}", selected_dims_json="[]",
            dims_json="{}", products_json=json.dumps(products, ensure_ascii=False),
            error_json="{}",
        ))
        await db.commit()
    return jid


async def _collect(uid: str, jid: str):
    from kb.deconstruct_import import collect_task_to_kb
    async with async_session() as db:
        task = await db.get(DeconstructJob, jid)
        return await collect_task_to_kb(db, uid, task)


async def _counts(uid: str) -> dict:
    async with async_session() as db:
        mats = (await db.execute(_t(
            "SELECT COUNT(*) FROM kb_entries WHERE user_id=:u AND origin='material' AND status='active'"), {"u": uid})).scalar()
        insts = (await db.execute(_t(
            "SELECT COUNT(*) FROM kb_knowledge_instances i JOIN kb_entries e ON e.id=i.knowledge_id "
            "WHERE e.user_id=:u"), {"u": uid})).scalar()
        dims = dict((await db.execute(_t(
            "SELECT e.concept, COUNT(*) FROM kb_entries e WHERE user_id=:u AND e.origin='material' "
            "AND e.status='active' GROUP BY e.concept"), {"u": uid})).fetchall())
        return {"mats": mats, "insts": insts, "dims": dims}


class TestReconcile:
    def test_试拆退役_全本为准_四维重收_幂等(self):
        uid = _mk("main")
        _run(_seed_user(uid))
        old_char = {"name": "旧角色", "role": "配角", "persona": "试拆版独有角色。", "gender": "男",
                    "background": "b", "plot": "p", "confidence": "high"}
        new_chars = [
            {"name": "李耀", "role": "主角", "persona": "全本主角。", "gender": "男",
             "background": "b", "plot": "p", "confidence": "high"},
            {"name": "六叔", "role": "反派", "persona": "全本反派。", "gender": "男",
             "background": "b", "plot": "p", "confidence": "high"},
        ]
        style_rule = {"name": "战斗短句", "how": "战斗场面短句连发加拟声词。", "confidence": "high", "evidence_ch": "第7章"}
        technique = {"name": "不可靠叙述开篇", "emotion_chain": "好奇→怀疑",
                     "repro_steps": ["先立异象", "再自我否认"], "evidence_ch": "第1章", "confidence": "high"}
        # 试拆（30 章，旧版只收角色）先收；全本（100 章，四维）不手动收——由收敛重收
        old_job = _run(_mk_job(uid, "斩神", 30, _products([old_char])))
        _run(_collect(uid, old_job))
        _run(_mk_job(uid, "斩神", 100, _products(new_chars, style_rule=style_rule, technique=technique)))

        before = _run(_counts(uid))
        assert before["mats"] == 1 and before["dims"].get("角色设定") == 1, before

        async def _go():
            async with async_session() as db:
                from kb.summarize import run_summarize
                await run_summarize(db, user_id=uid, genre="都市", trigger="manual")
        _run(_go())  # 试拆版先总结（旧实例在库）

        r = _run(reconcile_deconstruct_versions(user_id=uid))
        assert r.get("斩神") == "rebuilt", r

        after = _run(_counts(uid))
        # 四维素材经总结归档 → active 素材清零；实例来自全本（角色+文风规则+手法）
        assert after["mats"] == 0, f"重收后素材应全部归档：{after}"

        async def _inst_names():
            async with async_session() as db:
                rows = (await db.execute(_t(
                    "SELECT i.text FROM kb_knowledge_instances i JOIN kb_entries e ON e.id=i.knowledge_id "
                    "WHERE e.user_id=:u"), {"u": uid})).scalars().all()
                return rows
        texts = _run(_inst_names())
        assert not any("旧角色" in t for t in texts), "试拆版角色必须退役"
        assert any("李耀" in t or "全本主角" in t for t in texts), "全本角色在位"
        assert any("战斗短句" in t for t in texts), "文风规则转实例"
        assert any("不可靠叙述" in t for t in texts), "手法转实例"

        # 幂等：二跑 current 零改写
        r2 = _run(reconcile_deconstruct_versions(user_id=uid))
        assert r2.get("斩神") == "current", r2
        assert _run(_counts(uid)) == after

    def test_共用知识点_单书拆除不误删(self):
        uid = _mk("shared")
        _run(_seed_user(uid))
        char_a = {"name": "书甲配角", "role": "配角", "persona": "甲书角色。", "gender": "女",
                  "background": "b", "plot": "p", "confidence": "high"}
        char_b = {"name": "书乙配角", "role": "配角", "persona": "乙书角色。", "gender": "男",
                  "background": "b", "plot": "p", "confidence": "high"}
        ja = _run(_mk_job(uid, "书甲", 50, _products([char_a])))
        jb = _run(_mk_job(uid, "书乙", 60, _products([char_b])))
        _run(_collect(uid, ja))
        _run(_collect(uid, jb))

        async def _sum():
            async with async_session() as db:
                from kb.summarize import run_summarize
                await run_summarize(db, user_id=uid, genre="都市", trigger="manual")
        _run(_sum())

        r = _run(reconcile_deconstruct_versions(user_id=uid))
        assert r.get("书甲") == "rebuilt" and r.get("书乙") == "rebuilt", r

        async def _kp_instances():
            async with async_session() as db:
                rows = (await db.execute(_t(
                    "SELECT e.title, COUNT(i.id) FROM kb_entries e "
                    "LEFT JOIN kb_knowledge_instances i ON i.knowledge_id=e.id "
                    "WHERE e.user_id=:u AND e.origin='summary' GROUP BY e.title"), {"u": uid})).fetchall()
                return dict(rows)
        kps = _run(_kp_instances())
        assert kps.get("配角", 0) == 2, f"两书共用配角知识点、实例各一：{kps}"
