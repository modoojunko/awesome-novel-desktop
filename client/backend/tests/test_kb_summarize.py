"""知识总结管线测试（c-kb-summarize 批A：素材态/过滤收口/删除；批B：管线）。"""

import asyncio
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

    def test_手录素材_不装载槽位_不物化标签(self):
        uid = _mk("mat")
        _run(_seed_user(uid))

        async def _go():
            async with async_session() as db:
                entry, gate, error = await create_entry(
                    db, user_id=uid, genre="玄幻", concept="文风",
                    instruction="句子要短，少形容词。",
                    payload={}, as_material=True,
                )
                assert entry is not None, f"{gate.errors} {error}"
                # 无标签物化、无默认库：kb_entry_tags 无该行
                from models.kb import KbEntryTag
                tags = (await db.execute(sel(KbEntryTag).where(KbEntryTag.entry_id == entry.id))).scalars().all()
                return entry, tags
        entry, tags = _run(_go())
        assert entry.origin == "material"
        assert entry.payload_json == "{}"
        assert tags == []

    def test_素材必须有类别归组(self):
        uid = _mk("nocat")
        _run(_seed_user(uid))

        async def _go():
            async with async_session() as db:
                return await create_entry(
                    db, user_id=uid, genre="玄幻", concept="",
                    instruction="x", payload={}, as_material=True,
                )
        entry, gate, _error = _run(_go())
        assert entry is None and gate.errors, "素材缺类别归组应被拒（明细在 gate.errors）"

    def test_列表含素材_排除参数滤掉(self):
        uid = _mk("list")
        _run(_seed_user(uid))

        async def _seed_both():
            async with async_session() as db:
                mat, _g, _e = await create_entry(
                    db, user_id=uid, genre="玄幻", concept="文风",
                    instruction="素材句。", payload={}, as_material=True)
                kb, _g2, _e2 = await create_entry(
                    db, user_id=uid, genre="玄幻", concept="文风",
                    instruction="句子要短。", payload={},
                    definition="短句文风的一般性定义。")
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
        uid = _mk("del")
        _run(_seed_user(uid))

        async def _seed():
            async with async_session() as db:
                mat, _g, _e = await create_entry(
                    db, user_id=uid, genre="玄幻", concept="文风",
                    instruction="素材句。", payload={}, as_material=True)
                kb, _g2, _e2 = await create_entry(
                    db, user_id=uid, genre="玄幻", concept="文风",
                    instruction="句子要短。", payload={}, definition="定义。")
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



