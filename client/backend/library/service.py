"""角色库域服务（c-character-library）——账号级跨书角色卡。

语义基线（见 change 的 spec/design）：
- 收录（书卡→库）＝整卡复制；provenance（src_kind/src_ref/src_character_id）幂等。
- 书→库手动同步＝PULL 书内最新书域格（名字/别名/人设/档案八格/认知/头像），库分类不动。
- 用到新书（库→书）＝复制落书内角色卡（含认知各格与头像），撞名自动后缀、主角冲突落配角。
- 头像：库域自持 BLOB（独立 blobs 表），复用 normalize_image("avatar") 的 512/96 档位；
  列表只回引用，字节走 GET /{id}/avatar。
- 随机起名：AI 能力，任何失败/无 Key/模板缺失一律本地词库兜底恒返回。
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.character import Character
from models.character_library import CharacterLibrary, CharacterLibraryBlob
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


# ── 卡片序列化与校验 ──────────────────────────────────────────────────────


def card_dict(card: CharacterLibrary, *, has_avatar: bool) -> dict:
    return {
        "id": card.id,
        "name": card.name,
        "aliases": _json_loads(card.aliases, []),
        "role": card.role,
        "genre": card.genre,
        "kind": card.kind,
        "persona": card.persona,
        "dossier": _json_loads(card.dossier, {}),
        "cog": _json_loads(card.cog, {}),
        "src": {
            "kind": card.src_kind,
            "novel_name": card.src_novel_name,
            "ref": card.src_ref,
            "character_id": card.src_character_id,
        },
        "avatar": {
            "has": has_avatar,
            "url": f"/api/character-library/{card.id}/avatar?variant=full" if has_avatar else "",
            "thumb_url": f"/api/character-library/{card.id}/avatar?variant=thumb" if has_avatar else "",
        },
        "rev": card.rev,
        "updated_at": card.updated_at.isoformat() if card.updated_at else "",
    }


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
    return {
        "name": str(body.get("name") or "").strip()[:NAME_MAX],
        "aliases": _clean_aliases(body.get("aliases")),
        "role": role,
        "genre": str(body.get("genre") or "").strip()[:GENRE_MAX],
        "kind": kind,
        "persona": str(body.get("persona") or "").strip()[:PERSONA_MAX],
        "dossier": _clean_cells(body.get("dossier"), DOSSIER_KEYS, "dossier"),
        "cog": _clean_cells(body.get("cog"), COG_KEYS, "cog"),
    }


# ── 读路径 ────────────────────────────────────────────────────────────────


async def _avatar_presence(db: AsyncSession, user_id: str) -> set[str]:
    rows = await db.execute(
        select(CharacterLibraryBlob.library_id)
        .join(CharacterLibrary, CharacterLibrary.id == CharacterLibraryBlob.library_id)
        .where(
            CharacterLibrary.user_id == user_id,
            CharacterLibraryBlob.variant == "thumb",
        )
    )
    return set(rows.scalars())


async def list_cards(db: AsyncSession, user_id: str) -> dict:
    cards = (
        await db.execute(
            select(CharacterLibrary)
            .where(CharacterLibrary.user_id == user_id)
            .order_by(CharacterLibrary.created_at, CharacterLibrary.id)
        )
    ).scalars().all()
    has_avatar = await _avatar_presence(db, user_id)
    items = [card_dict(c, has_avatar=c.id in has_avatar) for c in cards]
    return {"count": len(items), "items": items}


async def get_card(db: AsyncSession, user_id: str, card_id: str) -> CharacterLibrary:
    card = (
        await db.execute(
            select(CharacterLibrary).where(
                CharacterLibrary.id == card_id,
                CharacterLibrary.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if card is None:
        raise LibraryError("not_found", "角色不存在")
    return card


async def get_card_view(db: AsyncSession, user_id: str, card_id: str) -> dict:
    card = await get_card(db, user_id, card_id)
    present = await _avatar_presence(db, user_id)
    return card_dict(card, has_avatar=card.id in present)


# ── 写路径：CRUD ──────────────────────────────────────────────────────────


async def create_card(db: AsyncSession, user_id: str, body: dict) -> dict:
    data = clean_payload(body)
    card = CharacterLibrary(
        user_id=user_id,
        name=data["name"],
        aliases=_json_dumps(data["aliases"]),
        role=data["role"],
        genre=data["genre"],
        kind=data["kind"],
        persona=data["persona"],
        dossier=_json_dumps(data["dossier"]),
        cog=_json_dumps(data["cog"]),
        src_kind="manual",
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return card_dict(card, has_avatar=False)


async def update_card(db: AsyncSession, user_id: str, card_id: str, body: dict) -> dict:
    card = await get_card(db, user_id, card_id)
    data = clean_payload(body)
    card.name = data["name"]
    card.aliases = _json_dumps(data["aliases"])
    card.role = data["role"]
    card.genre = data["genre"]
    card.kind = data["kind"]
    card.persona = data["persona"]
    card.dossier = _json_dumps(data["dossier"])
    card.cog = _json_dumps(data["cog"])
    card.rev += 1
    await db.commit()
    await db.refresh(card)
    present = await _avatar_presence(db, user_id)
    return card_dict(card, has_avatar=card.id in present)


async def delete_card(db: AsyncSession, user_id: str, card_id: str) -> dict:
    card = await get_card(db, user_id, card_id)
    # 复制语义：只删库里的卡（blobs 级联），书内已导入的副本不受影响。
    await db.delete(card)
    await db.commit()
    return {"deleted": card_id}


# ── 头像 ──────────────────────────────────────────────────────────────────


async def put_avatar(
    db: AsyncSession, card: CharacterLibrary, full: bytes, thumb: bytes
) -> None:
    await db.execute(
        delete(CharacterLibraryBlob).where(CharacterLibraryBlob.library_id == card.id)
    )
    db.add(CharacterLibraryBlob(library_id=card.id, variant="full", data=full))
    db.add(CharacterLibraryBlob(library_id=card.id, variant="thumb", data=thumb))


async def _copy_book_avatar(
    db: AsyncSession, user_id: str, character_id: str, card: CharacterLibrary
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
    await put_avatar(db, card, blobs["full"], blobs["thumb"])
    return True


async def avatar_bytes(db: AsyncSession, user_id: str, card_id: str, variant: str) -> tuple[bytes, str]:
    if variant not in AVATAR_VARIANTS:
        raise LibraryError("invalid_variant", "variant 只能是 full 或 thumb")
    await get_card(db, user_id, card_id)  # 归属校验
    blob = (
        await db.execute(
            select(CharacterLibraryBlob).where(
                CharacterLibraryBlob.library_id == card_id,
                CharacterLibraryBlob.variant == variant,
            )
        )
    ).scalar_one_or_none()
    if blob is None:
        raise LibraryError("avatar_not_found", "这张卡还没有头像")
    return blob.data, hashlib.sha256(blob.data).hexdigest()


# ── 收录（书卡 → 库） ─────────────────────────────────────────────────────


async def _story_genre(db: AsyncSession, novel: Novel) -> str:
    try:
        from filesystem.storage import get_storage

        story = await get_storage().read_yaml(novel.root_path, "story.yaml") or {}
        return str(story.get("genre") or "").strip()[:GENRE_MAX]
    except Exception:  # noqa: BLE001 — 题材继承是尽力而为，不阻断收录
        return ""


async def _existing_source_card(
    db: AsyncSession, user_id: str, src_ref: str, src_character_id: str
) -> CharacterLibrary | None:
    return (
        await db.execute(
            select(CharacterLibrary).where(
                CharacterLibrary.user_id == user_id,
                CharacterLibrary.src_ref == src_ref,
                CharacterLibrary.src_character_id == src_character_id,
            )
        )
    ).scalar_one_or_none()


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
    """书内卡整卡收进库；同一书卡重复收录返回已有卡（幂等）。调用方已校验书归属。"""
    existing = await _existing_source_card(db, user_id, novel.id, character_id)
    if existing is not None:
        present = await _avatar_presence(db, user_id)
        return {"created": False, "card": card_dict(existing, has_avatar=existing.id in present)}

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
        name, age = picked["name"], str(picked["age"])
        dossier = {**dossier, "age": age}

    card = CharacterLibrary(
        user_id=user_id,
        name=name[:NAME_MAX],
        aliases=character.aliases or "[]",
        role=_role_of_character(character),
        genre=await _story_genre(db, novel),
        kind="",
        persona=character.persona or "",
        dossier=_json_dumps(dossier),
        cog=character.cog or "{}",
        src_kind="book",
        src_ref=novel.id,
        src_character_id=character.id,
        src_novel_name=novel.name,
    )
    db.add(card)
    await db.flush()
    await _copy_book_avatar(db, user_id, character.id, card)
    try:
        await db.commit()
    except IntegrityError:
        # 双击/并发：唯一索引兜底，回查返回已有卡
        await db.rollback()
        existing = await _existing_source_card(db, user_id, novel.id, character_id)
        if existing is None:
            raise
        present = await _avatar_presence(db, user_id)
        return {"created": False, "card": card_dict(existing, has_avatar=existing.id in present)}
    await db.refresh(card)
    present = await _avatar_presence(db, user_id)
    logger.info("event=character_library.collect novel=%s card=%s", novel.id, card.id)
    return {"created": True, "card": card_dict(card, has_avatar=card.id in present)}


# ── 书 → 库手动同步 ───────────────────────────────────────────────────────


async def sync_from_book(db: AsyncSession, user_id: str, card_id: str) -> dict:
    card = await get_card(db, user_id, card_id)
    if card.src_kind != "book" or not card.src_ref or not card.src_character_id:
        raise LibraryError("not_book_sourced", "这张卡不是从书里收进来的，没有可同步的来源")
    novel = (
        await db.execute(
            select(Novel).where(
                Novel.id == card.src_ref,
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
                    Character.id == card.src_character_id,
                    Character.novel_id == novel.id,
                )
            )
        ).scalar_one_or_none()
    if source is None:
        raise LibraryError("source_gone", "书里的这张卡找不到了（书或卡可能已删除）")

    card.name = (source.name.lstrip("\u0000") or "")[:NAME_MAX]
    card.aliases = source.aliases or "[]"
    card.persona = source.persona or ""
    card.dossier = source.dossier or "{}"
    card.cog = source.cog or "{}"
    card.src_novel_name = novel.name
    card.rev += 1
    if not await _copy_book_avatar(db, user_id, source.id, card):
        await db.execute(
            delete(CharacterLibraryBlob).where(CharacterLibraryBlob.library_id == card.id)
        )
    await db.commit()
    await db.refresh(card)
    present = await _avatar_presence(db, user_id)
    logger.info("event=character_library.sync card=%s novel=%s", card.id, novel.id)
    return card_dict(card, has_avatar=card.id in present)


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

    card = await get_card(db, user_id, card_id)
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

    dossier = _json_loads(card.dossier, {})
    base_name = card.name
    if rename:
        picked = random_name_local(dossier.get("gender") or "")
        base_name = picked["name"]
        dossier = {**dossier, "age": str(picked["age"])}

    role = card.role
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
                persona=card.persona,
                aliases=_json_loads(card.aliases, []),
                dossier=dossier,
                cog=_json_loads(card.cog, {}),
            )
            break
        except Conflict:
            continue
    if created is None:
        raise LibraryError("name_exhausted", "这本书里同名角色太多了，换个名字再试")

    avatar_copied = False
    full = (
        await db.execute(
            select(CharacterLibraryBlob).where(
                CharacterLibraryBlob.library_id == card.id,
                CharacterLibraryBlob.variant == "full",
            )
        )
    ).scalar_one_or_none()
    if full is not None:
        try:
            from image_assets.service import adopt_asset, create_generated_asset

            asset = await create_generated_asset(
                db,
                user_id=user_id,
                novel_id=novel_id,
                kind="avatar",
                data=full.data,
                character_id=created.id,
                source="library",
            )
            await adopt_asset(db, user_id, asset.id)
            avatar_copied = True
        except Exception as e:  # noqa: BLE001 — 头像失败不拖垮落卡（卡片无图可后补）
            logger.warning("event=character_library.avatar_copy_fail card=%s error=%s", card.id, e)

    return {
        "character_id": created.id,
        "name": created.name.lstrip("\u0000") or created.name,
        "role": created.role,
        "renamed": created.name != card.name,
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
        select(CharacterLibrary.src_character_id).where(
            CharacterLibrary.user_id == user_id,
            CharacterLibrary.src_kind == "deconstruct",
            CharacterLibrary.src_ref == task_id,
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
    return str(genre or "").strip()[:GENRE_MAX]


async def import_from_deconstruct(
    db: AsyncSession,
    user_id: str,
    task,
    *,
    picks: list[str],
    rename: bool = False,
) -> dict:
    """拆书产物角色收进库：走 cards 单源投影；provenance 幂等；只写库不动书。"""
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
        entry = by_key.get(key)
        if entry is None:
            skipped += 1
            continue
        idx, card = entry
        payload = card_to_book_payload(card, idx)
        dossier = dict(payload["dossier"])
        if rename:
            picked = random_name_local(dossier.get("gender") or "")
            payload["name"] = picked["name"]
            dossier["age"] = str(picked["age"])
        record = CharacterLibrary(
            user_id=user_id,
            name=payload["name"][:NAME_MAX],
            aliases=_json_dumps(payload["aliases"] or []),
            role=payload["role"],
            genre=genre,
            kind="",
            persona=payload["persona"] or "",
            dossier=_json_dumps(dossier),
            # 认知格：建书路径不从产物合成（产物无 cog）；库卡先空，后续可补
            cog="{}",
            src_kind="deconstruct",
            src_ref=task.id,
            src_character_id=key,
            src_novel_name=task.book_name or "",
        )
        db.add(record)
        try:
            # 逐卡提交：并发/双击的唯一索引冲突只回滚当前这张，不吞本批已建的卡
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await _existing_source_card(db, user_id, task.id, key)
            if existing is not None:
                skipped += 1
                library_ids.append(existing.id)
                continue
            raise
        created += 1
        library_ids.append(record.id)
    if created:
        logger.info("event=character_library.import_deconstruct task=%s created=%s", task.id, created)
    return {"created": created, "skipped": skipped, "library_ids": library_ids}

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
    card = await get_card(db, user_id, card_id)
    prompt = await build_library_avatar_prompt(db, user_id, card)
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
    config = (await db.execute(
        select(ImageConfig).where(
            ImageConfig.user_id == user_id,
            ImageConfig.status == "active",
            ImageConfig.provider == prompt["provider"],
        ).order_by(ImageConfig.is_default.desc(), ImageConfig.created_at.asc())
    )).scalars().first()
    if config is None:
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
    await put_avatar(db, card, processed["full"], processed["thumb"])
    card.rev += 1
    await db.commit()
    logger.info("event=character_library.avatar_generated card=%s bytes=%s", card.id, processed["bytes"])
    return {
        "card_id": card.id,
        "avatar": {
            "has": True,
            "url": f"/api/character-library/{card.id}/avatar?variant=full",
            "thumb_url": f"/api/character-library/{card.id}/avatar?variant=thumb",
        },
        "rev": card.rev,
    }
