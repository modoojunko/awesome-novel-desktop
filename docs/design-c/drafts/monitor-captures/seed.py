# -*- coding: utf-8 -*-
"""种监控演示数据：deconstruct_jobs(running)＋deconstruct_units（真形状，镜像参考截图）。

前置：后端须先以同款 env boot 一次（DB 世代守卫——先种库再起后端会被隔离成
.mismatch-<ts>）；本脚本只做数据直插（create_all 幂等）。DATA_ROOT/DATABASE_URL
默认 /tmp/decmon-data（私有草稿区，不触主检出库）；TID 须与 capture-detail.cjs 一致。
含 2 条 running 单元行（在途/「● 进行中」行的真渲染数据源）。
"""
import json
import os
from datetime import datetime, timedelta, UTC

os.environ.setdefault("DATA_ROOT", "/tmp/decmon-data")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:////tmp/decmon-data/proto.db")
os.environ.setdefault("DECONSTRUCT_DISPATCHER_OFF", "1")

import asyncio
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "client", "backend"))


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _go():
    from db import Base, async_session, engine
    from models.deconstruct import DeconstructJob, DeconstructUnit
    from deconstruct.service import source_path_of

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    now = datetime.now(UTC).replace(tzinfo=None)
    TID = "dec-mon-proto-1"

    def ago(sec):
        return now - timedelta(seconds=sec)

    cards = {"state": "completed", "done": 258, "total": 258, "started_at": ago(8 * 3600).isoformat()}
    dims = {
        "intro": {"state": "completed", "seg_done": 3, "seg_total": 3},
        "genre": {"state": "completed", "seg_done": 1, "seg_total": 1},
        "world": {"state": "completed", "seg_done": 4, "seg_total": 6},
        "characters": {"state": "completed", "seg_done": 15, "seg_total": 22},
        "relations": {"state": "completed", "seg_done": 4, "seg_total": 6},
        "mainplot": {"state": "completed", "seg_done": 5, "seg_total": 6},
        "structure": {"state": "completed", "seg_done": 3, "seg_total": 3},
        "style": {"state": "completed", "seg_done": 4, "seg_total": 4},
        "techniques": {"state": "completed", "seg_done": 4, "seg_total": 5},
        "foreshadow": {"state": "running", "seg_done": 6, "seg_total": 7,
                        "started_at": ago(1200).isoformat()},
    }
    activity = {"label": "正在收束 伏笔", "at": ago(90).isoformat()}
    dims_json = json.dumps({"cards": cards, "dims": dims, "activity": activity}, ensure_ascii=False)

    async with async_session() as s:
        s.add(DeconstructJob(
            id=TID, user_id="proto", status="running", queue_seq=1,
            book_name="13路末班车", source_path=source_path_of(TID),
            encoding="utf-8", api_config_id="cfg-proto", ai_model="deepseek-v4.1-flash",
            selected_dims_json=json.dumps(["intro", "genre", "world", "characters", "relations",
                                           "mainplot", "structure", "style", "techniques", "foreshadow"]),
            total_chars=820000, chapter_count=258, volume_count=12,
            dims_json=dims_json, products_json="{}",
        ))
        # 单元账：l1 49/63（含 2 failed）＋近期流水若干（速度窗内/外混布）
        rows = []
        n = 0
        def u(stage, status, mins_ago, dur_ms, tok, kind="", dim="foreshadow", ukey=None, tok_in=0):
            nonlocal n
            n += 1
            rows.append(DeconstructUnit(
                task_id=TID, stage=stage, dim=dim,
                unit_key=ukey or f"{stage}-{n:03d}",
                status=status, attempts=1, error_kind=kind,
                duration_ms=dur_ms, tokens_out=tok, tokens_in=tok_in,
                created_at=ago(mins_ago * 60), updated_at=ago(mins_ago * 60),
            ))
        # 在途（派发未完）：调度即现——「在途 2」＋流水置顶「● 进行中」
        u("l1", "running", 0.3, 0, 0, dim="foreshadow")
        u("card", "running", 0.8, 0, 0, dim="", ukey="142")
        # l1 归并批：49 行（2 failed invalid_output）
        for i in range(12):
            u("l1", "failed" if i % 6 == 5 else "done", 1.2 + i * 2.3,
              130000 + i * 4300, 62000 + i * 2400,
              kind="invalid_output" if i % 6 == 5 else "", tok_in=41000 + i * 1300)
        for i in range(6):
            u("l1", "done", 25 + i * 4, 140000 + i * 2100, 55000 + i * 1800)
        for i in range(31):
            u("l1", "done", 70 + i * 7.5, 120000 + (i % 9) * 5200, 48000 + (i % 7) * 2300)
        # 拆卡：早前完成
        for i in range(8):
            u("card", "done", 300 + i * 9, 42000 + (i % 5) * 3100, 21000 + i * 900)
        u("card", "failed", 420, 38000, 0, kind="content_filter")
        # 收敛与其他阶段
        for i in range(4):
            u("reduce", "done", 6 + i * 3, 95000 + i * 4100, 88000 + i * 3200)
        u("place", "done", 33, 51000, 30000)
        u("presence", "done", 44, 47000, 26000)
        # reduce_state 检查点（不进账）
        for i in range(3):
            u("reduce_state", "done", 5 + i, 0, 0)
        for r in rows:
            s.add(r)
        await s.commit()
    print("seeded", TID, "units:", len(rows))


_run(_go())
