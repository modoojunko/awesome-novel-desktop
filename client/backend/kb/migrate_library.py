"""角色库 → 知识库迁移（c-kb-character-migration 批6）。

character_library 全量 → kb_entries（concept=角色设定）：
- 幂等：src_kind="character_library_migration"、src_ref="character_library"、
  src_key=原卡 id；部分唯一索引 (user_id, src_ref, src_key) 兜底，重复迁移零副本
- 字段映射 parity：卡名→archetype/title、persona、档案八格、认知十一格逐格复制；
  空格不落（payload 扁平形态见 CharacterPayload）；plot 尾部「（第N章）」回查锚
  剥到 evidence 列——粘尾形态只活在拆书预览角色页（#906），知识库证据有自己的列
- legacy 原文不迁移（6.5 口径）；头像仍住 CharacterLibraryBlob（src_key 可回联），
  UI 数据源切换（6.4）后再迁头像引用
- character_library 表本身原样保留（6.6 deprecated 标注在模型），删除属后续版本
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deconstruct.cards import split_plot_evidence
from models.character_library import CharacterLibrary
from models.kb import KbEntry

logger = logging.getLogger(__name__)

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
    # 卡级分类（6.4 数据源切换：与库卡同构；aliases 解析失败按空）
    try:
        aliases = json.loads(card.aliases or "[]")
    except ValueError:
        aliases = []
    if isinstance(aliases, list) and aliases:
        payload["aliases"] = [str(a).strip()[:50] for a in aliases if str(a).strip()][:20]
    if str(card.role or "").strip():
        payload["role"] = str(card.role).strip()[:10]
    if str(card.kind or "").strip():
        payload["kind"] = str(card.kind).strip()[:20]
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
        if not v:
            continue
        if k == "plot":
            # 尾部「（第N章）」是拆书预览页的回查锚（#906）；KB 证据有自己的列，落库换轨
            v = split_plot_evidence(v)[0]
        payload[k] = v[:_CELL_MAX]
    for k in _COG_GRID:
        v = str(cog.get(k) or "").strip()
        if v:
            payload[k] = v[:_CELL_MAX]
    return payload


def payload_to_card(entry: KbEntry) -> dict[str, Any]:
    """kb 条目 → 库卡形状（数据源切换适配器读侧单源；与 card_to_payload 互逆）。

    返回 dict 而非模型——适配器拼 API 响应用；avatar 头像经 src_key 回联
    （src_ref=character_library 时 url=/api/character-library/{src_key}/avatar）。
    """
    try:
        payload = json.loads(entry.payload_json or "{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    dossier = {k: str(payload[k]) for k in _DOSSIER_GRID if payload.get(k)}
    cog = {k: str(payload[k]) for k in _COG_GRID if payload.get(k)}
    return {
        "id": entry.id,
        "name": str(payload.get("archetype") or entry.title or "")[:50],
        "aliases": [str(a) for a in (payload.get("aliases") or [])][:20],
        "role": str(payload.get("role") or "配角")[:10],
        "genre": entry.genre or "",
        "kind": str(payload.get("kind") or "")[:20],
        "persona": str(payload.get("persona") or "")[:300],
        "dossier": dossier,
        "cog": cog,
        # 剧情定位剥出的「（第N章）」回查锚（角色库卡页显式「证据章节」行数据源）
        "evidence": entry.evidence or "",
        "src_kind": entry.src_kind,
        "src_ref": entry.src_ref,
        "src_character_id": entry.src_key,
        "src_novel_name": entry.src_novel_name or "",
        "rev": entry.rev,
    }


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
        # 证据＝剧情定位尾部剥出的「（第N章）」回查锚（无则空）；小说名住 src_novel_name 专列
        try:
            dossier_raw = json.loads(card.dossier or "{}")
        except ValueError:
            dossier_raw = {}
        plot_anchor = ""
        if isinstance(dossier_raw, dict):
            plot_anchor = split_plot_evidence(str(dossier_raw.get("plot") or ""))[1]
        db.add(
            KbEntry(
                user_id=user_id,
                # 题材照旧卡原样拷贝（含目录外自由文本）——读取侧由 genre_norm 归一
                #（#980 口径：存量不重写）；空题材落 ""（跨题材通用）
                genre=card.genre if card.genre else "",
                concept="角色设定",
                concept_id=f"{card.genre or ''}:角色设定",
                title=str(card.name or "")[:40],
                payload_json=json.dumps(payload, ensure_ascii=False),
                # 指令＝一句人设（手录闸门句末断口径：补句号）
                instruction=(persona or str(card.name or ""))[:240],
                when_json="{}",
                evidence=plot_anchor[:200],
                src_kind="character_library_migration",
                src_ref="character_library",
                src_key=card.id,
                src_novel_name=str(card.src_novel_name or "")[:100],
            )
        )
        migrated += 1
    await db.commit()
    return {"migrated": migrated, "skipped": skipped}


async def repair_character_evidence(db: AsyncSession, *, user_id: str) -> int:
    """存量自愈：老迁移把小说名写进证据列（真机 35/35），换轨为剧情定位尾部锚。

    病形＝evidence 与 src_novel_name 相同（concept=角色设定）。修＝payload.plot
    剥「（第N章）」锚落证据列（无锚只清空证据），payload 其余格零变动。
    查无病形即返（自熄）；返回修复条数。失败不抛（读面永不因自愈失败红）。
    """
    try:
        broken = (
            await db.scalars(
                select(KbEntry).where(
                    KbEntry.user_id == user_id,
                    KbEntry.concept == "角色设定",
                    KbEntry.evidence != "",
                    KbEntry.evidence == KbEntry.src_novel_name,
                )
            )
        ).all()
        fixed = 0
        for entry in broken:
            try:
                payload = json.loads(entry.payload_json or "{}")
            except ValueError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            plot, evidence = split_plot_evidence(str(payload.get("plot") or ""))
            if plot:
                payload["plot"] = plot
            else:  # plot 只剩锚本身 → 键不落（空格不落口径）
                payload.pop("plot", None)
            entry.payload_json = json.dumps(payload, ensure_ascii=False)
            entry.evidence = evidence
            fixed += 1
        if fixed:
            await db.commit()
        return fixed
    except Exception:  # noqa: BLE001 — 读面永不因自愈失败红
        logger.warning("event=kb.repair_character_evidence.fail user=%s", user_id, exc_info=True)
        return 0


async def ensure_legacy_migrated(db: AsyncSession, *, user_id: str) -> None:
    """老版库卡一次性搬入知识库（c-kb-library-once-migration）。

    升级用户首次触达库域读面（kb 条目列表 / 角色库卡列表）时执行；**拍板（boss
    2026-11-02）：不挂 boot**——一次性升级迁移，非例行自愈。幂等自熄：
    - 无 legacy 行＝单次索引点查即返（全新账号恒走此路，零成本）；
    - 已有 migration 来源条目＝快路跳过（迁移恒整账号进行，见过条目即整账号完成；
      备份恢复带来的新 legacy 行由 importer 恢复链路自调 migrate_character_library，
      不经本入口）；
    - 否则整账号迁移（per-card 存在性检查不过滤 status——软删的迁移卡不复活）。
    失败不抛（读面降级返回现有数据，下次触达重试）。

    先跑 repair_character_evidence（老映射把小说名写进证据列的存量换轨）：
    独立于 stamped 短路——备份恢复回的旧形状条目不经迁移入口，也要能被修。
    """
    try:
        await repair_character_evidence(db, user_id=user_id)
        has_legacy = (
            await db.execute(
                select(CharacterLibrary.id)
                .where(CharacterLibrary.user_id == user_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if has_legacy is None:
            return
        stamped = (
            await db.execute(
                select(KbEntry.id)
                .where(
                    KbEntry.user_id == user_id,
                    KbEntry.src_kind == "character_library_migration",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if stamped is not None:
            return
        await migrate_character_library(db, user_id=user_id)
    except Exception:  # noqa: BLE001 — 读面永不因迁移失败红
        logger.warning("event=kb.ensure_legacy_migrated.fail user=%s", user_id, exc_info=True)
