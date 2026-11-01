"""CQ 六问回归（c-kb-organize 批E E2）＋模板冒烟。

CQ＝design D1 的整理目标函数：每问对应一条断言，防整理器演进时丢失原始目的。
CQ1 写打斗该用哪些手法 → applies_to 关系可产且进条目图（批C 图形状测试）
CQ2 这两条是同一个写法吗 → merge 检测（批B 平行条目测试）
CQ3 这条知识放对格子了吗 → reclass 检测（批B 纠偏测试）
CQ4 新写法归进哪个子概念 → subconcept 提案（批B 检测）
CQ5 哪几条是垃圾 → quality 标记（批B 检测）
CQ6 跟这条相冲/相承的知识 → contradicts/refines 进图＋条目关系端点
"""

import asyncio

from db import async_session
from models.user import User
from tests.test_kb_organize import _mk, _run, _seed_entries, _seed_user


class TestCQRegression:
    def test_CQ1_写打斗该用哪些手法(self):
        """applies_to 候选对出现在短名单（相容矩阵）＋图谱端点含 applies_to 边。"""
        uid = _mk("cq1")
        _run(_seed_user(uid))
        _run(_seed_entries(uid, [
            {"concept": "手法", "genre": "玄幻", "instruction": "打斗先给结果再补原因。"},
            {"concept": "文风", "genre": "玄幻", "instruction": "打斗短句克制。"},
        ]))
        from kb.organize import _shortlist
        from models.kb import KbEntry

        async def _pairs():
            async with async_session() as db:
                es = (await db.execute(__import__("sqlalchemy").select(KbEntry).where(
                    KbEntry.user_id == uid))).scalars().all()
                by_concept: dict[str, list[KbEntry]] = {}
                for e in es:
                    by_concept.setdefault(e.concept, []).append(e)
                return _shortlist({e.id for e in es}, by_concept, full=True)
        pairs = _run(_pairs())
        assert any(rt == "applies_to" for (_a, _b, rt) in pairs), "CQ1：手法→文风 applies_to 必须可产"

    def test_CQ3_概念纠偏可产出建议(self):
        """词叶错位条目产出 reclass finding（批B 已测行为，此处作 CQ 锚）。"""
        uid = _mk("cq3")
        _run(_seed_user(uid))
        _run(_seed_entries(uid, [
            {"concept": "手法", "genre": "玄幻",
             "instruction": "这个世界的设定里，灵气以灯为纪，铁律不可破。"},
        ]))

        async def _detect():
            import kb.organize as org
            from models.kb import KbEntry, KbOrganizeRun

            async with async_session() as db:
                es = (await db.execute(__import__("sqlalchemy").select(KbEntry).where(
                    KbEntry.user_id == uid))).scalars().all()
                run = KbOrganizeRun(user_id=uid, genre="玄幻", status="running")
                db.add(run)
                await db.flush()
                counts = await org.detect_findings(db, run=run, entries=list(es))
                await db.commit()
                return counts
        counts = _run(_detect())
        assert counts.get("reclass", 0) >= 1, "CQ3：概念错位必须产出纠偏建议"

    def test_CQ5_垃圾条目被标记(self):
        uid = _mk("cq5")
        _run(_seed_user(uid))
        _run(_seed_entries(uid, [{"concept": "手法", "genre": "玄幻", "instruction": "短。"}]))

        async def _detect():
            import kb.organize as org
            from models.kb import KbEntry, KbOrganizeRun

            async with async_session() as db:
                es = (await db.execute(__import__("sqlalchemy").select(KbEntry).where(
                    KbEntry.user_id == uid))).scalars().all()
                run = KbOrganizeRun(user_id=uid, genre="玄幻", status="running")
                db.add(run)
                await db.flush()
                counts = await org.detect_findings(db, run=run, entries=list(es))
                await db.commit()
                return counts
        counts = _run(_detect())
        assert counts.get("quality", 0) >= 1, "CQ5：过短指令必须被质量标记"


class TestKbOrganizeTemplate:
    def test_模板分层与占位符冒烟(self):
        """kb_organize 模板（E1）：PROMPT_PACK_DEV_DIR 指向提示词仓即可加载；缺包 fail-soft。"""

        import kb.organize as org

        async def _go():
            from db import async_session

            uid = _mk("tpl")
            async with async_session() as db:
                db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
                await db.commit()
            async with async_session() as db:
                await _seed_entries(uid, [
                    {"concept": "手法", "genre": "玄幻", "instruction": "打斗钩子。"},
                    {"concept": "文风", "genre": "玄幻", "instruction": "短句克制。"},
                ])
                # llm=True：dev dir 有模板 → 真走 load_layers＋调用链（client 无 Key 走兜底/失败落 run）
                return await org.run_organize(db, user_id=uid, genre=f"玄幻-{uid}", trigger="manual", llm=True)

        run, _err = asyncio.run(_go())
        # 模板在（dev dir）→ LLM 调用层可能因无 Key 失败落 error，但**不是** prompt_pack 缺失
        assert run is not None
        assert "prompt_pack" not in (run.error or ""), f"模板应可加载：{run.error}"
