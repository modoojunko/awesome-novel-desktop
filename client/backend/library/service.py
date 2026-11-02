"""角色库域服务（c-character-library）——账号级跨书角色卡。

数据源切换（c-kb-character-migration 刀2c ①，后端适配器方案）：
- 存储单源＝kb_entries（concept=角色设定）；映射单源＝kb/migrate_library.py 的
  card_to_payload（写侧）/ payload_to_card（读侧），卡形状 API 响应不变，
  前端零改动。character_library 主表停写（deprecated；迁移/备份恢复镜像除外）。
- 头像字节：新写入住 KbEntryBlob（entry id 键；CharacterLibraryBlob 有指向
  character_library 的真 FK，entry id 键插不进去——实证裁定，见模型注释）。
  迁移存量仍住 CharacterLibraryBlob，读经 src_key 回联；删除双清。
  （交接文档原计划「新卡键=entry id 写 CharacterLibraryBlob」不可行，已按
  kb_entry_blobs 方案落地。）
- 收录（书卡→库）＝整卡进 kb；provenance（src_kind/src_ref/src_key）幂等，
  软删过的卡重新收录＝同键复活（unique 索引挡重插）。
- 书→库手动同步＝PULL 书内最新书域格（名字/别名/人设/档案八格/认知/头像），
  库分类不动。用到新书（库→书）＝复制落书内角色卡，撞名自动后缀、主角冲突落配角。
- 随机起名：AI 能力，任何失败/无 Key/模板缺失一律本地词库兜底恒返回。
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from genres.theme_catalog import normalize_theme
from kb.migrate_library import card_to_payload, ensure_legacy_migrated, payload_to_card
from kb.service import create_entry as kb_create_entry
from kb.service import delete_entry as kb_delete_entry
from kb.service import update_entry as kb_update_entry
from models.character import Character
from models.character_library import CharacterLibraryBlob
from models.kb import KbEntry, KbEntryBlob
from models.project import Novel
from settings.character_model import COG_KEYS, DOSSIER_KEYS, ROLES

logger = logging.getLogger(__name__)

NAME_MAX = 50
PERSONA_MAX = 300
CELL_MAX = 300
ALIASES_MAX = 20
ALIAS_MAX = 50
GENRE_MAX = 40
SRC_KINDS = ("book", "deconstruct", "manual")
KIND_VALUES = ("亲人", "朋友", "挚友", "小弟", "下人", "长辈", "敌人", "其他")
AVATAR_VARIANTS = ("full", "thumb")
AGE_MIN, AGE_MAX = 16, 55

CONCEPT = "角色设定"
# 迁移存量卡的 legacy 锚（头像字节仍住 CharacterLibraryBlob，src_key 回联）
LEGACY_SRC_REF = "character_library"


class LibraryError(Exception):
    """域错误：code 供 router 映射 HTTP 状态与可读文案。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _json_loads(text: str, fallback):
    try:
        value = json.loads(text or "")
    except (TypeError, ValueError):
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


def _json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ── kb 条目 ↔ 卡形状（适配器读侧单源＝payload_to_card） ─────────────────


def _card_ns(
    *, name: str, aliases, role: str, kind: str, persona: str, dossier, cog
) -> SimpleNamespace:
    """卡字段 → card_to_payload 入参（鸭子类型：与 CharacterLibrary 卡列同形，JSON 串或原生）。"""
    def _as_json(v) -> str:
        return v if isinstance(v, str) else _json_dumps(v or ())
    return SimpleNamespace(
        name=str(name or ""),
        aliases=_as_json(aliases),
        role=str(role or ""),
        kind=str(kind or ""),
        persona=str(persona or ""),
        dossier=_as_json(dossier),
        cog=_as_json(cog),
    )


def _instruction_of(persona: str, name: str) -> str:
    """一句人设（闸门硬性非空 ≤240）：persona 优先，名字兜底。"""
    return (str(persona or "").strip() or str(name or "").strip())[:240]


def _gate_message(gate) -> str:
    if gate is not None and gate.errors:
        return "；".join(str(v) for v in gate.errors.values())
    return "内容不完整"


def _card_view(entry: KbEntry, *, has_avatar: bool) -> dict:
    """kb 条目 → 库卡 API 形状（与旧 card_dict 逐键一致，前端零改动）。"""
    v = payload_to_card(entry)
    return {
        "id": v["id"],
        "name": v["name"],
        "aliases": v["aliases"],
        "role": v["role"],
        "genre": v["genre"],
        # 归一题材（c-library-genre-gate）：跨书门禁前端过滤用；老卡自由文本也归得出
        "genre_norm": normalize_theme(v["genre"]),
        "kind": v["kind"],
        "persona": v["persona"],
        "dossier": v["dossier"],
        "cog": v["cog"],
        "src": {
            "kind": v["src_kind"],
            "novel_name": v["src_novel_name"],
            "ref": v["src_ref"],
            "character_id": v["src_character_id"],
        },
        "avatar": {
            "has": has_avatar,
            "url": f"/api/character-library/{entry.id}/avatar?variant=full" if has_avatar else "",
            "thumb_url": f"/api/character-library/{entry.id}/avatar?variant=thumb" if has_avatar else "",
        },
        "rev": v["rev"],
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else "",
    }


