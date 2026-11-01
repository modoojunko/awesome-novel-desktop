"""AI 知识整理测试（c-kb-organize 批A）：触发矩阵/确定性打分/三级落位/上限淘汰/坑闸/保留策略/备份往返。"""

import asyncio
import io
import uuid
import zipfile

import yaml
from sqlalchemy import select as sel

import kb.organize as org
from db import async_session
from kb.organize import confidence, pair_signature, run_organize
from kb.service import create_entry
from models.kb import (
    KbEntry,
    KbEntryMerge,
    KbOrganizeFeedback,
    KbOrganizeFinding,
    KbOrganizeOutput,
    KbOrganizeRun,
    KbRelation,
)
from models.user import User


def _run(coro):
    return asyncio.run(coro)


async def _seed_entries(uid: str, specs: list[dict]) -> dict[str, KbEntry]:
    """经 create_entry 造条目（真实闸门＋alias 物化路径）。specs: concept/genre/instruction/aliases/evidence。"""
    out: dict[str, KbEntry] = {}
    async with async_session() as db:
        for i, sp in enumerate(specs, start=1):
            entry, _gate, error = await create_entry(
                db,
                user_id=uid,
                genre=sp.get("genre", ""),
                concept=sp["concept"],
                title=sp.get("title", f"条目{i}"),
                payload=sp.get("payload", {}),
                instruction=sp["instruction"],
                evidence=sp.get("evidence", ""),
                evidence_json=sp.get("evidence_json"),
                src_kind="manual",
            )
            assert entry is not None, f"seed 失败: {error}"
            out[entry.id] = entry
        await db.commit()
    return out


async def _seed_user(uid: str):
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="整理钉"))
        await db.commit()


def _mk(uid: str):
    return f"orga-{uuid.uuid4().hex[:8]}-{uid}"


class TestConfidence:
    def test_确定性_同输入同分(self):
        kw = {"chapter_a": 3, "chapter_b": 5, "genre_a": "玄幻", "genre_b": "玄幻",
              "alias_cooccur": True, "neg_hit": False}
        assert confidence("applies_to", "手法", "文风", **kw) == confidence("applies_to", "手法", "文风", **kw)

    def test_无章中性值(self):
        s = confidence("refines", "文风", "文风", chapter_a=None, chapter_b=None,
                       genre_a="都市", genre_b="都市", alias_cooccur=False, neg_hit=False)
        assert s == round(0.2 + 0.35 * 0.5 + 0.25, 4)

    def test_矩阵外零分(self):
        assert confidence("refines", "手法", "文风", chapter_a=1, chapter_b=1,
                          genre_a="玄幻", genre_b="玄幻", alias_cooccur=True, neg_hit=False) == 0.0
        assert confidence("instance_of", "手法", "手法", chapter_a=1, chapter_b=1,
                          genre_a="", genre_b="", alias_cooccur=False, neg_hit=False) == 0.0

    def test_负反馈减半_章距衰减(self):
        near = confidence("applies_to", "手法", "文风", chapter_a=3, chapter_b=3,
                          genre_a="玄幻", genre_b="玄幻", alias_cooccur=True, neg_hit=False)
        far = confidence("applies_to", "手法", "文风", chapter_a=1, chapter_b=30,
                         genre_a="玄幻", genre_b="玄幻", alias_cooccur=True, neg_hit=False)
        assert near > far
        negged = confidence("applies_to", "手法", "文风", chapter_a=3, chapter_b=3,
                            genre_a="玄幻", genre_b="玄幻", alias_cooccur=True, neg_hit=True)
        assert negged == round(near * 0.5, 4)

    def test_签名排序无关(self):
        assert pair_signature("a", "b") == pair_signature("b", "a")


