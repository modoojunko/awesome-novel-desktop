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
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy import text as _t
from sqlalchemy.ext.asyncio import AsyncSession

from deconstruct.cards import split_plot_evidence
from models.character_library import CharacterLibrary
from models.kb import KbEntry, KbEntryTag, KbKnowledgeInstance

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


# ── 存量数据自愈（2026-11-07 走查实锤，c-kb-instance-list 真机库）─────────────

# 嵌套感知的章锚：cards._PLOT_ANCHOR_RE 只认简单尾锚「（第N章）」，拆书 LLM 产物
# 实锤带嵌套尾锚「（第6章（提及逃脱）/第24章（正面出场））」（鬼面王案）——这里扩
# 一层括号嵌套：尾括号组内含「第N章」字样即整组算锚，全局替换。「（泛指）」等
# 不含章号的括号不动。预览页粘尾互逆的简单形仍归 cards.split_plot_evidence 同址维护。
_KB_CHAPTER_ANCHOR_RE = re.compile(
    r"（(?=[^（）]*第[\d零一二三四五六七八九十百]+章)[^（）]*(?:（[^（）]*）[^（）]*)*）"
)


def strip_chapter_anchor(value: str) -> str:
    """剥字符串内的章节锚（含嵌套形，全局替换）；无锚原样返回。"""
    return _KB_CHAPTER_ANCHOR_RE.sub("", str(value or "")).strip()


# 双前缀（boss 2026-11-09「星币：星币：…」实锤）：拆书产物 content 自带名字头、
# 收集拼接又加一遍——「X：X：正文」→「X：正文」（循环收三连以上）
_DUAL_PREFIX_RE = re.compile(r"^([^：\n]{1,24})：\1(?=：)")


def dedupe_dual_prefix(text: str) -> str:
    prev = None
    t = str(text or "")
    while t != prev:
        prev = t
        t = _DUAL_PREFIX_RE.sub(r"\1", t)
    return t


async def normalize_legacy_genres(*, user_id: str) -> int:
    """存量题材归一自愈：词表外写法归一到目录名。

    病形＝老角色库时代的录入漂移在迁移镜像里原样沉积（实锤「灵异志怪」35 条 ↔
    目录「志怪/民俗灵异」39 条分家，题材栏两棵树、过滤/tag 投影分家）。修＝
    normalize_theme 归一（组件匹配专为此造），连 concept_id（{genre}:{concept}）
    与物化 genre 标签同步改写；normalize_theme 归不动的词（→空串）不动。
    查无病形即返（自熄）；返回改写条数。失败不抛（读面永不因自愈失败红）。
    **自开短会话**（maybe_auto_summarize 先例）：与调用方读请求的事务彻底解耦，
    撞锁（busy_timeout 内拿不到）即本轮放弃、下次读面重试——绝不纠缠调用方事务。
    """
    try:
        from db import async_session

        async with async_session() as db:
            return await _normalize_legacy_genres_on(db, user_id=user_id)
    except Exception:  # noqa: BLE001 — 读面永不因自愈失败红
        logger.warning("event=kb.normalize_legacy_genres.fail user=%s", user_id, exc_info=True)
        return 0


async def _normalize_legacy_genres_on(db: AsyncSession, *, user_id: str) -> int:
    from genres.theme_catalog import normalize_theme
    from kb.concepts import THEMES

    rows = (
        await db.execute(select(KbEntry.genre).where(KbEntry.user_id == user_id).distinct())
    ).all()
    drift = {
        g
        for (g,) in rows
        if g and g not in THEMES and (norm := normalize_theme(g)) and norm != g
    }
    fixed = 0
    for old in drift:
        new = normalize_theme(old)
        res = await db.execute(
            _t(
                "UPDATE kb_entries SET genre = :new, "
                "concept_id = :new || substr(concept_id, :cut) "
                "WHERE user_id = :u AND genre = :old"
            ),
            {"new": new, "cut": len(old) + 1, "u": user_id, "old": old},
        )
        fixed += res.rowcount
        await db.execute(
            _t("UPDATE kb_entry_tags SET value = :new WHERE user_id = :u AND dim = 'genre' AND value = :old"),
            {"new": new, "u": user_id, "old": old},
        )
    if fixed:
        await db.commit()
    return fixed


def strip_anchors_deep(value: Any) -> Any:
    """标量剥锚；列表逐项剥并弃空项（剥后只剩锚的别名项不落）；其余透传。"""
    if isinstance(value, str):
        return strip_chapter_anchor(value)
    if isinstance(value, list):
        out = [strip_chapter_anchor(x) if isinstance(x, str) else x for x in value]
        return [x for x in out if x] if all(isinstance(x, str) for x in out) else out
    return value


