"""知识总结管线（c-kb-summarize）：实例素材 → 大模型提炼候选知识 → 确认制采纳。

模型口径（boss 2026-11-06）：实例是事实层（素材 origin='material'），知识是总结层
（origin='summary'），图谱由总结生成——知识树（parent_id 无限嵌套）＋六类关联。

流程：素材按题材×类别分桶 → LLM 提炼候选（名称/定义/层级归属/素材归组）→
候选 pending 清单 → 作家逐条采纳（建知识＋素材转实例＋素材行归档）或忽略。
运行独立落 kb_summarize_runs，同题材单飞；模板缺失 fail-soft 记 error。
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
        candidates_created INTEGER NOT NULL DEFAULT 0,
        error TEXT NOT NULL DEFAULT '',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""))
    await db.execute(_t("""CREATE TABLE IF NOT EXISTS kb_summarize_candidates (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        genre TEXT NOT NULL DEFAULT '',
        concept TEXT NOT NULL DEFAULT '',
        proposed_title TEXT NOT NULL DEFAULT '',
        proposed_definition TEXT NOT NULL DEFAULT '',
        parent_knowledge_id TEXT NOT NULL DEFAULT '',
        material_ids TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'pending',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""))
    await db.execute(_t(
        "CREATE INDEX IF NOT EXISTS ix_kb_summarize_candidates_user "
        "ON kb_summarize_candidates (user_id, status)"
    ))
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
        return {"collected": 0, "candidates": 0}, ""

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

    created = 0
    valid_concepts = {"文风", "文笔", "世界设定", "角色设定", "手法"}
    mat_ids = {m.id for m in materials}
    for c in candidates:
        # 管线层三闸（不依赖传输层自觉）：素材归组须属本桶、标题非空、concept 白名单、
        # parent 白名单（非法落概念根）
        mids = [m for m in (c.get("material_ids") or []) if m in mat_ids]
        if not mids or not (c.get("title") or "").strip():
            continue
        concept = c.get("concept") if c.get("concept") in valid_concepts else "手法"
        parent = c.get("parent", "ROOT")
        parent = parent if parent in existing_ids else ""
        await db.execute(
            _t(
                "INSERT INTO kb_summarize_candidates "
                "(id, run_id, user_id, genre, concept, proposed_title, proposed_definition, "
                "parent_knowledge_id, material_ids, status) "
                "VALUES (:i, :r, :u, :g, :c, :t, :d, :p, :m, 'pending')"
            ),
            {
                "i": uuid.uuid4().hex, "r": run_id, "u": user_id, "g": genre,
                "c": concept[:12],
                "t": c["title"].strip()[:40],
                "d": (c.get("definition") or "").strip()[:500],
                "p": parent,
                "m": json.dumps(mids, ensure_ascii=False),
            },
        )
        created += 1

    status = "error" if error else "completed"
    await db.execute(
        _t(
            "UPDATE kb_summarize_runs SET status=:s, candidates_created=:n, error=:e WHERE id=:i"
        ),
        {"s": status, "n": created, "e": error, "i": run_id},
    )
    await db.commit()
    return {"collected": len(materials), "candidates": created}, error


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


async def pending_candidates(db: AsyncSession, *, user_id: str, genre: str = "") -> list[dict]:
    sql = (
        "SELECT id, genre, concept, proposed_title, proposed_definition, "
        "parent_knowledge_id, material_ids, created_at FROM kb_summarize_candidates "
        "WHERE user_id=:u AND status='pending'"
    )
    params: dict = {"u": user_id}
    if genre:
        sql += " AND genre=:g"
        params["g"] = genre
    sql += " ORDER BY created_at, id"
    rows = (await db.execute(_t(sql), params)).mappings().all()
    out = []
    for r in rows:
        mids = json.loads(r["material_ids"] or "[]")
        titles = {}
        if mids:
            mat_rows = (
                await db.execute(
                    select(KbEntry.id, KbEntry.title).where(KbEntry.id.in_(mids))
                )
            ).all()
            titles = {eid: t or "" for eid, t in mat_rows}
        out.append({
            "id": r["id"], "genre": r["genre"], "concept": r["concept"],
            "proposed_title": r["proposed_title"],
            "proposed_definition": r["proposed_definition"],
            "parent_knowledge_id": r["parent_knowledge_id"],
            "materials": [
                {"id": m, "title": titles.get(m, m), "available": m in titles} for m in mids
            ],
        })
    return out


