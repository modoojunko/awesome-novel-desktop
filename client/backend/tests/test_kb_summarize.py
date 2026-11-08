"""知识总结管线测试（c-kb-summarize 批A：素材态/过滤收口/删除；批B：管线）。"""

import asyncio
import json
import uuid

from sqlalchemy import select as sel
from sqlalchemy import text as _t

from db import async_session
from kb.service import create_entry, delete_entry, list_entries
from models.kb import KbEntry
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _mk(tag: str) -> str:
    return f"kbsm-{tag}-{uuid.uuid4().hex[:8]}"


async def _seed_user(uid: str):
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="总结钉"))
        await db.commit()




class TestMaterialEntry:
    """批A：手录落素材态。"""

    def _mk(self, tag):
        return f"kbsm-{tag}-{uuid.uuid4().hex[:8]}"

    def test_手录素材_不装载槽位_不物化标签(self):
        uid = self._mk("mat")
        _run(_seed_user(uid))

        async def _go():
            async with async_session() as db:
                entry, _gate, _err = await create_entry(
                    db, user_id=uid, genre="玄幻", concept="文风",
                    instruction="句子要短。", payload={}, as_material=True,
                )
                from models.kb import KbEntryTag
                tags = (await db.execute(sel(KbEntryTag).where(KbEntryTag.entry_id == entry.id))).scalars().all()
                return entry, tags
        entry, tags = _run(_go())
        assert entry.origin == "material"
        assert entry.payload_json == "{}"
        assert tags == []

    def test_素材必须有类别归组(self):
        uid = self._mk("nocat")
        _run(_seed_user(uid))

        async def _go():
            async with async_session() as db:
                return await create_entry(
                    db, user_id=uid, genre="玄幻", concept="",
                    instruction="x", payload={}, as_material=True,
                )
        entry, gate, _err = _run(_go())
        assert entry is None and gate.errors, "素材缺类别归组应被拒（明细在 gate.errors）"

    def test_列表含素材_排除参数滤掉(self):
        uid = self._mk("list")
        _run(_seed_user(uid))

        async def _seed_both():
            async with async_session() as db:
                mat, _g, _e = await create_entry(
                    db, user_id=uid, genre="玄幻", concept="文风",
                    instruction="素材句。", payload={}, as_material=True)
                kb, _g2, _e2 = await create_entry(
                    db, user_id=uid, genre="玄幻", concept="文风",
                    instruction="句子要短。", payload={},
                    definition="短句文风的一般性定义。", as_knowledge=True)
                await db.commit()
                return mat.id, kb.id
        mat_id, kb_id = _run(_seed_both())

        async def _list(include_material):
            async with async_session() as db:
                rows, _cur = await list_entries(db, user_id=uid, include_material=include_material)
                return {e.id for e in rows}
        with_mat = _run(_list(True))
        without_mat = _run(_list(False))
        assert mat_id in with_mat and kb_id in with_mat
        assert mat_id not in without_mat and kb_id in without_mat

    def test_素材删除真删_知识删除归档(self):
        uid = self._mk("del")
        _run(_seed_user(uid))

        async def _seed():
            async with async_session() as db:
                mat, _g, _e = await create_entry(
                    db, user_id=uid, genre="玄幻", concept="文风",
                    instruction="素材句。", payload={}, as_material=True)
                kb, _g2, _e2 = await create_entry(
                    db, user_id=uid, genre="玄幻", concept="文风",
                    instruction="句子要短。", payload={}, definition="定义。", as_knowledge=True)
                await db.commit()
                return mat.id, kb.id
        mat_id, kb_id = _run(_seed())

        async def _del(entry_id):
            async with async_session() as db:
                return await delete_entry(db, user_id=uid, entry_id=entry_id)
        assert _run(_del(mat_id)) is True
        assert _run(_del(kb_id)) is True

        async def _check():
            async with async_session() as db:
                mat = await db.get(KbEntry, mat_id)
                kb = await db.get(KbEntry, kb_id)
                return (mat is None, kb.status)
        mat_gone, kb_status = _run(_check())
        assert mat_gone is True, "素材行应真删"
        assert kb_status == "archived", "知识行应归档"


