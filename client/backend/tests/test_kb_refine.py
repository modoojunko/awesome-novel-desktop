"""知识提炼测试（c-kb-refine）：其他暂存原始材料 → 归类进树／长新节点。

钉的口径（boss 2026-11-08）：
- 未命中树的拆书材料落「其他」节点（不再临时造知识点）；
- 提炼挂已有知识点：按目标节点模板重映射落格＋LLM 补缺口格；
- 提议新节点：自动建行挂树（先有节点后有实例）、实例按提案格归位；
- 护栏：每轮新节点 ≤3、LLM 挂了不挪任何东西、单飞 running。
"""

import asyncio
import json
import uuid
from datetime import datetime

from sqlalchemy import text as _t

import kb.refine as refine_mod
from db import async_session
from kb.refine import run_refine
from models.kb import KbEntry, KbKnowledgeInstance
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _mk(tag: str) -> str:
    return f"kbref-{tag}-{uuid.uuid4().hex[:8]}"


async def _seed_user(uid: str):
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="提炼钉"))
        await db.commit()


async def _seed_staged(uid: str, genre: str, rows: list[dict]) -> str:
    """直建「其他」节点行＋其下原始实例（fields_json＝拆书产物原始键）。"""
    async with async_session() as db:
        other = KbEntry(
            id=uuid.uuid4().hex, user_id=uid, genre=genre, concept="", concept_id=f"{genre}:",
            title="其他",
            definition=f"{genre}·其他——拆书直接输出的原始材料暂存。",
            payload_json="{}", instruction="", origin="summary", status="active",
            version=1, parent_id="",
        )
        db.add(other)
        for i, r in enumerate(rows):
            db.add(KbKnowledgeInstance(
                knowledge_id=other.id,
                text=r["text"],
                source_kind="拆书",
                source_novel=r.get("novel", "测试书"),
                source_chapter=r.get("ch", ""),
                quote=r.get("quote", ""),
                fields_json=json.dumps(r.get("fields", {}), ensure_ascii=False),
                sort=i,
            ))
        await db.commit()
        return other.id


async def _kp_rows(uid: str) -> list[dict]:
    async with async_session() as db:
        rows = (await db.execute(_t(
            "SELECT e.title, e.parent_id, e.schema_json, e.concept FROM kb_entries e "
            "WHERE e.user_id=:u AND e.origin='summary'"), {"u": uid})).mappings().all()
        return [dict(r) for r in rows]


class Test其他暂存:
    def test_未命中树的拆书材料落其他(self):
        """文风 sample 槽位树上没有 → 不临时造知识点，落「其他」。"""
        uid = _mk("stage")
        _run(_seed_user(uid))

        async def _seed():
            async with async_session() as db:
                db.add(KbEntry(
                    id=uuid.uuid4().hex, user_id=uid, genre="都市", concept="文风",
                    concept_id="都市:文风", title="示范素材",
                    payload_json=json.dumps({"slot": "sample", "sample": "他推门进来，风铃响了一声。"},
                                            ensure_ascii=False),
                    instruction="他推门进来，风铃响了一声。",
                    origin="material", status="active", rev=1,
                    src_kind="deconstruct", src_ref="j1", src_key="s0",
                ))
                await db.commit()
        _run(_seed())

        from kb.summarize import run_summarize

        async def _go():
            async with async_session() as db:
                return await run_summarize(db, user_id=uid, genre="都市", trigger="manual")
        r, err = _run(_go())
        assert err == "" and r["knowledge"] >= 1, f"{r} {err}"

        async def _check():
            async with async_session() as db:
                kps = (await db.execute(_t(
                    "SELECT title, concept FROM kb_entries WHERE user_id=:u AND origin='summary' "
                    "AND concept=''"), {"u": uid})).mappings().all()
                inst = (await db.execute(_t(
                    "SELECT i.text FROM kb_knowledge_instances i JOIN kb_entries e ON e.id=i.knowledge_id "
                    "WHERE e.user_id=:u AND e.title='其他'"), {"u": uid})).mappings().all()
                return kps, inst
        kps, inst = _run(_check())
        titles = {k["title"] for k in kps}
        assert titles == {"写作知识", "其他"}, kps
        assert len(inst) == 1 and "风铃" in inst[0]["text"], inst