async def adopt_candidate(
    db: AsyncSession, *, user_id: str, candidate_id: str
) -> tuple[bool, str]:
    """采纳候选：建知识（origin=summary）＋素材转实例＋素材行归档＋候选 adopted。

    素材已被先前采纳用尽的候选拒绝采纳（提示已无素材）。
    """
    await ensure_kb_summarize(db)
    row = (
        await db.execute(
            _t("SELECT * FROM kb_summarize_candidates WHERE id=:i AND user_id=:u AND status='pending'"),
            {"i": candidate_id, "u": user_id},
        )
    ).mappings().first()
    if row is None:
        return False, "not_found"

    mids = json.loads(row["material_ids"] or "[]")
    mats = (
        await db.execute(
            select(KbEntry).where(
                KbEntry.id.in_(mids),
                KbEntry.user_id == user_id,
                KbEntry.origin == "material",
                KbEntry.status == "active",
            ).order_by(KbEntry.id)
        )
    ).scalars().all()
    if not mats:
        await db.execute(_t("UPDATE kb_summarize_candidates SET status='dismissed' WHERE id=:i"),
                   {"i": candidate_id})
        await db.commit()
        return False, "no_materials"

    genre = row["genre"]
    concept = row["concept"] or mats[0].concept
    parent = row["parent_knowledge_id"] or ""
    if parent:
        p_row = (
            await db.execute(
                select(KbEntry).where(
                    KbEntry.id == parent, KbEntry.user_id == user_id,
                    KbEntry.origin != "material", KbEntry.status == "active",
                )
            )
        ).scalar_one_or_none()
        if p_row is None:
            parent = ""  # 父知识已不可达：落概念根

    kid = uuid.uuid4().hex
    db.add(KbEntry(
        id=kid,
        user_id=user_id,
        genre=genre,
        concept=concept,
        concept_id=f"{genre}:{concept}",
        title=row["proposed_title"] or "未命名知识",
        payload_json="{}",
        instruction="",
        definition=row["proposed_definition"] or "",
        origin="summary",
        status="active",
        version=1,
        parent_id=parent,
    ))
    for sort, m in enumerate(mats):
        db.add(KbKnowledgeInstance(
            knowledge_id=kid,
            text=m.instruction or "",
            source_kind="拆书" if m.src_kind == "deconstruct" else "手录",
            source_novel=m.src_novel_name or "",
            quote=(m.evidence or "")[:500],
            sort=sort,
        ))
        m.status = "archived"  # 素材行归档（审计可回溯）
    await db.execute(_t("UPDATE kb_summarize_candidates SET status='adopted' WHERE id=:i"),
               {"i": candidate_id})
    await db.commit()
    return True, ""


async def dismiss_candidate(
    db: AsyncSession, *, user_id: str, candidate_id: str
) -> bool:
    await ensure_kb_summarize(db)
    await db.execute(
        _t("UPDATE kb_summarize_candidates SET status='dismissed' WHERE id=:i AND user_id=:u AND status='pending'"),
        {"i": candidate_id, "u": user_id},
    )
    await db.commit()
    return True


async def maybe_auto_summarize(*, user_id: str) -> list[str]:
    """启动钩：素材积压 ≥ 阈值的题材各自动总结一次（llm=True；失败静默）。

    自开 session（同 organize startup 钩先例，lifespan 直接 await）。
    """
    from db import async_session

    async with async_session() as db:
        return await _maybe_auto_summarize(db, user_id=user_id)


async def _maybe_auto_summarize(db: AsyncSession, *, user_id: str) -> list[str]:
    stats = await material_stats(db, user_id=user_id)
    triggered: list[str] = []
    for genre, n in sorted(stats.items()):
        if n < AUTO_MATERIAL_THRESHOLD:
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
