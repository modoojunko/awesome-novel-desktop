"""知识库万级数据性能回归（tasks 1.16）：列表/搜索/题材计数/游标深翻页。

10 万行 sqlite 实测口径（宽松阈值为防抖动的回归闸，非基准跑分）；
行用 Core 批插（绕过 ORM 逐条 flush），隔离 user 不污染他测。
"""

import asyncio
import time
import uuid

from sqlalchemy import insert

from db import async_session
from models.kb import KbEntry, KbEntryTag
from models.user import User

N = 100_000
CONCEPTS = ("文风", "文笔", "世界设定", "角色设定", "手法")


def _run(coro):
    return asyncio.run(coro)


async def _seed() -> dict:
    uid = f"kbperf-{uuid.uuid4().hex[:8]}"
    async with async_session() as db:
        db.add(User(
            id=uid, email=f"{uid}@t.local", password_hash="x", display_name="性能测试",
            api_key="", api_base_url="", api_model="",
        ))
        await db.commit()
        rows = []
        tags = []
        for i in range(N):
            eid = f"{uid}-{i:06d}"
            concept = CONCEPTS[i % len(CONCEPTS)]
            rows.append({
                "id": eid,
                "user_id": uid,
                "genre": "都市" if i % 2 == 0 else "悬疑",
                "concept": concept,
                "concept_id": f"都市:{concept}",
                "title": f"条目{i}——{concept}写法",
                "payload_json": '{"slot": "rule", "rule": "x"}',
                "instruction": f"第{i}条指令，句末断。" + ("独门钩子打斗" if i % 500 == 7 else ""),
                "when_json": "{}",
                "src_kind": "manual",
            })
            tags.append({"entry_id": eid, "user_id": uid, "dim": "concept", "value": concept})
        # Core 批插：500 一批
        for start in range(0, N, 500):
            await db.execute(insert(KbEntry), rows[start:start + 500])
        for start in range(0, N, 2000):
            await db.execute(insert(KbEntryTag), tags[start:start + 2000])
        await db.commit()
        return {"uid": uid}


def test_十万级_列表_搜索_计数_深翻页():
    seed = _run(_seed())
    from kb.service import genre_counts, list_entries

    async def _go():
        async with async_session() as db:
            t0 = time.monotonic()
            page1, cursor = await list_entries(db, user_id=seed["uid"], limit=30)
            t_list = time.monotonic() - t0

            t1 = time.monotonic()
            hits, _ = await list_entries(db, user_id=seed["uid"], q="独门钩子", limit=30)
            t_search = time.monotonic() - t1

            t2 = time.monotonic()
            page2, _c2 = await list_entries(db, user_id=seed["uid"], cursor=cursor, limit=30)
            t_page2 = time.monotonic() - t2

            t3 = time.monotonic()
            counts = await genre_counts(db, user_id=seed["uid"])
            t_counts = time.monotonic() - t3

            # 深翻页：连跳 100 页到 5 万行深处
            t4 = time.monotonic()
            cur = ""
            for _ in range(100):
                rows, cur = await list_entries(db, user_id=seed["uid"], cursor=cur, limit=500)
                if not rows:
                    break
            t_deep = time.monotonic() - t4
            return page1, hits, page2, counts, (t_list, t_search, t_page2, t_counts, t_deep)

    page1, hits, page2, counts, times = _run(_go())
    t_list, t_search, t_page2, t_counts, t_deep = times
    assert len(page1) == 30
    assert len(page2) == 30
    assert page2[0].id != page1[0].id  # 游标推进
    assert len(hits) == 30 and all("独门钩子" in h.instruction for h in hits)
    assert counts["都市"] == N // 2 and counts["悬疑"] == N - N // 2
    # 宽松回归闸（本机毫秒级，CI 波动留足余量）
    assert t_list < 5, f"首页列表 {t_list:.2f}s"
    assert t_search < 8, f"全文搜索 {t_search:.2f}s"
    assert t_page2 < 5, f"第二页 {t_page2:.2f}s"
    assert t_counts < 5, f"题材计数 {t_counts:.2f}s"
    assert t_deep < 30, f"百页深翻 {t_deep:.2f}s"


def test_十万级_整理预筛与打分预算():
    """c-kb-organize A9：10 万级题材下，增量整理的预筛＋特征打分路径过预算闸。

    只跑确定性路径（llm=False＝候选空，预筛/打分骨架全走）；
    证明增量对＋桶 cap 使 organize 不因全库规模退化。
    """
    from sqlalchemy import select as _sel

    from db import async_session
    from kb.organize import run_organize, startup_sweep_and_maybe_run
    from models.kb import KbOrganizeRun, KbRelation
    from models.user import User

    uid = f"orgaperf-{uuid.uuid4().hex[:8]}"

    async def _seed():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="整理性能"))
            rows = []
            tags = []
            for i in range(N):
                eid = f"{uid}-{i:06d}"
                concept = CONCEPTS[i % len(CONCEPTS)]
                rows.append({
                    "id": eid, "user_id": uid,
                    "genre": "都市" if i % 2 == 0 else "悬疑",
                    "concept": concept, "concept_id": f"都市:{concept}",
                    "title": f"条目{i}", "payload_json": "{}",
                    "instruction": f"第{i}条整理指令。", "when_json": "{}", "src_kind": "manual",
                })
                tags.append({"entry_id": eid, "user_id": uid, "dim": "concept", "value": concept})
            for start in range(0, N, 500):
                await db.execute(insert(KbEntry), rows[start:start + 500])
            for start in range(0, N, 2000):
                await db.execute(insert(KbEntryTag), tags[start:start + 2000])
            await db.commit()
    _run(_seed())

    t0 = time.monotonic()
    run, err = _run(_run_with_session(lambda db: run_organize(
        db, user_id=uid, genre="都市", trigger="manual", llm=False)))
    t_elapsed = time.monotonic() - t0
    assert err == "" and run.status == "completed"
    # 宽松回归闸（非跑分）：预筛＋打分骨架在 10 万级条目上秒级完成
    assert t_elapsed < 30, f"organize 预算爆了：{t_elapsed:.1f}s"
    # 关系零候选（llm=False）→ 无 active 边；run 计数在
    async def _check():
        async with async_session() as db:
            rels = (await db.execute(_sel(KbRelation).where(KbRelation.user_id == uid))).scalars().all()
            runs = (await db.execute(_sel(KbOrganizeRun).where(KbOrganizeRun.user_id == uid))).scalars().all()
            return len(rels), runs[-1].entries_scanned if runs else 0
    n_rels, scanned = _run(_check())
    assert n_rels == 0 and scanned == N // 2  # 都市半库

    # 启动钩（sweep＋保留）在 10 万级不炸不超时
    t3 = time.monotonic()
    _run(startup_sweep_and_maybe_run())
    assert time.monotonic() - t3 < 30


def _run_with_session(fn):
    async def _go():
        async with async_session() as db:
            return await fn(db)
    return _go()