class TestRefine:
    def _seed(self, uid, genre="都市"):
        return _run(_seed_staged(uid, genre, [
            {"text": "擂台比武先立规矩再开打：裁判唱名、双方亮兵刃、观众押注。", "ch": "第3章",
             "fields": {"scene": "战斗", "confidence": "high"}},
            {"text": "主角以气御刀，刀气离体三尺斩断石柱。", "ch": "第9章",
             "fields": {"scene": "战斗", "confidence": "mid"}},
        ]))

    def test_挂已有知识点_模板重映射加LLM补格(self):
        uid = _mk("move")
        _run(_seed_user(uid))
        self._seed(uid)

        async def _fake_llm(user_id, genre, tree, items):
            assert "tech_finisher" in tree, "树清单要给到 LLM"
            return {"moves": [{"id": items[0].split("|")[0], "to": "tech_finisher",
                               "fields": {"情绪链": "蓄力—爆发—代价"}},
                              {"id": items[1].split("|")[0], "to": "tech_more",
                               "fields": {}}],
                    "new_nodes": []}

        orig = refine_mod._llm_refine
        refine_mod._llm_refine = _fake_llm
        try:
            async def _go():
                async with async_session() as db:
                    return await run_refine(db, user_id=uid, genre="都市", llm=True)
            r, err = _run(_go())
        finally:
            refine_mod._llm_refine = orig
        assert err == "" and r["moved"] == 2 and r["nodes_created"] == 0, (r, err)

        async def _check():
            async with async_session() as db:
                rows = (await db.execute(_t(
                    "SELECT e2.title AS kp, i.fields_json FROM kb_knowledge_instances i "
                    "JOIN kb_entries e2 ON e2.id=i.knowledge_id "
                    "WHERE e2.user_id=:u AND e2.concept='手法'"), {"u": uid})).mappings().all()
                return [dict(x) for x in rows]
        rows = _run(_check())
        by_kp = {r["kp"]: json.loads(r["fields_json"]) for r in rows}
        # 大招打法：模板映射（scene→适用场面、confidence→可信度）＋LLM 补情绪链
        assert by_kp["大招打法"]["适用场面"] == "战斗", by_kp
        assert by_kp["大招打法"]["可信度"] == "高", by_kp
        assert by_kp["大招打法"]["情绪链"] == "蓄力—爆发—代价", by_kp
        assert "更多场面打法" in by_kp, by_kp

    def test_提议新节点_自动挂树_实例按提案格归位(self):
        uid = _mk("newnode")
        _run(_seed_user(uid))
        self._seed(uid)

        async def _fake_llm(user_id, genre, tree, items):
            return {"moves": [{"id": items[0].split("|")[0], "to": "n1", "fields": {}}],
                    "new_nodes": [{
                        "key": "n1", "parent": "tech_fallback",
                        "title": "心理博弈打法", "definition": "对峙攻心、以言语压人的场面写法。",
                        "concept": "手法",
                        "fields": [{"name": "博弈点", "desc": "双方在争什么"},
                                   {"name": "可信度", "desc": "可信程度"}],
                        "instances": [items[0].split("|")[0]],
                    }]}

        orig = refine_mod._llm_refine
        refine_mod._llm_refine = _fake_llm
        try:
            async def _go():
                async with async_session() as db:
                    return await run_refine(db, user_id=uid, genre="都市", llm=True)
            r, err = _run(_go())
        finally:
            refine_mod._llm_refine = orig
        assert err == "" and r["nodes_created"] == 1 and r["moved"] == 1, (r, err)

        async def _check():
            async with async_session() as db:
                node = (await db.execute(_t(
                    "SELECT e.title, e.definition, e.schema_json, p.title AS parent "
                    "FROM kb_entries e LEFT JOIN kb_entries p ON p.id=e.parent_id "
                    "WHERE e.user_id=:u AND e.title='心理博弈打法'"), {"u": uid})).mappings().first()
                inst = (await db.execute(_t(
                    "SELECT i.fields_json, e2.title AS kp FROM kb_knowledge_instances i "
                    "JOIN kb_entries e2 ON e2.id=i.knowledge_id "
                    "WHERE e2.title='心理博弈打法' AND e2.user_id=:u"), {"u": uid})).mappings().first()
                return dict(node) if node else None, dict(inst) if inst else None
        node, inst = _run(_check())
        assert node["parent"] == "场面打法", node
        assert "对峙攻心" in node["definition"], node
        schema = json.loads(node["schema_json"])
        assert [s["name"] for s in schema] == ["博弈点", "可信度"], schema
        assert inst["kp"] == "心理博弈打法"
        fields = json.loads(inst["fields_json"])
        assert fields.get("博弈点") == "" or "博弈点" not in fields, fields  # LLM 没给就不硬填

    def test_护栏_每轮新节点最多三个(self):
        uid = _mk("cap")
        _run(_seed_user(uid))
        _run(_seed_staged(uid, "都市", [{"text": f"材料{i}", "fields": {}} for i in range(5)]))

        async def _fake_llm(user_id, genre, tree, items):
            return {"moves": [], "new_nodes": [
                {"key": f"n{i}", "parent": "tech_fallback", "title": f"打法{i}",
                 "definition": f"第{i}类打法。", "concept": "手法",
                 "fields": [{"name": "说明", "desc": "d"}], "instances": []}
                for i in range(5)
            ]}

        orig = refine_mod._llm_refine
        refine_mod._llm_refine = _fake_llm
        try:
            async def _go():
                async with async_session() as db:
                    return await run_refine(db, user_id=uid, genre="都市", llm=True)
            r, _err = _run(_go())
        finally:
            refine_mod._llm_refine = orig
        assert r["nodes_created"] == 3, r

    def test_LLM挂了_不挪任何东西(self):
        uid = _mk("fail")
        _run(_seed_user(uid))
        self._seed(uid)

        async def _fake_llm(user_id, genre, tree, items):
            raise RuntimeError("boom")

        orig = refine_mod._llm_refine
        refine_mod._llm_refine = _fake_llm
        try:
            async def _go():
                async with async_session() as db:
                    return await run_refine(db, user_id=uid, genre="都市", llm=True)
            r, err = _run(_go())
        finally:
            refine_mod._llm_refine = orig
        assert r is None and err.startswith("llm:"), (r, err)
        kps = _run(_kp_rows(uid))
        assert not any(k["title"] == "大招打法" for k in kps), kps

    def test_单飞_running(self):
        uid = _mk("lock")
        _run(_seed_user(uid))
        lock = refine_mod._user_lock(uid, "都市")

        async def _go():
            async with async_session() as db:
                return await run_refine(db, user_id=uid, genre="都市", llm=False)
        _run(lock.acquire())  # 真持有锁（asyncio.Lock.acquire 是协程）
        try:
            r, err = _run(_go())
            assert r is None and err == "running", (r, err)
        finally:
            lock.release()
        r2, err2 = _run(_go())  # 放锁后可跑
        assert err2 == "" and r2 is not None, (r2, err2)

    def test_llm关_留守不动(self):
        uid = _mk("nollm")
        _run(_seed_user(uid))
        self._seed(uid)

        async def _go():
            async with async_session() as db:
                return await run_refine(db, user_id=uid, genre="都市", llm=False)
        r, err = _run(_go())
        assert err == "" and r["kept"] == 2 and r["moved"] == 0, (r, err)