class TestRunOrganize:
    def test_单飞与空题材(self):
        uid = _mk("sf")
        _run(_seed_user(uid))

        async def _seed_running():
            async with async_session() as db:
                db.add(KbOrganizeRun(user_id=uid, genre="玄幻", status="running"))
                await db.commit()
        _run(_seed_running())
        run, err = _run(_run_with_db(lambda db: run_organize(db, user_id=uid, genre="玄幻", trigger="manual", llm=False)))
        assert run is None and err == "running"

        # 空题材：无条目 → completed 零扫描
        run2, err2 = _run(_run_with_db(lambda db: run_organize(db, user_id=uid, genre="都市", trigger="manual", llm=False)))
        assert err2 == "" and run2.status == "completed" and run2.entries_scanned == 0

    def test_三级落位与坑闸(self):
        uid = _mk("tier")
        _run(_seed_user(uid))
        specs = [
            {"concept": "手法", "genre": "玄幻", "instruction": "打斗先给结果再补原因。",
             "evidence": "第3章 灯灭", "payload": {"instruction": "打斗先给结果再补原因。", "scene": "打斗"}},
            {"concept": "文风", "genre": "玄幻", "instruction": "打斗要短促克制。", "evidence": "第3章"},
            {"concept": "文风", "genre": "玄幻", "instruction": "冷峻旁白不抢戏。"},
        ]
        entries = _run(_seed_entries(uid, specs))
        ids = list(entries)
        cand = [
            {"a": ids[0], "b": ids[1], "rel_type": "applies_to", "note": "n", "evidence": "第3章"},   # 高分→active
            {"a": ids[1], "b": ids[2], "rel_type": "refines", "note": "n", "evidence": ""},            # 中分→pending（refines 文风→文风）
            {"a": ids[0], "b": ids[0], "rel_type": "refines", "note": "n", "evidence": ""},           # 自环→invalid
            {"a": ids[0], "b": "no-such", "rel_type": "refines", "note": "n", "evidence": ""},        # 端点缺失→invalid
            {"a": ids[1], "b": ids[2], "rel_type": "applies_to", "note": "n", "evidence": ""},        # 矩阵外→invalid
        ]

        async def _go(db):
            async def fake_llm(db_, uid_, genre_, sl):
                return cand, None
            orig = org._llm_candidates
            org._llm_candidates = fake_llm
            try:
                return await run_organize(db, user_id=uid, genre="玄幻", trigger="manual", llm=True)
            finally:
                org._llm_candidates = orig

        run, err = _run(_run_with_db(_go))
        assert err == "" and run.status == "completed"

        async def _check():
            async with async_session() as db:
                rows = (await db.execute(sel(KbRelation).where(KbRelation.user_id == uid))).scalars().all()
                return {(r.from_id, r.to_id, r.rel_type): r.status for r in rows}
        rels = _run(_check())
        assert rels[(ids[0], ids[1], "applies_to")] == "active"
        assert rels[(ids[1], ids[2], "refines")] == "pending"
        assert len(rels) == 2  # 自环/缺端点/矩阵外三条全被坑闸拒绝

    def test_上限淘汰_置信升序(self):
        uid = _mk("cap")
        _run(_seed_user(uid))
        specs = [{"concept": "手法", "genre": "玄幻", "instruction": f"手法{i}。"} for i in range(3)]
        entries = _run(_seed_entries(uid, specs))
        ids = list(entries)

        async def _seed_rels():
            async with async_session() as db:
                for i, a in enumerate(ids):
                    db.add(KbRelation(user_id=uid, from_id=a, to_id=ids[(i + 1) % 3],
                                      rel_type="depends_on", confidence=0.8 + i * 0.05,
                                      status="active", source="ai"))
                # 手法 3 条 → cap = 3×5 = 15；已插 3 条 active，再塞 13 条低置信 → 超 1 条
                for i in range(13):
                    db.add(KbRelation(user_id=uid, from_id=ids[0], to_id=ids[1],
                                      rel_type="derived_from", confidence=0.5 + i * 0.001,
                                      status="active", source="ai"))
                await db.commit()
        _run(_seed_rels())
        _run_org, err = _run(_run_with_db(lambda db: run_organize(db, user_id=uid, genre="玄幻", trigger="manual", llm=False)))
        assert err == ""

        async def _check():
            async with async_session() as db:
                rows = (await db.execute(sel(KbRelation).where(
                    KbRelation.user_id == uid, KbRelation.status == "active"))).scalars().all()
                archived = (await db.execute(sel(KbRelation).where(
                    KbRelation.user_id == uid, KbRelation.status == "archived"))).scalars().all()
                return len(rows), sorted(r.confidence for r in archived)
        n_active, archived_confs = _run(_check())
        assert n_active <= 15
        assert archived_confs and archived_confs[0] == min(0.5, 0.8)  # 低置信先淘汰

    def test_模板缺失_fail_soft(self):
        uid = _mk("nompl")
        _run(_seed_user(uid))
        _run(_seed_entries(uid, [
            {"concept": "手法", "genre": "玄幻", "instruction": "钩子开场。"},
            {"concept": "文风", "genre": "玄幻", "instruction": "打斗短促。"},  # 造短名单（否则 LLM 不被调）
        ]))

        async def _go(db):
            import kb.organize as o

            async def fake_llm(db_, uid_, genre_, sl):
                assert sl, "短名单应非空——模板缺失路径要先有候选"
                return [], "prompt_pack: missing"
            o._llm_candidates = fake_llm
            try:
                return await run_organize(db, user_id=uid, genre="玄幻", trigger="manual", llm=True)
            finally:
                pass
        run, _err = _run(_run_with_db(_go))
        assert run.status == "completed" and "prompt_pack" in (run.error or "")


