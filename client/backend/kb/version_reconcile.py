"""拆书版本收敛（c-kb-collect-dims，2026-11-07）：同书以全本任务为准重建收录。

病形（真机斩神/749 实锤）：同一本书先试拆（前 N 章）后全本，收卡各收各的——
幂等键带任务 id，跨任务永不撞键 → 双版本素材并存（749 两版 72 份）、全本只收
8/26 角色；且存量收卡发生在四维映射上线前，文风/文笔/手法/世界从未入库。

修法＝**推倒重收**（读面自愈挂点，幂等、失败不抛）：
1. 按书分组找 canonical 任务（completed 中章数最大，并列取新）；
2. 拆除该书全部拆书素材＋由其转生的实例（summarize 转生时 text=素材 instruction
   原样复制——匹配确定）；清掉因此变空的知识点（同题材他书共用者保留）；
3. 用**现行四维映射**重收 canonical 产物（文风/文笔/手法/世界/角色全量）；
4. 对该书题材重跑总结（素材→实例→知识点，素材归档）；
5. app_meta 记 book→canonical 标记，重跑幂等跳过。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from sqlalchemy import bindparam
from sqlalchemy import text as _t

logger = logging.getLogger(__name__)

# v5：锚正则类补分隔符（第9、56、57章 多章形 v4 闭形仍剥不动——168 中 81 条的真正根因）
# ＋裸串条目无名化＋锚全文任意位置剥出；v6 起含并发单飞锁
# 每次映射/总结语义变更都升版强制重收敛一次
_MARKER_PREFIX = "kb.reconcile:v11:"

# 进程内单飞（真机 2026-11-08 实锤：页面加载＋探针并发命中 /kb/instances → 双收敛并发
# 写同书同键 → UNIQUE 撞键整轮失败）——后跑者等锁，醒来时标记已落即快路返回
_USER_LOCKS: dict[str, asyncio.Lock] = {}


def _user_lock(user_id: str) -> asyncio.Lock:
    return _USER_LOCKS.setdefault(user_id, asyncio.Lock())

_TRIAL_SUFFIX = re.compile(r"-前\d+章$")


def _norm_book(name: str) -> str:
    """书名归一：剥试拆后缀（斩神-前30章 → 斩神）——试拆与全本同书收敛。"""
    return _TRIAL_SUFFIX.sub("", str(name or "").strip())


async def reconcile_deconstruct_versions(*, user_id: str) -> dict:
    """读面自愈入口：同书多版本素材收敛＋四维重收。返回 {book: 状态} 摘要。"""
    try:
        from db import async_session

        async with _user_lock(user_id), async_session() as db:
            return await _reconcile_on(db, user_id=user_id)
    except Exception:  # noqa: BLE001 — 读面永不因自愈失败红
        logger.warning("event=kb.reconcile_versions.fail user=%s", user_id, exc_info=True)
        return {}


async def _reconcile_on(db, *, user_id: str) -> dict:
    from kb.deconstruct_import import collect_task_to_kb, genre_from_products
    from kb.summarize import run_summarize
    from models.deconstruct import DeconstructJob

    # 书名归一分组（斩神-前30章 与 斩神 同组）——归一在 Python 侧（SQLite 无正则 REPLACE）
    raw_books = (
        await db.execute(
            _t(
                "SELECT DISTINCT src_novel_name FROM kb_entries "
                "WHERE user_id=:u AND origin='material' AND src_kind='deconstruct' "
                "AND src_novel_name != '' "
                "UNION SELECT DISTINCT j.book_name FROM kb_entries e "
                "JOIN deconstruct_jobs j ON j.id=e.src_ref "
                "WHERE e.user_id=:u AND e.origin='material' AND e.src_kind='deconstruct' "
                "AND (e.src_novel_name='' OR e.src_novel_name LIKE '%前_%章') AND j.book_name!=''"
            ),
            {"u": user_id},
        )
    ).scalars().all()
    books = sorted({_norm_book(b) for b in raw_books})
    result: dict[str, str] = {}
    for book in books:
        # canonical＝已完成任务中章数最大（并列取新）
        jobs = (
            await db.execute(
                _t(
                    "SELECT id, chapter_count, products_json, book_name FROM deconstruct_jobs "
                    "WHERE status IN ('completed','imported') "
                    "ORDER BY chapter_count DESC, created_at DESC"
                )
            )
        ).fetchall()
        jobs = [j for j in jobs if _norm_book(j[3]) == book]
        if not jobs:
            result[book] = "no_job"  # 指纹收录等无任务行的书不动
            continue
        canonical_id = jobs[0][0]

        marked = (
            await db.execute(
                _t("SELECT value FROM app_meta WHERE key=:k"),
                {"k": _MARKER_PREFIX + book},
            )
        ).scalar_one_or_none()
        if marked == canonical_id:
            result[book] = "current"
            continue

        # ── 拆除：该书素材 + 转生实例（text=instruction 匹配）+ 空知识点 ──
        group_refs = [j[0] for j in jobs]
        group_names = {j[3] for j in jobs} | {book}
        mats = (
            await db.execute(
                _t(
                    "SELECT e.id, e.instruction, e.genre FROM kb_entries e "
                    "WHERE e.user_id=:u AND e.origin='material' AND e.src_kind='deconstruct' "
                    "AND (e.src_novel_name IN :names OR e.src_ref IN :refs)"
                ).bindparams(bindparam("names", expanding=True),
                             bindparam("refs", expanding=True)),
                {"u": user_id, "names": sorted(group_names), "refs": group_refs},
            )
        ).fetchall()
        instructions = [m[1] for m in mats if m[1]]
        genres = {m[2] for m in mats if m[2]}
        if instructions:
            await _delete_instances_by_texts(db, user_id, instructions)
        await db.execute(
            _t(
                "DELETE FROM kb_entries WHERE user_id=:u AND origin='material' "
                "AND src_kind='deconstruct' AND (src_novel_name IN :names OR src_ref IN :refs)"
            ).bindparams(bindparam("names", expanding=True),
                         bindparam("refs", expanding=True)),
            {"u": user_id, "names": sorted(group_names), "refs": group_refs},
        )
        # 因拆除变空的总结知识点（同题材他书共用者有实例，保留）
        for g in genres:
            await db.execute(
                _t(
                    "DELETE FROM kb_entries WHERE user_id=:u AND origin='summary' "
                    "AND genre=:g AND NOT EXISTS ("
                    "SELECT 1 FROM kb_knowledge_instances i WHERE i.knowledge_id=kb_entries.id) "
                    "AND NOT EXISTS (SELECT 1 FROM kb_entries c WHERE c.parent_id=kb_entries.id)"
                ),
                {"u": user_id, "g": g},
            )
        await db.commit()

        # ── 重收 canonical（现行四维映射）＋ 重跑总结 ──
        task = await db.get(DeconstructJob, canonical_id)
        status = "rebuilt"
        if task is None:
            status = "job_missing"
        else:
            try:
                products = json.loads(task.products_json or "{}")
                genre = genre_from_products(products) if products else ""
                await collect_task_to_kb(db, user_id, task)
                if genre:
                    _r, err = await run_summarize(db, user_id=user_id, genre=genre, trigger="reconcile")
                    if err:
                        status = f"summarize:{err}"
            except Exception as exc:  # noqa: BLE001 — 单书失败不拖垮整体
                logger.warning("event=kb.reconcile_versions.book_fail book=%s err=%s", book, exc)
                status = "collect_fail"
                # 失败会话带着未决事务——先回滚再走标记写入；失败不落 canonical 标记
                # （下次触达整书重试，不把半成品钉成「已完成」）
                await db.rollback()
        if status != "collect_fail":
            await db.execute(
                _t(
                    "INSERT OR REPLACE INTO app_meta (key, value) VALUES (:k, :v)"
                ),
                {"k": _MARKER_PREFIX + book, "v": canonical_id},
            )
            await db.commit()
        result[book] = status
    return result


async def _delete_instances_by_texts(db, user_id: str, texts: list[str]) -> None:
    """按实例正文批量删（SQLite IN 列表分片，防超变量上限）。"""
    for i in range(0, len(texts), 200):
        chunk = texts[i : i + 200]
        placeholders = ",".join(f":t{i}" for i in range(len(chunk)))
        await db.execute(
            _t(
                "DELETE FROM kb_knowledge_instances WHERE id IN ("
                "SELECT i.id FROM kb_knowledge_instances i "
                f"JOIN kb_entries e ON e.id=i.knowledge_id "
                f"WHERE e.user_id=:u AND i.text IN ({placeholders}))"
            ),
            {"u": user_id, **{f"t{i}": t for i, t in enumerate(chunk)}},
        )