class TestRefineTask:
    """知识提炼任务（原型定稿）：任务归任务清单，提炼＋关系梳理一炉。"""

    def test_建任务_编排完成_结果账与时间线(self):
        from kb.refine_task import (
            create_task,
            delete_task,
            execute_task,
            get_task,
            list_tasks,
        )

        uid = _mk("task")
        _run(_seed_user(uid))
        _run(_seed_staged(uid, "都市", [
            {"text": "擂台比武先立规矩再开打：裁判唱名、双方亮兵刃、观众押注。", "ch": "第3章",
             "fields": {"scene": "战斗", "confidence": "high"}},
            {"text": "主角以气御刀，刀气离体三尺斩断石柱。", "ch": "第9章",
             "fields": {"scene": "战斗", "confidence": "mid"}},
        ]))

        async def _fake_llm(user_id, genre, tree, items):
            return {"moves": [{"id": items[0].split("|")[0], "to": "tech_finisher", "fields": {}}],
                    "new_nodes": [{"key": "n1", "parent": "tech_fallback", "title": "心理博弈打法",
                                   "definition": "对峙攻心的场面写法。", "concept": "手法",
                                   "fields": [{"name": "博弈点", "desc": "双方在争什么"}],
                                   "instances": []}]}

        orig = refine_mod._llm_refine
        refine_mod._llm_refine = _fake_llm
        # organize 的 LLM 候选关掉（任务编排里关系走确定性路径即可）
        import kb.organize as org_mod
        orig_cand = org_mod._llm_candidates
        org_mod._llm_candidates = lambda *a, **k: ([], None)
        try:
            async def _go():
                async with async_session() as db:
                    task, err = await create_task(db, user_id=uid, genre="都市")
                    return task, err
            task, err = _run(_go())
            assert err == "" and task["status"] == "queued", (task, err)
            _run(execute_task(task["id"], user_id=uid, genre="都市"))

            async def _check():
                async with async_session() as db:
                    return await get_task(db, user_id=uid, task_id=task["id"])
            done = _run(_check())
        finally:
            refine_mod._llm_refine = orig
            org_mod._llm_candidates = orig_cand
        assert done["status"] == "completed", done
        assert done["result"]["moved"] == 1 and done["result"]["nodes_created"] == 1, done["result"]
        assert done["result"]["details"]["new_nodes"][0]["title"] == "心理博弈打法"
        assert done["result"]["details"]["new_nodes"][0]["parent_title"] == "场面打法"
        assert done["result"]["details"]["moves"][0]["to"] == "大招打法"
        keys = [s["key"] for s in done["timeline"]]
        assert keys == ["read", "classify", "grow", "relate", "done"], keys

        # 重复建任务被单飞拒（任务已 completed 不占running——可再建，验列表）
        async def _again():
            async with async_session() as db:
                _t2, e2 = await create_task(db, user_id=uid, genre="都市")
                rows = await list_tasks(db, user_id=uid)
                return e2, rows
        e2, rows = _run(_again())
        assert e2 == "" and len(rows) == 2, (e2, len(rows))
        # 删除：completed 可删
        async def _del():
            async with async_session() as db:
                return await delete_task(db, user_id=uid, task_id=task["id"])
        assert _run(_del()) == ""

    def test_重复建任务_运行中拒(self):
        from kb.refine_task import create_task, execute_task

        uid = _mk("taskbusy")
        _run(_seed_user(uid))
        async def _go():
            async with async_session() as db:
                task, err = await create_task(db, user_id=uid, genre="都市")
                return task, err
        task, err = _run(_go())
        assert err == ""
        # 摆一条暂存实例（让编排真走到 LLM）；LLM 挂 → 任务 failed（不挪任何东西）
        _run(_seed_staged(uid, "都市", [{"text": "擂台比武先立规矩再开打。", "ch": "第3章",
                                         "fields": {"scene": "战斗", "confidence": "high"}}]))
        orig = refine_mod._llm_refine
        async def _boom(*a, **k):
            raise RuntimeError("boom")
        refine_mod._llm_refine = _boom
        try:
            _run(execute_task(task["id"], user_id=uid, genre="都市"))
        finally:
            refine_mod._llm_refine = orig
        done = self._get_task(uid, task["id"])
        assert done["status"] == "failed" and "boom" in done["error"], done

    def _get_task(self, uid, tid):
        from kb.refine_task import get_task
        async def _go():
            async with async_session() as db:
                return await get_task(db, user_id=uid, task_id=tid)
        return _run(_go())