async def _get_entry(db: AsyncSession, user_id: str, card_id: str) -> KbEntry:
    entry = (
        await db.execute(
            select(KbEntry).where(
                KbEntry.id == card_id,
                KbEntry.user_id == user_id,
                KbEntry.concept == CONCEPT,
                KbEntry.status == "active",
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise LibraryError("not_found", "角色不存在")
    return entry


async def _existing_source_entry(
    db: AsyncSession, user_id: str, src_ref: str, src_key: str,
    *, include_archived: bool = False,
) -> KbEntry | None:
    stmt = select(KbEntry).where(
        KbEntry.user_id == user_id,
        KbEntry.concept == CONCEPT,
        KbEntry.src_ref == src_ref,
        KbEntry.src_key == src_key,
    )
    if not include_archived:
        stmt = stmt.where(KbEntry.status == "active")
    return (await db.execute(stmt)).scalar_one_or_none()


# ── 卡片入参校验（形状/枚举不变；落库走 kb 闸门） ────────────────────────


def _clean_aliases(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.replace("，", "、").replace(",", "、").split("、")
    elif isinstance(value, list):
        parts = value
    else:
        raise LibraryError("invalid_aliases", "别名格式不对")
    out: list[str] = []
    for part in parts:
        if len(out) >= ALIASES_MAX:
            break
        text = str(part or "").strip()[:ALIAS_MAX]
        if text and text not in out:
            out.append(text)
    return out


def _clean_cells(value, allowed: tuple[str, ...], what: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise LibraryError("invalid_" + what, f"{what} 格式不对")
    bad = [k for k in value if k not in allowed]
    if bad:
        raise LibraryError("invalid_" + what, f"{what} 里有不认识的格：{'、'.join(sorted(bad))}")
    return {k: str(v or "").strip()[:CELL_MAX] for k, v in value.items()}


def clean_payload(body: dict) -> dict:
    """新建/整卡保存的入参清洗（白名单 + 截断 + 枚举）。"""
    if not isinstance(body, dict):
        raise LibraryError("invalid_body", "请求格式不对")
    role = str(body.get("role") or "配角").strip()
    if role not in ROLES:
        raise LibraryError("invalid_role", f"定位只能是 {'/'.join(ROLES)}")
    kind = str(body.get("kind") or "").strip()
    if kind and kind not in KIND_VALUES:
        raise LibraryError("invalid_kind", "小类不合法")
    raw_genre = str(body.get("genre") or "").strip()
    genre = normalize_theme(raw_genre)
    if raw_genre and not genre:
        raise LibraryError(
            "invalid_genre", "题材要用开书时的题材目录里的大类（如：都市、玄幻、悬疑）"
        )
    return {
        "name": str(body.get("name") or "").strip()[:NAME_MAX],
        "aliases": _clean_aliases(body.get("aliases")),
        "role": role,
        "genre": genre[:GENRE_MAX],
        "kind": kind,
        "persona": str(body.get("persona") or "").strip()[:PERSONA_MAX],
        "dossier": _clean_cells(body.get("dossier"), DOSSIER_KEYS, "dossier"),
        "cog": _clean_cells(body.get("cog"), COG_KEYS, "cog"),
    }


# ── 写路径：kb create/update 复用（闸门/payload 校验/标签物化/rev 并发） ──


async def _create_card_entry(
    db: AsyncSession,
    user_id: str,
    *,
    name: str, aliases, role: str, kind: str, persona: str, dossier, cog,
    genre: str,
    src_kind: str,
    src_ref: str = "",
    src_key: str = "",
    src_novel_name: str = "",
    evidence: str = "",
) -> KbEntry:
    """卡字段 → kb create_entry。card_to_payload 出的 payload 已逐格 clamp，
    过 CharacterPayload 必绿；失败只可能来自指令闸（空/超长）→ 可读文案。"""
    entry, gate, _error = await kb_create_entry(
        db,
        user_id=user_id,
        genre=genre,
        concept=CONCEPT,
        title=str(name or "")[:40],
        payload=card_to_payload(_card_ns(
            name=name, aliases=aliases, role=role, kind=kind,
            persona=persona, dossier=dossier, cog=cog,
        )),
        instruction=_instruction_of(persona, name),
        evidence=str(evidence or "")[:200],
        src_kind=src_kind,
        src_ref=src_ref,
        src_key=src_key,
        src_novel_name=str(src_novel_name or "")[:100],
    )
    if entry is None:  # 判例：闸门失败时 error_dict 可能为 None，判 entry 而非 error
        raise LibraryError("invalid_card", f"这张卡存不进知识库：{_gate_message(gate)}")
    await db.refresh(entry)  # commit 后属性过期
    return entry


async def _revive_card_entry(
    db: AsyncSession,
    user_id: str,
    stale: KbEntry,
    *,
    name: str, aliases, role: str, kind: str, persona: str, dossier, cog,
    genre: str,
    src_novel_name: str = "",
) -> KbEntry:
    """软删条目同键复活（unique 索引挡重插）：置回 active 后走 update_entry
    闸门整卡覆盖（tags/rev/题材同步全复用）。"""
    stale.status = "active"
    await db.commit()
    entry, gate, error = await kb_update_entry(
        db,
        user_id=user_id,
        entry_id=stale.id,
        title=str(name or "")[:40],
        instruction=_instruction_of(persona, name),
        payload=card_to_payload(_card_ns(
            name=name, aliases=aliases, role=role, kind=kind,
            persona=persona, dossier=dossier, cog=cog,
        )),
        genre=genre,
        src_novel_name=str(src_novel_name or "")[:100] or None,
    )
    if entry is None:
        raise LibraryError("invalid_card", f"这张卡存不进知识库：{error or _gate_message(gate)}")
    return entry


# ── 读路径 ────────────────────────────────────────────────────────────────


async def _avatar_presence(db: AsyncSession, entries: list[KbEntry]) -> dict[str, bool]:
    """entry id → 是否有头像：新表字节（entry id 键）∪ legacy 回联（src_key 键）。"""
    if not entries:
        return {}
    ids = [e.id for e in entries]
    legacy_keys = sorted({e.src_key for e in entries if e.src_ref == LEGACY_SRC_REF and e.src_key})
    hits: set[str] = set(
        (
            await db.execute(
                select(KbEntryBlob.entry_id).where(
                    KbEntryBlob.entry_id.in_(ids),
                    KbEntryBlob.variant == "thumb",
                )
            )
        ).scalars()
    )
    if legacy_keys:
        legacy_hits = set(
            (
                await db.execute(
                    select(CharacterLibraryBlob.library_id).where(
                        CharacterLibraryBlob.library_id.in_(legacy_keys),
                        CharacterLibraryBlob.variant == "thumb",
                    )
                )
            ).scalars()
        )
        hits |= {e.id for e in entries if e.src_ref == LEGACY_SRC_REF and e.src_key in legacy_hits}
    return {i: i in hits for i in ids}


async def list_cards(db: AsyncSession, user_id: str) -> dict:
    """一次给全（文本字段＋头像引用）；筛选/搜索/排序在前端内存完成。"""
    # 老版角色库存量一次性迁移挂点（c-kb-library-once-migration）：升级账号首次
    # 触达角色库读面即整账号搬入；幂等自熄，失败降级不阻断（详见 ensure 文档）
    await ensure_legacy_migrated(db, user_id=user_id)
    # 题材回填挂点（c-library-genre-gate）：来源可解的空题材卡补题材，幂等自熄
    await ensure_genre_backfill(db, user_id)
    entries = (
        await db.execute(
            select(KbEntry)
            .where(
                KbEntry.user_id == user_id,
                KbEntry.concept == CONCEPT,
                KbEntry.status == "active",
            )
            .order_by(KbEntry.created_at, KbEntry.id)
        )
    ).scalars().all()
    presence = await _avatar_presence(db, list(entries))
    items = [_card_view(e, has_avatar=presence.get(e.id, False)) for e in entries]
    return {"count": len(items), "items": items}


async def get_card_view(db: AsyncSession, user_id: str, card_id: str) -> dict:
    entry = await _get_entry(db, user_id, card_id)
    presence = await _avatar_presence(db, [entry])
    return _card_view(entry, has_avatar=presence.get(entry.id, False))


# ── 写路径：CRUD ──────────────────────────────────────────────────────────


async def create_card(db: AsyncSession, user_id: str, body: dict) -> dict:
    data = clean_payload(body)
    entry = await _create_card_entry(
        db, user_id,
        name=data["name"], aliases=_json_dumps(data["aliases"]), role=data["role"],
        kind=data["kind"], persona=data["persona"],
        dossier=_json_dumps(data["dossier"]), cog=_json_dumps(data["cog"]),
        genre=data["genre"], src_kind="manual",
    )
    return _card_view(entry, has_avatar=False)


async def update_card(db: AsyncSession, user_id: str, card_id: str, body: dict) -> dict:
    await _get_entry(db, user_id, card_id)  # 先 404 后 400（与旧顺序一致）
    data = clean_payload(body)
    entry, gate, error = await kb_update_entry(
        db,
        user_id=user_id,
        entry_id=card_id,
        title=data["name"][:40],
        instruction=_instruction_of(data["persona"], data["name"]),
        payload=card_to_payload(_card_ns(
            name=data["name"], aliases=_json_dumps(data["aliases"]), role=data["role"],
            kind=data["kind"], persona=data["persona"],
            dossier=_json_dumps(data["dossier"]), cog=_json_dumps(data["cog"]),
        )),
        genre=data["genre"],
    )
    if entry is None:
        if error and error.get("code") == "not_found":
            raise LibraryError("not_found", "角色不存在")
        raise LibraryError("invalid_card", f"这张卡存不进知识库：{error or _gate_message(gate)}")
    presence = await _avatar_presence(db, [entry])
    return _card_view(entry, has_avatar=presence.get(entry.id, False))


async def delete_card(db: AsyncSession, user_id: str, card_id: str) -> dict:
    entry = await _get_entry(db, user_id, card_id)
    # 复制语义：只删库里的卡（头像字节双清），书内已导入的副本不受影响。
    await _delete_avatars(db, entry)
    if not await kb_delete_entry(db, user_id=user_id, entry_id=card_id):
        raise LibraryError("not_found", "角色不存在")
    return {"deleted": card_id}


# ── 头像（KbEntryBlob 主写；legacy 回联读；删除双清） ─────────────────────


async def _put_avatar_blobs(db: AsyncSession, entry_id: str, full: bytes, thumb: bytes) -> None:
    await db.execute(delete(KbEntryBlob).where(KbEntryBlob.entry_id == entry_id))
    db.add(KbEntryBlob(entry_id=entry_id, variant="full", data=full))
    db.add(KbEntryBlob(entry_id=entry_id, variant="thumb", data=thumb))


async def _delete_avatars(db: AsyncSession, entry: KbEntry) -> None:
    await db.execute(delete(KbEntryBlob).where(KbEntryBlob.entry_id == entry.id))
    if entry.src_ref == LEGACY_SRC_REF and entry.src_key:
        await db.execute(
            delete(CharacterLibraryBlob).where(
                CharacterLibraryBlob.library_id == entry.src_key
            )
        )


async def _entry_avatar_bytes(db: AsyncSession, entry: KbEntry, variant: str) -> bytes | None:
    row = (
        await db.execute(
            select(KbEntryBlob).where(
                KbEntryBlob.entry_id == entry.id,
                KbEntryBlob.variant == variant,
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return row.data
    if entry.src_ref == LEGACY_SRC_REF and entry.src_key:
        row = (
            await db.execute(
                select(CharacterLibraryBlob).where(
                    CharacterLibraryBlob.library_id == entry.src_key,
                    CharacterLibraryBlob.variant == variant,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            return row.data
    return None


async def _copy_book_avatar(
    db: AsyncSession, user_id: str, character_id: str, entry: KbEntry
) -> bool:
    """收录时从书内当前头像资产复制字节（已是 512/96 档，不再转码）。"""
    from models.image_asset import ImageAsset, ImageAssetBlob

    asset = (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.user_id == user_id,
                ImageAsset.character_id == character_id,
                ImageAsset.kind == "avatar",
                ImageAsset.status == "current",
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        return False
    blobs = {
        b.variant: b.data
        for b in (
            await db.execute(
                select(ImageAssetBlob).where(ImageAssetBlob.asset_id == asset.id)
            )
        ).scalars()
    }
    if "full" not in blobs or "thumb" not in blobs:
        return False
    await _put_avatar_blobs(db, entry.id, blobs["full"], blobs["thumb"])
    return True


async def avatar_bytes(db: AsyncSession, user_id: str, card_id: str, variant: str) -> tuple[bytes, str]:
    if variant not in AVATAR_VARIANTS:
        raise LibraryError("invalid_variant", "variant 只能是 full 或 thumb")
    entry = await _get_entry(db, user_id, card_id)  # 归属校验
    data = await _entry_avatar_bytes(db, entry, variant)
    if data is None:
        raise LibraryError("avatar_not_found", "这张卡还没有头像")
    return data, hashlib.sha256(data).hexdigest()


# ── 收录（书卡 → 库） ─────────────────────────────────────────────────────


async def _story_genre(db: AsyncSession, novel: Novel) -> str:
    try:
        from filesystem.storage import get_storage

        story = await get_storage().read_yaml(novel.root_path, "story.yaml") or {}
        return normalize_theme(story.get("genre"))[:GENRE_MAX]
    except Exception:  # noqa: BLE001 — 题材继承是尽力而为，不阻断收录
        return ""


# 回填节流（跟进 P3）：跑完仍有解不出的条目时逐用户记一次时间，窗口内读面直接
# 跳过——避免搜索逐键触发重复点查与 story 读取；源补好后窗口到期自然重试。
_BACKFILL_RETRY_SEC = 600.0
_BACKFILL_UNSETTLED: dict[str, float] = {}


async def ensure_genre_backfill(db: AsyncSession, user_id: str) -> None:
    """题材回填（c-library-genre-gate）：来源可解的空题材库卡补题材。

    拍板口径同 c-kb-library-once-migration：**不挂 boot**、读面触达、幂等自熄。
    覆盖两种条目形状：
    - 直连来源：src_kind∈{deconstruct,book}——回查任务产物 genre 维度（与收录时
      _deconstruct_genre 同源）/ story.genre（与 _story_genre 同源）；
    - 迁移镜像：src_kind=character_library_migration——真实来源藏在 legacy 卡
      （src_key＝卡 id）里：卡自带题材优先，否则按卡的 src_kind/src_ref 再回查。
    解不出＝保持空（跨题材通用语义不动，手动卡不碰）；全部补完探测即返。失败降级。
    节流（跟进 P3）：跑完仍有解不出的条目（源已删/书无题材/目录外自由文本）时，
    该用户 10 分钟内再触达直接跳过——避免搜索框逐键触发时的重复点查与 story
    读取；期间源被补好则等窗口到期自然重试（进程内即可：桌面后端单进程）。
    """
    try:
        now = time.monotonic()
        if now - _BACKFILL_UNSETTLED.get(user_id, 0.0) < _BACKFILL_RETRY_SEC:
            return
        rows = (
            await db.execute(
                select(KbEntry).where(
                    KbEntry.user_id == user_id,
                    KbEntry.concept == CONCEPT,
                    KbEntry.src_kind.in_(
                        ("deconstruct", "book", "character_library_migration")
                    ),
                    or_(KbEntry.genre.is_(None), KbEntry.genre == ""),
                )
            )
        ).scalars().all()
        if not rows:
            _BACKFILL_UNSETTLED.pop(user_id, None)
            return
        from models.character_library import CharacterLibrary
        from models.deconstruct import DeconstructJob
        from models.project import Novel

        # 迁移镜像：经 legacy 卡（src_key＝卡 id）反查真实来源
        mirror = {
            e.src_key for e in rows
            if e.src_kind == "character_library_migration" and e.src_key
        }
        cards = {}
        if mirror:
            for card in (
                await db.execute(
                    select(CharacterLibrary).where(
                        CharacterLibrary.user_id == user_id,
                        CharacterLibrary.id.in_(sorted(mirror)),
                    )
                )
            ).scalars():
                cards[card.id] = card

        task_ids = {e.src_ref for e in rows if e.src_kind == "deconstruct" and e.src_ref}
        novel_ids = {e.src_ref for e in rows if e.src_kind == "book" and e.src_ref}
        for card in cards.values():
            if normalize_theme(card.genre):
                continue  # 卡自带题材，直接采用
            if card.src_kind == "deconstruct" and card.src_ref:
                task_ids.add(card.src_ref)
            elif card.src_kind == "book" and card.src_ref:
                novel_ids.add(card.src_ref)

        resolved: dict[str, str] = {}
        if task_ids:
            tasks = (
                await db.execute(select(DeconstructJob).where(DeconstructJob.id.in_(task_ids)))
            ).scalars().all()
            for t in tasks:
                g = _deconstruct_genre(t)
                if g:
                    resolved[t.id] = g
        if novel_ids:
            novels = (
                await db.execute(
                    select(Novel).where(Novel.id.in_(novel_ids), Novel.user_id == user_id)
                )
            ).scalars().all()
            for nv in novels:
                g = await _story_genre(db, nv)
                if g:
                    resolved[nv.id] = g

        changed = 0
        for e in rows:
            if e.src_kind == "character_library_migration":
                card = cards.get(e.src_key or "")
                if card is None:
                    continue
                g = normalize_theme(card.genre) or (
                    resolved.get(card.src_ref or "")
                    if card.src_kind in ("deconstruct", "book")
                    else ""
                )
            else:
                g = resolved.get(e.src_ref or "")
            if g:
                e.genre = g
                e.concept_id = f"{g}:{e.concept}"
                changed += 1
        if changed:
            await db.commit()
            logger.info(
                "event=character_library.genre_backfill user=%s changed=%s", user_id, changed
            )
        if changed < len(rows):
            _BACKFILL_UNSETTLED[user_id] = now  # 仍有解不出的 → 窗口内不再重探
        else:
            _BACKFILL_UNSETTLED.pop(user_id, None)
    except Exception:  # noqa: BLE001 — 读面永不因回填失败红
        logger.warning(
            "event=character_library.genre_backfill.fail user=%s", user_id, exc_info=True
        )


def _role_of_character(character: Character) -> str:
    return character.role if character.role in ROLES else "配角"


async def collect_from_book(
    db: AsyncSession,
    user_id: str,
    novel: Novel,
    character_id: str,
    *,
    rename: bool = False,
) -> dict:
    """书内卡整卡收进库；同一书卡重复收录返回已有卡（幂等）。
    软删过的卡重新收录＝同键复活整卡覆盖。调用方已校验书归属。"""
    character = (
        await db.execute(
            select(Character).where(
                Character.id == character_id, Character.novel_id == novel.id
            )
        )
    ).scalar_one_or_none()
    if character is None:
        raise LibraryError("character_not_found", "书里没有这张角色卡")

    name = character.name.lstrip("\u0000") or ""
    dossier = _json_loads(character.dossier, {})
    if rename:
        picked = random_name_local(dossier.get("gender") or "")
        name = picked["name"]
        dossier = {**dossier, "age": str(picked["age"])}
    fields = {
        "name": name[:NAME_MAX],
        "aliases": character.aliases or "[]",
        "role": _role_of_character(character),
        "kind": "",
        "persona": character.persona or "",
        "dossier": _json_dumps(dossier),
        "cog": character.cog or "{}",
    }
    genre = await _story_genre(db, novel)
    novel_name = novel.name

    stale = await _existing_source_entry(
        db, user_id, novel.id, character_id, include_archived=True
    )
    created = True
    entry: KbEntry
    if stale is not None and stale.status == "active":
        created = False
        entry = stale
    elif stale is not None and stale.status == "merged":
        # c-kb-organize：已合并条目不复活（spec——收录侧以既有卡呈现，不产生第三条）
        created = False
        entry = stale
    else:
        try:
            if stale is not None:  # 软删过：unique 键被占，复活而非重插
                entry = await _revive_card_entry(
                    db, user_id, stale, **fields, genre=genre, src_novel_name=novel_name,
                )
            else:
                entry = await _create_card_entry(
                    db, user_id, **fields, genre=genre, src_kind="book",
                    src_ref=novel.id, src_key=character_id,
                    src_novel_name=novel_name, evidence=novel_name,
                )
        except IntegrityError:
            # 双击/并发：唯一索引兜底，回查返回已有卡（软删过的同键复活）
            await db.rollback()
            race = await _existing_source_entry(
                db, user_id, novel.id, character_id, include_archived=True
            )
            if race is None:
                raise
            if race.status in ("active", "merged"):
                created = False
                entry = race
            else:
                entry = await _revive_card_entry(
                    db, user_id, race, **fields, genre=genre, src_novel_name=novel_name,
                )
    await _copy_book_avatar(db, user_id, character_id, entry)
    await db.commit()
    await db.refresh(entry)
    presence = await _avatar_presence(db, [entry])
    if created:
        logger.info("event=character_library.collect novel=%s card=%s", novel.id, entry.id)
    return {"created": created, "card": _card_view(entry, has_avatar=presence.get(entry.id, False))}


# ── 书 → 库手动同步 ───────────────────────────────────────────────────────


async def sync_from_book(db: AsyncSession, user_id: str, card_id: str) -> dict:
    entry = await _get_entry(db, user_id, card_id)
    if entry.src_kind != "book" or not entry.src_ref or not entry.src_key:
        raise LibraryError("not_book_sourced", "这张卡不是从书里收进来的，没有可同步的来源")
    novel = (
        await db.execute(
            select(Novel).where(
                Novel.id == entry.src_ref,
                Novel.user_id == user_id,
                Novel.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    source = None
    if novel is not None:
        source = (
            await db.execute(
                select(Character).where(
                    Character.id == entry.src_key,
                    Character.novel_id == novel.id,
                )
            )
        ).scalar_one_or_none()
    if source is None:
        raise LibraryError("source_gone", "书里的这张卡找不到了（书或卡可能已删除）")

    view = payload_to_card(entry)  # 库分类（role/kind）不动；题材也不动
    name = (source.name.lstrip("\u0000") or "")[:NAME_MAX]
    entry, gate, error = await kb_update_entry(
        db,
        user_id=user_id,
        entry_id=card_id,
        title=name[:40],
        instruction=_instruction_of(source.persona or "", name),
        payload=card_to_payload(_card_ns(
            name=name,
            aliases=source.aliases or "[]",
            role=view["role"],
            kind=view["kind"],
            persona=source.persona or "",
            dossier=source.dossier or "{}",
            cog=source.cog or "{}",
        )),
        src_novel_name=novel.name,
    )
    if entry is None:
        raise LibraryError("invalid_card", f"同步失败：{error or _gate_message(gate)}")
    if not await _copy_book_avatar(db, user_id, source.id, entry):
        await _delete_avatars(db, entry)
    await db.commit()
    await db.refresh(entry)
    presence = await _avatar_presence(db, [entry])
    logger.info("event=character_library.sync card=%s novel=%s", entry.id, novel.id)
    return _card_view(entry, has_avatar=presence.get(entry.id, False))


# ── 用到新书（库 → 书内复制落卡） ─────────────────────────────────────────


def _with_suffix(base: str, n: int) -> str:
    suffix = f"（角色库{n}）"
    body = base or "角色"
    room = max(1, NAME_MAX - len(suffix))
    return body[:room] + suffix


async def apply_to_book(
    db: AsyncSession,
    user_id: str,
    card_id: str,
    novel_id: str,
    *,
    rename: bool = False,
) -> dict:
    """复制落卡：撞名自动后缀、主角冲突落配角；整卡含认知格与头像。"""
    from settings.character_service import Conflict, create_character

    entry = await _get_entry(db, user_id, card_id)
    novel = (
        await db.execute(
            select(Novel).where(
                Novel.id == novel_id,
                Novel.user_id == user_id,
                Novel.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if novel is None:
        raise LibraryError("novel_not_found", "目标书不存在")

    view = payload_to_card(entry)
    # 题材门（c-library-genre-gate，boss 拍板硬拦）：卡题材与目标书题材同域才可落卡；
    # 任一侧空（跨题材通用卡 / 书题材未设）放行。两侧同走 normalize_theme 归一比较，
    # 与收录/回填同源。
    card_genre = normalize_theme(view["genre"])
    book_genre = await _story_genre(db, novel)
    if card_genre and book_genre and card_genre != book_genre:
        raise LibraryError(
            "genre_mismatch",
            f"这本书是「{book_genre}」题材，这张角色卡属于「{card_genre}」——跨题材不能落卡。",
        )
    dossier = dict(view["dossier"])
    base_name = view["name"]
    if rename:
        picked = random_name_local(dossier.get("gender") or "")
        base_name = picked["name"]
        dossier = {**dossier, "age": str(picked["age"])}

    role = view["role"]
    demoted = False
    if role == "主角":
        has_protagonist = (
            await db.execute(
                select(Character.id).where(
                    Character.novel_id == novel_id, Character.role == "主角"
                )
            )
        ).first()
        if has_protagonist:
            role = "配角"
            demoted = True

    base = base_name or "角色"
    candidates = [base] + [_with_suffix(base, n) for n in range(1, 5)]
    created = None
    for candidate in candidates:
        try:
            created = await create_character(
                db,
                novel_id,
                name=candidate,
                role=role,
                persona=view["persona"],
                aliases=view["aliases"],
                dossier=dossier,
                cog=view["cog"],
            )
            break
        except Conflict:
            continue
    if created is None:
        raise LibraryError("name_exhausted", "这本书里同名角色太多了，换个名字再试")

    avatar_copied = False
    full = await _entry_avatar_bytes(db, entry, "full")
    if full is not None:
        try:
            from image_assets.service import adopt_asset, create_generated_asset

            asset = await create_generated_asset(
                db,
                user_id=user_id,
                novel_id=novel_id,
                kind="avatar",
                data=full,
                character_id=created.id,
                source="library",
            )
            await adopt_asset(db, user_id, asset.id)
            avatar_copied = True
        except Exception as e:  # noqa: BLE001 — 头像失败不拖垮落卡（卡片无图可后补）
            logger.warning("event=character_library.avatar_copy_fail card=%s error=%s", entry.id, e)

    return {
        "character_id": created.id,
        "name": created.name.lstrip("\u0000") or created.name,
        "role": created.role,
        "renamed": created.name != view["name"],
        "demoted": demoted,
        "avatar": avatar_copied,
    }


# ── AI 随机改名换龄（本地词库兜底恒可用） ────────────────────────────────

_SURNAMES = ["王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗", "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于", "董", "萧", "程", "曹", "袁", "邓", "许", "傅", "沈", "曾", "彭", "吕"]
_MALE_GIVEN = ["青山", "远舟", "长风", "惊鸿", "铁衣", "无咎", "云鹤", "砚秋", "少游", "承影", "听澜", "枕星", "行简", "沉舟", "拾遗", "观澜", "破晓", "执戈", "逐月", "归尘"]
_FEMALE_GIVEN = ["绾绾", "阮阮", "惊蝉", "九歌", "望舒", "菱歌", "青梧", "疏影", "听雨", "扶苏", "卿卿", "含章", "拾雪", "临溪", "望津", "知微", "枕月", "流萤", "照水", "弄晴"]


def random_name_local(gender: str) -> dict:
    surname = random.choice(_SURNAMES)
    pool = _FEMALE_GIVEN if str(gender).startswith("女") else _MALE_GIVEN
    return {"name": surname + random.choice(pool), "age": random.randint(AGE_MIN, AGE_MAX)}


def _parse_ai_name(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    # 只接受一个短名字：首行、去引号/标点、长度 2–4 个汉字
    first = raw.splitlines()[0].strip().strip("\u300c\u300d\u300e\u300f\"'\u201c\u201d\u2018\u2019\u3002\uff0c,\uff1a: ")
    if 2 <= len(first) <= 4 and all("\u4e00" <= ch <= "\u9fff" for ch in first):
        return first
    return ""


async def random_name(db: AsyncSession, user_id: str, gender: str) -> dict:
    """AI 起名；无 Key/超时/模板缺失/输出不合规一律本地兜底，恒返回 200。"""
    age = random.randint(AGE_MIN, AGE_MAX)
    try:
        from prompts import load_layers

        system, prompt = load_layers("charlib_random_name")
        from ai_client import get_ai_client_for_user

        client = await get_ai_client_for_user(user_id)
        picked = ""
        try:
            usage: dict = {}
            text = await client.chat(
                model="haiku",
                system=system.format(gender=gender or "男"),
                messages=[{"role": "user", "content": prompt.format(gender=gender or "男")}],
                max_tokens=32,
                usage=usage,
                operation="charlib_random_name",
            )
            picked = _parse_ai_name(text)
        except Exception as e:  # noqa: BLE001 — 失败静默走兜底（不烧配额日志噪音过重）
            logger.info("event=character_library.random_name ai_fail error=%s", e)
        if picked:
            return {"name": picked, "age": age, "source": "ai"}
    except Exception as e:  # noqa: BLE001 — 模板缺失/客户端构造失败均兜底
        logger.info("event=character_library.random_name fallback error=%s", e)
    picked = random_name_local(gender)
    return {"name": picked["name"], "age": picked["age"], "source": "local"}

# ── 拆书收录（c-charlib-deconstruct-exit） ────────────────────────────────


def deconstruct_source_key(card: dict, index: int) -> str:
    """拆书来源角色身份键：trim 后非空主名；空名用稳定占位（同任务内唯一）。"""
    name = str(card.get("name") or "").strip()
    return name or f"未命名#{index}"


async def collected_source_keys(db: AsyncSession, user_id: str, task_id: str) -> set[str]:
    rows = await db.execute(
        select(KbEntry.src_key).where(
            KbEntry.user_id == user_id,
            KbEntry.concept == CONCEPT,
            KbEntry.src_kind == "deconstruct",
            KbEntry.src_ref == task_id,
            KbEntry.status == "active",
            KbEntry.src_key != "",
        )
    )
    return set(rows.scalars())


def _deconstruct_genre(task) -> str:
    """题材继承：产物 genre 维度（与建书同源）；取不到则空（可后改）。"""
    try:
        products = json.loads(task.products_json or "{}")
    except (TypeError, ValueError):
        return ""
    genre = ((products.get("genre") or {}).get("data") or {}).get("genre")
    return normalize_theme(genre)[:GENRE_MAX]


async def import_from_deconstruct(
    db: AsyncSession,
    user_id: str,
    task,
    *,
    picks: list[str],
    rename: bool = False,
) -> dict:
    """拆书产物角色收进库：走 cards 单源投影；provenance 幂等；只写库不动书。
    软删过的卡重新收录＝同键复活。"""
    from deconstruct.cards import card_to_book_payload, cards_from_products

    try:
        products = json.loads(task.products_json or "{}")
    except (TypeError, ValueError):
        products = {}
    product = products.get("characters") if isinstance(products, dict) else None
    data = product.get("data") if isinstance(product, dict) else None
    cards = cards_from_products(data or {})
    by_key: dict[str, tuple[int, dict]] = {}
    for idx, card in enumerate(cards, start=1):
        by_key[deconstruct_source_key(card, idx)] = (idx, card)

    genre = _deconstruct_genre(task)
    collected = await collected_source_keys(db, user_id, task.id)
    created = 0
    skipped = 0
    library_ids: list[str] = []
    for key in picks:
        if key in collected:
            skipped += 1
            continue
        entry_data = by_key.get(key)
        if entry_data is None:
            skipped += 1
            continue
        idx, card = entry_data
        payload = card_to_book_payload(card, idx)
        dossier = dict(payload["dossier"])
        if rename:
            picked = random_name_local(dossier.get("gender") or "")
            payload["name"] = picked["name"]
            dossier["age"] = str(picked["age"])
        stale = await _existing_source_entry(
            db, user_id, task.id, key, include_archived=True
        )
        try:
            if stale is not None and stale.status in ("active", "merged"):
                skipped += 1  # merged 不复活不重建（c-kb-organize）
                library_ids.append(stale.id)
                continue
            if stale is not None:  # 软删过：同键复活
                record = await _revive_card_entry(
                    db, user_id, stale,
                    name=payload["name"][:NAME_MAX],
                    aliases=_json_dumps(payload["aliases"] or []),
                    role=payload["role"], kind="",
                    persona=payload["persona"] or "",
                    dossier=_json_dumps(dossier),
                    # 认知格：建书路径不从产物合成（产物无 cog）；库卡先空，后续可补
                    cog="{}",
                    genre=genre, src_novel_name=task.book_name or "",
                )
            else:
                record = await _create_card_entry(
                    db, user_id,
                    name=payload["name"][:NAME_MAX],
                    aliases=_json_dumps(payload["aliases"] or []),
                    role=payload["role"], kind="",
                    persona=payload["persona"] or "",
                    dossier=_json_dumps(dossier),
                    cog="{}",
                    genre=genre, src_kind="deconstruct",
                    src_ref=task.id, src_key=key,
                    src_novel_name=task.book_name or "", evidence=task.book_name or "",
                )
        except IntegrityError:
            # 逐卡提交：并发/双击的唯一索引冲突只回滚当前这张，不吞本批已建的卡
            await db.rollback()
            race = await _existing_source_entry(
                db, user_id, task.id, key, include_archived=True
            )
            if race is None:
                raise
            if race.status == "active":
                skipped += 1
                library_ids.append(race.id)
                continue
            record = await _revive_card_entry(
                db, user_id, race,
                name=payload["name"][:NAME_MAX],
                aliases=_json_dumps(payload["aliases"] or []),
                role=payload["role"], kind="",
                persona=payload["persona"] or "",
                dossier=_json_dumps(dossier), cog="{}",
                genre=genre, src_novel_name=task.book_name or "",
            )
        created += 1
        library_ids.append(record.id)
    if created:
        logger.info("event=character_library.import_deconstruct task=%s created=%s", task.id, created)
    return {"created": created, "skipped": skipped, "library_ids": library_ids, "genre": genre}

# ── 库卡头像生成（c-library-avatar-gen：复用书内头像生成能力） ─────────────


async def generate_avatar(
    db: AsyncSession, user_id: str, card_id: str, body: dict | None = None,
) -> dict:
    """按卡上档案生成头像：复用图像配置＋供应商适配器＋512/96 压缩链。

    与书内头像生成同权（image-generate / PRO，门在 router）；账号级同步调用
    （无书上下文，不经 ImageJob 异步队列）。失败一律可读文案。
    """
    import asyncio

    from api_configs.crypto import decrypt_api_key
    from image_assets.adapters import (
        ImageGenerationSpec,
        ImageProviderError,
        generate_images,
    )
    from image_assets.prompt_builder import build_library_avatar_prompt
    from image_assets.service import Unprocessable as ImageUnprocessable
    from image_assets.service import normalize_image
    from models.image_asset import ImageConfig

    body = body or {}
    entry = await _get_entry(db, user_id, card_id)
    # prompt builder 鸭子读卡列（name/aliases/dossier JSON 串/persona/id/genre）
    view = payload_to_card(entry)
    card_ns = SimpleNamespace(
        id=entry.id,
        name=view["name"],
        aliases=_json_dumps(view["aliases"]),
        dossier=_json_dumps(view["dossier"]),
        persona=view["persona"],
        genre=entry.genre,
    )
    prompt = await build_library_avatar_prompt(db, user_id, card_ns)
    if not prompt.get("provider"):
        raise LibraryError(
            "no_image_config", "还没有可用的图像配置——去「模型配置」添加一个图像模型再试"
        )
    spec = ImageGenerationSpec(
        provider=str(prompt["provider"]),
        model=str(prompt.get("model") or ""),
        prompt=prompt["prompt"],
        negative_prompt=prompt["negative_prompt"],
        kind="avatar",
        n=1,
        seed=prompt.get("seed"),
        capabilities=prompt.get("capabilities") or {},
    )
    config_id = str((prompt.get("sources") or {}).get("image_config_id") or "")
    config = await db.get(ImageConfig, config_id) if config_id else None
    if config is None or config.user_id != user_id or config.status != "active":
        raise LibraryError("no_image_config", "图像配置已被删除——去「模型配置」重新添加再试")

    try:
        images = await asyncio.wait_for(
            generate_images(
                base_url=config.base_url,
                api_key=decrypt_api_key(config.api_key),
                spec=spec,
            ),
            timeout=120,
        )
    except TimeoutError:
        raise LibraryError("image_timeout", "图像生成超时了，稍后再试一次")
    except ImageProviderError as e:
        raise LibraryError("image_failed", f"图像生成失败：{e.message}")
    if not images:
        raise LibraryError("image_failed", "图像生成失败：供应商没有返回图片")
    try:
        processed = normalize_image(images[0].data, "avatar")
    except ImageUnprocessable as e:
        raise LibraryError("image_failed", f"图像生成失败：{e.message}")
    await _put_avatar_blobs(db, entry.id, processed["full"], processed["thumb"])
    entry.rev += 1
    await db.commit()
    await db.refresh(entry)
    logger.info("event=character_library.avatar_generated card=%s bytes=%s", entry.id, processed["bytes"])
    return {
        "card_id": entry.id,
        "avatar": {
            "has": True,
            "url": f"/api/character-library/{entry.id}/avatar?variant=full",
            "thumb_url": f"/api/character-library/{entry.id}/avatar?variant=thumb",
        },
        "rev": entry.rev,
    }
