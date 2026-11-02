"""本章写法块注入器（c-kb-write-block B3/B4/B5＋批F 架构加固）——write 链专用组装段。

- 信号抽取住本模块（批F F8：章纲语义归 write 域，kb 不认识章纲表）
- 启用判定：kb_book_bindings（enabled）join kb_libraries（enabled＋概念∈手法/文风/文笔）
  ——未启用任何相关库 → (None, None, None)，调用方零变化；同时清理「知识库·」影子行
- 复用语义：同章同素材（brief_hash）且库域指纹一致 → 复用 run 重建块（items.text_snapshot
  固化文本，条目编辑不破坏字节一致）；续写/补足按章节复用当章最新 run；
  停用后无块（SHALL NOT 注入旧 run）
- run/items 落库：首生成选择完成即落（并发首生成撞唯一键 → rollback 后复用赢家 run，
  F1 竞态修）；影子行变更与 run/items 同事务提交（F4）
- SSE 事件由调用方转发（type=write_block）
"""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kb.block import build_block
from kb.concepts import normalize_emotion, normalize_scene
from kb.match import (
    MatchSignals,
    SelectedItem,
    Selection,
    digest_candidates,  # noqa: F401 — P1 LLM 选择器候选摘要域（公开预留）
    is_quantitative,
    select_block,
)
from models.chapter import Chapter, ChapterCharacter
from models.kb import KbBookBinding, KbEntry, KbLibrary, KbMatchItem, KbMatchRun
from models.project import Novel

logger = logging.getLogger(__name__)

_BLOCK_CONCEPTS = ("手法", "文风", "文笔")
_SHADOW_KB_PREFIX = "知识库·"


def _stage_to_pos(stage: str | None) -> str:
    """拆章六档 plot_stage → 章位封闭值（CHAPTER_POS）；空/未知 → ""（不硬猜）。"""
    return {
        "开局铺垫": "开头",
        "冲突初现": "中段",
        "矛盾升级": "中段",
        "重要转折": "中段",
        "高潮爆发": "中段",
        "卷末收束": "卷末",
    }.get(stage or "", "")


def _plot_items(raw: str | None) -> list[str]:
    try:
        items = json.loads(raw or "[]")
    except ValueError:
        return []
    return [str(i) for i in items if isinstance(i, str) and i.strip()] if isinstance(items, list) else []


async def extract_signals(
    db: AsyncSession, *, novel_id: str, chapter_ref: str, genre: str
) -> MatchSignals:
    """章纲行 → 选块信号（批F F8 从 kb/match.py 上移；章纲语义住 write 域）。

    场面：概要优先，miss 逐条剧情条目（首个命中即用）；情绪：primary_mood 字段
    优先，miss 概要与剧情条目文本归类；章位：拆章六档 plot_stage 映射；
    出场角色：章纲角色快照名直取（order_by 固定序——进 hash 与打分的顺序契约）；
    归类不出保持空串，不硬猜。
    """
    ch = (
        await db.execute(
            select(Chapter).where(
                Chapter.project_id == novel_id,
                Chapter.ref == chapter_ref,
                Chapter.ghost_of.is_(None),
            )
        )
    ).scalar_one_or_none()
    if ch is None:
        return MatchSignals(genre=genre)
    scene = normalize_scene(ch.summary or "")
    if not scene:
        for item in _plot_items(ch.plot_items):
            scene = normalize_scene(item)
            if scene:
                break
    emotion = normalize_emotion(ch.primary_mood or "")
    if not emotion:
        emotion = normalize_emotion(ch.summary or "")
    if not emotion:
        for item in _plot_items(ch.plot_items):
            emotion = normalize_emotion(item)
            if emotion:
                break
    names = (
        (
            await db.execute(
                select(ChapterCharacter.character_name)
                .where(ChapterCharacter.chapter_id == ch.id)
                .order_by(ChapterCharacter.character_name)
            )
        )
        .scalars()
        .all()
    )
    return MatchSignals(
        scene=scene,
        emotion=emotion,
        chapter_pos=_stage_to_pos(ch.plot_stage),
        characters=[n for n in names if n],
        genre=genre,
    )


