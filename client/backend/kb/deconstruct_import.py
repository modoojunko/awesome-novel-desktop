"""拆书产物 → 知识库条目映射（薄壳——映射核心已迁 SDK 一期，c-knowledge-source-align）。

映射逻辑单源住 vendor_sdk/novel_deconstruct_sdk.mapping（纯核心零应用层依赖，
知识仓 deconstruct_batch 同调该 SDK）——本模块只保留：

- 薄壳签名兼容：map_deconstruct_products / genre_from_products（EntryData→KbKnowledge 适配）
- C 端编排：collect_task_to_kb（落库/去重/默认库/标签物化——应用层，不进 SDK）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# SDK 仓内包定位（dev 态路径注入；冻结态由 Nuitka --include-plugin-directory 编译内嵌）
_VENDOR_SDK = Path(__file__).resolve().parent.parent / "vendor_sdk"
if str(_VENDOR_SDK) not in sys.path:
    sys.path.insert(0, str(_VENDOR_SDK))

from novel_deconstruct_sdk import EntryData
from novel_deconstruct_sdk import genre_from_products as _sdk_genre_from_products
from novel_deconstruct_sdk.mapping import map_deconstruct_products as _sdk_map_products

from models.kb import KbKnowledge

__all__ = ["collect_task_to_kb", "genre_from_products", "map_deconstruct_products"]


def _to_orm(entry: EntryData) -> KbKnowledge:
    """SDK EntryData → C 端 KbKnowledge ORM（字段一一对应；本薄壳唯一适配点）。"""
    return KbKnowledge(
        user_id=entry.user_id,
        genre=entry.genre,
        concept=entry.concept,
        concept_id=entry.concept_id,
        title=entry.title,
        payload_json=entry.payload_json,
        payload_version=entry.payload_version,
        instruction=entry.instruction,
        example=entry.example,
        negative_example=entry.negative_example,
        when_json=entry.when_json,
        evidence=entry.evidence,
        evidence_json=entry.evidence_json,
        src_kind=entry.src_kind,
        src_ref=entry.src_ref,
        src_key=entry.src_key,
        src_novel_name=entry.src_novel_name,
    )


def genre_from_products(products: dict) -> str:
    """薄壳 re-export（单源在 SDK）。"""
    return _sdk_genre_from_products(products)


def map_deconstruct_products(
    user_id: str,
    task_id: str,
    genre: str,
    products: dict,
    *,
    src_ref: str | None = None,
) -> tuple[list[KbKnowledge], list[str]]:
    """薄壳：SDK 纯映射（EntryData）→ ORM 对象（C 端落库口径不变）。"""
    entries, warnings = _sdk_map_products(user_id, task_id, genre, products, src_ref=src_ref)
    return [_to_orm(e) for e in entries], warnings


async def collect_task_to_kb(
    db: AsyncSession,
    user_id: str,
    task,
    *,
    genre_override: str = "",
    src_ref: str = "",
) -> dict:
    """拆书任务 → 知识库（幂等）：映射＋去重＋默认库＋标签物化。

    返回 {collected, skipped, total_mapped, warnings, genre}；
    产物为空抛 ValueError（端点转 422，脚本按失败记账）。
    """
    try:
        products = json.loads(getattr(task, "products_json", "") or "{}")
    except ValueError:
        products = {}
    if not isinstance(products, dict) or not products:
        raise ValueError("这批产物为空，无法收录")

    if genre_override:
        from genres.theme_catalog import normalize_theme

        genre = normalize_theme(str(genre_override).strip())
    else:
        genre = genre_from_products(products)

    entries, warnings = map_deconstruct_products(
        user_id, str(task.id), genre, products, src_ref=src_ref or None
    )

    existing_keys: set[str] = set()
    if entries:
        # 兼容两种来源键（脚本按书内容指纹、界面按 task_id）：任一已入库即跳过，
        # 防止同一份产物经两条入口各收一遍。src_key 序号在两次映射间稳定（同一产物）。
        refs = {src_ref or str(task.id)}
        if src_ref:
            refs.add(str(task.id))
        stmt = select(KbKnowledge.src_key).where(
            KbKnowledge.user_id == user_id,
            KbKnowledge.src_ref.in_(refs),
            KbKnowledge.src_key.in_([e.src_key for e in entries]),
        )
        existing_keys = set((await db.execute(stmt)).scalars().all())

    new_entries = [e for e in entries if e.src_key not in existing_keys]
    for entry in new_entries:
        # c-kb-summarize：收录落素材行（origin='material'）——产物卡是事实记录，
        # 经总结采纳才成为知识。不物化标签、不长默认库（素材不进选择器/星图）。
        entry.origin = "material"
        # 出处书名（c-kb-collect-dims）：此前恒空致实例出处行结构性无值——
        # 落任务书名，素材/转生实例的「源自：书名」从此有源
        entry.src_novel_name = str(getattr(task, "book_name", "") or "")[:100]
        db.add(entry)
        await db.flush()
    await db.commit()

    return {
        "collected": len(new_entries),
        "skipped": len(entries) - len(new_entries),
        "total_mapped": len(entries),
        "warnings": warnings,
        "genre": genre,
    }
