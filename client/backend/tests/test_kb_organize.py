"""AI 知识整理测试（c-kb-organize 批A）：触发矩阵/确定性打分/三级落位/上限淘汰/坑闸/保留策略/备份往返。"""

import asyncio
import io
import json
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
                src_kind=sp.get("src_kind", "manual"),
                src_ref=sp.get("src_ref", ""),
                src_key=sp.get("src_key", ""),
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
        _run_org, err = _run(_run_with_db(lambda db: run_organize(
            db, user_id=uid, genre="玄幻", trigger="manual", llm=False)))
        assert err == ""
        assert _run_org.entries_scanned == 3

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
        # 直调 _prune_runs（保留语义的隔离验证；不经 run_organize——共享库免疫）
        async def _prune():
            from kb.organize import _prune_runs

            async with async_session() as db:
                return await _prune_runs(db, user_id=uid, genre="玄幻")
        _run(_prune())

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


class TestFindingsAndAdoption:
    """批B：四类检测→findings→采纳语义＋merged 跨端。"""

    def _mk_uid(self):
        return _mk("find")

    def test_平行条目合并全链(self):
        """双出口平行条目（同 src_ref）：检测→建议→采纳→merged 不删数据→详情追溯。"""
        uid = _mk("para")
        _run(_seed_user(uid))

        async def _seed_pair():
            async with async_session() as db:
                for eid, key in (("p-a", "洛九歌"), ("p-b", "character:1")):
                    db.add(KbEntry(
                        id=f"{eid}-{uid[:6]}", user_id=uid, genre="玄幻",
                        concept="角色设定", concept_id="玄幻:角色设定",
                        title="洛九歌", payload_json=json.dumps(
                            {"archetype": "洛九歌", "aliases": ["掌灯人"], "gender": "女"},
                            ensure_ascii=False),
                        instruction="掌灯人，笑里藏刀。",
                        src_kind="deconstruct", src_ref="task-x", src_key=key,
                    ))
                await db.commit()
        _run(_seed_pair())

        async def _detect():
            async with async_session() as db:
                entries = (await db.execute(sel(KbEntry).where(
                    KbEntry.user_id == uid, KbEntry.status == "active"))).scalars().all()
                run = KbOrganizeRun(user_id=uid, genre="玄幻", status="running")
                db.add(run)
                await db.flush()
                counts = await org_detect(db, run=run, entries=list(entries))
                await db.commit()
                finds = (await db.execute(sel(KbOrganizeFinding).where(
                    KbOrganizeFinding.user_id == uid, KbOrganizeFinding.kind == "merge"))).scalars().all()
                return counts, finds
        counts, finds = _run(_detect())
        print("DBG-PARA counts:", counts, "finds:", [(f.kind, f.subject_id[:8], f.subject2_id[:8], f.signature[:10], f.status) for f in finds])
        assert counts.get("merge", 0) >= 1 and len(finds) == 1
        f = finds[0]
        payload = json.loads(f.payload_json)
        assert "同来源" in payload["reason"]  # provenance 线索在案

        # 采纳合并
        async def _adopt():
            async with async_session() as db:
                from kb.organize import adopt_finding

                return await adopt_finding(db, user_id=uid, finding_id=f.id)
        ok, msg = _run(_adopt())
        assert ok, msg

        async def _verify():
            async with async_session() as db:
                rows = (await db.execute(sel(KbEntry).where(KbEntry.user_id == uid))).scalars().all()
                states = {r.id: r.status for r in rows}
                merges = (await db.execute(sel(KbEntryMerge).where(
                    KbEntryMerge.merged_id.in_([f.subject_id, f.subject2_id])))).scalars().all()
                detail = await db.get(KbEntry, f.subject_id)
                return states, len(merges), detail.status, detail.payload_json
        states, n_merges, merged_status, merged_payload = _run(_verify())
        assert set(states.values()) == {"active", "merged"}          # 不删行
        assert n_merges == 1 and merged_status == "merged"
        assert "洛九歌" in merged_payload                             # 载荷原样保留

    def test_纠偏删建_溯源键防撞(self):
        uid = _mk("recl")
        _run(_seed_user(uid))
        specs = [
            # 词叶「世界/设定」双重命中，落在手法 → reclass 建议
            {"concept": "手法", "genre": "玄幻",
             "instruction": "这个世界的设定里，灵气以灯为纪，铁律不可破。",
             "src_kind": "deconstruct", "src_ref": "task-r", "src_key": "world:1"},
            {"concept": "文风", "genre": "玄幻", "instruction": "冷峻旁白，短句克制。"},
        ]
        entries = _run(_seed_entries(uid, specs))
        subj_id = next(iter(entries))

        async def _detect_and_adopt():
            async with async_session() as db:
                es = (await db.execute(sel(KbEntry).where(
                    KbEntry.user_id == uid, KbEntry.status == "active"))).scalars().all()
                run = KbOrganizeRun(user_id=uid, genre="玄幻", status="running")
                db.add(run)
                await db.flush()
                await org_detect(db, run=run, entries=list(es))
                await db.commit()
                f = (await db.execute(sel(KbOrganizeFinding).where(
                    KbOrganizeFinding.user_id == uid, KbOrganizeFinding.kind == "reclass"))).scalars().all()
                return [x for x in f if x.subject_id == subj_id]
        finds = _run(_detect_and_adopt())
        assert finds, "应有纠偏建议"
        payload = json.loads(finds[0].payload_json)
        assert payload["target_concept"] == "世界设定"

        async def _adopt():
            async with async_session() as db:
                from kb.organize import adopt_finding

                return await adopt_finding(db, user_id=uid, finding_id=finds[0].id)
        ok, _msg = _run(_adopt())
        assert ok

        async def _verify():
            async with async_session() as db:
                rows = (await db.execute(sel(KbEntry).where(
                    KbEntry.user_id == uid, KbEntry.status.in_(("active", "archived"))))).scalars().all()
                return [(r.concept, r.status, r.src_key) for r in rows]
        rows = _run(_verify())
        worlds = [r for r in rows if r[0] == "世界设定" and r[1] == "active"]
        assert worlds and worlds[0][2] == "world:1:reclass"  # 溯源键防撞后缀
        assert any(r[0] == "手法" and r[1] == "archived" for r in rows)  # 原条目归档

    def test_质量标记_采纳归档_不影响打分输入(self):
        uid = _mk("qual")
        _run(_seed_user(uid))
        specs = [{"concept": "手法", "genre": "玄幻", "instruction": "太短。"}]  # <20 字
        entries = _run(_seed_entries(uid, specs))

        async def _detect():
            async with async_session() as db:
                es = (await db.execute(sel(KbEntry).where(
                    KbEntry.user_id == uid, KbEntry.status == "active"))).scalars().all()
                run = KbOrganizeRun(user_id=uid, genre="玄幻", status="running")
                db.add(run)
                await db.flush()
                counts = await org_detect(db, run=run, entries=list(es))
                await db.commit()
                f = (await db.execute(sel(KbOrganizeFinding).where(
                    KbOrganizeFinding.user_id == uid, KbOrganizeFinding.kind == "quality"))).scalars().all()
                return counts, f
        counts, finds = _run(_detect())
        assert counts.get("quality", 0) >= 1 and finds
        # 打分输入不受标记影响（confidence 纯函数吃显式特征，无 findings 读点）
        s1 = confidence("applies_to", "手法", "文风", chapter_a=3, chapter_b=3,
                        genre_a="玄幻", genre_b="玄幻", alias_cooccur=True, neg_hit=False)
        s2 = confidence("applies_to", "手法", "文风", chapter_a=3, chapter_b=3,
                        genre_a="玄幻", genre_b="玄幻", alias_cooccur=True, neg_hit=False)
        assert s1 == s2

        async def _adopt():
            async with async_session() as db:
                from kb.organize import adopt_finding

                return await adopt_finding(db, user_id=uid, finding_id=finds[0].id)
        ok, _msg = _run(_adopt())
        assert ok

        async def _status():
            async with async_session() as db:
                e = await db.get(KbEntry, next(iter(entries)))
                return e.status
        assert _run(_status()) == "archived"

    def test_忽略签名不再提_rev变再提(self):
        uid = _mk("ign")
        _run(_seed_user(uid))
        pair_specs = [
            {"concept": "角色设定", "genre": "玄幻", "instruction": "掌灯人，笑里藏刀。",
             "payload": {"archetype": "洛九歌", "aliases": ["掌灯人"]}},
            {"concept": "角色设定", "genre": "玄幻", "instruction": "洛九歌，掌灯人。",
             "payload": {"archetype": "洛九歌", "aliases": ["掌灯人"]}},
        ]
        _run(_seed_entries(uid, pair_specs))

        async def _detect():
            async with async_session() as db:
                es = (await db.execute(sel(KbEntry).where(
                    KbEntry.user_id == uid, KbEntry.status == "active"))).scalars().all()
                run = KbOrganizeRun(user_id=uid, genre="玄幻", status="running")
                db.add(run)
                await db.flush()
                await org_detect(db, run=run, entries=list(es))
                await db.commit()
                return (await db.execute(sel(KbOrganizeFinding).where(
                    KbOrganizeFinding.user_id == uid, KbOrganizeFinding.kind == "merge"))).scalars().all()
        finds1 = _run(_detect())
        assert len(finds1) == 1

        async def _ignore():
            async with async_session() as db:
                from kb.organize import ignore_finding

                return await ignore_finding(db, user_id=uid, finding_id=finds1[0].id)
        assert _run(_ignore()) is True

        # rev 未变再跑 → 不再提出
        finds2 = _run(_detect())
        assert all(f.status == "ignored" for f in finds2) and not [
            f for f in finds2 if f.status == "proposed"
        ]

        # rev 变化（模拟条目被编辑）→ 重新提出
        async def _bump():
            async with async_session() as db:
                es = (await db.execute(sel(KbEntry).where(
                    KbEntry.user_id == uid))).scalars().all()
                es[0].rev += 1
                await db.commit()
        _run(_bump())
        finds3 = _run(_detect())
        assert any(f.status == "proposed" for f in finds3)

    def test_merged_不复活_详情追溯(self):
        uid = _mk("mrev")
        _run(_seed_user(uid))
        # 书＋角色＋条目（src_kind=book, src_ref=novel）
        from models.project import Novel

        async def _seed_full():
            from models.character import Character as _C

            async with async_session() as db:
                novel = Novel(user_id=uid, name="合并钉书", slug=f"mrg-{uuid.uuid4().hex[:6]}",
                              root_path=f"./data/mrg-{uuid.uuid4().hex[:6]}",
                              source="manual", current_phase="write")
                db.add(novel)
                await db.flush()
                ch = _C(novel_id=novel.id, seq=1, name="洛九歌", role="反派")
                db.add(ch)
                await db.flush()
                db.add(KbEntry(
                    id=f"mrg-{uid[:6]}", user_id=uid, genre="", concept="角色设定",
                    concept_id=":角色设定", title="洛九歌",
                    payload_json=json.dumps({"archetype": "洛九歌"}, ensure_ascii=False),
                    instruction="掌灯人。", status="merged",
                    src_kind="book", src_ref=novel.id, src_key=ch.id,  # 与 collect 的 character_id 同源
                ))
                await db.commit()
                return novel.id
        novel_id = _run(_seed_full())

        # 收录同源角色：merged 不复活（created=False 且状态保持 merged）
        from library import service as libsvc

        _run(_ensure_char(novel_id))

        async def _char_id(nid):
            from models.character import Character as _C

            async with async_session() as db:
                ch = (await db.execute(sel(_C).where(_C.novel_id == nid))).scalars().first()
                return ch.id
        cid = _run(_char_id(novel_id))

        async def _collect():
            async with async_session() as db:
                novel = await db.get(Novel, novel_id)
                r = await libsvc.collect_from_book(db, uid, novel, cid, rename=False)
                return r
        result = _run(_collect())
        assert result["created"] is False

        async def _state():
            async with async_session() as db:
                e = await db.get(KbEntry, f"mrg-{uid[:6]}")
                return e.status
        assert _run(_state()) == "merged"  # 不复活

        # 详情追溯：include_merged 放行＋merged_into 指向（端点层）
        async def _override():
            return {"id": uid}
        app.dependency_overrides[get_current_user] = _override
        try:
            with TestClient(app) as c:
                r404 = c.get(f"/api/kb/entries/mrg-{uid[:6]}")
                assert r404.status_code == 404  # 默认 active-only
                r = c.get(f"/api/kb/entries/mrg-{uid[:6]}?include_merged=1")
                assert r.status_code == 200
                data = r.json()["data"]
                assert data["status"] == "merged"
        finally:
            app.dependency_overrides.clear()


from fastapi.testclient import TestClient  # noqa: E402

from auth_local.middleware import get_current_user  # noqa: E402
from main import app  # noqa: E402


async def _ensure_char(novel_id: str) -> None:
    from db import async_session as _session
    from models.character import Character as _Character

    async with _session() as db:
        ch = (await db.execute(sel(_Character).where(_Character.novel_id == novel_id))).scalars().first()
        if ch is None:
            db.add(_Character(novel_id=novel_id, seq=1, name="洛九歌", role="反派"))
            await db.commit()


async def _char_id(novel_id: str) -> str:
    from db import async_session as _session
    from models.character import Character as _Character

    async with _session() as db:
        ch = (await db.execute(sel(_Character).where(_Character.novel_id == novel_id))).scalars().first()
        return ch.id


# 别名：批B 检测入口（run_organize 内同名函数；测试直接打它）
org_detect = org.detect_findings
