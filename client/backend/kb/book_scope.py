"""书级知识副本（c-kb-book-scope 批A/D）——作家的知识与书的知识分家。

- stream_import_genre_knowledge：分概念组流式复制（SSE 进度条数据源）；
  组内批量克隆、组间 yield 进度事件；基线面（style/world KV）收尾统一落。
- import_genre_knowledge：非流式包装（跑完生成器返回汇总）——测试/存量调用用。
- 幂等：src_key（源条目 id）已复制即跳过；复制即脱离（双向零回写）。
- 基线面：world 只落舞台/力量/代价（源书事实/铁律不灌新书，评审 F-2）；
  文风示范段来源标记（F-1）；量化合成保守基线（F-3）。
- book_scope_fingerprint：书级域指纹（无状态 hash——副本计数＋最新 updated_at；
  pref 标记不刷新 → 不打破重试字节一致）。
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.kb import (
    KbBookEntry,
    KbBookEntryTag,
    KbEntry,
    KbEntryTag,
    KbLibrary,
    KbPref,
)
from settings.style_quant_model import BASELINE_KEYS

_CONCEPT_ORDER = ("手法", "文风", "文笔", "世界设定", "角色设定")


async def _load_import_state(
    db: AsyncSession, *, novel_id: str, user_id: str, genre: str
) -> tuple[list[KbEntry], list[KbEntry]]:
    """导入差集：(active 题材命中＋通用条目, 尚未复制进本书的条目)。"""
    rows = (
        await db.execute(
            select(KbEntry).where(
                KbEntry.user_id == user_id,
                KbEntry.status == "active",
                (KbEntry.genre == genre) | (KbEntry.genre == ""),
            )
        )
    ).scalars().all()
    have = set(
        (
            await db.execute(
                select(KbBookEntry.src_key).where(
                    KbBookEntry.novel_id == novel_id,
                    KbBookEntry.src_kind == "book_copy",
                    KbBookEntry.status == "active",
                )
            )
        ).scalars()
    )
    return list(rows), [src for src in rows if src.id not in have]


async def stream_import_genre_knowledge(
    db: AsyncSession, *, novel_id: str, user_id: str, genre: str
) -> AsyncIterator[dict]:
    """流式导入（async generator）：逐概念组复制并 yield 进度事件，收尾基线面。

    事件形状：
      {"type": "phase", "phase": "copy", "concept": X, "done": n, "total": N}
      {"type": "phase", "phase": "baseline"}
      {"type": "done", "imported": n, "skipped": n, "style_land": {...}, "world_land": {...}}
    副本行/标签/种子权重单事务（末尾 commit）；基线 KV 落地在其后（另一介质）。
    并发双开（两个标签页同时点导入）：唯一索引冲突时回滚重算差集重来一次，
    不把 UNIQUE 错误丢给用户（对方已落库的条目按 skipped 计）。"""
    rows, todo = await _load_import_state(
        db, novel_id=novel_id, user_id=user_id, genre=genre
    )
    total = len(todo)
    skipped = len(rows) - total  # 幂等跳过数（已复制过）
    yield {"type": "phase", "phase": "copy", "total": total}

    copied = 0
    new_rows: list[tuple[KbBookEntry, KbEntry]] = []
    attempt = 0
    while True:
        done = 0
        try:
            for concept in _CONCEPT_ORDER:
                group = [src for src in todo if src.concept == concept]
                if not group:
                    continue
                for src in group:
                    row = KbBookEntry(
                        novel_id=novel_id,
                        user_id=user_id,
                        genre=src.genre,
                        concept=src.concept,
                        concept_id=src.concept_id,
                        title=src.title,
                        payload_json=src.payload_json,
                        payload_version=src.payload_version,
                        instruction=src.instruction,
                        example=src.example,
                        negative_example=src.negative_example,
                        when_json=src.when_json,
                        evidence=src.evidence,
                        evidence_json=src.evidence_json,
                        rev=src.rev,
                        src_kind="book_copy",
                        src_ref=novel_id,
                        src_key=src.id,
                    )
                    db.add(row)
                    new_rows.append((row, src))
                    copied += 1
                    done += 1
                await db.flush()
                yield {
                    "type": "phase", "phase": "copy", "concept": concept,
                    "done": done, "total": total,
                }

            if new_rows:
                # 标签物化：源条目 tags 原样克隆（比重算保真）
                src_ids = [src.id for _row, src in new_rows]
                src_tags = (
                    await db.execute(
                        select(KbEntryTag).where(KbEntryTag.entry_id.in_(src_ids))
                    )
                ).scalars().all()
                copy_by_src = {row.src_key: row for row, _src in new_rows}
                for t in src_tags:
                    copy = copy_by_src.get(t.entry_id)
                    if copy is None:
                        continue
                    db.add(KbBookEntryTag(
                        entry_id=copy.id, novel_id=novel_id, user_id=user_id,
                        dim=t.dim, value=t.value,
                    ))
                # 经验继承：源条目 pref 有用率播种为副本初始权重（未标记源=1.0）
                src_prefs = {
                    p.entry_id: p
                    for p in (
                        await db.execute(
                            select(KbPref).where(
                                KbPref.user_id == user_id, KbPref.entry_id.in_(src_ids)
                            )
                        )
                    ).scalars()
                }
                for row, src in new_rows:
                    p = src_prefs.get(src.id)
                    if p is not None and (p.adopt_count + p.drop_count) > 0:
                        total_cnt = p.adopt_count + p.drop_count
                        db.add(KbPref(
                            user_id=user_id, entry_id=row.id,
                            weight=max(0.2, p.adopt_count / total_cnt),
                            adopt_count=p.adopt_count, drop_count=p.drop_count,
                        ))
            await db.commit()  # 副本＋标签＋种子权重一次落（KV 落地在其后，另一介质）
            break
        except IntegrityError:
            # 并发导入抢先落库（同 (novel_id, src_key) 已存在）——回滚重算差集重来；
            # 第二轮仍冲突＝真实数据问题，照旧上抛。
            await db.rollback()
            if attempt >= 1:
                raise
            attempt += 1
            rows, todo = await _load_import_state(
                db, novel_id=novel_id, user_id=user_id, genre=genre
            )
            total = len(todo)
            skipped = len(rows) - total
            copied = 0
            new_rows = []
            yield {"type": "phase", "phase": "copy", "total": total}

    yield {"type": "phase", "phase": "baseline"}
    style_land, world_land = await _land_baselines(
        db, novel_id=novel_id, user_id=user_id, genre=genre
    )
    if new_rows:
        from models.project import Novel as _Novel

        novel = await db.get(_Novel, novel_id)
        if novel is not None and novel.root_path:
            await synthesize_quant_baseline(
                novel.root_path, [row for row, _src in new_rows]
            )
    yield {
        "type": "done",
        "imported": copied,
        "skipped": skipped,
        "style_land": style_land,
        "world_land": world_land,
    }


async def import_genre_knowledge(
    db: AsyncSession, *, novel_id: str, user_id: str, genre: str
) -> dict:
    """非流式包装：跑完流式导入，返回最终汇总（测试/存量调用方用）。"""
    summary: dict = {}
    async for ev in stream_import_genre_knowledge(
        db, novel_id=novel_id, user_id=user_id, genre=genre
    ):
        if ev["type"] == "done":
            summary = {
                "imported": ev["imported"],
                "skipped": ev["skipped"],
                "style_land": ev["style_land"],
                "world_land": ev["world_land"],
            }
    return summary


async def _land_baselines(
    db: AsyncSession, *, novel_id: str, user_id: str, genre: str
) -> tuple[dict, dict]:
    """题材默认库（auto/enabled）的基线条目 → 本书 style/world KV（复用 apply_members）。

    world 白名单只落舞台/力量/代价（源书事实/铁律不灌新书——评审 F-2）；
    文风示范段来源标注走 style_meta.source="kb-genre"（渲染端分源，F-1）。"""
    from kb.snapshot import apply_members, build_members, library_base_entries
    from models.project import Novel

    libs = (
        await db.execute(
            select(KbLibrary).where(
                KbLibrary.user_id == user_id,
                KbLibrary.genre == genre,
                KbLibrary.status == "active",
                KbLibrary.rule_kind == "auto",
                KbLibrary.enabled.is_(True),
                KbLibrary.concept.in_(("文风", "文笔", "世界设定")),
            )
        )
    ).scalars().all()
    style_land: dict = {}
    world_land: dict = {}
    novel = await db.get(Novel, novel_id)
    if novel is None or not libs:
        return style_land, world_land
    for lib in libs:
        entries = await library_base_entries(db, lib)
        await db.commit()  # 结束隐式读事务——KV 写（另一连接）不等本会话读锁
        members = build_members(entries)
        landed = await apply_members(novel.root_path, members, source="kb-genre")
        for k, v in landed.items():
            if k.startswith("style."):
                style_land[k] = v
            elif k.startswith("world."):
                world_land[k] = v
    return style_land, world_land


async def novel_genre(root_path: str) -> str:
    """本书题材名（story KV 的 `genre` 键）——知识库题材匹配口径。

    D19 关系化后题材目录仍落 KV（genres/service.py resolve_genre_context 同源读法）；
    Novel 模型本身没有 genre 列，不要读 novel.genre。"""
    from filesystem.storage import get_storage

    story = await get_storage().read_yaml(root_path, "story.yaml")
    if not isinstance(story, dict):
        return ""
    return str(story.get("genre") or "").strip()


async def read_import_declined(root_path: str) -> bool:
    """作家是否已选过「我自己设定」（不再自动弹导入弹窗）。"""
    from filesystem.paths import KB_IMPORT_PATH
    from filesystem.storage import get_storage

    doc = await get_storage().read_yaml(root_path, KB_IMPORT_PATH)
    return bool(isinstance(doc, dict) and doc.get("declined"))


async def write_import_declined(root_path: str, declined: bool) -> None:
    """写/清「我自己设定」决策；改题材时调用方传 False 复位。"""
    from filesystem.paths import KB_IMPORT_PATH
    from filesystem.storage import get_storage

    await get_storage().write_yaml(root_path, KB_IMPORT_PATH, {"declined": bool(declined)})


async def book_scope_fingerprint(db: AsyncSession, *, novel_id: str) -> str:
    """书级域指纹（写法块复用守卫）＝hash(副本计数, max(updated_at))。

    无状态现算零维护；pref 标记不刷 updated_at → 不打破重试字节一致。"""
    row = (
        await db.execute(
            select(
                func.count(KbBookEntry.id),
                func.max(KbBookEntry.updated_at),
            ).where(
                KbBookEntry.novel_id == novel_id,
                KbBookEntry.status == "active",
            )
        )
    ).one()
    payload = f"{novel_id}:{row[0]}:{row[1].isoformat() if row[1] else ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:64]


async def synthesize_quant_baseline(root_path: str, copies) -> None:
    """量化合成保守基线（c-kb-book-scope 批C；提示词评审 F-3）。

    书级 style-quant 未蒸馏（confidence=0/缺）且副本含量化条目时：按维度合成
    六行基线（confidence=40 → ±30% 最保守档），来源标注「知识库·题材（合成）」；
    作者后续蒸馏 SHALL 覆盖合成值。下限型（不少于/至少）不进「约 X」框架——跳过。"""
    import re as _re
    from datetime import datetime as _dt

    from filesystem.paths import STYLE_QUANT_PATH
    from filesystem.storage import get_storage
    from settings.style_quant_model import quant_doc

    doc = quant_doc(await get_storage().read_yaml(root_path, STYLE_QUANT_PATH))
    if int(doc.get("confidence") or 0) > 0:
        return  # 已蒸馏：作者资产不动
    baseline = doc.get("baseline") if isinstance(doc.get("baseline"), dict) else {}
    value_pat = _re.compile(
        r"(不少于|至少|高于)?\s*\d+(?:\.\d+)?\s*(?:字|句|段|行|%|％)"
    )
    for row in sorted(copies, key=lambda c: c.title or ""):
        if row.concept not in ("文笔", "文风", "手法"):
            continue
        text = (row.instruction or "").strip()
        m = value_pat.search(text)
        if not m:
            continue
        if m.group(1):  # 下限型：不进「约 X」框架
            continue
        from kb.match import is_quantitative

        dim = is_quantitative(row)
        if dim not in BASELINE_KEYS or dim in baseline and baseline[dim].get("value"):
            continue
        baseline[dim] = {"value": m.group(0).strip(), "tolerance": 30}
    if not baseline:
        return
    doc["confidence"] = 40
    doc["sample_chars"] = 0
    doc["updated_at"] = _dt.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    doc["baseline"] = baseline
    doc["source"] = "kb-synthesized"
    await get_storage().write_yaml(root_path, STYLE_QUANT_PATH, doc)
