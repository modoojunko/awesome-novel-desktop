"""知识总结管线（c-kb-summarize）：实例素材 → 大模型定期自动整理 → 知识直接生效。

模型口径（boss 2026-11-06）：实例是事实层（素材 origin='material'），知识是总结层
（origin='summary'），图谱由总结生成——知识树（parent_id 无限嵌套）＋六类关联。

流程：素材按题材×类别分桶 → LLM 提炼知识点（名称/定义/层级归属/素材归组，管线层
三闸校验）→ **直接建知识＋素材转实例＋素材行归档**（无确认制——定期任务自动整理，
boss 拍板；兜底＝总结产的知识按普通知识管理，作家可改可删）。
运行独立落 kb_summarize_runs，同题材单飞；模板缺失 fail-soft 记 error。
触发：素材积压 ≥阈值启动期自动 / 整理面板手动 / 定期（>7 天且有素材随启动钩）。
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.kb import KbEntry, KbKnowledgeInstance

AUTO_MATERIAL_THRESHOLD = 5  # 素材积压自动触发阈值（题内）

async def ensure_kb_summarize(db: AsyncSession) -> dict[str, int]:
    """幂等 DDL：总结 runs/候选两表＋kb_entries.parent_id 列（知识树，c-kb-summarize 批E）。"""
    added = 0
    cols = [r[1] for r in (await db.execute(_t("PRAGMA table_info(kb_entries)"))).fetchall()]
    if "parent_id" not in cols:
        await db.execute(_t(
            "ALTER TABLE kb_entries ADD COLUMN parent_id TEXT NOT NULL DEFAULT ''"
        ))
        added += 1
    await db.execute(_t("""CREATE TABLE IF NOT EXISTS kb_summarize_runs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        genre TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'running',
        trigger TEXT NOT NULL DEFAULT '',
        materials_scanned INTEGER NOT NULL DEFAULT 0,
        knowledge_created INTEGER NOT NULL DEFAULT 0,
        error TEXT NOT NULL DEFAULT '',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""))
    await db.commit()
    return {"ddl": added}


def _t(sql: str):
    from sqlalchemy import text

    return text(sql)


# ─── 素材统计 ────────────────────────────────────────────────────────────


async def material_stats(db: AsyncSession, *, user_id: str) -> dict[str, int]:
    """各题材素材积压数（origin=material 且 active）。"""
    rows = (
        await db.execute(
            select(KbEntry.genre, func.count(KbEntry.id))
            .where(
                KbEntry.user_id == user_id,
                KbEntry.status == "active",
                KbEntry.origin == "material",
            )
            .group_by(KbEntry.genre)
        )
    ).all()
    return {g or "_general": int(n) for g, n in rows}


# ─── 核心跑一次总结 ──────────────────────────────────────────────────────


async def run_summarize(
    db: AsyncSession,
    *,
    user_id: str,
    genre: str,
    trigger: str,
    llm: bool = True,
) -> tuple[dict | None, str]:
    """总结一个题材：分桶素材 → LLM 提炼候选 → pending 清单。

    返回 (摘要 dict, error)；单飞命中返回 (None, "running")。
    llm=False 供测试走确定性路径（跳过 LLM，零候选直接 done）。
    """
    await ensure_kb_summarize(db)

    # 单飞：同题材 running 即跳过
    running = (
        await db.execute(_t(
            "SELECT id FROM kb_summarize_runs WHERE user_id=:u AND genre=:g AND status='running'"
        ), {"u": user_id, "g": genre})
    ).first()
    if running is not None:
        return None, "running"

    materials = (
        await db.execute(
            select(KbEntry).where(
                KbEntry.user_id == user_id,
                KbEntry.status == "active",
                KbEntry.origin == "material",
                KbEntry.genre == genre,
                KbEntry.concept != "情节",
            ).order_by(KbEntry.id)
        )
    ).scalars().all()
    if not materials:
        return {"collected": 0, "knowledge": 0}, ""

    run_id = uuid.uuid4().hex
    await db.execute(_t(
        "INSERT INTO kb_summarize_runs (id, user_id, genre, status, trigger, materials_scanned) "
        "VALUES (:i, :u, :g, 'running', :t, :n)"
    ), {"i": run_id, "u": user_id, "g": genre, "t": trigger, "n": len(materials)})
    await db.commit()

    # 既有知识清单（层级归属用）
    existing = (
        await db.execute(
            select(KbEntry.id, KbEntry.title).where(
                KbEntry.user_id == user_id,
                KbEntry.status == "active",
                KbEntry.origin != "material",
                KbEntry.genre == genre,
            ).order_by(KbEntry.id)
        )
    ).all()
    existing_lines = [f"{eid}|{title or ''}" for eid, title in existing]
    existing_ids = {eid for eid, _ in existing}

    error = ""
    candidates: list[dict] = []
    if llm and materials:
        candidates, error = await _llm_candidates(
            user_id, genre, materials, existing_lines, existing_ids
        )
        error = error or ""

    # 直接建知识（无确认制——定期任务自动整理，boss 拍板；兜底＝总结产的知识按
    # 普通知识管理：作家可修改可归档）。
    created = 0
    used_material_ids: set[str] = set()
    valid_concepts = {"文风", "文笔", "世界设定", "角色设定", "手法"}
    mat_ids = {m.id for m in materials}
    mats_by_id = {m.id: m for m in materials}
    for c in candidates:
        # 管线层三闸：素材归组须属本桶且未被本轮先行知识用掉、标题非空、
        # concept 白名单、parent 白名单（非法落概念根）
        mids = [m for m in (c.get("material_ids") or []) if m in mat_ids and m not in used_material_ids]
        if not mids or not (c.get("title") or "").strip():
            continue
        concept = c.get("concept") if c.get("concept") in valid_concepts else "手法"
        parent = c.get("parent", "ROOT")
        parent = parent if parent in existing_ids else ""

        kid = uuid.uuid4().hex
        db.add(KbEntry(
            id=kid,
            user_id=user_id,
            genre=genre,
            concept=concept,
            concept_id=f"{genre}:{concept}",
            title=c["title"].strip()[:40],
            payload_json="{}",
            instruction="",
            definition=(c.get("definition") or "").strip()[:500],
            origin="summary",
            status="active",
            version=1,
            parent_id=parent,
        ))
        for sort, mid in enumerate(mids):
            m = mats_by_id[mid]
            db.add(KbKnowledgeInstance(
                knowledge_id=kid,
                text=m.instruction or "",
                source_kind="拆书" if m.src_kind == "deconstruct" else "手录",
                source_novel=m.src_novel_name or "",
                quote=(m.evidence or "")[:500],
                sort=sort,
            ))
            m.status = "archived"  # 素材行归档（审计可回溯）
            used_material_ids.add(mid)
        created += 1

    status = "error" if error else "completed"
    await db.execute(
        _t(
            "UPDATE kb_summarize_runs SET status=:s, knowledge_created=:n, error=:e WHERE id=:i"
        ),
        {"s": status, "n": created, "e": error, "i": run_id},
    )
    await db.commit()
    return {"collected": len(materials), "knowledge": created}, error


