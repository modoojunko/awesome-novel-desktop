"""AI 知识整理（c-kb-organize 二阶段⑦）——关系整理核心。

方法论落点（design D1-D11）：LLM 只产候选与理由（只见确定性预筛后的短名单 ≤200 对，
SHALL NOT 见全库）；置信分由确定性特征合成（同输入同分数，SHALL NOT 采信模型自报）；
三级落位 active/pending/archived；安全原则＝只写关系不改条目。

依赖方向：kb/organize.py SHALL NOT import write/、deconstruct/（触发由
deconstruct/router.py 在 commit 成功后调本模块唯一入口，deconstruct→kb 同向）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.kb import (
    KbEntry,
    KbEntryTag,
    KbOrganizeFeedback,
    KbOrganizeFinding,
    KbOrganizeOutput,
    KbOrganizeRun,
    KbRelation,
)

logger = logging.getLogger(__name__)

# ─── 词表与常量（design D2/D6/D10） ─────────────────────────────────────

REL_TYPES = ("refines", "contradicts", "depends_on", "instance_of", "derived_from", "applies_to")
RUN_KEEP_PER_GENRE = 50          # runs/outputs 保留：每 user+genre 最近 50 条 run
SHORTLIST_MAX = 200              # LLM 候选短名单硬顶（对）
BUCKET_CAP = 50                  # 相容矩阵每概念桶参与产对的条目上限（id 序）——防全量 O(n²)
WRITE_BATCH = 50                 # 关系写入分批 commit 行数
RELATION_CAP_MULTIPLE = 5        # active 关系数 ≤ active 条目数 × 5
ACTIVE, PENDING, ARCHIVED = "active", "pending", "archived"

# 证据章接近度权重等（特征合成公式，常量入码保证可测）
_W_BASE, _W_CHAPTER, _W_GENRE, _W_ALIAS = 0.2, 0.35, 0.25, 0.2
_CONF_ACTIVE, _CONF_PENDING = 0.75, 0.5
_NEG_FACTOR = 0.5

# 概念相容矩阵（D6）：rel_type → 允许的有向概念对；表外组合零分不产候选
_COMPAT: dict[str, set[tuple[str, str]]] = {
    "applies_to": {("手法", "文风"), ("手法", "文笔"), ("手法", "手法"), ("手法", "世界设定"), ("手法", "角色设定")},
    "depends_on": {
        ("文风", "文风"), ("文笔", "文笔"), ("世界设定", "世界设定"), ("角色设定", "角色设定"),
        ("手法", "手法"), ("手法", "世界设定"), ("手法", "角色设定"),
    },
    "refines": {
        ("文风", "文风"), ("文笔", "文笔"), ("世界设定", "世界设定"),
        ("角色设定", "角色设定"), ("手法", "手法"),
    },
    "contradicts": {
        ("文风", "文风"), ("文笔", "文笔"), ("世界设定", "世界设定"),
        ("角色设定", "角色设定"), ("手法", "手法"), ("手法", "文风"),
        ("手法", "文笔"), ("文风", "手法"), ("文笔", "手法"),
    },
    "derived_from": {
        ("文风", "文风"), ("文笔", "文笔"), ("世界设定", "世界设定"),
        ("角色设定", "角色设定"), ("手法", "手法"), ("手法", "文风"),
    },
}

_CHAPTER_RE = re.compile(r"第?(\d{1,4})章?")


def chapter_no(text: str) -> int | None:
    """从证据自由串归一章号（"3"/"第3章"）；抽不出返回 None（特征取中性值）。"""
    m = _CHAPTER_RE.search(str(text or ""))
    return int(m.group(1)) if m else None


def pair_signature(a: str, b: str) -> str:
    """候选对/关系特征签名：两端 id 排序拼接后 sha256（负反馈与忽略记忆共用）。"""
    raw = "┃".join(sorted([str(a), str(b)]))
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


# ─── 确定性特征合成（同输入同分数；纯函数可单测） ────────────────────────


def confidence(
    rel_type: str,
    concept_a: str,
    concept_b: str,
    *,
    chapter_a: int | None,
    chapter_b: int | None,
    genre_a: str,
    genre_b: str,
    alias_cooccur: bool,
    neg_hit: bool,
) -> float:
    """候选关系置信分（0–1）。特征缺失取中性值（章号缺→0.5），公式内写死保证可测。"""
    if rel_type not in REL_TYPES:
        return 0.0
    if (concept_a, concept_b) not in _COMPAT.get(rel_type, set()):
        return 0.0
    if chapter_a is None or chapter_b is None:
        chapter_prox = 0.5
    else:
        chapter_prox = 1.0 - min(abs(chapter_a - chapter_b), 10) / 10.0
    score = _W_BASE + _W_CHAPTER * chapter_prox
    score += _W_GENRE * (1.0 if genre_a == genre_b else 0.0)
    score += _W_ALIAS * (1.0 if alias_cooccur else 0.0)
    return round(min(1.0, score) * (_NEG_FACTOR if neg_hit else 1.0), 4)


# ─── 内部工具 ────────────────────────────────────────────────────────────


def _entry_chapter(e: KbEntry) -> int | None:
    try:
        ej = json.loads(e.evidence_json or "{}")
        quotes = ej.get("quotes") or []
        for q in quotes:
            n = chapter_no((q or {}).get("loc") or "")
            if n is not None:
                return n
    except (TypeError, ValueError):
        pass
    return chapter_no(e.evidence or "")


async def _alias_set(db: AsyncSession, user_id: str, entry_ids: list[str]) -> dict[str, set[str]]:
    """条目 → 物化别名集合（kb_entry_tags dim=alias；SHALL NOT 读 payload_json）。"""
    if not entry_ids:
        return {}
    rows = await db.execute(
        select(KbEntryTag.entry_id, KbEntryTag.value).where(
            KbEntryTag.user_id == user_id,
            KbEntryTag.dim == "alias",
            KbEntryTag.entry_id.in_(entry_ids),
        )
    )
    out: dict[str, set[str]] = {}
    for eid, val in rows:
        out.setdefault(eid, set()).add(str(val))
    return out


async def _neg_signatures(db: AsyncSession, user_id: str) -> set[str]:
    rows = await db.execute(
        select(KbOrganizeFeedback.signature).where(
            KbOrganizeFeedback.user_id == user_id, KbOrganizeFeedback.kind == "relation"
        )
    )
    return {r for r in rows.scalars()}


async def _last_ok_run(db: AsyncSession, user_id: str, genre: str) -> KbOrganizeRun | None:
    rows = await db.execute(
        select(KbOrganizeRun)
        .where(
            KbOrganizeRun.user_id == user_id,
            KbOrganizeRun.genre == genre,
            KbOrganizeRun.status == "completed",
        )
        .order_by(KbOrganizeRun.started_at.desc())
        .limit(1)
    )
    return rows.scalars().first()


async def _pending_run(db: AsyncSession, user_id: str, genre: str) -> KbOrganizeRun | None:
    rows = await db.execute(
        select(KbOrganizeRun).where(
            KbOrganizeRun.user_id == user_id,
            KbOrganizeRun.genre == genre,
            KbOrganizeRun.status == "running",
        )
    )
    return rows.scalars().first()


def _count_output(db: AsyncSession, run_id: str, kind: str, count: int) -> None:
    if count:
        db.add(KbOrganizeOutput(run_id=run_id, kind=kind, count=count))


def _out_count(outputs: dict[str, int], kind: str) -> int:
    return int(outputs.get(kind) or 0)


# ─── 候选短名单（确定性预筛；LLM 只见这个） ──────────────────────────────


def _shortlist(
    new_ids: set[str], by_concept: dict[str, list[KbEntry]], full: bool
) -> list[tuple[KbEntry, KbEntry, str]]:
    """增量候选对 ∩ 相容矩阵 → ≤SHORTLIST_MAX 对（id 序稳定截断）。

    全量深度整理＝新集视为全库（仍受短名单硬顶约束，按 concept 桶轮转产出）。
    """
    ids_new = new_ids if not full else None
    seen: set[tuple[str, str, str]] = set()
    out: list[tuple[KbEntry, KbEntry, str]] = []
    for rel_type, pairs in _COMPAT.items():
        for (ca, cb) in sorted(pairs):
            a_list = (by_concept.get(ca) or [])[:BUCKET_CAP]
            b_list = (by_concept.get(cb) or [])[:BUCKET_CAP]
            for a in a_list:
                for b in b_list:
                    if a.id == b.id:
                        continue
                    if ids_new is not None and a.id not in ids_new and b.id not in ids_new:
                        continue  # 增量范围：至少一端属本轮更新集
                    key = (a.id, b.id, rel_type)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append((a, b, rel_type))
    out.sort(key=lambda t: (t[0].id, t[1].id, t[2]))  # id 序稳定
    return out[:SHORTLIST_MAX]


# ─── LLM 候选生成（fail-soft；批A 用最小解析，模板随批E 进提示词仓） ─────


async def _llm_candidates(
    db: AsyncSession, user_id: str, genre: str, shortlist: list[tuple[KbEntry, KbEntry, str]]
) -> tuple[list[dict], str | None]:
    """调 kb_organize 模板批产候选。返回 (候选列表, error)。error 非 None 即本轮 LLM 侧失败。"""
    if not shortlist:
        return [], None
    try:
        from ai_client import get_ai_client_for_user
        from prompts import load_layers

        system, prompt = load_layers("kb_organize")
    except Exception as e:  # noqa: BLE001 — 模板缺失/构造失败 fail-soft（design D8）
        return [], f"prompt_pack: {e}"
    lines = [
        f"{a.id}|{a.title}|{(a.instruction or '')[:120]}#{b.id}|{b.title}|{(b.instruction or '')[:120]}|{rt}"
        for (a, b, rt) in shortlist
    ]
    usage: dict = {}
    try:
        client = await get_ai_client_for_user(user_id)
        text = await client.chat(
            model="haiku",
            system=system.format(genre=genre),
            messages=[{"role": "user", "content": prompt.format(pairs="\n".join(lines), genre=genre)}],
            max_tokens=2000,
            usage=usage,
            operation="kb_organize",
        )
    except Exception as e:  # noqa: BLE001 — 调用失败不阻断（run error）
        return [], f"llm: {e}"
    try:
        data = json.loads(text or "{}")
        cands = data.get("candidates") or []
        return (cands if isinstance(cands, list) else []), None
    except ValueError:
        return [], "llm: bad json"


# ─── 核心：一次一题材整理 ────────────────────────────────────────────────


async def run_organize(
    db: AsyncSession,
    *,
    user_id: str,
    genre: str,
    trigger: str,
    full: bool = False,
    llm: bool = True,
) -> tuple[KbOrganizeRun | None, str]:
    """整理一个题材。返回 (run, error)；singleflight 命中返回 (None, "running")。

    llm=False 供测试跑确定性路径（候选为空→只走特征与落位骨架）。
    """
    existing = await _pending_run(db, user_id, genre)
    if existing is not None:
        return None, "running"

    run = KbOrganizeRun(user_id=user_id, genre=genre, status="running")
    db.add(run)
    await db.flush()
    # 触发方式落明细表（runs 无 trigger 列且无 alembic——P0 方案 b 口径）
    db.add(KbOrganizeOutput(run_id=run.id, kind=f"trigger:{trigger}", count=1))
    outputs: dict[str, int] = {}

    try:
        rows = (
            await db.execute(
                select(KbEntry).where(
                    KbEntry.user_id == user_id,
                    KbEntry.genre == genre,
                    KbEntry.concept != "情节",
                    KbEntry.status == ACTIVE,
                )
            )
        ).scalars().all()
        entries_all = list(rows)
        _count_output(db, run.id, "scan", len(entries_all))
        if not entries_all:
            run.status = "completed"
            run.finished_at = datetime.now(UTC).replace(tzinfo=None)
            run.entries_scanned = 0
            await db.commit()
            return run, ""

        last = await _last_ok_run(db, user_id, genre)
        cutoff = last.started_at if (last and last.started_at and not full) else None
        by_concept: dict[str, list[KbEntry]] = {}
        new_ids: set[str] = set()
        for e in entries_all:
            by_concept.setdefault(e.concept, []).append(e)
            if cutoff is None or (e.updated_at and e.updated_at > cutoff):
                new_ids.add(e.id)
        if full or cutoff is None:
            new_ids = {e.id for e in entries_all}  # 无历史/全量＝全部视为本轮

        shortlist = _shortlist(new_ids, by_concept, full=full)
        # 截断语义：短名单构造阶段已硬顶（BUCKET_CAP×SHORTLIST_MAX），超顶对不进池
        _count_output(db, run.id, "shortlist", len(shortlist))

        error = None
        cands: list[dict] = []
        if llm and shortlist:
            cands, error = await _llm_candidates(db, user_id, genre, shortlist)

        entry_by_id = {e.id: e for e in entries_all}
        alias_map: dict[str, set[str]] = {}
        neg: set[str] = set()
        existing_active: set[tuple[str, str, str]] = set()
        if cands:
            # 打分查询只涉短名单两端（≤400 id）——SHALL NOT 全库 in（SQLite 变量上限＋性能）
            involved = sorted({str(c.get("a")) for c in cands} | {str(c.get("b")) for c in cands})
            involved = [i for i in involved if i in entry_by_id]
            alias_map = await _alias_set(db, user_id, involved)
            neg = await _neg_signatures(db, user_id)
            existing_active = set(
                
                    await db.execute(
                        select(KbRelation.from_id, KbRelation.to_id, KbRelation.rel_type).where(
                            KbRelation.user_id == user_id,
                            KbRelation.status == ACTIVE,
                            KbRelation.rel_type.in_(REL_TYPES),
                        )
                    )
                
            )

        to_write: list[KbRelation] = []
        pending_n = active_n = dup_n = drop_n = invalid_n = 0
        for cand in cands:
            try:
                aid, bid = str(cand.get("a") or ""), str(cand.get("b") or "")
                rt = str(cand.get("rel_type") or "")
                ea, eb = entry_by_id.get(aid), entry_by_id.get(bid)
                if ea is None or eb is None or aid == bid or rt not in REL_TYPES:
                    invalid_n += 1
                    continue
                if (ea.concept, eb.concept) not in _COMPAT.get(rt, set()):
                    invalid_n += 1
                    continue
                sig = pair_signature(aid, bid)
                conf = confidence(
                    rt, ea.concept, eb.concept,
                    chapter_a=_entry_chapter(ea), chapter_b=_entry_chapter(eb),
                    genre_a=ea.genre, genre_b=eb.genre,
                    alias_cooccur=bool(alias_map.get(aid, set()) & alias_map.get(bid, set())),
                    neg_hit=sig in neg,
                )
            except Exception:  # noqa: BLE001 — 单条候选畸形不拖垮整批
                invalid_n += 1
                continue
            if conf < _CONF_PENDING:
                drop_n += 1
                continue
            if (aid, bid, rt) in existing_active:
                dup_n += 1
                continue
            to_write.append(KbRelation(
                user_id=user_id, from_id=aid, to_id=bid, rel_type=rt,
                note=str(cand.get("note") or "")[:500],
                confidence=conf, status=(ACTIVE if conf >= _CONF_ACTIVE else PENDING),
                source="ai", run_id=run.id,
                evidence=str(cand.get("evidence") or "")[:500],
            ))

        # 分批写入（≤WRITE_BATCH 行/批）——防大事务挤压生成链写锁
        for i in range(0, len(to_write), WRITE_BATCH):
            db.add_all(to_write[i:i + WRITE_BATCH])
            await db.flush()
        pending_n = sum(1 for r in to_write if r.status == PENDING)
        active_n = len(to_write) - pending_n
        outputs.update({
            "active_relations": active_n, "pending_relations": pending_n,
            "duplicates": dup_n, "dropped": drop_n, "invalid": invalid_n,
        })
        for kind, n in outputs.items():
            _count_output(db, run.id, kind, n)

        # 5× 上限淘汰：per user+genre，confidence 升序 → created_at 升序
        cap = max(1, len(entries_all) * RELATION_CAP_MULTIPLE)
        active_rows = (
            await db.execute(
                select(KbRelation).where(
                    KbRelation.user_id == user_id,
                    KbRelation.status == ACTIVE,
                    KbRelation.rel_type.in_(REL_TYPES),
                )
            )
        ).scalars().all()
        overflow = len(active_rows) - cap
        if overflow > 0:
            victims = sorted(active_rows, key=lambda r: (r.confidence, r.created_at or datetime.now(UTC)))[:overflow]
            for v in victims:
                v.status = ARCHIVED
            outputs["evicted"] = overflow
            _count_output(db, run.id, "evicted", overflow)

        run.status = "completed"
        run.entries_scanned = len(entries_all)
        run.relations_added = active_n
        run.relations_updated = pending_n
        run.relations_skipped = dup_n + drop_n + invalid_n
        run.error = error or ""
        run.finished_at = datetime.now(UTC).replace(tzinfo=None)
        await db.commit()

        # runs/outputs 保留：每 user+genre 最近 RUN_KEEP_PER_GENRE 条 run，outputs 随 run 级联
        await _prune_runs(db, user_id, genre)
        return run, ""
    except Exception as e:  # noqa: BLE001 — 任何异常落 run error（不阻断知识库）
        run.status = "error"
        run.error = str(e)[:500]
        run.finished_at = datetime.now(UTC).replace(tzinfo=None)
        await db.commit()
        logger.warning("event=kb_organize error run=%s err=%s", run.id, e)
        return run, str(e)


async def _prune_runs(db: AsyncSession, user_id: str, genre: str) -> int:
    """runs/outputs 保留：每 user+genre 最近 RUN_KEEP_PER_GENRE 条。"""
    rows = (
        await db.execute(
            select(KbOrganizeRun.id).where(
                KbOrganizeRun.user_id == user_id, KbOrganizeRun.genre == genre
            ).order_by(KbOrganizeRun.started_at.desc(), KbOrganizeRun.id.desc())
        )
    ).scalars().all()
    stale = rows[RUN_KEEP_PER_GENRE:]
    if not stale:
        return 0
    await db.execute(delete(KbOrganizeOutput).where(KbOrganizeOutput.run_id.in_(stale)))
    await db.execute(delete(KbOrganizeRun).where(KbOrganizeRun.id.in_(stale)))
    await db.commit()
    return len(stale)


# ─── 触发入口（唯一；deconstruct/router 与 lifespan 只调这里） ───────────


async def trigger_after_collect(user_id: str, genre: str) -> None:
    """拆书入库成功后的 fire-and-forget 触发（进程死丢触发由启动 7 天钩兜底）。"""
    import asyncio

    if not genre:
        return

    async def _job() -> None:
        from db import async_session

        try:
            async with async_session() as db:
                await run_organize(db, user_id=user_id, genre=genre, trigger="deconstruct")
        except Exception as e:  # noqa: BLE001 — 触发失败不惊动收录响应
            logger.warning("event=kb_organize trigger_failed user=%s genre=%s err=%s", user_id, genre, e)

    asyncio.create_task(_job())


async def startup_sweep_and_maybe_run() -> dict:
    """lifespan 挂钩：僵尸 running sweep＋runs 保留＋距上次成功 >7 天的题材各整理一次。

    失败不抛（照 import backfill 先例，调用方 except 兜底）。
    """
    from db import async_session

    swept = kept = triggered = 0
    async with async_session() as db:
        zombies = (
            await db.execute(select(KbOrganizeRun).where(KbOrganizeRun.status == "running"))
        ).scalars().all()
        for z in zombies:
            z.status = "error"
            z.error = "startup sweep: interrupted"
            z.finished_at = datetime.now(UTC).replace(tzinfo=None)
        swept = len(zombies)
        await db.commit()

        groups = (
            await db.execute(
                select(KbEntry.user_id, KbEntry.genre)
                .where(KbEntry.status == ACTIVE, KbEntry.genre != "")
                .group_by(KbEntry.user_id, KbEntry.genre)
            )
        ).all()
        now = datetime.now(UTC).replace(tzinfo=None)
        for uid, g in groups:
            last = await _last_ok_run(db, uid, g)
            stale = last is None or last.started_at is None
            if not stale:
                started = last.started_at if last.started_at.tzinfo is None else last.started_at.replace(tzinfo=UTC)
                age_days = (now - started).total_seconds() / 86400
                stale = age_days > 7
            kept += 1
            if stale:
                await _prune_runs(db, uid, g)
                await run_organize(db, user_id=uid, genre=g, trigger="startup_7d")
                triggered += 1
    return {"swept": swept, "genres": kept, "triggered": triggered}


async def ignore_finding(db: AsyncSession, user_id: str, finding_id: str) -> bool:
    """忽略建议：status=ignored＋同 signature 记忆（B 批端点用；先落核心语义）。"""
    f = (
        await db.execute(
            select(KbOrganizeFinding).where(
                KbOrganizeFinding.id == finding_id, KbOrganizeFinding.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if f is None:
        return False
    f.status = "ignored"
    await db.commit()
    return True
