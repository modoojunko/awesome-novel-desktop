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

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kb.query_scope import visible_knowledge_filter
from models.kb import (
    KbConcept,
    KbEntry,
    KbEntryMerge,
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
DETECT_POOL_MAX = 2000           # 四类标注的扫描池上限（id 序截断）——防 infer 全库爆预算
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


_IN_CHUNK = 500  # SQLite 变量上限防御：大 id 集分块查询


async def _alias_set(db: AsyncSession, user_id: str, entry_ids: list[str]) -> dict[str, set[str]]:
    """条目 → 物化别名集合（kb_entry_tags dim=alias；SHALL NOT 读 payload_json）。

    entry_ids 分块查询（防 SQLite too many SQL variables）；返回键只含命中的条目。
    """
    if not entry_ids:
        return {}
    out: dict[str, set[str]] = {}
    for start in range(0, len(entry_ids), _IN_CHUNK):
        rows = await db.execute(
            select(KbEntryTag.entry_id, KbEntryTag.value).where(
                KbEntryTag.user_id == user_id,
                KbEntryTag.dim == "alias",
                KbEntryTag.entry_id.in_(entry_ids[start:start + _IN_CHUNK]),
            )
        )
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
        # 剥 ```json 围栏（haiku 高频跑偏，不剥即 bad json 全损）
        _cleaned = (text or "").strip()
        if _cleaned.startswith("```"):
            _cleaned = _cleaned.removeprefix("```json").removeprefix("```")
            _cleaned = _cleaned.removesuffix("```").strip()
        data = json.loads(_cleaned or "{}")
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

        run.relations_added = active_n
        run.relations_updated = pending_n
        run.relations_skipped = dup_n + drop_n + invalid_n

        # 批B：四类检测（合并/纠偏/子概念/质量）→ findings（作家确认制，不动条目）
        detect_pool = sorted(new_ids)[:DETECT_POOL_MAX]
        detect_entries = [entry_by_id[i] for i in detect_pool if i in entry_by_id]
        _count_output(db, run.id, "detect_scanned", len(detect_entries))
        counts = await detect_findings(
            db, run=run, entries=entries_all, detect_entries=detect_entries
        )
        outputs.update({f"suggestion_{k}": v for k, v in counts.items()})

        run.status = "completed"
        run.entries_scanned = len(entries_all)
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

    # genre 空串（目录外/跨题材通用）也触发：按 "" 题材分组跑一次
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


# ─── 批B：合并·纠偏·子概念·质量 检测与采纳（作家确认制，SHALL NOT 自动动数据） ──

QUALITY_MIN_INSTRUCTION = 20     # 质量标记阈值：指令 <20 字＝过短（spec 钉死）
RECLASS_MIN_TARGET = 2           # 纠偏：目标概念词叶命中 ≥2
RECLASS_GAP = 2                  # 纠偏：目标得分须超现概念 2 分以上
FINDING_KINDS = ("merge", "reclass", "subconcept", "quality")


def _payload_keys(e: KbEntry) -> set[str]:
    try:
        v = json.loads(e.payload_json or "{}")
    except (TypeError, ValueError):
        return set()
    return {k for k in v if k != "aliases"} if isinstance(v, dict) else set()


def _merge_reason(a: KbEntry, b: KbEntry, alias_a: set[str], alias_b: set[str]) -> str:
    """合并判据（design D4/B1）：须含至少一条强线索（同名/别名共现/同源）；槽位重合只是佐证。"""
    reasons: list[str] = []
    na, nb = (a.title or "").strip(), (b.title or "").strip()
    if na and na == nb:
        reasons.append("同名")
    elif na and nb and min(len(na), len(nb)) >= 2 and (na in nb or nb in na):
        reasons.append("名字互含")
    if alias_a & alias_b:
        reasons.append("别名共现")
    if a.src_ref and a.src_ref == b.src_ref and a.src_kind == b.src_kind:
        reasons.append("同来源（疑似双出口平行条目）")
    if not reasons:
        return ""
    ka, kb_ = _payload_keys(a), _payload_keys(b)
    if ka and kb_ and len(ka & kb_) / len(ka | kb_) >= 0.5:
        reasons.append("槽位重合")
    return "、".join(reasons)


async def _upsert_finding(
    db: AsyncSession, *, user_id: str, genre: str, kind: str,
    subject_id: str, subject2_id: str, payload: dict, run_id: str,
) -> str:
    """findings 落库（签名去重）：proposed 已在→跳；adopted→永不重提；
    ignored→两端 rev 指纹未变→跳，变了→重新提出。返回落库状态。"""
    ids = sorted([subject_id, subject2_id] if subject2_id else [subject_id])
    sig = hashlib.sha256((kind + "┃" + "┃".join(ids)).encode()).hexdigest()[:64]
    existing = (
        await db.execute(
            select(KbOrganizeFinding).where(
                KbOrganizeFinding.user_id == user_id,
                KbOrganizeFinding.kind == kind,
                KbOrganizeFinding.signature == sig,
            )
        )
    ).scalars().all()
    for f in existing:
        if f.status == "proposed":
            return "dup"
        if f.status == "adopted":
            return "adopted"
        if f.status == "ignored":
            try:
                old_revs = (json.loads(f.payload_json or "{}").get("revs") or {})
            except (TypeError, ValueError):
                old_revs = {}
            cur_revs = {"revs": {}}
            for sid in ([f.subject_id, f.subject2_id] if f.subject2_id else [f.subject_id]):
                s_ = await db.get(KbEntry, sid)
                cur_revs["revs"][sid] = int(getattr(s_, "rev", 0) or 0)
            if old_revs == cur_revs["revs"]:
                return "ignored_hold"
            break  # rev 指纹变了 → 重新提出
    subj = await db.get(KbEntry, subject_id)
    revs = {"revs": {subject_id: int(getattr(subj, "rev", 0) or 0)}}
    if subject2_id:
        s2 = await db.get(KbEntry, subject2_id)
        revs["revs"][subject2_id] = int(getattr(s2, "rev", 0) or 0)
    payload = {**payload, **revs}
    try:
        # SAVEPOINT 隔离：签名撞 unique 只回滚 savepoint，不连带主事务（淘汰块等已做改动）
        async with db.begin_nested():
            db.add(KbOrganizeFinding(
                user_id=user_id, genre=genre, kind=kind, subject_id=subject_id,
                subject2_id=subject2_id, payload_json=json.dumps(payload, ensure_ascii=False),
                status="proposed", signature=sig, run_id=run_id,
            ))
            await db.flush()
        return "proposed"
    except IntegrityError:
        # 并发缝隙（singleflight 间隙/跨会话）：同签名 proposed 已落 → 视为重复
        return "dup"


async def detect_findings(
    db: AsyncSession, *, run: KbOrganizeRun, entries: list[KbEntry],
    detect_entries: list[KbEntry] | None = None,
) -> dict[str, int]:
    """四类检测 → findings（作家确认制；本函数 SHALL NOT 改任何条目）。

    merge 对照池＝entries（全库桶，桶 cap 限价）；reclass/subconcept/quality 只扫
    detect_entries（增量集，≤DETECT_POOL_MAX 截断——10 万级全库 infer 会爆预算）。
    """
    uid, genre = run.user_id, run.genre
    counts: dict[str, int] = {}
    scan_entries = detect_entries if detect_entries is not None else entries
    alias_map = await _alias_set(
        db, uid, sorted({e.id for e in entries} | {e.id for e in scan_entries})
    )

    async def _emit(kind: str, subject_id: str, subject2_id: str, payload: dict) -> None:
        st = await _upsert_finding(
            db, user_id=uid, genre=genre, kind=kind, subject_id=subject_id,
            subject2_id=subject2_id, payload=payload, run_id=run.id,
        )
        if st == "proposed":
            counts[kind] = counts.get(kind, 0) + 1

    # ── 合并（同概念桶内 pairwise；桶 cap 同短名单） ──
    by_concept: dict[str, list[KbEntry]] = {}
    for e in entries:
        by_concept.setdefault(e.concept, []).append(e)
    seen_pairs: set[tuple[str, str]] = set()
    for bucket in by_concept.values():
        bucket = bucket[:BUCKET_CAP]
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                key = tuple(sorted([a.id, b.id]))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                reason = _merge_reason(a, b, alias_map.get(a.id, set()), alias_map.get(b.id, set()))
                if reason:
                    lo, hi = sorted([a.id, b.id])
                    surviving = hi if (a.title or "") <= (b.title or "") else lo
                    merged = b if surviving == a.id else a
                    await _emit("merge", merged.id, surviving,
                                {"surviving": surviving, "merged": merged.id,
                                 "reason": reason, "titles": [a.title, b.title]})

    # ── 纠偏（词叶得分超现概念且差 ≥2；目标须在六概念注册表内） ──
    from kb.infer import infer_scores

    for e in scan_entries:
        scores = infer_scores(e.instruction or "")
        scores.pop(e.concept, None)
        if not scores:
            continue
        target, ts = max(scores.items(), key=lambda kv: (kv[1], kv[0]))
        cur_score = max((v for k, v in scores.items() if k == e.concept), default=0)
        if ts >= RECLASS_MIN_TARGET and ts - cur_score >= RECLASS_GAP and target in (
            "文风", "文笔", "世界设定", "角色设定", "手法"
        ):
            await _emit("reclass", e.id, "",
                        {"target_concept": target, "reason": f"词叶更匹配 {target}（{ts} 命中）",
                         "title": e.title})

    # ── 子概念提案（命中 kb_concepts 子概念名/别名；提案制 SHALL NOT 自动建行） ──
    sub_rows = (
        await db.execute(
            select(KbConcept).where(KbConcept.level == 2, KbConcept.status == "active")
        )
    ).scalars().all()
    for e in scan_entries:
        text = f"{e.title}｜{e.instruction or ''}"
        for sc in sub_rows:
            names = [sc.name]
            try:
                names += [str(x) for x in json.loads(sc.aliases or "[]")]
            except (TypeError, ValueError):
                pass
            if any(n and n in text for n in names):
                await _emit("subconcept", e.id, "",
                            {"subconcept": sc.name, "reason": f"命中子概念「{sc.name}」",
                             "title": e.title})
                break

    # ── 质量标记（指令 <20 字／无证据／标题与已归档重复——首判据即出） ──
    archived_titles = set(
        (
            await db.execute(
                select(KbEntry.title).where(
                    KbEntry.user_id == uid, KbEntry.genre == genre, KbEntry.status == "archived"
                )
            )
        ).scalars()
    )
    for e in scan_entries:
        reason = ""
        if len((e.instruction or "").strip()) < QUALITY_MIN_INSTRUCTION:
            reason = f"指令过短（<{QUALITY_MIN_INSTRUCTION} 字）"
        elif not (e.evidence or "").strip() and (e.evidence_json or "{}") in ("", "{}"):
            reason = "无证据来源"
        elif (e.title or "") in archived_titles:
            reason = "标题与已归档条目重复"
        if reason:
            await _emit("quality", e.id, "", {"reason": reason, "title": e.title})

    for kind, n in counts.items():
        db.add(KbOrganizeOutput(run_id=run.id, kind=f"suggestion_{kind}", count=n))
        _count_output(db, run.id, f"suggestion_{kind}", n)
    await db.commit()
    return counts


async def adopt_finding(db: AsyncSession, *, user_id: str, finding_id: str) -> tuple[bool, str]:
    """采纳建议（作家确认动作）。返回 (ok, message)。merge/reclass 动数据，quality 归档，subconcept 仅落状态。"""
    f = (
        await db.execute(
            select(KbOrganizeFinding).where(
                KbOrganizeFinding.id == finding_id,
                KbOrganizeFinding.user_id == user_id,
                KbOrganizeFinding.status == "proposed",
            )
        )
    ).scalar_one_or_none()
    if f is None:
        return False, "not_found"
    payload = {}
    try:
        payload = json.loads(f.payload_json or "{}")
    except (TypeError, ValueError):
        pass

    if f.kind == "merge":
        merged_id, surviving_id = f.subject_id, (payload.get("surviving") or f.subject2_id)
        merged = await db.get(KbEntry, merged_id)
        surviving = await db.get(KbEntry, surviving_id)
        if merged is None or surviving is None:
            return False, "entry_gone"
        if merged.status != ACTIVE or surviving.status != ACTIVE:
            return False, "state_changed"
        merged.status = "merged"
        db.add(KbEntryMerge(surviving_id=surviving.id, merged_id=merged.id, run_id=f.run_id))
        f.status = "adopted"
        await db.commit()
        return True, f"已合并进「{surviving.title}」"

    if f.kind == "reclass":
        e = await db.get(KbEntry, f.subject_id)
        if e is None or e.status != ACTIVE:
            return False, "entry_gone"
        target = str(payload.get("target_concept") or "")
        if target not in ("文风", "文笔", "世界设定", "角色设定", "手法"):
            return False, "bad_target"
        from kb.service import create_entry as kb_create_entry

        new_entry, _gate, error = await kb_create_entry(
            db,
            user_id=user_id,
            genre=e.genre,
            concept=target,
            title=e.title,
            payload={},  # 空载荷走手录默认装载（错位载荷不平移；作家后续编辑）
            instruction=e.instruction,
            evidence=e.evidence,
            src_kind=e.src_kind,
            src_ref=e.src_ref,
            src_key=(e.src_key + ":reclass") if e.src_key else "",
            src_novel_name=e.src_novel_name,
        )
        if new_entry is None:
            return False, f"recreate_failed: {error}"
        e.status = ARCHIVED
        f.status = "adopted"
        await db.commit()
        return True, f"已按 {target} 重建"

    if f.kind == "quality":
        e = await db.get(KbEntry, f.subject_id)
        if e is None or e.status != ACTIVE:
            return False, "entry_gone"
        e.status = ARCHIVED
        f.status = "adopted"
        await db.commit()
        return True, "已归档"

    # subconcept：提案确认只落状态（数据落点 P1；SHALL NOT 自动建概念行）
    f.status = "adopted"
    await db.commit()
    return True, "提案已确认"


# ─── 批C：端点服务层（清单/反馈/条目图） ─────────────────────────────────


async def organize_status(db: AsyncSession, *, user_id: str, genre: str) -> dict:
    """运行状态：最近一次 run＋待确认计数（pending 关系＋proposed findings）。"""
    last = (
        await db.execute(
            select(KbOrganizeRun)
            .where(KbOrganizeRun.user_id == user_id, KbOrganizeRun.genre == genre)
            .order_by(KbOrganizeRun.started_at.desc())
            .limit(1)
        )
    ).scalars().first()
    pending_rel = (
        await db.execute(
            select(func.count(KbRelation.id)).where(
                KbRelation.user_id == user_id,
                KbRelation.status == PENDING,
                KbRelation.rel_type.in_(REL_TYPES),
            )
        )
    ).scalar() or 0
    proposed_f = (
        await db.execute(
            select(func.count(KbOrganizeFinding.id)).where(
                KbOrganizeFinding.user_id == user_id,
                KbOrganizeFinding.status == "proposed",
            )
        )
    ).scalar() or 0
    return {
        "genre": genre,
        "running": bool(last and last.status == "running"),
        "last_run": {
            "id": last.id,
            "status": last.status,
            "started_at": last.started_at.isoformat() if last.started_at else "",
            "finished_at": last.finished_at.isoformat() if last.finished_at else "",
            "entries_scanned": last.entries_scanned,
            "relations_added": last.relations_added,
            "error": last.error or "",
        } if last else None,
        "pending_relations": int(pending_rel),
        "proposed_findings": int(proposed_f),
    }


async def run_manual(db: AsyncSession, *, user_id: str, genre: str, full: bool) -> dict:
    """手动整理入口（端点用）：running 即幂等跳过；fire-and-forget 不适用（端点等结果）。"""
    existing = await _pending_run(db, user_id, genre)
    if existing is not None:
        return {"ok": False, "code": "running", "run_id": existing.id,
                "message": "该题材正在整理中，稍后再看结果"}
    run, err = await run_organize(
        db, user_id=user_id, genre=genre, trigger="manual", full=full, llm=True
    )
    if run is None:
        return {"ok": False, "code": "running", "message": "该题材正在整理中"}
    return {
        "ok": err == "",
        "code": "done" if err == "" else "error",
        "run_id": run.id,
        "status": run.status,
        "entries_scanned": run.entries_scanned,
        "relations_added": run.relations_added,
        "relations_updated": run.relations_updated,
        "relations_skipped": run.relations_skipped,
        "error": run.error or "",
        "message": ("整理完成" if err == "" else f"整理失败：{err[:120]}"),
    }


async def list_pending(db: AsyncSession, *, user_id: str, genre: str = "") -> dict:
    """待确认清单：pending 关系＋proposed findings（四类建议）汇聚。"""
    rel_rows = (
        await db.execute(
            select(KbRelation).where(
                KbRelation.user_id == user_id,
                KbRelation.status == PENDING,
                KbRelation.rel_type.in_(REL_TYPES),
            )
        )
    ).scalars().all()
    f_stmt = select(KbOrganizeFinding).where(
        KbOrganizeFinding.user_id == user_id, KbOrganizeFinding.status == "proposed"
    )
    if genre:
        f_stmt = f_stmt.where(KbOrganizeFinding.genre == genre)
    f_rows = (
        await db.execute(f_stmt.order_by(KbOrganizeFinding.created_at.desc()).limit(200))
    ).scalars().all()

    entry_ids = sorted(
        {r.from_id for r in rel_rows} | {r.to_id for r in rel_rows}
        | {f.subject_id for f in f_rows} | {f.subject2_id for f in f_rows if f.subject2_id}
    )
    titles: dict[str, str] = {}
    if entry_ids:
        for e in (
            await db.execute(select(KbEntry).where(KbEntry.id.in_(entry_ids)))
        ).scalars():
            titles[e.id] = e.title

    relations = [
        {
            "id": r.id,
            "rel_type": r.rel_type,
            "from_id": r.from_id,
            "to_id": r.to_id,
            "from_title": titles.get(r.from_id, r.from_id),
            "to_title": titles.get(r.to_id, r.to_id),
            "confidence": r.confidence,
            "note": r.note,
            "evidence": r.evidence,
        }
        for r in rel_rows
    ]
    findings = [
        {
            "id": f.id,
            "kind": f.kind,
            "subject_id": f.subject_id,
            "subject2_id": f.subject2_id,
            "subject_title": titles.get(f.subject_id, f.subject_id),
            "payload": _safe_json(f.payload_json),
        }
        for f in f_rows
    ]
    return {"relations": relations, "findings": findings,
            "counts": {"relations": len(relations), "findings": len(findings)}}


def _safe_json(raw: str) -> dict:
    try:
        v = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


async def relation_feedback(
    db: AsyncSession, *, user_id: str, relation_id: str
) -> tuple[bool, str]:
    """「这条不对」：落特征签名反馈（下次整理降权），SHALL NOT 删改关系本体。"""
    r = (
        await db.execute(
            select(KbRelation).where(
                KbRelation.id == relation_id, KbRelation.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if r is None:
        return False, "not_found"
    sig = pair_signature(r.from_id, r.to_id)
    exists = (
        await db.execute(
            select(KbOrganizeFeedback.id).where(
                KbOrganizeFeedback.user_id == user_id,
                KbOrganizeFeedback.kind == "relation",
                KbOrganizeFeedback.signature == sig,
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        db.add(KbOrganizeFeedback(
            user_id=user_id, kind="relation", signature=sig, entry_id=r.from_id,
        ))
        await db.commit()
    return True, "已记录，下次整理会降低同类候选权重"


async def adopt_pending_relation(db: AsyncSession, *, user_id: str, relation_id: str) -> tuple[bool, str]:
    r = (
        await db.execute(
            select(KbRelation).where(
                KbRelation.id == relation_id,
                KbRelation.user_id == user_id,
                KbRelation.status == PENDING,
            )
        )
    ).scalar_one_or_none()
    if r is None:
        return False, "not_found"
    r.status = ACTIVE
    await db.commit()
    return True, "关系已生效"


async def reject_pending_relation(db: AsyncSession, *, user_id: str, relation_id: str) -> tuple[bool, str]:
    r = (
        await db.execute(
            select(KbRelation).where(
                KbRelation.id == relation_id,
                KbRelation.user_id == user_id,
                KbRelation.status == PENDING,
            )
        )
    ).scalar_one_or_none()
    if r is None:
        return False, "not_found"
    r.status = ARCHIVED
    await db.commit()
    return True, "已否决"


GRAPH_EDGE_CAP = 500  # 条目图边硬顶（design D7）：按 confidence 降序取


async def graph_entries(db: AsyncSession, *, user_id: str, genre: str) -> dict:
    """条目图数据：题材内 active 条目为节点、active 关系为边（≤GRAPH_EDGE_CAP）。

    pending 关系、merged 条目、merged_into（独立表）SHALL NOT 出现。
    """
    conds = [KbEntry.user_id == user_id, KbEntry.concept != "情节",
                visible_knowledge_filter(), KbEntry.status == ACTIVE]
    if genre:
        conds.append(KbEntry.genre == genre)
    nodes = (
        await db.execute(
            select(KbEntry).where(*conds).order_by(KbEntry.created_at, KbEntry.id)
        )
    ).scalars().all()
    node_ids = {e.id for e in nodes}
    edges_all = (
        await db.execute(
            select(KbRelation)
            .where(
                KbRelation.user_id == user_id,
                KbRelation.status == ACTIVE,
                KbRelation.rel_type.in_(REL_TYPES),
            )
            .order_by(KbRelation.confidence.desc(), KbRelation.created_at.asc())
        )
    ).scalars().all()
    edges = []
    truncated = 0
    for r in edges_all:
        if r.from_id not in node_ids or r.to_id not in node_ids or r.from_id == r.to_id:
            continue
        if len(edges) >= GRAPH_EDGE_CAP:
            truncated += 1
            continue
        edges.append({
            "rel_type": r.rel_type,
            "from_id": r.from_id,
            "to_id": r.to_id,
            "confidence": r.confidence,
            "note": r.note,
            "evidence": r.evidence,
        })
    return {
        "genre": genre,
        "nodes": [
            {"id": e.id, "title": e.title, "concept": e.concept,
             "instruction": (e.instruction or "")[:120]}
            for e in nodes
        ],
        "edges": edges,
        "edge_count": len(edges),
        "edge_truncated": truncated,
    }


async def entry_relations(
    db: AsyncSession, *, user_id: str, entry_id: str, status: str = "all"
) -> dict:
    """条目详情的关系列表：active＋pending 中两端含该条目的关系（含对方标题）。

    status="active" 只回生效关系（c-kb-relations-view 知识视图段用）。
    对端缺失或对端已归档（status=archived，点跳不可达）的关系行剔除——视图段点跳永不落 404。
    merged 条目的追溯（kb_entry_merges 指向）随返回（merged_into 段）。
    """
    e = await db.get(KbEntry, entry_id)
    if e is None or e.user_id != user_id:
        return {"error": "not_found"}
    wanted_statuses = (ACTIVE,) if status == "active" else (ACTIVE, PENDING)
    rel_rows = (
        await db.execute(
            select(KbRelation).where(
                KbRelation.user_id == user_id,
                KbRelation.status.in_(wanted_statuses),
                KbRelation.rel_type.in_(REL_TYPES),
            )
        )
    ).scalars().all()
    mine = [r for r in rel_rows if r.from_id == entry_id or r.to_id == entry_id]
    other_ids = sorted(
        {r.from_id if r.from_id != entry_id else r.to_id for r in mine}
    )
    others: dict[str, KbEntry] = {}
    if other_ids:
        for o in (
            await db.execute(select(KbEntry).where(KbEntry.id.in_(other_ids)))
        ).scalars():
            others[o.id] = o
    # 死链剔除：对端行缺失（备份恢复孤儿端点）或对端已归档（点跳 404 口径）
    mine = [
        r for r in mine
        if (o := others.get(r.from_id if r.from_id != entry_id else r.to_id))
        is not None and o.status != "archived"
    ]
    relations = [
        {
            "id": r.id,
            "rel_type": r.rel_type,
            "status": r.status,
            "direction": "out" if r.from_id == entry_id else "in",
            "other_id": r.from_id if r.from_id != entry_id else r.to_id,
            "other_title": others[
                r.from_id if r.from_id != entry_id else r.to_id
            ].title,
            "confidence": r.confidence,
            "note": r.note,
            "evidence": r.evidence,
        }
        for r in mine
    ]
    from models.kb import KbEntryMerge

    merged_into = None
    if e.status == "merged":
        m = (
            await db.execute(
                select(KbEntryMerge).where(KbEntryMerge.merged_id == entry_id)
            )
        ).scalar_one_or_none()
        if m is not None:
            surv = await db.get(KbEntry, m.surviving_id)
            merged_into = {
                "surviving_id": m.surviving_id,
                "title": surv.title if surv else "",
            }
    return {"relations": relations, "merged_into": merged_into}