async def _binding_domain(
    db: AsyncSession, novel_id: str
) -> tuple[str, list[str], str] | None:
    """书内启用且可进块的库域：(genre, concepts, fingerprint)。无 → None。

    fingerprint＝启用库 id 集的稳定指纹（换库/启停即变——复用守卫，批F F3）。
    零绑定账号 → 基线回退域（c-kb-baseline 批B D0-3）：官方精选层就绪即出块，
    不要求先建库绑定；有绑定的账号行为完全不变。"""
    rows = (
        await db.execute(
            select(KbBookBinding, KbLibrary)
            .join(KbLibrary, KbLibrary.id == KbBookBinding.library_id)
            .where(
                KbBookBinding.novel_id == novel_id,
                KbBookBinding.enabled.is_(True),
                KbLibrary.enabled.is_(True),
                KbLibrary.concept.in_(_BLOCK_CONCEPTS),
                KbLibrary.status == "active",
            )
        )
    ).all()
    if not rows:
        return await _baseline_domain(db, novel_id)
    genres = sorted({lib.genre for _b, lib in rows if lib.genre})
    genre = genres[0] if len(genres) == 1 else ""
    concepts = sorted({lib.concept for _b, lib in rows})
    fingerprint = hashlib.sha256(
        json.dumps(sorted(lib.id for _b, lib in rows), ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:64]
    return genre, concepts, fingerprint


async def _baseline_domain(
    db: AsyncSession, novel_id: str
) -> tuple[str, list[str], str] | None:
    """冷启动回退域：基线层未就绪（未同步/失败/空层）→ None（写法块不出现）。

    genre 取书题材（story KV），concepts 恒为可进块三类，fingerprint 由
    pack_version 派生——官方升级即换域重选（不误复用旧 run）。
    """
    from kb.baseline import VERSION_KEY
    from models.app_meta import AppMeta
    from models.kb import KbBaselineEntry

    probe = (
        await db.execute(select(KbBaselineEntry.entry_id).limit(1))
    ).scalar_one_or_none()
    if not probe:
        return None
    meta = await db.get(AppMeta, VERSION_KEY)
    version = int(meta.value) if meta and str(meta.value).isdigit() else 0

    genre = ""
    try:
        from filesystem.paths import PATH_TO_KEY
        from filesystem.storage import get_storage

        novel = await db.get(Novel, novel_id)
        if novel is not None and novel.root_path:
            story = await get_storage().read_yaml(
                novel.root_path, PATH_TO_KEY["story.yaml"]
            ) or {}
            genre = str(story.get("genre") or "").strip()
    except Exception:  # noqa: BLE001 — 题材读不到＝空（跨题材通用条目照出）
        genre = ""
    fingerprint = hashlib.sha256(
        f"baseline:{version}:{genre}".encode()
    ).hexdigest()[:64]
    return genre, list(_BLOCK_CONCEPTS), fingerprint


def _material_hash(novel_id: str, chapter_ref: str, signals_brief: dict) -> str:
    payload = json.dumps(
        {"novel": novel_id, "ref": chapter_ref, "signals": signals_brief},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _load_run_items(
    db: AsyncSession, run: KbMatchRun, *, user_id: str
) -> list[tuple[KbMatchItem, object | None]]:
    """run 清单 → (item, 条目) 双表解析（c-kb-baseline 批B）。

    代理 id 可能落 kb_entries（用户条目）或 kb_baseline_entries（官方精选层）：
    先查用户表，未命中的 id 再走 merged 基线回读（hide 已排、edit 副本已套）。
    两边都缺（条目已删/官方下架）→ entry=None，重建时按 text_snapshot 仍可出块。
    """
    from kb.merged import load_baseline_entries

    items = (
        await db.execute(
            select(KbMatchItem).where(KbMatchItem.run_id == run.id).order_by(KbMatchItem.id)
        )
    ).scalars().all()
    if not items:
        return []
    wanted = sorted({i.entry_id for i in items})
    entries: dict[str, object] = {
        e.id: e
        for e in (
            await db.execute(select(KbEntry).where(KbEntry.id.in_(wanted)))
        ).scalars()
    }
    missing = [i for i in wanted if i not in entries]
    if missing:
        for b in await load_baseline_entries(db, user_id=user_id, ids=missing):
            entries[b.id] = b
    return [(i, entries.get(i.entry_id)) for i in items]


def _rebuild_selection(
    items_with_entries, signals: MatchSignals | None = None
) -> Selection | None:
    """run 清单 → Selection（批F F2：条目文本走 text_snapshot 快照——条目编辑后
    同 run 重建仍逐字节同块）。decision=to_shadow 的条目不回块（量化走影子）。"""
    picked: list[SelectedItem] = []
    for item, entry in items_with_entries:
        if entry is None or item.decision != "included":
            continue
        picked.append(SelectedItem(
            entry=entry, score=item.score or 0.0, reason=item.reason or "",
            text_override=item.text_snapshot or "",  # F2：重建用固化文本
        ))
    if not picked:
        return None
    return Selection(signals=signals, items=picked)


async def _clear_kb_shadow_rows(db: AsyncSession, chapter_id: int) -> None:
    """清当章全部「知识库·」影子行（批F F4：停用/零命中/重选路径同清——
    旧量化约束不得绕过停用语义继续注入）。作者手填行不动。"""
    import json as _json

    ch = await db.get(Chapter, chapter_id)
    if ch is None:
        return
    try:
        shadow = _json.loads(ch.style_shadow or "{}")
    except Exception:  # noqa: BLE001
        return
    rows = shadow.get("rows") if isinstance(shadow.get("rows"), dict) else {}
    kept = {k: v for k, v in rows.items()
            if not str(v.get("reason") or "").startswith(_SHADOW_KB_PREFIX)}
    if kept != rows:
        shadow["rows"] = kept
        ch.style_shadow = _json.dumps(shadow, ensure_ascii=False)


async def _apply_quant_shadow(
    db: AsyncSession, chapter_id: int, quant_items: list[tuple[str, SelectedItem]]
) -> None:
    """量化条目 → 当章影子行（F6：value 只提数值短语＋condition 拆场面短语，
    「约 X」槽位不再塞整句；condition 进 reason 面具「交手场面适用」）。

    幂等：reason 前缀「知识库·」的行覆盖更新不堆叠；作者手填行不动。
    与 run/items 同事务（本函数只改对象不 commit——F4 单事务口径）。"""
    import json as _json
    import re as _re

    ch = await db.get(Chapter, chapter_id)
    if ch is None:
        return
    try:
        shadow = _json.loads(ch.style_shadow or "{}")
    except Exception:  # noqa: BLE001
        shadow = {}
    rows = shadow.get("rows") if isinstance(shadow.get("rows"), dict) else {}
    value_pat = _re.compile(
        r"(?:不超过|不少于|至少|至多|低于|约|左右|以内)?\s*\d+(?:\.\d+)?\s*"
        r"(?:字|句|段|行|%|％)(?:以内|左右|上下)?"
    )
    for dim, item in quant_items:
        text = (item.entry.instruction or "").strip()
        m = value_pat.search(text)
        value = m.group(0).strip() if m else text
        head = text[: m.start()] if m else ""
        dim_word = ""
        for w in ("句长", "段落", "篇幅", "修饰", "对话", "情绪", "镜头"):
            if w in head[-6:]:
                dim_word = w
                break
        if dim_word:
            value = f"{dim_word}{value}"
        cond_m = _re.match(r"^([\u4e00-\u9fa5]{1,4})(时|场面|情况)", text)
        condition = cond_m.group(0) if cond_m else ""
        title = item.entry.title or text[:16]
        reason = f"{_SHADOW_KB_PREFIX}{title}"
        rows[dim] = {
            "value": value,
            "reason": reason,
            **({"condition": condition} if condition else {}),
            "source": "kb",
        }
    shadow["rows"] = rows
    ch.style_shadow = _json.dumps(shadow, ensure_ascii=False)


async def _split_quantitative(
    db: AsyncSession, *, chapter_id: int, selection: Selection
) -> Selection | None:
    """量化条目（句长≤N字 类）→ 当章影子行数据变更（不 commit——与 run 同事务），
    其余条目留在写法块——同槽双写因此为 0。

    基线前提：书级 style_quant 未蒸馏或缺该维度基线行时影子无处渲染，量化条目
    回退进写法块（无基线＝无双写冲突源，design.md C2 注记）。"""
    from filesystem.paths import STYLE_QUANT_PATH
    from filesystem.storage import get_storage
    from settings.style_quant_model import BASELINE_KEYS

    ch = await db.get(Chapter, chapter_id)
    if ch is None:
        return selection
    novel = await db.get(Novel, ch.project_id)
    if novel is None or not novel.root_path:
        return selection
    doc = await get_storage().read_yaml(novel.root_path, STYLE_QUANT_PATH) or {}
    baseline = doc.get("baseline") if isinstance(doc.get("baseline"), dict) else {}

    def _baseline_has(key: str) -> bool:
        item = baseline.get(key)
        return bool(isinstance(item, dict) and str(item.get("value", "") or "").strip())

    stay, to_shadow = [], []
    for item in selection.items:
        dim = is_quantitative(item.entry)
        if dim in BASELINE_KEYS and _baseline_has(dim):
            to_shadow.append((dim, item))
        else:
            stay.append(item)
    if to_shadow:
        await _apply_quant_shadow(db, chapter_id, to_shadow)
    return Selection(signals=selection.signals, items=stay)


async def prepare_write_block(
    db: AsyncSession, *, novel_id: str, chapter_ref: str, user_id: str,
    refill: bool = False,
) -> tuple[str | None, str | None, list[dict] | None]:
    """主入口。返回 (块文本, run_id, 清单摘要[前端只读区])；整链不抛（失败无块）。"""
    try:
        domain = await _binding_domain(db, novel_id)
        ch = (
            await db.execute(
                select(Chapter).where(
                    Chapter.project_id == novel_id,
                    Chapter.ref == chapter_ref,
                    Chapter.ghost_of.is_(None),
                )
            )
        ).scalar_one_or_none()
        if domain is None or ch is None:
            if ch is not None:
                await _clear_kb_shadow_rows(db, ch.id)
                await db.commit()
            return None, None, None
        genre, concepts, fingerprint = domain
        chapter_pk = ch.id  # int 值拷贝：F1 rollback 会使 ORM 实例过期（MissingGreenlet 判例）

        runs = (
            await db.execute(
                select(KbMatchRun)
                .where(
                    KbMatchRun.novel_id == novel_id,
                    KbMatchRun.chapter_ref == chapter_ref,
                    KbMatchRun.status == "completed",
                )
                .order_by(KbMatchRun.created_at.desc(), KbMatchRun.id.desc())
                .limit(1)
            )
        ).scalars().all()

        signals = await extract_signals(
            db, novel_id=novel_id, chapter_ref=chapter_ref, genre=genre
        )
        if refill and runs:
            run = runs[0]  # 续写按章节复用当章最新 run（spec 口径：不比对 hash）
        else:
            run = None
            brief_hash = _material_hash(novel_id, chapter_ref, signals.brief())
            same = (
                await db.execute(
                    select(KbMatchRun)
                    .where(
                        KbMatchRun.novel_id == novel_id,
                        KbMatchRun.chapter_ref == chapter_ref,
                        KbMatchRun.brief_hash == brief_hash,
                        KbMatchRun.status == "completed",
                        KbMatchRun.domain_fingerprint == fingerprint,  # F3：换库即重选
                    )
                    .order_by(KbMatchRun.created_at.desc())
                    .limit(1)
                )
            ).scalars().all()
            same_hash_any_domain = (
                await db.execute(
                    select(KbMatchRun)
                    .where(
                        KbMatchRun.novel_id == novel_id,
                        KbMatchRun.chapter_ref == chapter_ref,
                        KbMatchRun.brief_hash == brief_hash,
                        KbMatchRun.status == "completed",
                    )
                    .order_by(KbMatchRun.created_at.desc())
                    .limit(1)
                )
            ).scalars().all()
            if same and same_hash_any_domain and same[0].id == same_hash_any_domain[0].id:
                run = same[0]
            elif same_hash_any_domain:
                # F3 换库（域指纹不匹配）：同素材恒一条 run——覆盖更新选集（唯一索引
                # uq(novel,ref,hash) 决定同 hash 不能并存两条；容量治理顺带收敛）
                run = same_hash_any_domain[0]
                selr = await select_block(
                    db, user_id=user_id, signals=signals,
                    genre=genre, concepts=concepts,
                )
                if selr is None:
                    await _clear_kb_shadow_rows(db, ch.id)
                    await db.commit()
                    return None, None, None
                selr = await _split_quantitative(db, chapter_id=chapter_pk, selection=selr)
                await _clear_kb_shadow_rows(db, chapter_pk)
                await db.flush()
                if selr is None:
                    await db.commit()
                    return None, None, None
                for old in (await db.execute(
                    select(KbMatchItem).where(KbMatchItem.run_id == run.id)
                )).scalars().all():
                    await db.delete(old)
                for it in selr.items:
                    db.add(KbMatchItem(
                        run_id=run.id,
                        clause="手法" if it.entry.concept == "手法" else "写法",
                        entry_id=it.entry.id, decision="included",
                        score=it.score, reason=it.reason,
                        text_snapshot=(it.entry.instruction or ""),
                    ))
                run.domain_fingerprint = fingerprint
                run.selector = "rule"
                run.scene, run.emotion, run.chapter_pos = signals.scene, signals.emotion, signals.chapter_pos
                await db.commit()
            elif same:
                run = same[0]
            else:
                selr = await select_block(
                    db, user_id=user_id, signals=signals,
                    genre=genre, concepts=concepts,
                )
                if selr is None:
                    await _clear_kb_shadow_rows(db, chapter_pk)  # F4：零命中同清影子
                    await db.commit()
                    return None, None, None  # 零命中不出块、不留 run
                selr = await _split_quantitative(db, chapter_id=chapter_pk, selection=selr)
                if selr is None:
                    return None, None, None
                run = KbMatchRun(
                    novel_id=novel_id,
                    chapter_ref=chapter_ref,
                    brief_hash=brief_hash,
                    scene=signals.scene,
                    emotion=signals.emotion,
                    chapter_pos=signals.chapter_pos,
                    status="completed",
                    domain_fingerprint=fingerprint,  # F3
                    selector="rule",                 # F8：P1 预留
                    brief_json=json.dumps(signals.brief(), ensure_ascii=False),
                )
                # F1 竞态：并发首生成撞唯一键 → rollback 后复用赢家 run（同素材同块）
                try:
                    db.add(run)
                    await db.flush()
                    for it in selr.items:
                        db.add(KbMatchItem(
                            run_id=run.id,
                            clause="手法" if it.entry.concept == "手法" else "写法",
                            entry_id=it.entry.id, decision="included",
                            score=it.score, reason=it.reason,
                            text_snapshot=(it.entry.instruction or ""),  # F2 快照
                        ))
                    await db.commit()
                except IntegrityError:
                    await db.rollback()
                    _ = chapter_pk
                    race = (
                        await db.execute(
                            select(KbMatchRun)
                            .where(
                                KbMatchRun.novel_id == novel_id,
                                KbMatchRun.chapter_ref == chapter_ref,
                                KbMatchRun.brief_hash == brief_hash,
                                KbMatchRun.status == "completed",
                            )
                            .order_by(KbMatchRun.created_at.desc())
                            .limit(1)
                        )
                    ).scalars().first()
                    if race is None:
                        raise
                    run = race
                    # 赢家 run 的量化条目影子补写（rollback 丢了本流影子改动）
                    pair = await _load_run_items(db, run, user_id=user_id)
                    quant = []
                    for it, entry in pair:
                        dim = is_quantitative(entry) if entry else None
                        if dim and it.decision == "included":
                            quant.append((dim, SelectedItem(
                                entry=entry, score=it.score or 0.0, reason=it.reason or "",
                            )))
                    await _apply_quant_shadow(db, chapter_pk, quant)
                    await db.commit()

        pair = await _load_run_items(db, run, user_id=user_id)
        run_signals = MatchSignals(
            scene=run.scene, emotion=run.emotion, chapter_pos=run.chapter_pos, genre=genre,
        )
        selr = _rebuild_selection(pair, signals=run_signals)
        if selr is None:
            return None, None, None
        block, _skipped = build_block(selr)
        listing = [
            {
                "entry_id": it.entry_id,
                "clause": it.clause,
                "reason": it.reason,
                "score": it.score,
                "text": it.text_snapshot or ((entry.instruction or "") if entry else ""),
            }
            for it, entry in pair
            if it.decision == "included"
        ]
        return block, run.id, listing
    except Exception as e:  # noqa: BLE001 — 写法块任何异常不阻断生成主链
        logger.warning("event=write_block_failed novel=%s ref=%s err=%s", novel_id, chapter_ref, e)
        return None, None, None
