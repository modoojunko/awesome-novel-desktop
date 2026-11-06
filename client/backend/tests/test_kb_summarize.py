"""知识总结管线测试（c-kb-summarize 批A：素材态/过滤收口/删除；批B：管线）。"""

import asyncio
import uuid

from sqlalchemy import select
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
    """批B：总结管线（定期任务自动整理——知识直接生效，无确认制）。"""

    def _mk(self, tag):
        return f"kbsm-{tag}-{uuid.uuid4().hex[:8]}"

    def _seed_materials(self, uid, genre, n, concept="文风"):
        async def _go():
            async with async_session() as db:
                rows = []
                for i in range(n):
                    e = KbEntry(
                        user_id=uid, genre=genre, concept=concept,
                        concept_id=f"{genre}:{concept}", title=f"素材{i}",
                        payload_json="{}", instruction=f"素材原文{i}。",
                        origin="material", status="active", rev=1,
                        src_kind="manual", src_ref="", src_key=f"k{i}",
                    )
                    db.add(e)
                    rows.append(e)
                await db.commit()
                return [e.id for e in rows]
        return _run(_go())

    def test_跑一次_done_单飞_无素材不落runs(self):
        uid = self._mk("run")
        _run(_seed_user(uid))
        self._seed_materials(uid, "玄幻", 2)

        from kb.summarize import run_summarize

        async def _go(llm):
            async with async_session() as db:
                return await run_summarize(db, user_id=uid, genre="玄幻", trigger="manual", llm=llm)
        summary, err = _run(_go(llm=False))
        assert err == "" and summary["knowledge"] == 0 and summary["collected"] == 2

        # 单飞：插一行 running → 再触发返回 running
        async def _insert_running():
            async with async_session() as db:
                await db.execute(_t(
                    "INSERT INTO kb_summarize_runs (id, user_id, genre, status, trigger) "
                    "VALUES ('r-running', :u, '玄幻', 'running', 'manual')"), {"u": uid})
                await db.commit()
        _run(_insert_running())
        summary2, err2 = _run(_go(llm=False))
        assert summary2 is None and err2 == "running"

    def test_三闸_非法素材id_空标题_坏parent_自动归根_直接建知识(self, monkeypatch):
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
                return await run_summarize(db, user_id=uid, genre="玄幻", trigger="auto", llm=True)
        summary, err = _run(_go())
        assert err == "" and summary["knowledge"] == 2, "非法素材引用与空标题簇被滤"

        async def _check():
            async with async_session() as db:
                rows = (await db.execute(_t(
                    "SELECT title, origin, parent_id FROM kb_entries WHERE user_id=:u AND origin='summary'"),
                    {"u": uid})).mappings().all()
                inst = (await db.execute(_t(
                    "SELECT count(*) FROM kb_knowledge_instances ki "
                    "JOIN kb_entries e ON e.id = ki.knowledge_id WHERE e.user_id=:u AND e.origin='summary'"),
                    {"u": uid})).scalar()
                return {r["title"]: (r["origin"], r["parent_id"]) for r in rows}, inst
        kb, inst_n = _run(_check())
        assert set(kb) == {"短句控节奏", "挂不存在父"}
        assert all(o == "summary" and p == "" for o, p in kb.values())
        assert inst_n == 2

    def test_自动建知识_转实例_归档素材_素材用尽不建空知识(self, monkeypatch):
        uid = self._mk("adopt")
        _run(_seed_user(uid))
        ids = self._seed_materials(uid, "玄幻", 1)

        async def _fake_llm(user_id, genre, materials, existing_lines, existing_ids):
            out = [{"title": "短句控节奏", "definition": "用短句控制叙事节奏。", "concept": "文风",
                    "parent": "ROOT", "material_ids": [ids[0]]}]
            if getattr(_fake_llm, "second", False):
                out.append({"title": "等价候选", "definition": "x", "concept": "文风",
                            "parent": "ROOT", "material_ids": [ids[0]]})  # 素材已用尽
            _fake_llm.second = True
            return out, None
        monkeypatch.setattr("kb.summarize._llm_candidates", _fake_llm)

        from kb.summarize import run_summarize

        async def _go():
            async with async_session() as db:
                return await run_summarize(db, user_id=uid, genre="玄幻", trigger="auto", llm=True)
        r1, _ = _run(_go())
        assert r1["knowledge"] == 1

        async def _check():
            async with async_session() as db:
                kb = (await db.execute(_t(
                    "SELECT id, definition, origin FROM kb_entries WHERE user_id=:u AND origin='summary'"),
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

        # 第二轮：素材已被用尽 → 不建空知识
        r2, _ = _run(_go())
        assert r2["knowledge"] == 0, "素材用尽的簇不建空知识"

    def test_积压阈值与定期兜底自动触发(self, monkeypatch):
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
        assert _run(_go()) == ["玄幻"]
        # 素材未消耗（fake 无候选）→ 积压恒 ≥5 → 阈值口径下持续触发（正确）；
        # 定期去重（7 天内不重复）由 4 条场景覆盖（阈值未达时才查定期）

        # 4 条题材：无运行记录＝定期兜底视为超期 → 首轮也整理；跑完后 7 天内不重复
        uid2 = self._mk("auto4")
        _run(_seed_user(uid2))
        self._seed_materials(uid2, "都市", 4)
        async def _go2():
            async with async_session() as db:
                return await _maybe_auto_summarize(db, user_id=uid2)
        assert _run(_go2()) == ["都市"]
        assert _run(_go2()) == []


def _shared_mk(tag):
    return f"kbsm-{tag}-{uuid.uuid4().hex[:8]}"


class TestLlmCandidatesParsing:
    """_llm_candidates 真 JSON 解析分支（评审缺口）：围栏/坏 JSON/非 list/越界过滤。"""

    def _mk(self, tag):
        return _shared_mk(tag)

    def _seed_materials(self, uid, genre, n, concept="文风"):
        async def _go():
            async with async_session() as db:
                rows = []
                for i in range(n):
                    e = KbEntry(
                        user_id=uid, genre=genre, concept=concept,
                        concept_id=f"{genre}:{concept}", title=f"素材{i}",
                        payload_json="{}", instruction=f"素材原文{i}。",
                        origin="material", status="active", rev=1,
                        src_kind="manual", src_ref="", src_key=f"k{i}",
                    )
                    db.add(e)
                    rows.append(e)
                await db.commit()
                return [e.id for e in rows]
        return _run(_go())

    def _materials(self, uid):
        async def _go():
            async with async_session() as db:
                return (
                    await db.execute(
                        select(KbEntry).where(
                            KbEntry.user_id == uid, KbEntry.origin == "material"
                        )
                    )
                ).scalars().all()
        return _run(_go())

    def test_围栏包裹_剥后可解析(self, monkeypatch):
        uid = self._mk("fence")
        _run(_seed_user(uid))
        self._seed_materials(uid, "玄幻", 1)

        from kb.summarize import _llm_candidates

        async def _material_rows():
            async with async_session() as db:
                return (await db.execute(sel(KbEntry).where(KbEntry.user_id == uid))).scalars().all()
        mats = _run(_material_rows())
        real_id = mats[0].id
        body = '{"candidates": [{"title": "短句", "definition": "d", "concept": "文风", "parent": "ROOT", "material_ids": ["' + real_id + '"]}]}'

        async def _fake_client(user_id):
            class _R:
                async def chat(self, **kw):
                    return '```json\n' + body + '\n```'
            return _R()
        monkeypatch.setattr("ai_client.get_ai_client_for_user", _fake_client)
        cands, err = _run(_llm_candidates(uid, "玄幻", mats, [], set()))
        assert err is None and len(cands) == 1, f"围栏 JSON 应剥后解析：{err} {cands}"

    def test_坏json_全损报错(self, monkeypatch):
        uid = self._mk("bad")
        _run(_seed_user(uid))
        self._seed_materials(uid, "玄幻", 1)

        async def _fake_client(user_id):
            class _R:
                async def chat(self, **kw):
                    return "经过分析，这些素材不值得提炼"  # 散文跑偏
            return _R()
        monkeypatch.setattr("ai_client.get_ai_client_for_user", _fake_client)

        from kb.summarize import _llm_candidates

        async def _material_rows():
            async with async_session() as db:
                return (await db.execute(sel(KbEntry).where(KbEntry.user_id == uid))).scalars().all()
        mats = _run(_material_rows())
        cands, err = _run(_llm_candidates(uid, "玄幻", mats, [], set()))
        assert cands == [] and err == "llm: bad json"

    def test_越界素材id被滤_非list容错(self, monkeypatch):
        uid = self._mk("oob")
        _run(_seed_user(uid))
        self._seed_materials(uid, "玄幻", 1)

        async def _fake_client(user_id):
            class _R:
                async def chat(self, **kw):
                    return '{"candidates": "not-a-list", "x": 1}'
            return _R()
        monkeypatch.setattr("ai_client.get_ai_client_for_user", _fake_client)

        from kb.summarize import _llm_candidates

        async def _material_rows():
            async with async_session() as db:
                return (await db.execute(sel(KbEntry).where(KbEntry.user_id == uid))).scalars().all()
        mats = _run(_material_rows())
        cands, err = _run(_llm_candidates(uid, "玄幻", mats, [], set()))
        assert cands == [] and err is None