class TestRefineReview:
    """评审整改钉（2026-11-09）：instances 兜底/moves 去重/重启回收/ORM 镜像。"""

    def test_instances兜底_LLM只填汇总不填moves也归位(self):
        uid = _mk("fb")
        _run(_seed_user(uid))
        _run(_seed_staged(uid, "都市", [{"text": "对峙攻心：言语压人先夺势。", "ch": "第5章",
                                         "fields": {}}]))

        async def _fake_llm(user_id, genre, tree, items):
            iid = items[0].split("|")[0]
            # 守规矩 LLM：新节点提案只填 instances、不重复填 moves（契约语义）
            return {"moves": [],
                    "new_nodes": [{"key": "n1", "parent": "tech_fallback",
                                   "title": "心理博弈打法", "definition": "对峙攻心的场面写法。",
                                   "concept": "手法",
                                   "fields": [{"name": "博弈点", "desc": "双方在争什么"}],
                                   "instances": [iid]}]}

        orig = refine_mod._llm_refine
        refine_mod._llm_refine = _fake_llm
        try:
            async def _go():
                async with async_session() as db:
                    return await run_refine(db, user_id=uid, genre="都市", llm=True)
            r, _err = _run(_go())
        finally:
            refine_mod._llm_refine = orig
        assert _err == "" and r["moved"] == 1 and r["kept"] == 0, (r, _err)

        async def _check():
            async with async_session() as db:
                return (await db.execute(_t(
                    "SELECT i.fields_json FROM kb_knowledge_instances i "
                    "JOIN kb_entries e ON e.id=i.knowledge_id WHERE e.title='心理博弈打法' "
                    "AND e.user_id=:u"), {"u": uid})).mappings().all()
        rows = _run(_check())
        assert len(rows) == 1, rows

    def test_moves重复id只归一次_kept不为负(self):
        uid = _mk("dup")
        _run(_seed_user(uid))
        _run(_seed_staged(uid, "都市", [{"text": "擂台先立规矩再开打。", "ch": "第3章",
                                         "fields": {"scene": "战斗", "confidence": "high"}}]))

        async def _fake_llm(user_id, genre, tree, items):
            iid = items[0].split("|")[0]
            return {"moves": [{"id": iid, "to": "tech_finisher", "fields": {}},
                              {"id": iid, "to": "tech_more", "fields": {}}],
                    "new_nodes": []}

        orig = refine_mod._llm_refine
        refine_mod._llm_refine = _fake_llm
        try:
            async def _go():
                async with async_session() as db:
                    return await run_refine(db, user_id=uid, genre="都市", llm=True)
            r, _err = _run(_go())
        finally:
            refine_mod._llm_refine = orig
        assert r["moved"] == 1 and r["kept"] == 0, r

    def test_重启回收_queued_running全落failed_单飞解锁(self):
        from kb.refine_task import _set, create_task, sweep_stale_on_boot

        uid = _mk("sweep")
        _run(_seed_user(uid))
        async def _mk_task():
            async with async_session() as db:
                return await create_task(db, user_id=uid, genre="都市")
        task, err = _run(_mk_task())
        assert err == ""
        # 模拟重启前的 running
        async def _running():
            async with async_session() as db:
                await _set(db, task["id"], status="running", current_step="归类进树")
        _run(_running())

        n = _run(sweep_stale_on_boot())
        assert n >= 1, n
        async def _check():
            from kb.refine_task import get_task
            async with async_session() as db:
                return await get_task(db, user_id=uid, task_id=task["id"])
        done = _run(_check())
        assert done["status"] == "failed" and "重启" in done["error"], done
        # 单飞解锁：可以再建
        async def _again():
            async with async_session() as db:
                return await create_task(db, user_id=uid, genre="都市")
        t2, e2 = _run(_again())
        assert e2 == "" and t2 is not None, (e2, t2)

    def test_ORM镜像进metadata_迁移计划面认得(self):
        from db_lifecycle import compute_schema_fingerprint
        from models.kb import Base
        fp = compute_schema_fingerprint(Base.metadata)
        assert fp, fp
        assert "kb_refine_tasks" in Base.metadata.tables


