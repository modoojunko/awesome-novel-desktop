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


# 可收录维度（与 deconstruct 维度键一一对应；简介/主线/章卷等暂无条目映射）
DIM_LABELS: dict[str, str] = {
    "techniques": "写作技法",
    "style": "写作文风",
    "world": "世界设定",
    "characters": "角色设定",
}

# SDK src_key 前缀 → 拆书维度（mapping.py 的 add(prefix, ...)；style./world./craft. 带点）。
# craft.craft/craft.taboo（文笔）与 style.*（文风）同出 products["style"]——
# 漏掉 craft 前缀会让「写作文风」组少算条数、按维过滤时文笔条目静默不收（review P1）。
_DIM_PREFIXES: tuple[tuple[str, str], ...] = (
    ("style.", "style"),
    ("craft", "style"),
    ("world.", "world"),
    ("technique", "techniques"),
    ("character", "characters"),
)


def entry_dim(src_key: str) -> str:
    """映射条目的来源维度；未知前缀返回空串（不进任何分组）。"""
    for prefix, dim in _DIM_PREFIXES:
        if str(src_key or "").startswith(prefix):
            return dim
    return ""


async def find_collected_keys(
    db: AsyncSession,
    user_id: str,
    refs: set[str],
    keys: list[str],
) -> set[str]:
    """已入库的来源键（收录去重与候选预览共用同一口径）。"""
    if not refs or not keys:
        return set()
    stmt = select(KbKnowledge.src_key).where(
        KbKnowledge.user_id == user_id,
        KbKnowledge.src_ref.in_(refs),
        KbKnowledge.src_key.in_(keys),
    )
    return set((await db.execute(stmt)).scalars().all())


async def collect_task_to_kb(
    db: AsyncSession,
    user_id: str,
    task,
    *,
    genre_override: str = "",
    src_ref: str = "",
    dims: list[str] | None = None,
) -> dict:
    """拆书任务 → 知识库（幂等）：映射＋去重＋默认库＋标签物化。

    dims 非 None 时只收所选维度（界面按勾选收）；None＝全量（批量脚本/reconcile）。
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
    if dims is not None:
        # 先全量映射再按维过滤：SDK 的 src_key 是全局自增序号（prefix:seq），
        # 先裁产物再映射会让剩余维度序号前移，与已入库键错位（判重会误跳/重写）。
        keep = {str(d) for d in dims if str(d) in DIM_LABELS}
        entries = [e for e in entries if entry_dim(e.src_key) in keep]

    existing_keys: set[str] = set()
    if entries:
        # 兼容两种来源键（脚本按书内容指纹、界面按 task_id）：任一已入库即跳过，
        # 防止同一份产物经两条入口各收一遍。src_key 序号在两次映射间稳定（同一产物）。
        refs = {src_ref or str(task.id)}
        if src_ref:
            refs.add(str(task.id))
        existing_keys = await find_collected_keys(
            db, user_id, refs, [e.src_key for e in entries]
        )

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
