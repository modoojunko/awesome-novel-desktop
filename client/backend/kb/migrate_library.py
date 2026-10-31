"""角色库 → 知识库迁移（c-kb-character-migration 批6）。

character_library 全量 → kb_entries（concept=角色设定）：
- 幂等：src_kind="character_library_migration"、src_ref="character_library"、
  src_key=原卡 id；部分唯一索引 (user_id, src_ref, src_key) 兜底，重复迁移零副本
- 字段映射 parity：卡名→archetype/title、persona、档案八格、认知十一格逐格复制；
  空格不落（payload 扁平形态见 CharacterPayload）
- legacy 原文不迁移（6.5 口径）；头像仍住 CharacterLibraryBlob（src_key 可回联），
  UI 数据源切换（6.4）后再迁头像引用
- character_library 表本身原样保留（6.6 deprecated 标注在模型），删除属后续版本
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.character_library import CharacterLibrary
from models.kb import KbEntry

# 迁移列：卡字段 → payload 顶层键（逐格 clamp 上限）
_DOSSIER_GRID = ("gender", "age", "race", "faction", "look", "speech", "background", "plot")
_COG_GRID = ("w1", "w5", "s1", "s5", "v1", "p2", "p6", "p3", "p4", "b1", "e3")
_CELL_MAX = 300


def card_to_payload(card: CharacterLibrary) -> dict[str, Any]:
    """库卡 → 角色设定 payload（扁平全量；空格不落）。"""
    payload: dict[str, Any] = {"archetype": str(card.name or "").strip()[:50]}
    persona = str(card.persona or "").strip()
    if persona:
        payload["persona"] = persona[:300]
    try:
        dossier = json.loads(card.dossier or "{}")
    except ValueError:
        dossier = {}
    try:
        cog = json.loads(card.cog or "{}")
    except ValueError:
        cog = {}
    if not isinstance(dossier, dict):
        dossier = {}
    if not isinstance(cog, dict):
        cog = {}
    for k in _DOSSIER_GRID:
        v = str(dossier.get(k) or "").strip()
        if v:
            payload[k] = v[:_CELL_MAX]
    for k in _COG_GRID:
        v = str(cog.get(k) or "").strip()
        if v:
            payload[k] = v[:_CELL_MAX]
    return payload


async def migrate_character_library(db: AsyncSession, *, user_id: str) -> dict[str, int]:
    """全量迁移一个账号的库卡。返回 {migrated, skipped}。

    可重复执行：已迁移卡按 src_key 跳过（部分唯一索引兜并发）。
    """
    cards = (
        await db.scalars(select(CharacterLibrary).where(CharacterLibrary.user_id == user_id))
    ).all()
    if not cards:
        return {"migrated": 0, "skipped": 0}

    migrated = skipped = 0
    for card in cards:
        existing = (
            await db.execute(
                select(KbEntry.id).where(
                    KbEntry.user_id == user_id,
                    KbEntry.src_ref == "character_library",
                    KbEntry.src_key == card.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue
        payload = card_to_payload(card)
        persona = str(card.persona or "").strip()
        db.add(
            KbEntry(
                user_id=user_id,
                # 题材不在 21 目录（旧卡自由填写）→ 落跨题材通用（""）
                genre=card.genre if card.genre else "",
                concept="角色设定",
                concept_id=f"{card.genre or ''}:角色设定",
                title=str(card.name or "")[:40],
                payload_json=json.dumps(payload, ensure_ascii=False),
                # 指令＝一句人设（手录闸门句末断口径：补句号）
                instruction=(persona or str(card.name or ""))[:240],
                when_json="{}",
                evidence=str(card.src_novel_name or "")[:200],
                src_kind="character_library_migration",
                src_ref="character_library",
                src_key=card.id,
            )
        )
        migrated += 1
    await db.commit()
    return {"migrated": migrated, "skipped": skipped}