class TestIncrementAndShortlist:
    def test_增量对只含新端(self):
        uid = _mk("inc")
        _run(_seed_user(uid))
        old = _run(_seed_entries(uid, [
            {"concept": "手法", "genre": "玄幻", "instruction": "旧手法。"},
            {"concept": "文风", "genre": "玄幻", "instruction": "旧文风。"},
        ]))
        new = _run(_seed_entries(uid, [
            {"concept": "手法", "genre": "玄幻", "instruction": "新手法。"},
        ]))
        by_concept: dict[str, list[KbEntry]] = {}
        for e in [*old.values(), *new.values()]:
            by_concept.setdefault(e.concept, []).append(e)
        sl = org._shortlist(set(new), by_concept, full=False)
        assert sl and all((a.id in new or b.id in new) for (a, b, _rt) in sl)
        sl_full = org._shortlist(set(new), by_concept, full=True)
        assert len(sl_full) >= len(sl)

    def test_短名单硬顶(self):
        uid = _mk("cap200")
        _run(_seed_user(uid))
        specs = ([{"concept": "手法", "genre": "玄幻", "instruction": f"手法{i}。"} for i in range(30)]
                 + [{"concept": "文风", "genre": "玄幻", "instruction": f"文风{i}。"} for i in range(30)])
        es = _run(_seed_entries(uid, specs))
        by_concept: dict[str, list[KbEntry]] = {}
        for e in es.values():
            by_concept.setdefault(e.concept, []).append(e)
        sl = org._shortlist(set(es), by_concept, full=True)
        assert len(sl) <= org.SHORTLIST_MAX


class TestAliasMaterializeAndRunsKeep:
    def test_alias_物化与共现读取(self):
        uid = _mk("alias")
        _run(_seed_user(uid))
        entries = _run(_seed_entries(uid, [
            {"concept": "角色设定", "genre": "玄幻", "instruction": "反派底子。",
             "payload": {"archetype": "秦重霄", "aliases": ["大当家", "老爷子"]}},
            {"concept": "角色设定", "genre": "玄幻", "instruction": "同类底子。",
             "payload": {"archetype": "秦二霄", "aliases": ["大当家"]}},
            {"concept": "角色设定", "genre": "玄幻", "instruction": "无关。",
             "payload": {"archetype": "王五", "aliases": []}},
        ]))
        ids = list(entries)

        async def _check():
            async with async_session() as db:
                amap = await org._alias_set(db, uid, ids)
                return {k: sorted(v) for k, v in amap.items()}
        amap = _run(_check())
        assert "大当家" in amap[ids[0]] and "老爷子" in amap[ids[0]]
        assert "大当家" in amap[ids[1]]
        assert amap.get(ids[2], set()) == set()
        assert set(amap[ids[0]]) & set(amap[ids[1]])  # 共现特征可用

    def test_runs_保留最近五十(self):
        uid = _mk("keep")
        _run(_seed_user(uid))

        _run(_seed_entries(uid, [{"concept": "手法", "genre": "玄幻", "instruction": "防早退。"}]))

        async def _seed_runs():
            async with async_session() as db:
                for i in range(55):
                    db.add(KbOrganizeRun(user_id=uid, genre="玄幻", status="completed"))
                await db.commit()
        _run(_seed_runs())
        _run_org, err = _run(_run_with_db(lambda db: run_organize(db, user_id=uid, genre="玄幻", trigger="manual", llm=False)))
        assert err == ""

        async def _count():
            async with async_session() as db:
                rows = (await db.execute(sel(KbOrganizeRun).where(
                    KbOrganizeRun.user_id == uid, KbOrganizeRun.genre == "玄幻"))).scalars().all()
                outs = (await db.execute(sel(KbOrganizeOutput))).scalars().all()
                return len(rows), len(outs)
        n_runs, n_outs = _run(_count())
        assert n_runs == org.RUN_KEEP_PER_GENRE
        assert n_outs <= org.RUN_KEEP_PER_GENRE * 2  # outputs 随 run 级联清