class TestCodeBucketedTree:
    """代码识别层次（boss 口径）：concept → 槽位 → 知识点，素材转实例。"""

    def _mk(self, tag):
        return f"kbsm-{tag}-{uuid.uuid4().hex[:8]}"

    def _seed_user(self, uid):
        return _seed_user(uid)

    def _seed_materials(self, uid, genre="玄幻", n=3):
        async def _go():
            async with async_session() as db:
                rows = []
                specs = [
                    ("角色设定", {"role": "主角", "gender": "男"}, "何沉舟小传"),
                    ("角色设定", {"role": "配角", "gender": "女"}, "马望津小传"),
                    ("文风", {"slot": "rule", "rule": "句子要短"}, "句子要短。"),
                ]
                for i in range(n):
                    concept, payload, inst = specs[i % len(specs)]
                    e = KbEntry(
                        user_id=uid, genre=genre, concept=concept,
                        concept_id=f"{genre}:{concept}", title=f"素材{i}",
                        payload_json=json.dumps(payload, ensure_ascii=False),
                        instruction=inst,
                        origin="material", status="active", rev=1,
                        src_kind="manual", src_ref="", src_key=f"k{i}",
                    )
                    db.add(e)
                    rows.append(e)
                await db.commit()
                return [e.id for e in rows]
        return _run(_go())

    def test_两级分桶_建树(self):
        uid = self._mk("tree")
        _run(_seed_user(uid))
        self._seed_materials(uid)

        from kb.summarize import run_summarize

        async def _go():
            async with async_session() as db:
                return await run_summarize(db, user_id=uid, genre="玄幻", trigger="auto")
        r, err = _run(_go())
        assert err == "" and r["knowledge"] == 3, f"3 桶 3 知识点：{r} {err}"

        async def _check():
            async with async_session() as db:
                rows = (await db.execute(_t(
                    "SELECT id, title, parent_id FROM kb_entries "
                    "WHERE user_id=:u AND origin='summary'"), {"u": uid})).mappings().all()
                insts = (await db.execute(_t(
                    "SELECT i.text, e.title AS ktitle FROM kb_knowledge_instances i "
                    "JOIN kb_entries e ON e.id = i.knowledge_id "
                    "WHERE e.user_id=:u"), {"u": uid})).mappings().all()
                return rows, insts
        rows, insts = _run(_check())
        # 风格维度四级树（boss 2026-11-08）：题材 → 笔法 → 写作视角 → 实例
        by_title = {r["title"]: r for r in rows}
        assert by_title["声音招式"]["parent_id"] == by_title["笔法"]["id"], "声音招式挂「笔法」父级"
        assert by_title["笔法"]["parent_id"] == "", "笔法挂题材根"
        assert by_title["主角"]["parent_id"] == "" and by_title["配角"]["parent_id"] == "", "角色知识点仍挂概念根"
        assert len(insts) == 3, f"每素材一条实例：{len(insts)}"

    def test_世界槽位_译名错位仍挂树(self):
        # 世界 power/extra 案（2026-11-08）：素材槽位原始值 power 经 _slot_label
        # 单译「力量与规则」，与节点标题「力量体系与规矩」（二次翻译）错位——
        # 槽位查不中树也不得掉出树自建，须按拼装标签重查并挂「世界」父级
        uid = self._mk("world")
        _run(_seed_user(uid))

        async def _seed():
            async with async_session() as db:
                for i, (part, inst) in enumerate([
                    ("power", "灵气复苏后武者分九品。"),
                    ("extra", "城西钟楼每到午夜自鸣。"),
                ]):
                    db.add(KbEntry(
                        user_id=uid, genre="都市", concept="世界设定",
                        concept_id="都市:世界设定", title=f"世界素材{i}",
                        payload_json=json.dumps({"part": part}, ensure_ascii=False),
                        instruction=inst,
                        origin="material", status="active", rev=1,
                        src_kind="manual", src_ref="", src_key=f"w{i}",
                    ))
                await db.commit()
        _run(_seed())

        from kb.summarize import run_summarize

        async def _go():
            async with async_session() as db:
                return await run_summarize(db, user_id=uid, genre="都市", trigger="auto")
        r, err = _run(_go())
        assert err == "" and r["knowledge"] == 2, f"两桶两知识点：{r} {err}"

        async def _check():
            async with async_session() as db:
                rows = (await db.execute(_t(
                    "SELECT id, title, parent_id FROM kb_entries "
                    "WHERE user_id=:u AND origin='summary' AND concept='世界设定'"), {"u": uid})).mappings().all()
                return {r["title"]: r for r in rows}
        kp = _run(_check())
        assert set(kp) == {"世界", "力量体系与规矩", "更多世界细节"}, f"树形标题随发版树：{set(kp)}"
        assert kp["世界"]["parent_id"] == "", "世界根挂题材根"
        assert kp["力量体系与规矩"]["parent_id"] == kp["世界"]["id"], "力量挂「世界」父级"
        assert kp["更多世界细节"]["parent_id"] == kp["世界"]["id"], "补充设定挂「世界」父级"

    def test_二次跑_素材已归档_零新建(self):
        uid = self._mk("idem")
        _run(_seed_user(uid))
        self._seed_materials(uid)

        from kb.summarize import run_summarize

        async def _go():
            async with async_session() as db:
                return await run_summarize(db, user_id=uid, genre="玄幻", trigger="manual")
        r1, _ = _run(_go())
        assert r1["knowledge"] >= 1
        r2, _ = _run(_go())
        assert r2["collected"] == 0, "素材已归档，二次跑零收集"

    def test_单飞_running_挡住并发(self):
        uid = self._mk("sf")
        _run(_seed_user(uid))
        self._seed_materials(uid)

        from kb.summarize import run_summarize

        async def _insert_running():
            async with async_session() as db:
                await db.execute(_t(
                    "INSERT INTO kb_summarize_runs (id, user_id, genre, status, trigger) "
                    "VALUES ('r-live', :u, '玄幻', 'running', 'manual')"), {"u": uid})
                await db.commit()
        _run(_insert_running())

        async def _go():
            async with async_session() as db:
                return await run_summarize(db, user_id=uid, genre="玄幻", trigger="manual")
        summary, err = _run(_go())
        assert summary is None and err == "running"

    def test_积压阈值与定期兜底触发(self):
        uid = self._mk("auto")
        _run(_seed_user(uid))
        self._seed_materials(uid, n=5)

        from kb.summarize import _maybe_auto_summarize

        async def _go():
            async with async_session() as db:
                return await _maybe_auto_summarize(db, user_id=uid)
        assert _run(_go()) == ["玄幻"]
        # 定期兜底：无运行记录视为超期——首次有素材即触发；跑完后 7 天内冷却不重复
        uid2 = self._mk("auto4")
        _seed_user(uid2)
        self._seed_materials(uid2, n=4)
        async def _go2():
            async with async_session() as db:
                return await _maybe_auto_summarize(db, user_id=uid2)
        assert _run(_go2()) == ["玄幻"]
        assert _run(_go2()) == []

    def test_直建知识通道_as_knowledge_带定义(self):
        uid = self._mk("direct")
        _run(_seed_user(uid))

        async def _go():
            async with async_session() as db:
                entry, _gate, _err = await create_entry(
                    db, user_id=uid, genre="玄幻", concept="文风",
                    instruction="句子要短。", payload={},
                    definition="短句文风的一般性定义。",
                    as_knowledge=True,
                )
                return entry
        entry = _run(_go())
        assert entry is not None
        assert entry.origin == "manual"
        assert entry.definition == "短句文风的一般性定义。"
        assert entry.status == "active"
