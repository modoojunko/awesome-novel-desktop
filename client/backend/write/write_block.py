"""本章写法块注入器（c-kb-write-block B3/B4/B5）——write 链专用组装段。

- 启用判定：kb_book_bindings（enabled）join kb_libraries（enabled＋概念∈手法/文风/文笔）
  ——未启用任何相关库 → (None, None, None)，调用方零变化
- 复用语义：同章同素材（brief_hash）重试复用既有 run 重建块（逐字节一致）；
  续写/补足按章节复用当章最新 run；停用后无块（SHALL NOT 注入旧 run）
- run/items 落库：首生成选择完成即落（失败章也有 run；status=completed）
- SSE 事件由调用方转发（type=write_block）
"""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kb.block import build_block
from kb.match import SelectedItem, Selection, is_quantitative, select_block
from models.kb import KbBookBinding, KbEntry, KbLibrary, KbMatchItem, KbMatchRun

logger = logging.getLogger(__name__)

_BLOCK_CONCEPTS = ("手法", "文风", "文笔")


async def _binding_domain(
    db: AsyncSession, novel_id: str
) -> tuple[str, list[str]] | None:
    """书内启用且可进块的库域：(genre, concepts)。无 → None。"""
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
        return None
    genres = sorted({lib.genre for _b, lib in rows if lib.genre})
    genre = genres[0] if len(genres) == 1 else ""
    concepts = sorted({lib.concept for _b, lib in rows})
    return genre, concepts


def _material_hash(novel_id: str, chapter_ref: str, signals_brief: dict) -> str:
    payload = json.dumps(
        {"novel": novel_id, "ref": chapter_ref, "signals": signals_brief},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _load_run_items(
    db: AsyncSession, run: KbMatchRun
) -> list[tuple[KbMatchItem, KbEntry | None]]:
    items = (
        await db.execute(
            select(KbMatchItem).where(KbMatchItem.run_id == run.id).order_by(KbMatchItem.id)
        )
    ).scalars().all()
    entries = {
        e.id: e
        for e in (
            await db.execute(
                select(KbEntry).where(KbEntry.id.in_([i.entry_id for i in items] or ["-"]))
            )
        ).scalars()
    } if items else {}
    return [(i, entries.get(i.entry_id)) for i in items]


def _rebuild_selection(items_with_entries) -> Selection | None:
    """run 清单 → Selection（组装器输入；跳过的条目当年已不进 items）。"""
    picked: list[SelectedItem] = []
    for item, entry in items_with_entries:
        if entry is None or item.decision != "included":
            continue
        picked.append(SelectedItem(entry=entry, score=item.score or 0.0, reason=item.reason or ""))
    if not picked:
        return None
    return Selection(signals=None, items=picked)  # type: ignore[arg-type]


async def _split_quantitative_to_shadow(
    db: AsyncSession, *, novel_id: str, chapter_ref: str, selection: Selection
) -> Selection | None:
    """量化条目（句长≤N字 类）→ 当章文风影子行（既有 shadow_override_lines 渲染
    「本章覆盖：知识库·…」），其余条目留在写法块——同槽双写因此为 0。

    基线前提：书级 style_quant 未蒸馏（confidence≤0 或缺该维度基线行）时影子无处
    渲染，量化条目回退进写法块（无基线＝无双写冲突源，design.md C2 注记）。
    幂等：reason 前缀「知识库·」的行每次覆盖更新，不堆叠；作者手填行不动。
    """
    from filesystem.paths import STYLE_QUANT_PATH
    from filesystem.storage import get_storage
    from models.chapter import Chapter as _Chapter
    from models.project import Novel as _Novel
    from settings.style_quant_model import BASELINE_KEYS

    ch = (
        await db.execute(
            select(_Chapter).where(
                _Chapter.project_id == novel_id, _Chapter.ref == chapter_ref
            )
        )
    ).scalar_one_or_none()
    novel = await db.get(_Novel, novel_id)
    if ch is None or novel is None or not novel.root_path:
        return selection
    root_path = novel.root_path
    doc = await get_storage().read_yaml(root_path, STYLE_QUANT_PATH) or {}
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
    if not to_shadow:
        return selection

    import json as _json

    try:
        shadow = _json.loads(ch.style_shadow or "{}")
    except Exception:  # noqa: BLE001 — 影子损坏按空处理
        shadow = {}
    rows = shadow.get("rows") if isinstance(shadow.get("rows"), dict) else {}
    for dim, item in to_shadow:
        rows[dim] = {
            "value": (item.entry.instruction or "").strip(),
            "reason": f"知识库·{item.entry.title or (item.entry.instruction or '')[:16]}",
        }
    shadow["rows"] = rows
    ch.style_shadow = _json.dumps(shadow, ensure_ascii=False)
    await db.commit()
    return Selection(signals=selection.signals, items=stay)


async def prepare_write_block(
    db: AsyncSession, *, novel_id: str, chapter_ref: str, user_id: str,
    refill: bool = False,
) -> tuple[str | None, str | None, list[dict] | None]:
    """主入口。返回 (块文本, run_id, 清单摘要[前端只读区])；整链不抛（失败无块）。"""
    try:
        domain = await _binding_domain(db, novel_id)
        if domain is None:
            return None, None, None
        genre, concepts = domain

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

        if refill and runs:
            run = runs[0]  # 续写按章节复用当章最新 run
        else:
            run = None
            # 生成路径：同章同素材（brief_hash）复用；素材变或无 run → 重新选择
            from kb.match import extract_signals

            signals = await extract_signals(
                db, novel_id=novel_id, chapter_ref=chapter_ref, genre=genre
            )
            brief_hash = _material_hash(novel_id, chapter_ref, signals.brief())
            same = (
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
            if same:
                run = same[0]
            else:
                selr = await select_block(
                    db, user_id=user_id, novel_id=novel_id, chapter_ref=chapter_ref,
                    genre=genre, concepts=concepts,
                )
                if selr is None:
                    return None, None, None  # 零命中不出块、不留 run
                selr = await _split_quantitative_to_shadow(
                    db, novel_id=novel_id, chapter_ref=chapter_ref, selection=selr
                )
                if selr is None:
                    return None, None, None  # 全部量化且无基线兜底路径为空（罕见）
                run = KbMatchRun(
                    novel_id=novel_id,
                    chapter_ref=chapter_ref,
                    brief_hash=brief_hash,
                    scene=signals.scene,
                    emotion=signals.emotion,
                    chapter_pos=signals.chapter_pos,
                    status="completed",
                )
                db.add(run)
                await db.flush()
                for it in selr.items:
                    db.add(KbMatchItem(
                        run_id=run.id, clause="手法" if it.entry.concept == "手法" else "写法",
                        entry_id=it.entry.id, decision="included",
                        score=it.score, reason=it.reason,
                    ))
                await db.commit()

        pair = await _load_run_items(db, run)
        selr = _rebuild_selection(pair)
        if selr is None:
            return None, None, None
        block, _skipped = build_block(selr)
        listing = [
            {
                "entry_id": it.entry_id,
                "clause": it.clause,
                "reason": it.reason,
                "score": it.score,
                "text": (entry.instruction or "") if entry else "",
            }
            for it, entry in pair
            if it.decision == "included"
        ]
        return block, run.id, listing
    except Exception as e:  # noqa: BLE001 — 写法块任何异常不阻断生成主链
        logger.warning("event=write_block_failed novel=%s ref=%s err=%s", novel_id, chapter_ref, e)
        return None, None, None