async def repair_chapter_anchors(*, user_id: str) -> int:
    """存量章锚自愈：拆书素材卡 payload 与由其转生的实例 fields_json。

    病形＝拆书 LLM 产物把「（第N章…）」回查锚带进 payload 字段（实锤 aliases
    「鬼面人（第26章）」＋plot 嵌套尾锚），条目可见面三源自愈（#1019）不覆盖
    summarize 转生链与已归档素材（读面碰不到归档行）——这里兜底洗两处；
    summarize 造实例的接链另行在 _field_val 落（新账不再进来）。
    查无病形即返（自熄）；返回清洗条数。失败不抛（读面永不因自愈失败红）。
    **自开短会话**（同 normalize_legacy_genres）：与调用方事务解耦，撞锁即弃、
    下次读面重试。
    """
    try:
        from db import async_session

        async with async_session() as db:
            return await _repair_chapter_anchors_on(db, user_id=user_id)
    except Exception:  # noqa: BLE001 — 读面永不因自愈失败红
        logger.warning("event=kb.repair_chapter_anchors.fail user=%s", user_id, exc_info=True)
        return 0


async def heal_dual_prefix_instances(*, user_id: str) -> int:
    """存量实例正文双前缀自愈：拆书旧映射产物「X：X：正文」→「X：正文」。

    生成点＝旧收集映射 content 已带名字头时重复拼名（SDK 拼接去重后新账不再进）；
    存量读面自愈（同 repair_chapter_anchors 先例：自开短会话、查无即返、失败不抛）。
    """
    try:
        from db import async_session

        async with async_session() as db:
            return await _heal_dual_prefix_on(db, user_id=user_id)
    except Exception:  # noqa: BLE001 — 读面永不因自愈失败红
        logger.warning("event=kb.heal_dual_prefix.fail user=%s", user_id, exc_info=True)
        return 0


async def _heal_dual_prefix_on(db: AsyncSession, *, user_id: str) -> int:
    pat = re.compile(r"^([^：\n]{1,24})：\1(?=：)")
    fixed = 0
    insts = (
        await db.execute(
            select(KbKnowledgeInstance).join(
                KbEntry, KbEntry.id == KbKnowledgeInstance.knowledge_id
            ).where(KbEntry.user_id == user_id)
        )
    ).scalars().all()
    for inst in insts:
        t = inst.text or ""
        new = pat.sub(lambda m: m.group(1) + "：", t)
        if new != t:
            inst.text = new
            fixed += 1
    return fixed


async def _repair_chapter_anchors_on(db: AsyncSession, *, user_id: str) -> int:
    fixed = 0
    insts = (
        await db.execute(
            select(KbKnowledgeInstance)
            .join(KbEntry, KbEntry.id == KbKnowledgeInstance.knowledge_id)
            .where(KbEntry.user_id == user_id, KbKnowledgeInstance.fields_json.like("%（%"))
        )
    ).scalars().all()
    for inst in insts:
        try:
            fields = json.loads(inst.fields_json or "{}")
        except ValueError:
            continue
        if not isinstance(fields, dict):
            continue
        cleaned = {k: strip_anchors_deep(v) for k, v in fields.items()}
        cleaned = {k: v for k, v in cleaned.items() if v or not fields.get(k)}  # 剥空的键不落
        if cleaned != fields:
            inst.fields_json = json.dumps(cleaned, ensure_ascii=False)
            fixed += 1
    mats = (
        await db.scalars(
            select(KbEntry).where(
                KbEntry.user_id == user_id,
                KbEntry.origin == "material",
                KbEntry.payload_json.like("%（%"),
            )
        )
    ).all()
    for entry in mats:
        try:
            payload = json.loads(entry.payload_json or "{}")
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        cleaned = {k: strip_anchors_deep(v) for k, v in payload.items()}
        cleaned = {k: v for k, v in cleaned.items() if v or not payload.get(k)}  # 剥空的键不落
        if cleaned != payload:
            entry.payload_json = json.dumps(cleaned, ensure_ascii=False)
            fixed += 1
    # 物化标签投影同步（评审 P3）：payload 剥了、标签不剥＝两套账——
    # kb/match 按 (dim, value) 消费投影，锚值标签与净值数据从此对不上
    tags = (
        await db.scalars(
            select(KbEntryTag).where(
                KbEntryTag.user_id == user_id,
                KbEntryTag.value.like("%（%"),
            )
        )
    ).all()
    for tag in tags:
        cleaned = strip_chapter_anchor(tag.value)
        if cleaned != tag.value:
            tag.value = cleaned
            fixed += 1
    if fixed:
        await db.commit()
    return fixed


