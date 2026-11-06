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
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.kb import KbEntry, KbKnowledgeInstance

AUTO_MATERIAL_THRESHOLD = 5  # 素材积压自动触发阈值（题内）

_log = logging.getLogger("uvicorn.error")

async def ensure_kb_summarize(db: AsyncSession) -> dict[str, int]:
    """幂等 DDL：总结 runs 表＋kb_entries.parent_id 列（知识树，c-kb-summarize 批E）。"""
    added = 0
    cols = [r[1] for r in (await db.execute(_t("PRAGMA table_info(kb_entries)"))).fetchall()]
    if "parent_id" not in cols:
        await db.execute(_t(
            "ALTER TABLE kb_entries ADD COLUMN parent_id TEXT NOT NULL DEFAULT ''"
        ))
        added += 1
    # 知识字段元数据（c-kb-summarize schema 层）：知识点带字段定义，实例按 schema 存字段值
    if "schema_json" not in cols:
        await db.execute(_t(
            "ALTER TABLE kb_entries ADD COLUMN schema_json TEXT NOT NULL DEFAULT '[]'"
        ))
        added += 1
    inst_cols = [r[1] for r in (await db.execute(_t("PRAGMA table_info(kb_knowledge_instances)"))).fetchall()]
    if inst_cols and "fields_json" not in inst_cols:
        await db.execute(_t(
            "ALTER TABLE kb_knowledge_instances ADD COLUMN fields_json TEXT NOT NULL DEFAULT '{}'"
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
    # 单飞竞态兜底（评审 P2）：同题材同时只允许一行 running——
    # 建索引前只把超时孤儿清成 error（30 分钟前；活跃 running 不动）
    await db.execute(_t(
        "UPDATE kb_summarize_runs SET status='error', error='stale running reclaimed' "
        "WHERE status='running' AND created_at < datetime('now', '-30 minutes')"
    ))
    await db.execute(_t(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_kb_summarize_runs_singleflight "
        "ON kb_summarize_runs (user_id, genre) WHERE status='running'"
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
                KbEntry.concept != "情节",  # 情节消费链未建，素材恒积压不触发
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

    # 单飞：同题材 30 分钟内的 running 即跳过；超时孤儿（进程中途死掉）置 error 回收
    stale = (
        await db.execute(_t(
            "SELECT id FROM kb_summarize_runs WHERE user_id=:u AND genre=:g "
            "AND status='running' AND created_at < datetime('now', '-30 minutes')"
        ), {"u": user_id, "g": genre})
    ).all()
    for (rid,) in stale:
        await db.execute(_t(
            "UPDATE kb_summarize_runs SET status='error', error='stale running reclaimed' WHERE id=:i"
        ), {"i": rid})
    live = (
        await db.execute(_t(
            "SELECT id FROM kb_summarize_runs WHERE user_id=:u AND genre=:g "
            "AND status='running' AND created_at >= datetime('now', '-30 minutes')"
        ), {"u": user_id, "g": genre})
    ).first()
    if live is not None:
        await db.commit()
        return None, "running"
    await db.commit()

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
    try:
        await db.execute(_t(
            "INSERT INTO kb_summarize_runs (id, user_id, genre, status, trigger, materials_scanned) "
            "VALUES (:i, :u, :g, 'running', :t, :n)"
        ), {"i": run_id, "u": user_id, "g": genre, "t": trigger, "n": len(materials)})
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — 部分唯一索引兜底：并发双击/重放在此收敛为 running
        if "ux_kb_summarize_runs_singleflight" not in str(exc):
            _log.warning("kb summarize run claim failed: %s", exc)
        await db.rollback()
        return None, "running"

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
    try:
        for c in candidates:
            # 管线层三闸：素材归组须属本桶且未被本轮先行知识用掉、标题非空、
            # concept 白名单、parent 白名单（非法落概念根）
            mids = [m for m in (c.get("material_ids") or []) if m in mat_ids and m not in used_material_ids]
            if not mids or not (c.get("title") or "").strip():
                continue
            concept = c.get("concept") if c.get("concept") in valid_concepts else "手法"
            parent = c.get("parent", "ROOT")
            parent = parent if parent in existing_ids else ""
            # 字段 schema 清洗（管线层校验）：schema 名非空去重 ≤6 个；空则落默认「要点」；
            # 实例 fields 按 schema 白名单过滤（编造字段不落库）
            c_schema = []
            for s in (c.get("schema") or []):
                if isinstance(s, dict) and str(s.get("name", "")).strip():
                    c_schema.append({"name": str(s["name"]).strip()[:20],
                                     "desc": str(s.get("desc", "")).strip()[:80]})
            c_schema = c_schema[:6] or [{"name": "要点", "desc": "这条写法的要点"}]
            schema_names = {s["name"] for s in c_schema}
            c_items = c.get("items") if isinstance(c.get("items"), dict) else {}

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
                schema_json=json.dumps(c_schema, ensure_ascii=False),
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
                    fields_json=json.dumps(
                        {k: str(v)[:200] for k, v in c_items.get(mid, {}).items()
                         if k in schema_names and str(v).strip()},
                        ensure_ascii=False,
                    ),
                    sort=sort,
                ))
                m.status = "archived"  # 素材行归档（审计可回溯）
                used_material_ids.add(mid)
            created += 1
    except Exception as exc:  # noqa: BLE001 — 中途异常回滚半截写入，run 置 error 不留 running 孤儿
        await db.rollback()
        await db.execute(
            _t("UPDATE kb_summarize_runs SET status='error', error=:e WHERE id=:i"),
            {"e": f"pipeline: {exc}", "i": run_id},
        )
        await db.commit()
        return {"collected": len(materials), "knowledge": 0}, f"pipeline: {exc}"

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
        # 剥 ```json 围栏（haiku 高频跑偏，不剥即 bad json 全损）；散文包裹用首尾花括号兜底
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```")
            cleaned = cleaned.removesuffix("```").strip()
        if not cleaned.startswith("{"):
            b, e = cleaned.find("{"), cleaned.rfind("}")
            if b >= 0 and e > b:
                cleaned = cleaned[b:e + 1]
        data = json.loads(cleaned or "{}")
        if not isinstance(data, dict):
            return [], "llm: bad json"
        cands = data.get("candidates") or []
        out: list[dict] = []
        for c in cands if isinstance(cands, list) else []:
            if not isinstance(c, dict):
                continue
            mids = [m for m in (c.get("material_ids") or []) if m in mat_ids]
            if not mids or not (c.get("title") or "").strip():
                continue  # 素材归属须属本桶、标题非空
            # 字段 schema 与实例字段值（c-kb-summarize schema 层）
            schema = [
                {"name": str(s.get("name", "")).strip()[:20],
                 "desc": str(s.get("desc", "")).strip()[:80]}
                for s in (c.get("schema") or [])
                if isinstance(s, dict) and str(s.get("name", "")).strip()
            ][:6]
            if not schema:
                schema = [{"name": "要点", "desc": "这条写法的要点"}]
            schema_names = {s["name"] for s in schema}
            items: dict[str, dict[str, str]] = {}
            for it in (c.get("items") or []):
                if not isinstance(it, dict) or it.get("material_id") not in mat_ids:
                    continue
                fields = {
                    str(k)[:20]: str(v).strip()[:200]
                    for k, v in (it.get("fields") or {}).items()
                    if str(k) in schema_names and str(v).strip()
                }
                items[it["material_id"]] = fields
            parent = c.get("parent", "ROOT")
            out.append({
                "title": c["title"].strip()[:40],
                "definition": (c.get("definition") or "").strip()[:500],
                "concept": c.get("concept") if c.get("concept") in valid_concepts else "手法",
                "parent": parent if parent in existing_ids else "",
                "material_ids": mids,
                "schema": schema,
                "items": items,
            })
        return out, None
    except ValueError:
        return [], "llm: bad json"


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
        # 触发口径：积压 ≥阈值 或 距上次总结超期；但 7 天内有过 completed（含零候选
        # 合法空转）则冷却不重跑——防止「无可提炼」题材每次启动白调一次模型
        older = await _last_run_older_than_days(db, user_id=user_id, genre=genre, days=7)
        recent_completed = not older
        due = (n >= AUTO_MATERIAL_THRESHOLD and not recent_completed) or older
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