async def _llm_candidates(
    user_id: str, genre: str, materials: list, existing_lines: list[str], existing_ids: set[str]
) -> tuple[list[dict], str | None]:
    """调 kb_summarize 模板提炼候选。返回 (候选列表, error)。"""
    try:
        from ai_client import get_ai_client_for_user
        from prompts import load_layers

        system, prompt = load_layers("kb_summarize")
    except Exception as e:  # noqa: BLE001 — 模板缺失 fail-soft（同 kb_organize 先例）
        return [], f"prompt_pack: {e}"

    lines = [
        f"{m.id}|{m.concept}|{(m.title or '')[:24]}|{(m.instruction or '')[:120]}"
        for m in materials
    ]
    usage: dict = {}
    try:
        client = await get_ai_client_for_user(user_id)
        text = await client.chat(
            model="haiku",
            system=system.format(genre=genre),
            messages=[{"role": "user", "content": prompt.format(
                genre=genre, materials="\n".join(lines), existing="\n".join(existing_lines) or "（无）",
            )}],
            max_tokens=3000,
            usage=usage,
            operation="kb_summarize",
        )
    except Exception as e:  # noqa: BLE001
        return [], f"llm: {e}"

    valid_concepts = {"文风", "文笔", "世界设定", "角色设定", "手法"}
    mat_ids = {m.id for m in materials}
    try:
        data = json.loads(text or "{}")
        cands = data.get("candidates") or []
        out: list[dict] = []
        for c in cands if isinstance(cands, list) else []:
            if not isinstance(c, dict):
                continue
            mids = [m for m in (c.get("material_ids") or []) if m in mat_ids]
            if not mids or not (c.get("title") or "").strip():
                continue  # 素材归属须属本桶、标题非空
            parent = c.get("parent", "ROOT")
            out.append({
                "title": c["title"].strip()[:40],
                "definition": (c.get("definition") or "").strip()[:500],
                "concept": c.get("concept") if c.get("concept") in valid_concepts else "手法",
                "parent": parent if parent in existing_ids else "",
                "material_ids": mids,
            })
        return out, None
    except ValueError:
        return [], "llm: bad json"


# ─── 候选清单与采纳/忽略 ────────────────────────────────────────────────


async def maybe_auto_summarize(*, user_id: str) -> list[str]:
    """启动钩：素材积压 ≥ 阈值的题材各自动总结一次（llm=True；失败静默）。

    自开 session（同 organize startup 钩先例，lifespan 直接 await）。
    """
    from db import async_session

    async with async_session() as db:
        return await _maybe_auto_summarize(db, user_id=user_id)


async def _last_run_older_than_days(
    db: AsyncSession, *, user_id: str, genre: str, days: int
) -> bool:
    """该题材距上次总结是否超过 days 天（无运行记录＝视为超期，定期兜底触发）。"""
    row = (
        await db.execute(
            _t(
                "SELECT created_at FROM kb_summarize_runs "
                "WHERE user_id=:u AND genre=:g AND status='completed' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"u": user_id, "g": genre},
        )
    ).first()
    import os as _os
    if _os.environ.get("KBSM_DEBUG"):
        print("DEBUG last_run row:", repr(tuple(row) if row else None))
    if row is None:
        return True
    from datetime import UTC, datetime, timedelta

    try:
        last = datetime.fromisoformat(str(row[0]))
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        return datetime.now(UTC) - last > timedelta(days=days)
    except ValueError:
        return True


async def _maybe_auto_summarize(db: AsyncSession, *, user_id: str) -> list[str]:
    stats = await material_stats(db, user_id=user_id)
    triggered: list[str] = []
    for genre, n in sorted(stats.items()):
        due = n >= AUTO_MATERIAL_THRESHOLD or await _last_run_older_than_days(db, user_id=user_id, genre=genre, days=7)
        if not due:
            continue
        try:
            _run, err = await run_summarize(db, user_id=user_id, genre=genre, trigger="auto", llm=True)
            if err not in ("", "running"):
                continue
            triggered.append(genre)
        except Exception as exc:  # noqa: BLE001 — 自动钩失败静默（下次启动重试），留痕不抛
            import logging

            logging.getLogger("uvicorn.error").warning(
                "kb summarize auto trigger failed for %s: %s", genre, exc,
            )
            continue
    return triggered