class TestBackupRoundtrip:
    def test_新表进配置包往返(self):
        suffix = uuid.uuid4().hex[:8]
        uid, uid2 = f"orgabk-{suffix}", f"orgabk2-{suffix}"
        run_id = f"run-{suffix}"
        ent_a, ent_b = f"ea-{suffix}", f"eb-{suffix}"

        async def _seed():
            async with async_session() as db:
                db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
                db.add(User(id=uid2, email=f"{uid2}@t.local", password_hash="x"))
                db.add(KbEntry(id=ent_a, user_id=uid, genre="玄幻", concept="手法",
                               concept_id="玄幻:手法", title="先果后因", instruction="先果后因。"))
                db.add(KbEntry(id=ent_b, user_id=uid, genre="玄幻", concept="文风",
                               concept_id="玄幻:文风", title="冷峻", instruction="冷峻。"))
                db.add(KbOrganizeRun(id=run_id, user_id=uid, genre="玄幻", status="completed"))
                db.add(KbOrganizeOutput(run_id=run_id, kind="scan", count=2))
                db.add(KbOrganizeFinding(
                    id=f"find-{suffix}", user_id=uid, genre="玄幻", kind="merge",
                    subject_id=ent_a, subject2_id=ent_b, payload_json="{}",
                    status="proposed", signature=pair_signature(ent_a, ent_b), run_id=run_id,
                ))
                db.add(KbOrganizeFeedback(user_id=uid, kind="relation", signature="sig", entry_id=ent_a))
                db.add(KbRelation(user_id=uid, from_id=ent_a, to_id=ent_b, rel_type="applies_to",
                                  confidence=0.9, status="active", source="ai", run_id=run_id))
                db.add(KbEntryMerge(surviving_id=ent_b, merged_id=ent_a, run_id=run_id))
                await db.commit()
        _run(_seed())

        async def _export():
            from backup.export import build_config_package_bytes

            async with async_session() as db:
                return await build_config_package_bytes(db, uid)
        blob, _n = _run(_export())
        cfg = yaml.safe_load(zipfile.ZipFile(io.BytesIO(blob)).read("config.yaml"))
        kb = cfg["knowledge_base"]
        for key in ("organize_outputs", "organize_findings", "organize_feedback", "entry_merges", "relations"):
            assert kb.get(key), f"缺段 {key}"

        # 模拟换机（共享库 db.get 不分用户——清源）
        async def _wipe():
            # 共享测试库 id 冲突判例：uid 的全部相关行都得清，否则 restore「同 id 忽略」短路
            from sqlalchemy import delete as _d

            async with async_session() as db:
                await db.execute(_d(KbEntry).where(KbEntry.id.in_([ent_a, ent_b])))
                await db.execute(_d(KbOrganizeRun).where(KbOrganizeRun.id == run_id))
                await db.execute(_d(KbOrganizeOutput).where(KbOrganizeOutput.run_id == run_id))
                await db.execute(_d(KbOrganizeFinding).where(KbOrganizeFinding.id == f"find-{suffix}"))
                await db.execute(_d(KbOrganizeFeedback).where(KbOrganizeFeedback.user_id == uid))
                await db.execute(_d(KbRelation).where(KbRelation.user_id == uid))
                await db.execute(_d(KbEntryMerge).where(KbEntryMerge.run_id == run_id))
                await db.commit()
        _run(_wipe())

        pkg = f"/tmp/orgabk-{suffix}.zip"
        with open(pkg, "wb") as fh:
            fh.write(blob)
        from backup.importer import _restore_config, parse_package

        cfg = parse_package([pkg])["config"]
        async def _restore():
            async with async_session() as db:
                s = await _restore_config(db, uid2, cfg)
                await db.commit()
                return s
        s = _run(_restore())
        created = s["knowledge_base"]["created"]
        assert created["organize_outputs"] == 1 and created["organize_findings"] == 1
        assert created["entry_merges"] == 1 and created["relations"] == 1


async def _run_with_db(fn):
    from db import async_session

    async with async_session() as db:
        return await fn(db)