class TestSummarizePipeline:
    """批B：总结管线（runs/候选/校验/采纳/忽略/单飞/自动触发）。"""

    def _mk(self, tag):
        return f"kbsm-{tag}-{uuid.uuid4().hex[:8]}"

    def _seed_materials(self, uid, genre, n, concept="文风"):
        async def _go():
            async with async_session() as db:
                ids = []
                for i in range(n):
                    e = KbEntry(
                        user_id=uid, genre=genre, concept=concept,
                        concept_id=f"{genre}:{concept}", title=f"素材{i}",
                        payload_json="{}", instruction=f"素材原文{i}。",
                        origin="material", status="active", rev=1,
                        src_kind="manual", src_ref="", src_key=f"k{i}",
                    )
                    db.add(e)
                    ids.append(e)
                await db.commit()
                return [e.id for e in ids]
        return _run(_go())

    def test_跑一次_done_零候选_单飞_素材不足不跑(self):
        uid = self._mk("run")
        _run(_seed_user(uid))
        self._seed_materials(uid, "玄幻", 2)

        from kb.summarize import run_summarize

        async def _go(llm):
            async with async_session() as db:
                return await run_summarize(db, user_id=uid, genre="玄幻", trigger="manual", llm=llm)
        summary, err = _run(_go(llm=False))
        assert err == "" and summary["candidates"] == 0 and summary["collected"] == 2

        # 单飞：插一行 running → 再触发返回 running
        async def _insert_running():
            async with async_session() as db:
                await db.execute(_t(
                    "INSERT INTO kb_summarize_runs (id, user_id, genre, status, trigger) "
                    "VALUES ('r-running', :u, '玄幻', 'running', 'manual')"), {"u": uid})
                await db.commit()
        from sqlalchemy import text as _t
        _run(_insert_running())
        summary2, err2 = _run(_go(llm=False))
        assert summary2 is None and err2 == "running"

        # 无素材题材：不跑（collected=0 且不落 runs？落 runs 前即返）
        summary3, err3 = _run(_go(llm=False))
        assert summary3 is None and err3 == "running"  # 仍被 running 单飞挡住

    def test_候选校验_非法素材id与parent被滤(self, monkeypatch):
        uid = self._mk("valid")
        _run(_seed_user(uid))
        ids = self._seed_materials(uid, "玄幻", 2)
        good_id = ids[0]

        async def _fake_llm(user_id, genre, materials, existing_lines, existing_ids):
            return [
                {"title": "短句控节奏", "definition": "用短句控制叙事节奏。", "concept": "文风",
                 "parent": "ROOT", "material_ids": [good_id]},
                {"title": "非法素材引用", "definition": "x", "concept": "文风",
                 "parent": "ROOT", "material_ids": ["not-exists"]},
                {"title": "", "definition": "x", "concept": "文风",
                 "parent": "ROOT", "material_ids": [good_id]},
                {"title": "挂不存在父", "definition": "x", "concept": "文风",
                 "parent": "ghost-parent", "material_ids": [ids[1]]},
            ], None
        monkeypatch.setattr("kb.summarize._llm_candidates", _fake_llm)

        from kb.summarize import run_summarize

        async def _go():
            async with async_session() as db:
                return await run_summarize(db, user_id=uid, genre="玄幻", trigger="manual", llm=True)
        summary, err = _run(_go())
        assert err == "" and summary["candidates"] == 2, "非法素材引用与空标题候选被滤"

        async def _pending():
            async with async_session() as db:
                rows = (await db.execute(_t(
                    "SELECT proposed_title, parent_knowledge_id FROM kb_summarize_candidates "
                    "WHERE user_id=:u AND status='pending'"), {"u": uid})).mappings().all()
                return {r["proposed_title"]: r["parent_knowledge_id"] for r in rows}
        pend = _run(_pending())
        print("DEBUG pend:", pend)
        async def _all_rows():
            async with async_session() as db:
                rows = (await db.execute(_t(
                    "SELECT user_id, proposed_title, status FROM kb_summarize_candidates"))).mappings().all()
                runs = (await db.execute(_t(
                    "SELECT user_id, genre, status, candidates_created, error FROM kb_summarize_runs"))).mappings().all()
                return [dict(r) for r in rows], [dict(r) for r in runs]
        all_rows, all_runs = _run(_all_rows())
        print("DEBUG all_candidates:", all_rows)
        print("DEBUG all_runs:", all_runs)
        assert pend["短句控节奏"] == ""  # ROOT 落空
        assert pend["挂不存在父"] == ""  # 非法 parent 落空（概念根）

    def test_采纳_转实例_归档素材_素材用尽拒(self, monkeypatch):
        uid = self._mk("adopt")
        _run(_seed_user(uid))
        ids = self._seed_materials(uid, "玄幻", 1)

        async def _fake_llm(user_id, genre, materials, existing_lines, existing_ids):
            return [{"title": "短句控节奏", "definition": "用短句控制叙事节奏。", "concept": "文风",
                     "parent": "ROOT", "material_ids": ids}], None
        monkeypatch.setattr("kb.summarize._llm_candidates", _fake_llm)

        from kb.summarize import adopt_candidate, run_summarize

        async def _run_summ():
            async with async_session() as db:
                return await run_summarize(db, user_id=uid, genre="玄幻", trigger="manual", llm=True)
        _run(_run_summ())

        async def _pending_id():
            async with async_session() as db:
                return (await db.execute(_t(
                    "SELECT id FROM kb_summarize_candidates WHERE user_id=:u AND status='pending'"),
                    {"u": uid})).scalar()
        cid = _run(_pending_id())

        async def _adopt(adopt_id):
            async with async_session() as db:
                return await adopt_candidate(db, user_id=uid, candidate_id=adopt_id)
        ok, msg = _run(_adopt(cid))
        assert ok is True, msg

        async def _check():
            async with async_session() as db:
                kb = (await db.execute(_t(
                    "SELECT id, definition, origin, parent_id FROM kb_entries WHERE user_id=:u AND origin='summary'"),
                    {"u": uid})).mappings().first()
                inst = (await db.execute(_t(
                    "SELECT count(*) FROM kb_knowledge_instances WHERE knowledge_id=:k"),
                    {"k": kb["id"]})).scalar()
                mat = await db.get(KbEntry, ids[0])
                return kb["definition"], inst, mat.status
        definition, inst_n, mat_status = _run(_check())
        assert definition == "用短句控制叙事节奏。"
        assert inst_n == 1
        assert mat_status == "archived"

        # 素材已用尽：新建等价候选再采纳 → no_materials + dismissed
        async def _insert_dup():
            async with async_session() as db:
                await db.execute(_t(
                    "INSERT INTO kb_summarize_candidates (id, run_id, user_id, genre, concept, "
                    "proposed_title, proposed_definition, material_ids, status) "
                    "VALUES ('c-dup', 'r-x', :u, '玄幻', '文风', '等价候选', 'x', :m, 'pending')"),
                    {"u": uid, "m": f'["{ids[0]}"]'})
                await db.commit()
        _run(_insert_dup())
        async def _peek():
            async with async_session() as db:
                rows = (await db.execute(_t(
                    "SELECT id, status FROM kb_summarize_candidates WHERE user_id=:u"),
                    {"u": uid})).mappings().all()
                return [dict(r) for r in rows]
        print("DEBUG candidates:", _run(_peek()))
        ok2, msg2 = _run(_adopt("c-dup"))
        assert ok2 is False and msg2 == "no_materials"

    def test_忽略候选(self, monkeypatch):
        uid = self._mk("dismiss")
        _run(_seed_user(uid))
        self._seed_materials(uid, "玄幻", 1)

        async def _fake_llm(user_id, genre, materials, existing_lines, existing_ids):
            return [{"title": "t", "definition": "d", "concept": "文风",
                     "parent": "ROOT", "material_ids": [m.id for m in materials]}], None
        monkeypatch.setattr("kb.summarize._llm_candidates", _fake_llm)

        from kb.summarize import dismiss_candidate, run_summarize

        async def _summ():
            async with async_session() as db:
                return await run_summarize(db, user_id=uid, genre="玄幻", trigger="manual", llm=True)
        _run(_summ())
        async def _pending_id():
            async with async_session() as db:
                return (await db.execute(_t(
                    "SELECT id FROM kb_summarize_candidates WHERE user_id=:u AND status='pending'"),
                    {"u": uid})).scalar()
        cid = _run(_pending_id())
        async def _dismiss():
            async with async_session() as db:
                return await dismiss_candidate(db, user_id=uid, candidate_id=cid)
        assert _run(_dismiss()) is True
        async def _pending_n():
            async with async_session() as db:
                return (await db.execute(_t(
                    "SELECT count(*) FROM kb_summarize_candidates WHERE user_id=:u AND status='pending'"),
                    {"u": uid})).scalar()
        assert _run(_pending_n()) == 0

    def test_积压阈值自动触发(self, monkeypatch):
        uid = self._mk("auto")
        _run(_seed_user(uid))
        self._seed_materials(uid, "玄幻", 5)

        async def _fake_llm(user_id, genre, materials, existing_lines, existing_ids):
            return [], None
        monkeypatch.setattr("kb.summarize._llm_candidates", _fake_llm)

        from kb.summarize import _maybe_auto_summarize

        async def _go():
            async with async_session() as db:
                return await _maybe_auto_summarize(db, user_id=uid)
        triggered = _run(_go())
        assert triggered == ["玄幻"]
        # 4 条不触发
        uid2 = self._mk("auto4")
        _run(_seed_user(uid2))
        self._seed_materials(uid2, "都市", 4)
        async def _go2():
            async with async_session() as db:
                return await _maybe_auto_summarize(db, user_id=uid2)
        assert _run(_go2()) == []