class TestRefineReReview:
    """复检整改钉（2026-11-09）：fresh 库时间列非空＋碰撞映射。"""

    def test_fresh库建任务_created_at非空_排序可用(self):
        """ORM 镜像时间列 DateTime+func.now()——fresh 库 create_all 建表后
        INSERT 不含 created_at 也落数据库默认时间（复检 P2：恒空串排序 NaN）。"""
        from datetime import datetime

        from kb.refine_task import create_task, list_tasks

        uid = _mk("fresh")
        _run(_seed_user(uid))

        async def _mk_task():
            async with async_session() as db:
                t, err = await create_task(db, user_id=uid, genre="都市")
                return t, err
        task, err = _run(_mk_task())
        assert err == ""
        assert (task.get("created_at") or "").strip() != "", task  # 非空串
        # 可按时间排序（datetime 对象/ISO 串都能 parse）——不炸即过
        v = task.get("created_at")
        assert isinstance(v, (str, datetime)), v

    def test_key碰撞_第二提案实例挂改写后节点不误挂首个(self):
        uid = _mk("collide")
        _run(_seed_user(uid))
        _run(_seed_staged(uid, "都市", [
            {"text": "材料甲：蓄力三息再爆发。", "ch": "第1章", "fields": {}},
            {"text": "材料乙：借力打力卸劲。", "ch": "第2章", "fields": {}},
        ]))

        async def _fake_llm(user_id, genre, tree, items):
            # 两个提案都自编 n1（碰撞）——材料乙归第二个提案（改写后 n1x2）
            return {"moves": [],
                    "new_nodes": [
                        {"key": "n1", "parent": "tech_fallback", "title": "蓄力打法",
                         "definition": "先蓄后发的场面写法。", "concept": "手法",
                         "fields": [{"name": "蓄力拍", "desc": "d"}],
                         "instances": [items[0].split("|")[0]]},
                        {"key": "n1", "parent": "tech_fallback", "title": "卸劲打法",
                         "definition": "借力打力的场面写法。", "concept": "手法",
                         "fields": [{"name": "卸劲拍", "desc": "d"}],
                         "instances": [items[1].split("|")[0]]},
                    ]}

        orig = refine_mod._llm_refine
        refine_mod._llm_refine = _fake_llm
        try:
            async def _go():
                async with async_session() as db:
                    return await run_refine(db, user_id=uid, genre="都市", llm=True)
            r, _err = _run(_go())
        finally:
            refine_mod._llm_refine = orig
        assert r["moved"] == 2 and r["nodes_created"] == 2, r

        async def _check():
            async with async_session() as db:
                return (await db.execute(_t(
                    "SELECT e.title, i.text FROM kb_knowledge_instances i "
                    "JOIN kb_entries e ON e.id=i.knowledge_id "
                    "WHERE e.user_id=:u AND e.concept='手法'"), {"u": uid})).fetchall()
        rows = _run(_check())
        by_inst = {text: title for title, text in rows}
        assert by_inst.get("材料甲：蓄力三息再爆发。") == "蓄力打法", rows
        assert by_inst.get("材料乙：借力打力卸劲。") == "卸劲打法", rows  # 不误挂首个
