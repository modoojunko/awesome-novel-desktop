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

import json
import logging

from sqlalchemy import text as _t

logger = logging.getLogger(__name__)

_MARKER_PREFIX = "kb.reconcile:"


async def reconcile_deconstruct_versions(*, user_id: str) -> dict:
    """读面自愈入口：同书多版本素材收敛＋四维重收。返回 {book: 状态} 摘要。"""
    try:
        from db import async_session

        async with async_session() as db:
            return await _reconcile_on(db, user_id=user_id)
    except Exception:  # noqa: BLE001 — 读面永不因自愈失败红
        logger.warning("event=kb.reconcile_versions.fail user=%s", user_id, exc_info=True)
        return {}


async def _reconcile_on(db, *, user_id: str) -> dict:
    from kb.deconstruct_import import collect_task_to_kb, genre_from_products
    from kb.summarize import run_summarize
    from models.deconstruct import DeconstructJob

    books = (
        await db.execute(
            _t(
                "SELECT DISTINCT src_novel_name FROM kb_entries "
                "WHERE user_id=:u AND origin='material' AND src_kind='deconstruct' "
                "AND src_novel_name != '' "
                # 存量素材书名恒空（c-kb-collect-dims 前收录）——经任务行反查书名并入
                "UNION SELECT DISTINCT j.book_name FROM kb_entries e "
                "JOIN deconstruct_jobs j ON j.id=e.src_ref "
                "WHERE e.user_id=:u AND e.origin='material' AND e.src_kind='deconstruct' "
                "AND e.src_novel_name='' AND j.book_name!=''"
            ),
            {"u": user_id},
        )
    ).scalars().all()
    result: dict[str, str] = {}
    for book in books:
        # canonical＝已完成任务中章数最大（并列取新）
        jobs = (
            await db.execute(
                _t(
                    "SELECT id, chapter_count, products_json FROM deconstruct_jobs "
                    "WHERE book_name=:b AND status IN ('completed','imported') "
                    "ORDER BY chapter_count DESC, created_at DESC"
                ),
                {"b": book},
            )
        ).fetchall()
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
        mats = (
            await db.execute(
                _t(
                    "SELECT e.id, e.instruction, e.genre FROM kb_entries e "
                    "WHERE e.user_id=:u AND e.origin='material' AND e.src_kind='deconstruct' "
                    "AND (e.src_novel_name=:b OR e.src_ref IN "
                    "(SELECT id FROM deconstruct_jobs WHERE book_name=:b))"
                ),
                {"u": user_id, "b": book},
            )
        ).fetchall()
        instructions = [m[1] for m in mats if m[1]]
        genres = {m[2] for m in mats if m[2]}
        if instructions:
            await _delete_instances_by_texts(db, user_id, instructions)
        await db.execute(
            _t(
                "DELETE FROM kb_entries WHERE user_id=:u AND origin='material' "
                "AND src_kind='deconstruct' AND (src_novel_name=:b OR src_ref IN "
                "(SELECT id FROM deconstruct_jobs WHERE book_name=:b))"
            ),
            {"u": user_id, "b": book},
        )
        # 因拆除变空的总结知识点（同题材他书共用者有实例，保留）
        for g in genres:
            await db.execute(
                _t(
                    "DELETE FROM kb_entries WHERE user_id=:u AND origin='summary' "
                    "AND genre=:g AND NOT EXISTS ("
                    "SELECT 1 FROM kb_knowledge_instances i WHERE i.knowledge_id=kb_entries.id)"
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