async def purge_instances_on_materials(*, user_id: str) -> int:
    """清挂错位的自指实例：实例挂「素材行」头上（knowledge_id 指向 origin=material）。

    病形＝旧版「素材归属既有知识直接转实例」把素材自身当目标知识，每素材自指一条
    （实锤 136 条，1:1 对应归档素材）。素材行不是知识（visible_knowledge_filter 口径），
    这些实例在任何读面都不可达（实例行列表 JOIN 排除素材知识、素材卡不渲染实例群）——
    纯垃圾却污染实例计数。修＝整批删除；查无即返（自熄）。
    失败不抛。**自开短会话**（同 normalize_legacy_genres）。
    """
    try:
        from db import async_session

        async with async_session() as db:
            res = await db.execute(
                _t(
                    "DELETE FROM kb_knowledge_instances WHERE knowledge_id IN "
                    "(SELECT id FROM kb_entries WHERE user_id = :u AND origin = 'material')"
                ),
                {"u": user_id},
            )
            n = res.rowcount
            if n:
                await db.commit()
            return n
    except Exception:  # noqa: BLE001 — 读面永不因自愈失败红
        logger.warning("event=kb.purge_instances_on_materials.fail user=%s", user_id, exc_info=True)
        return 0


async def backfill_instance_names(*, user_id: str) -> int:
    """存量角色实例补名字：角色实例的「名字」（archetype）被旧版总结跳过未进字段。

    病形＝角色设定实例 fields_json 无 archetype，实例无名。修＝按 instruction
    与归档素材一一对应（summarize 转生时 text=素材 instruction 原样复制），
    回查素材卡 archetype 回填进 fields_json。查无病形即返（自熄）；
    失败不抛。**自开短会话**（同 normalize_legacy_genres）。
    """
    try:
        from db import async_session

        async with async_session() as db:
            insts = (
                await db.execute(
                    select(KbKnowledgeInstance)
                    .join(KbEntry, KbEntry.id == KbKnowledgeInstance.knowledge_id)
                    .where(
                        KbEntry.user_id == user_id,
                        KbEntry.concept == "角色设定",
                        ~KbKnowledgeInstance.fields_json.like('%"archetype"%'),
                    )
                )
            ).scalars().all()
            if not insts:
                return 0
            mats = (
                await db.scalars(
                    select(KbEntry).where(
                        KbEntry.user_id == user_id,
                        KbEntry.concept == "角色设定",
                        KbEntry.origin == "material",
                        KbEntry.status == "archived",
                        KbEntry.payload_json.like('%"archetype"%'),
                    )
                )
            ).all()
            by_instruction = {}
            for m in mats:
                try:
                    p = json.loads(m.payload_json or "{}")
                except ValueError:
                    continue
                name = str(p.get("archetype") or "").strip()
                if name:
                    by_instruction[m.instruction] = name
            fixed = 0
            for inst in insts:
                name = by_instruction.get(inst.text)
                if not name:
                    continue
                try:
                    fields = json.loads(inst.fields_json or "{}")
                except ValueError:
                    fields = {}
                if isinstance(fields, dict) and not fields.get("archetype"):
                    fields["archetype"] = name
                    inst.fields_json = json.dumps(fields, ensure_ascii=False)
                    fixed += 1
            if fixed:
                await db.commit()
            return fixed
    except Exception:  # noqa: BLE001 — 读面永不因自愈失败红
        logger.warning("event=kb.backfill_instance_names.fail user=%s", user_id, exc_info=True)
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
    同位再跑 normalize_legacy_genres / repair_chapter_anchors / purge_instances_on_materials /
    backfill_instance_names（2026-11-07 走查实锤的存量沉积，见各函数 docstring），
    同为幂等自熄、独立于 stamped。再跑 heal_dual_prefix_instances（2026-11-09
    「星币：星币：」双前缀存量自愈，c-knowledge-source-align）。
    """
    try:
        # 官方基线撤回（2026-11-11 版权合规）：读面兜底，进程内成功后零成本；
        # carry/备份恢复的强制重扫在各自钩子里，不依赖本入口。
        from kb.revocation import revoke_official_baseline

        await revoke_official_baseline()
        await repair_character_evidence(db, user_id=user_id)
        await heal_dual_prefix_instances(user_id=user_id)
        await normalize_legacy_genres(user_id=user_id)
        await repair_chapter_anchors(user_id=user_id)
        await purge_instances_on_materials(user_id=user_id)
        await backfill_instance_names(user_id=user_id)
        # 拆书版本收敛（c-kb-collect-dims）：同书以全本为准重收＋四维扩收；
        # 自开会话、幂等（app_meta 标记）、失败不抛——首触达一次性重建，量大稍慢
        from kb.version_reconcile import reconcile_deconstruct_versions

        await reconcile_deconstruct_versions(user_id=user_id)
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
