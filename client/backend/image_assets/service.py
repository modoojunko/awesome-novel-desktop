"""图像配置/资产服务（c-cover-avatar 阶段 1）。

阶段 1 只做：配置 CRUD、上传、采用、撤销、签名读取、每书绑定。
生成/测试/试画不在本文件；后续阶段复用同一资产与签名管线。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from api_configs.crypto import decrypt_api_key, encrypt_api_key
from api_configs.schemas import mask_api_key
from image_assets.prompt_builder import (
    STYLE_KEYS,
    build_avatar_prompt,
    build_cover_prompt,
)
from models.app_meta import AppMeta
from models.character import Character
from models.image_asset import (
    BookImageSettings,
    CharacterImageSettings,
    ImageAsset,
    ImageAssetBlob,
    ImageConfig,
)
from models.project import Novel

PROVIDERS = {"volcengine", "aliyun", "zhipu", "openai", "minimax", "openai-compat"}
KINDS = {"cover", "avatar"}
VARIANTS = {"full", "thumb"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 30_000_000
MAX_DIMENSION = 4096
CANDIDATE_TTL = timedelta(hours=24)
UNDO_TTL = timedelta(seconds=8)
TARGETS = {
    "cover": ((768, 1024), (208, 277)),
    "avatar": ((512, 512), (96, 96)),
}
SIGNING_KEY_ROW = "image_asset_signing_key"
SIGN_TTL_SECONDS = 3600
# 缓存必须短于签名有效期，否则浏览器会拿着过期签名反复 403。
SIGN_CACHE_SECONDS = 3300

logger = logging.getLogger("uvicorn.error")


class Unprocessable(Exception):
    def __init__(self, detail: str, code: str = "invalid_request"):
        self.detail = detail
        self.code = code


class Conflict(Exception):
    def __init__(self, detail: str, code: str = "conflict"):
        self.detail = detail
        self.code = code


class SigningUnavailable(Exception):
    """签名密钥不可用：图像能力降级，但不拖垮书/角色主链。"""



def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _epoch() -> int:
    return int((now_utc() - datetime(1970, 1, 1)).total_seconds())


# ── 配置 ───────────────────────────────────────────────────────────────────


def _safe_json(value: str | None, fallback):
    try:
        return json.loads(value) if value else fallback
    except (TypeError, ValueError):
        return fallback


def config_to_dict(c: ImageConfig) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "provider": c.provider,
        "base_url": c.base_url,
        "api_key_masked": mask_api_key(decrypt_api_key(c.api_key)) if c.api_key else "",
        "default_model": c.default_model,
        "models": _safe_json(c.models, []),
        "declared_capabilities": _safe_json(c.declared_capabilities, {}),
        "is_default": bool(c.is_default),
        "status": c.status,
        "last_test_status": c.last_test_status,
        "last_test_error": c.last_test_error,
        "last_tested_at": c.last_tested_at.isoformat() if c.last_tested_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


async def list_configs(db: AsyncSession, user_id: str, include_deleted: bool = False) -> list[dict]:
    statuses = ["active", "deleted"] if include_deleted else ["active"]
    rows = (await db.execute(
        select(ImageConfig)
        .where(ImageConfig.user_id == user_id, ImageConfig.status.in_(statuses))
        .order_by(ImageConfig.is_default.desc(), ImageConfig.created_at.asc())
    )).scalars().all()
    return [config_to_dict(c) for c in rows]


async def _clear_other_defaults(db: AsyncSession, user_id: str, keep_id: str | None):
    rows = (await db.execute(
        select(ImageConfig).where(
            ImageConfig.user_id == user_id,
            ImageConfig.status == "active",
            ImageConfig.is_default.is_(True),
        )
    )).scalars().all()
    for row in rows:
        if row.id != keep_id:
            row.is_default = False


async def _ensure_default(db: AsyncSession, user_id: str, exclude_id: str | None = None) -> str | None:
    """active 配置必须有一个默认；显式取消默认时优先补另一个配置。"""
    rows = (await db.execute(
        select(ImageConfig).where(
            ImageConfig.user_id == user_id,
            ImageConfig.status == "active",
        ).order_by(ImageConfig.created_at.asc())
    )).scalars().all()
    for row in rows:
        if row.is_default:
            return row.id
    candidates = [row for row in rows if row.id != exclude_id] or rows
    if candidates:
        candidates[0].is_default = True
        await db.flush()
        return candidates[0].id
    return None


async def _commit_config(db: AsyncSession, detail: str, code: str) -> None:
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise Conflict(detail, code) from e


async def create_config(db: AsyncSession, user_id: str, data: dict) -> dict:
    provider = str(data.get("provider") or "").strip()
    if provider not in PROVIDERS:
        raise Unprocessable("provider 不在支持列表", "invalid_provider")
    name = str(data.get("name") or "").strip()
    if not name:
        raise Unprocessable("配置名称不能为空", "invalid_name")
    existing = (await db.execute(
        select(ImageConfig).where(
            ImageConfig.user_id == user_id, ImageConfig.name == name,
        )
    )).scalar_one_or_none()
    if existing and existing.status == "active":
        raise Conflict("同名图像配置已存在", "duplicate_name")
    active_ids = (await db.execute(
        select(ImageConfig.id).where(
            ImageConfig.user_id == user_id, ImageConfig.status == "active",
        )
    )).scalars().all()
    # 第一条 active 配置自动成为默认；之后只有显式 is_default 才改默认。
    is_default = bool(data.get("is_default")) or not active_ids
    if is_default:
        await _clear_other_defaults(db, user_id, None)
        await db.flush()
    # 同名软删行直接复活，避免 UNIQUE(user_id,name) 撞车
    c = existing or ImageConfig(user_id=user_id, name=name)
    c.provider = provider
    c.base_url = str(data.get("base_url") or "")
    c.api_key = encrypt_api_key(str(data.get("api_key") or ""))
    c.default_model = str(data.get("default_model") or "")
    c.models = json.dumps(data.get("models") or [], ensure_ascii=False)
    c.declared_capabilities = json.dumps(data.get("declared_capabilities") or {}, ensure_ascii=False)
    c.is_default = is_default
    c.status = "active"
    c.last_test_status = None
    c.last_test_error = None
    c.last_tested_at = None
    if not existing:
        db.add(c)
    if not is_default:
        # 兼容历史库“有 active 但无默认”的不一致状态。
        await db.flush()
        await _ensure_default(db, user_id)
    await _commit_config(db, "同名或默认配置并发冲突，请刷新后重试", "config_conflict")
    await db.refresh(c)
    return config_to_dict(c)


async def update_config(db: AsyncSession, user_id: str, config_id: str, data: dict) -> dict:
    c = (await db.execute(
        select(ImageConfig).where(
            ImageConfig.id == config_id, ImageConfig.user_id == user_id,
            ImageConfig.status == "active",
        )
    )).scalar_one_or_none()
    if not c:
        raise Unprocessable("图像配置不存在", "config_not_found")
    if "provider" in data and data["provider"] not in PROVIDERS:
        raise Unprocessable("provider 不在支持列表", "invalid_provider")
    if "name" in data and data["name"] is not None:
        name = str(data["name"]).strip()
        if not name:
            raise Unprocessable("配置名称不能为空", "invalid_name")
        if name != c.name:
            dup = (await db.execute(
                select(ImageConfig).where(
                    ImageConfig.user_id == user_id, ImageConfig.name == name,
                    ImageConfig.id != c.id,
                )
            )).scalar_one_or_none()
            if dup:
                raise Conflict("同名图像配置已存在（含已删除配置）", "duplicate_name")
            c.name = name
    provider_changed = (
        "provider" in data and data["provider"] is not None
        and data["provider"] != c.provider
    )
    for key in ("provider", "base_url", "default_model"):
        if key in data and data[key] is not None:
            setattr(c, key, str(data[key]))
    if provider_changed:
        # 换供应商不能继续用旧 Key/模型打到新 Base；未随请求提供即清空。
        if "api_key" not in data:
            c.api_key = encrypt_api_key("")
        if "base_url" not in data:
            c.base_url = ""
        if "default_model" not in data:
            c.default_model = ""
        if "models" not in data:
            c.models = "[]"
        c.last_test_status = None
        c.last_test_error = None
        c.last_tested_at = None
        await db.execute(
            update(BookImageSettings)
            .where(
                BookImageSettings.novel_id.in_(
                    select(Novel.id).where(Novel.user_id == user_id)
                ),
                BookImageSettings.image_config_id == c.id,
            )
            .values(image_model="")
        )
    if "api_key" in data:
        c.api_key = encrypt_api_key(str(data["api_key"] or ""))
    if "models" in data and data["models"] is not None:
        c.models = json.dumps(data["models"], ensure_ascii=False)
    if "declared_capabilities" in data and data["declared_capabilities"] is not None:
        c.declared_capabilities = json.dumps(data["declared_capabilities"], ensure_ascii=False)
    if "is_default" in data and data["is_default"] is not None:
        if data["is_default"]:
            # 先落“其他配置取消默认”，再置本行——同一条 flush 里唯一索引可能先写新默认。
            await _clear_other_defaults(db, user_id, c.id)
            await db.flush()
            c.is_default = True
        else:
            c.is_default = False
        await db.flush()
        await _ensure_default(db, user_id, exclude_id=None if data["is_default"] else c.id)
    await _commit_config(db, "配置并发更新冲突，请刷新后重试", "config_conflict")
    await db.refresh(c)
    return config_to_dict(c)


async def delete_config(db: AsyncSession, user_id: str, config_id: str) -> dict:
    c = (await db.execute(
        select(ImageConfig).where(
            ImageConfig.id == config_id, ImageConfig.user_id == user_id,
            ImageConfig.status == "active",
        )
    )).scalar_one_or_none()
    if not c:
        raise Unprocessable("图像配置不存在", "config_not_found")
    # 软删后书上的绑定必须一起解掉，否则设置页会指向一个不存在于列表的配置。
    affected_books = int((await db.execute(
        select(func.count()).select_from(BookImageSettings).where(
            BookImageSettings.novel_id.in_(
                select(Novel.id).where(Novel.user_id == user_id)
            ),
            BookImageSettings.image_config_id == c.id,
        )
    )).scalar_one() or 0)
    await db.execute(
        update(BookImageSettings)
        .where(
            BookImageSettings.novel_id.in_(
                select(Novel.id).where(Novel.user_id == user_id)
            ),
            BookImageSettings.image_config_id == c.id,
        )
        .values(image_config_id=None, image_model="")
    )
    c.status = "deleted"
    c.is_default = False
    await db.flush()
    default_id = await _ensure_default(db, user_id)
    await _commit_config(db, "配置并发删除冲突，请刷新后重试", "config_conflict")
    return {
        "id": config_id, "status": "deleted", "default_image_config_id": default_id,
        "affected_book_count": affected_books,
    }


async def restore_config(db: AsyncSession, user_id: str, config_id: str) -> dict:
    c = (await db.execute(
        select(ImageConfig).where(
            ImageConfig.id == config_id, ImageConfig.user_id == user_id,
            ImageConfig.status == "deleted",
        )
    )).scalar_one_or_none()
    if not c:
        raise Unprocessable("图像配置不存在或未删除", "config_not_deleted")
    dup = (await db.execute(
        select(ImageConfig).where(
            ImageConfig.user_id == user_id, ImageConfig.name == c.name,
            ImageConfig.status == "active",
        )
    )).scalar_one_or_none()
    if dup:
        raise Conflict("同名图像配置已存在，无法恢复", "duplicate_name")
    c.status = "active"
    await db.flush()
    await _ensure_default(db, user_id)
    await _commit_config(db, "配置并发恢复冲突，请刷新后重试", "config_conflict")
    await db.refresh(c)
    return config_to_dict(c)



# ── 图片处理 ───────────────────────────────────────────────────────────────


def _encode_webp(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=85, method=4)
    return out.getvalue()


def normalize_image(data: bytes, kind: str) -> dict:
    if kind not in TARGETS:
        raise Unprocessable("kind 必须是 cover 或 avatar", "invalid_kind")
    if len(data) > MAX_BYTES:
        raise Unprocessable("图片超过 10MB", "file_too_large")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise Unprocessable("仅支持 JPG/PNG/WebP 图片", "unsupported_format")
            probe.verify()
    except Unprocessable:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
        raise Unprocessable("不是可识别的图片", "invalid_image") from e
    try:
        with Image.open(io.BytesIO(data)) as src:
            src = ImageOps.exif_transpose(src)
            if src.width * src.height > MAX_PIXELS:
                raise Unprocessable("图片像素超过上限", "pixels_too_large")
            if src.width > MAX_DIMENSION or src.height > MAX_DIMENSION:
                raise Unprocessable("图片边长超过上限", "dimension_too_large")
            if src.mode in ("RGBA", "LA") or (src.mode == "P" and "transparency" in src.info):
                bg = Image.new("RGBA", src.size, (255, 255, 255, 255))
                bg.alpha_composite(src.convert("RGBA"))
                src = bg.convert("RGB")
            else:
                src = src.convert("RGB")
            (tw, th), (thumb_w, thumb_h) = TARGETS[kind]
            full = ImageOps.fit(src, (tw, th), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            thumb = ImageOps.fit(src, (thumb_w, thumb_h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            full_bytes = _encode_webp(full)
            thumb_bytes = _encode_webp(thumb)
            return {
                "full": full_bytes,
                "thumb": thumb_bytes,
                "width": tw,
                "height": th,
                "bytes": len(full_bytes),
                "sha256": hashlib.sha256(full_bytes).hexdigest(),
                "mime": "image/webp",
            }
    except Unprocessable:
        raise
    except (OSError, ValueError) as e:
        raise Unprocessable("图片解码或转码失败", "image_decode_failed") from e



# ── 资产 ───────────────────────────────────────────────────────────────────


async def _owned_novel(db: AsyncSession, user_id: str, novel_id: str) -> Novel:
    n = (await db.execute(
        select(Novel).where(Novel.id == novel_id, Novel.user_id == user_id,
                            Novel.status != "deleted")
    )).scalar_one_or_none()
    if not n:
        raise Unprocessable("书不存在", "novel_not_found")
    return n


async def _owned_character(
    db: AsyncSession, user_id: str, novel_id: str, character_id: str,
) -> Character:
    c = (await db.execute(
        select(Character)
        .join(Novel, Novel.id == Character.novel_id)
        .where(
            Character.id == character_id,
            Character.novel_id == novel_id,
            Novel.user_id == user_id,
            Novel.status != "deleted",
        )
    )).scalar_one_or_none()
    if not c:
        raise Unprocessable("角色不存在", "character_not_found")
    return c


async def create_asset(
    db: AsyncSession, user_id: str, novel_id: str, kind: str,
    data: bytes, character_id: str | None = None,
) -> ImageAsset:
    await _owned_novel(db, user_id, novel_id)
    if kind not in KINDS:
        raise Unprocessable("kind 必须是 cover 或 avatar", "invalid_kind")
    if kind == "avatar":
        if not character_id:
            raise Unprocessable("头像必须指定角色", "character_required")
        await _owned_character(db, user_id, novel_id, character_id)
    elif character_id:
        raise Unprocessable("封面不能指定角色", "cover_no_character")
    # 写路径在落库前确认签名能力；密钥不可用时不制造“已上传但拿不到 URL”的孤儿。
    await ensure_signing_key(db)
    await sweep_expired_assets(db, user_id=user_id)
    processed = normalize_image(data, kind)
    asset = ImageAsset(
        user_id=user_id,
        novel_id=novel_id,
        character_id=character_id if kind == "avatar" else None,
        kind=kind,
        status="candidate",
        sha256=processed["sha256"],
        mime=processed["mime"],
        width=processed["width"],
        height=processed["height"],
        bytes=processed["bytes"],
        source="upload",
        expires_at=now_utc() + CANDIDATE_TTL,
    )
    db.add(asset)
    await db.flush()
    db.add(ImageAssetBlob(asset_id=asset.id, variant="full", data=processed["full"]))
    db.add(ImageAssetBlob(asset_id=asset.id, variant="thumb", data=processed["thumb"]))
    await db.commit()
    await db.refresh(asset)
    return asset



async def _asset_for_user(db: AsyncSession, user_id: str, asset_id: str) -> ImageAsset:
    a = (await db.execute(
        select(ImageAsset).where(ImageAsset.id == asset_id, ImageAsset.user_id == user_id)
    )).scalar_one_or_none()
    if not a:
        raise Unprocessable("资产不存在", "asset_not_found")
    return a


def _target_filter(asset: ImageAsset):
    if asset.kind == "cover":
        return ImageAsset.novel_id == asset.novel_id, ImageAsset.kind == "cover"
    return ImageAsset.character_id == asset.character_id, ImageAsset.kind == "avatar"


async def list_assets(
    db: AsyncSession, user_id: str, novel_id: str, *,
    kind: str | None = None, character_id: str | None = None,
    status: str | None = None, limit: int = 50,
) -> list[dict]:
    await _owned_novel(db, user_id, novel_id)
    if kind and kind not in KINDS:
        raise Unprocessable("kind 必须是 cover 或 avatar", "invalid_kind")
    if status and status not in {"candidate", "current", "previous"}:
        raise Unprocessable("status 必须是 candidate/current/previous", "invalid_status")
    if character_id:
        await _owned_character(db, user_id, novel_id, character_id)
    q = select(ImageAsset).where(
        ImageAsset.user_id == user_id, ImageAsset.novel_id == novel_id,
    )
    if kind:
        q = q.where(ImageAsset.kind == kind)
    if character_id:
        q = q.where(ImageAsset.character_id == character_id)
    if status:
        q = q.where(ImageAsset.status == status)
        if status in {"candidate", "previous"}:
            q = q.where(ImageAsset.expires_at.is_not(None), ImageAsset.expires_at >= now_utc())
    else:
        # 过期候选/previous 不再出现在列表里；清理由 sweep 负责，读取不写库。
        q = q.where(
            (ImageAsset.status == "current")
            | ImageAsset.expires_at.is_(None)
            | (ImageAsset.expires_at >= now_utc())
        )
    rows = (await db.execute(
        q.order_by(ImageAsset.created_at.desc()).limit(max(1, min(int(limit), 100)))
    )).scalars().all()
    return await assets_to_dict(db, rows)


async def adopt_asset(db: AsyncSession, user_id: str, asset_id: str) -> ImageAsset:
    await ensure_signing_key(db)
    asset = await _asset_for_user(db, user_id, asset_id)
    if asset.status != "candidate":
        raise Conflict("只有候选图可以被采用", "asset_not_candidate")
    now = now_utc()
    if asset.expires_at is not None and asset.expires_at < now:
        raise Conflict("候选图已过期，请重新上传", "asset_expired")
    await sweep_expired_assets(db, user_id=user_id)
    # sweep 可能 commit 并 expire 已加载对象；重新取一次再读 novel/kind/character_id。
    asset = await _asset_for_user(db, user_id, asset_id)
    now = now_utc()
    if asset.status != "candidate" or (asset.expires_at is not None and asset.expires_at < now):
        raise Conflict("候选图状态已变化，请刷新后重试", "asset_state_conflict")
    target, kind_filter = _target_filter(asset)

    # 先按状态谓词删掉更早的 previous；returning 拿到真正删掉的行，避免把
    # 并发 undo 刚恢复成 current 的资产按旧 id 误删。
    prev_res = await db.execute(
        delete(ImageAsset)
        .where(target, kind_filter, ImageAsset.status == "previous")
        .returning(ImageAsset.id)
    )
    prev_ids = list(prev_res.scalars())
    if prev_ids:
        await db.execute(delete(ImageAssetBlob).where(ImageAssetBlob.asset_id.in_(prev_ids)))

    current_row = (await db.execute(
        select(ImageAsset.id, ImageAsset.version).where(
            target, kind_filter, ImageAsset.status == "current",
        )
    )).first()
    current_id, current_version = (current_row[0], current_row[1]) if current_row else (None, 0)
    if current_id:
        demote = await db.execute(
            update(ImageAsset)
            .where(ImageAsset.id == current_id, ImageAsset.status == "current")
            .values(
                status="previous", undo_token=None, undo_expires_at=None,
                expires_at=now + UNDO_TTL,
            )
            .execution_options(synchronize_session=False)
        )
        if demote.rowcount != 1:
            await db.rollback()
            raise Conflict("图片状态已被其他操作改变，请刷新后重试", "asset_state_conflict")

    token = secrets.token_urlsafe(18)
    promote = await db.execute(
        update(ImageAsset)
        .where(
            ImageAsset.id == asset.id,
            ImageAsset.user_id == user_id,
            ImageAsset.status == "candidate",
            or_(ImageAsset.expires_at.is_(None), ImageAsset.expires_at >= now),
        )
        .values(
            status="current", undo_token=token,
            undo_expires_at=now + UNDO_TTL, adopted_at=now,
            expires_at=None, version=(current_version or 0) + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if promote.rowcount != 1:
        await db.rollback()
        raise Conflict("候选图状态已变化，请刷新后重试", "asset_state_conflict")
    try:
        await db.commit()
    except (IntegrityError, StaleDataError) as e:
        await db.rollback()
        raise Conflict("图片状态已被其他操作改变，请刷新后重试", "asset_state_conflict") from e
    refreshed = await db.get(ImageAsset, asset.id, populate_existing=True)
    if refreshed is None:
        raise Conflict("图片状态已被其他操作改变，请刷新后重试", "asset_state_conflict")
    return refreshed


async def undo_asset(db: AsyncSession, user_id: str, asset_id: str, token: str) -> dict:
    await ensure_signing_key(db)
    asset = await _asset_for_user(db, user_id, asset_id)
    if (
        asset.status != "current"
        or not asset.undo_token
        or not hmac.compare_digest(asset.undo_token.encode(), token.encode())
    ):
        raise Conflict("撤销凭证无效或已过期", "undo_invalid")
    undo_expires = asset.undo_expires_at
    if undo_expires is None and asset.adopted_at is not None:
        undo_expires = asset.adopted_at + UNDO_TTL
    now = now_utc()
    if undo_expires is None or undo_expires < now:
        raise Conflict("撤销窗口已过（8 秒）", "undo_expired")
    target, kind_filter = _target_filter(asset)

    removed_res = await db.execute(
        delete(ImageAsset)
        .where(
            ImageAsset.id == asset.id,
            ImageAsset.user_id == user_id,
            ImageAsset.status == "current",
            ImageAsset.undo_token == token,
            ImageAsset.undo_expires_at.is_not(None),
            ImageAsset.undo_expires_at >= now,
        )
        .returning(ImageAsset.id)
    )
    removed_ids = list(removed_res.scalars())
    if not removed_ids:
        await db.rollback()
        raise Conflict("撤销凭证无效或已过期", "undo_invalid")
    await db.execute(delete(ImageAssetBlob).where(ImageAssetBlob.asset_id.in_(removed_ids)))

    restored_id = None
    if asset.version > 1:
        restored_res = await db.execute(
            update(ImageAsset)
            .where(target, kind_filter, ImageAsset.status == "previous")
            .values(
                status="current", undo_token=None,
                undo_expires_at=None, expires_at=None,
            )
            .returning(ImageAsset.id)
            .execution_options(synchronize_session=False)
        )
        restored = list(restored_res.scalars())
        if not restored:
            # 上一张已被 sweep/其他操作清掉；不能假装撤销成功把 current 删掉。
            await db.rollback()
            raise Conflict("上一张已被清理，无法撤销", "undo_expired")
        restored_id = restored[0]
    try:
        await db.commit()
    except (IntegrityError, StaleDataError) as e:
        await db.rollback()
        raise Conflict("图片状态已被其他操作改变，请刷新后重试", "asset_state_conflict") from e
    return {"restored_asset_id": restored_id, "removed_asset_id": asset_id}


async def sweep_expired_assets(db: AsyncSession, user_id: str | None = None) -> int:
    """清理过期的候选（24h）和撤销窗口后的 previous（8s）。

    删除与状态/过期条件同一条 SQL：并发 undo 刚把 previous 恢复成 current 时，
    旧 id 不会被这里按 id 误删。启动时全库扫一次；上传/采用前按用户扫一次。
    """
    stmt = (
        delete(ImageAsset)
        .where(
            ImageAsset.status.in_(("candidate", "previous")),
            ImageAsset.expires_at.is_not(None),
            ImageAsset.expires_at < now_utc(),
        )
        .returning(ImageAsset.id)
    )
    if user_id:
        stmt = stmt.where(ImageAsset.user_id == user_id)
    ids = list((await db.execute(stmt)).scalars())
    if not ids:
        return 0
    await db.execute(delete(ImageAssetBlob).where(ImageAssetBlob.asset_id.in_(ids)))
    await db.commit()
    return len(ids)


async def delete_candidate_asset(db: AsyncSession, user_id: str, asset_id: str) -> dict:
    asset = await _asset_for_user(db, user_id, asset_id)
    if asset.status not in {"candidate", "previous"}:
        raise Conflict("当前图不能直接删除，请先采用其他图", "asset_not_candidate")
    res = await db.execute(
        delete(ImageAsset)
        .where(
            ImageAsset.id == asset_id,
            ImageAsset.user_id == user_id,
            ImageAsset.status.in_(("candidate", "previous")),
        )
        .returning(ImageAsset.id)
    )
    ids = list(res.scalars())
    if not ids:
        await db.rollback()
        raise Conflict("图片状态已变化，请刷新后重试", "asset_state_conflict")
    await db.execute(delete(ImageAssetBlob).where(ImageAssetBlob.asset_id.in_(ids)))
    await db.commit()
    return {"deleted_asset_id": asset_id}




def _as_seed(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        seed = int(value)
    except (TypeError, ValueError) as e:
        raise Unprocessable("seed 必须是整数", "invalid_seed") from e
    if seed < 0 or seed > 2**31 - 1:
        raise Unprocessable("seed 必须在 0..2147483647 之间", "invalid_seed")
    return seed


async def get_book_settings(db: AsyncSession, user_id: str, novel_id: str) -> dict:
    await _owned_novel(db, user_id, novel_id)
    row = (await db.execute(select(BookImageSettings).where(
        BookImageSettings.novel_id == novel_id))).scalar_one_or_none()
    config, effective_model, effective_source = await _effective_image_config(
        db, user_id, row,
    )
    return {
        "novel_id": novel_id,
        "style_key": row.style_key if row else "ink",
        "cover_prompt": row.cover_prompt if row else "",
        "cover_seed": row.cover_seed if row else None,
        "image_config_id": row.image_config_id if row else None,
        "image_model": row.image_model if row else "",
        # 生成端/前端都读这三个字段，不再各自推导“没绑定就用默认”的规则。
        "effective_image_config_id": config.id if config else None,
        "effective_image_model": effective_model,
        "effective_source": effective_source,
    }


async def _effective_image_config(db: AsyncSession, user_id: str, row: BookImageSettings | None):
    config = None
    if row and row.image_config_id:
        config = (await db.execute(select(ImageConfig).where(
            ImageConfig.id == row.image_config_id,
            ImageConfig.user_id == user_id,
            ImageConfig.status == "active",
        ))).scalar_one_or_none()
    if config is None:
        config = (await db.execute(select(ImageConfig).where(
            ImageConfig.user_id == user_id,
            ImageConfig.status == "active",
        ).order_by(ImageConfig.is_default.desc(), ImageConfig.created_at.asc()))).scalars().first()
    explicit = bool(
        row and row.image_config_id and config and config.id == row.image_config_id
    )
    model = (row.image_model if row else "") or (config.default_model if config else "")
    source = "explicit" if explicit else ("default" if config else "none")
    return config, model, source


def _apply_book_settings(row: BookImageSettings, body: dict, *, partial: bool) -> None:
    if not partial or "style_key" in body:
        style_key = str(body.get("style_key") or "ink")
        if style_key not in STYLE_KEYS:
            raise Unprocessable("style_key 不在支持列表", "invalid_style")
        row.style_key = style_key
    if not partial or "cover_prompt" in body:
        row.cover_prompt = str(body.get("cover_prompt") or "")
    if "cover_seed" in body:
        row.cover_seed = _as_seed(body.get("cover_seed"))
    if not partial or "image_config_id" in body:
        row.image_config_id = body.get("image_config_id") or None
    if not partial or "image_model" in body:
        row.image_model = str(body.get("image_model") or "")


async def _save_book_settings(
    db: AsyncSession, user_id: str, novel_id: str, body: dict, *, partial: bool,
) -> dict:
    await _owned_novel(db, user_id, novel_id)
    config_id = body.get("image_config_id") or None
    if config_id:
        c = (await db.execute(select(ImageConfig).where(
            ImageConfig.id == config_id, ImageConfig.user_id == user_id,
            ImageConfig.status == "active"))).scalar_one_or_none()
        if not c:
            raise Unprocessable("图像配置不存在", "config_not_found")
    row = (await db.execute(select(BookImageSettings).where(
        BookImageSettings.novel_id == novel_id))).scalar_one_or_none()
    if not row:
        row = BookImageSettings(novel_id=novel_id)
        db.add(row)
    _apply_book_settings(row, body, partial=partial)
    try:
        await db.commit()
    except IntegrityError:
        # 并发首次 PUT/PATCH：另一请求已插入同一 novel_id；按更新重试一次。
        await db.rollback()
        row = (await db.execute(select(BookImageSettings).where(
            BookImageSettings.novel_id == novel_id))).scalar_one()
        _apply_book_settings(row, body, partial=partial)
        await db.commit()
    return await get_book_settings(db, user_id, novel_id)


async def put_book_settings(db: AsyncSession, user_id: str, novel_id: str, body: dict) -> dict:
    return await _save_book_settings(db, user_id, novel_id, body, partial=False)


async def patch_book_settings(db: AsyncSession, user_id: str, novel_id: str, body: dict) -> dict:
    return await _save_book_settings(db, user_id, novel_id, body, partial=True)


async def get_character_settings(
    db: AsyncSession, user_id: str, novel_id: str, character_id: str,
) -> dict:
    await _owned_novel(db, user_id, novel_id)
    await _owned_character(db, user_id, novel_id, character_id)
    row = (await db.execute(select(CharacterImageSettings).where(
        CharacterImageSettings.character_id == character_id))).scalar_one_or_none()
    return {
        "character_id": character_id,
        "avatar_prompt": row.avatar_prompt if row else "",
        "seed": row.seed if row else None,
    }


async def _save_character_settings(
    db: AsyncSession, user_id: str, novel_id: str, character_id: str,
    body: dict, *, partial: bool,
) -> dict:
    await _owned_novel(db, user_id, novel_id)
    await _owned_character(db, user_id, novel_id, character_id)
    row = (await db.execute(select(CharacterImageSettings).where(
        CharacterImageSettings.character_id == character_id))).scalar_one_or_none()
    if not row:
        row = CharacterImageSettings(character_id=character_id)
        db.add(row)
    if not partial or "avatar_prompt" in body:
        row.avatar_prompt = str(body.get("avatar_prompt") or "")
    if "seed" in body:
        row.seed = _as_seed(body.get("seed"))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        row = (await db.execute(select(CharacterImageSettings).where(
            CharacterImageSettings.character_id == character_id))).scalar_one()
        if not partial or "avatar_prompt" in body:
            row.avatar_prompt = str(body.get("avatar_prompt") or "")
        if "seed" in body:
            row.seed = _as_seed(body.get("seed"))
        await db.commit()
    return await get_character_settings(db, user_id, novel_id, character_id)


async def patch_character_settings(
    db: AsyncSession, user_id: str, novel_id: str, character_id: str, body: dict,
) -> dict:
    return await _save_character_settings(
        db, user_id, novel_id, character_id, body, partial=True,
    )


# ── Prompt 预览（书/角色 → 画面；只读，不生成） ─────────────────────────────


async def get_cover_prompt(db: AsyncSession, user_id: str, novel_id: str) -> dict:
    novel = await _owned_novel(db, user_id, novel_id)
    return await build_cover_prompt(db, novel)


async def get_avatar_prompt(db: AsyncSession, user_id: str, novel_id: str,
                            character_id: str) -> dict:
    novel = await _owned_novel(db, user_id, novel_id)
    ch = await _owned_character(db, user_id, novel_id, character_id)
    return await build_avatar_prompt(db, novel, ch)


# ── 签名读取 ───────────────────────────────────────────────────────────────


async def init_signing_key(db: AsyncSession) -> bytes:
    """启动期初始化签名密钥；并发首启撞 PK 时以先落库者为准。"""
    row = (await db.execute(select(AppMeta).where(AppMeta.key == SIGNING_KEY_ROW))).scalar_one_or_none()
    if row is not None:
        return row.value.encode()
    raw = secrets.token_hex(32)
    db.add(AppMeta(key=SIGNING_KEY_ROW, value=raw))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
    row = (await db.execute(select(AppMeta).where(AppMeta.key == SIGNING_KEY_ROW))).scalar_one_or_none()
    if row is None:
        raise RuntimeError("图像资产签名密钥初始化失败")
    return row.value.encode()


async def ensure_signing_key(db: AsyncSession) -> bytes:
    """写路径/显式刷新用的可重试入口；GET 读取仍只读，不在请求里创建密钥。"""
    try:
        return await init_signing_key(db)
    except Exception as e:  # noqa: BLE001 — 统一收敛成 503
        logger.error("event=image_assets.signing_key_init result=fail error=%s", e)
        raise SigningUnavailable("图像签名密钥不可用") from e


async def _signing_key(db: AsyncSession) -> bytes:
    row = (await db.execute(select(AppMeta).where(AppMeta.key == SIGNING_KEY_ROW))).scalar_one_or_none()
    if row is None:
        # 正常路径由 lifespan 预置；读取端点绝不在这里写库（并发写会撞 PK）。
        raise SigningUnavailable("图像签名密钥未初始化")
    return row.value.encode()


async def initialize_image_assets(db: AsyncSession) -> None:
    try:
        await init_signing_key(db)
    except Exception as e:  # noqa: BLE001 — 图像降级，不阻断写作主链启动
        logger.error("event=image_assets.init result=fail error=%s", e)
    try:
        n = await sweep_expired_assets(db)
        if n:
            logger.info("event=image_assets.sweep deleted=%d user=-", n)
    except Exception as e:  # noqa: BLE001
        logger.error("event=image_assets.sweep result=fail error=%s", e)


def _signature(key: bytes, asset_id: str, variant: str, exp: int) -> str:
    msg = f"{asset_id}:{variant}:{exp}".encode()
    return base64.urlsafe_b64encode(hmac.new(key, msg, hashlib.sha256).digest()).decode().rstrip("=")


def _links_with_key(key: bytes, asset_id: str, exp: int) -> dict:
    return {
        variant: f"/api/image-assets/{asset_id}?variant={variant}&exp={exp}&sig={_signature(key, asset_id, variant, exp)}"
        for variant in VARIANTS
    }


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _exp_iso(exp: int) -> str:
    return datetime.fromtimestamp(exp, UTC).isoformat().replace("+00:00", "Z")


def _asset_ref(asset: ImageAsset, key: bytes, exp: int) -> dict:
    links = _links_with_key(key, asset.id, exp)
    return {
        "asset_id": asset.id,
        "url": links["full"],
        "thumb_url": links["thumb"],
        "links": links,
        "status": asset.status,
        "width": asset.width,
        "height": asset.height,
        "version": asset.version,
        "source": asset.source,
        "style_key": asset.style_key,
        "adopted_at": _iso_utc(asset.adopted_at),
        "url_expires_at": _exp_iso(exp),
    }


async def get_asset_links(db: AsyncSession, user_id: str, asset_id: str) -> dict:
    await _asset_for_user(db, user_id, asset_id)
    key = await ensure_signing_key(db)
    exp = _epoch() + SIGN_TTL_SECONDS
    return {"links": _links_with_key(key, asset_id, exp), "url_expires_at": _exp_iso(exp)}


async def current_cover_refs(
    db: AsyncSession, user_id: str, novel_ids: list[str],
) -> dict[str, dict]:
    if not novel_ids:
        return {}
    rows = (await db.execute(
        select(ImageAsset).where(
            ImageAsset.user_id == user_id,
            ImageAsset.novel_id.in_(novel_ids),
            ImageAsset.kind == "cover",
            ImageAsset.status == "current",
        )
    )).scalars().all()
    if not rows:
        return {}
    try:
        key = await _signing_key(db)
    except SigningUnavailable as e:
        logger.warning("event=image_assets.cover_refs result=degraded error=%s", e)
        return {}
    exp = _epoch() + SIGN_TTL_SECONDS
    return {a.novel_id: _asset_ref(a, key, exp) for a in rows}


async def current_avatar_refs(
    db: AsyncSession, user_id: str, character_ids: list[str],
) -> dict[str, dict]:
    if not character_ids:
        return {}
    rows = (await db.execute(
        select(ImageAsset).where(
            ImageAsset.user_id == user_id,
            ImageAsset.character_id.in_(character_ids),
            ImageAsset.kind == "avatar",
            ImageAsset.status == "current",
        )
    )).scalars().all()
    if not rows:
        return {}
    try:
        key = await _signing_key(db)
    except SigningUnavailable as e:
        logger.warning("event=image_assets.avatar_refs result=degraded error=%s", e)
        return {}
    exp = _epoch() + SIGN_TTL_SECONDS
    return {a.character_id: _asset_ref(a, key, exp) for a in rows}


async def delete_assets_for_novel(db: AsyncSession, user_id: str, novel_id: str) -> int:
    ids = (await db.execute(
        select(ImageAsset.id).where(
            ImageAsset.user_id == user_id, ImageAsset.novel_id == novel_id,
        )
    )).scalars().all()
    await db.execute(delete(BookImageSettings).where(BookImageSettings.novel_id == novel_id))
    char_ids = select(Character.id).where(Character.novel_id == novel_id)
    await db.execute(delete(CharacterImageSettings).where(
        CharacterImageSettings.character_id.in_(char_ids),
    ))
    if not ids:
        await db.flush()
        return 0
    await db.execute(delete(ImageAssetBlob).where(ImageAssetBlob.asset_id.in_(ids)))
    await db.execute(delete(ImageAsset).where(ImageAsset.id.in_(ids)))
    await db.flush()
    return len(ids)


async def delete_assets_for_character(
    db: AsyncSession, novel_id: str, character_id: str, user_id: str | None = None,
) -> int:
    q = select(ImageAsset.id).where(
        ImageAsset.novel_id == novel_id,
        ImageAsset.character_id == character_id,
    )
    if user_id:
        q = q.where(ImageAsset.user_id == user_id)
    ids = (await db.execute(q)).scalars().all()
    if not ids:
        return 0
    await db.execute(delete(ImageAssetBlob).where(ImageAssetBlob.asset_id.in_(ids)))
    await db.execute(delete(ImageAsset).where(ImageAsset.id.in_(ids)))
    await db.execute(delete(CharacterImageSettings).where(
        CharacterImageSettings.character_id == character_id,
    ))
    await db.flush()
    return len(ids)


async def signed_links(db: AsyncSession, asset_id: str) -> dict:
    key = await _signing_key(db)
    exp = _epoch() + SIGN_TTL_SECONDS
    return _links_with_key(key, asset_id, exp)


async def read_blob(db: AsyncSession, asset_id: str, variant: str, exp: int, sig: str) -> bytes:
    if variant not in VARIANTS:
        raise Unprocessable("variant 非法", "invalid_variant")
    if exp < _epoch():
        raise Unprocessable("链接已过期", "link_expired")
    key = await _signing_key(db)
    if not hmac.compare_digest(
        _signature(key, asset_id, variant, exp).encode(), sig.encode(),
    ):
        raise Unprocessable("签名无效", "signature_invalid")
    blob = (await db.execute(select(ImageAssetBlob).where(
        ImageAssetBlob.asset_id == asset_id, ImageAssetBlob.variant == variant))).scalar_one_or_none()
    if not blob:
        raise Unprocessable("资产不存在", "asset_not_found")
    return blob.data


def _asset_dict(asset: ImageAsset, key: bytes, exp: int) -> dict:
    links = _links_with_key(key, asset.id, exp)
    return {
        "asset_id": asset.id,
        "novel_id": asset.novel_id,
        "character_id": asset.character_id,
        "kind": asset.kind,
        "status": asset.status,
        "version": asset.version,
        "sha256": asset.sha256,
        "mime": asset.mime,
        "width": asset.width,
        "height": asset.height,
        "bytes": asset.bytes,
        "source": asset.source,
        "provider": asset.provider,
        "model": asset.model,
        "style_key": asset.style_key,
        "prompt_hash": asset.prompt_hash,
        "prompt_text": asset.prompt_text,
        "negative_prompt": asset.negative_prompt,
        "prompt_template_version": asset.prompt_template_version,
        "seed": asset.seed,
        "created_at": _iso_utc(asset.created_at),
        "adopted_at": _iso_utc(asset.adopted_at),
        "expires_at": _iso_utc(asset.expires_at),
        "undo_expires_at": _iso_utc(asset.undo_expires_at),
        "url": links["full"],
        "thumb_url": links["thumb"],
        "links": links,
        "url_expires_at": _exp_iso(exp),
    }


async def assets_to_dict(db: AsyncSession, assets: list[ImageAsset]) -> list[dict]:
    if not assets:
        return []
    key = await _signing_key(db)
    exp = _epoch() + SIGN_TTL_SECONDS
    return [_asset_dict(asset, key, exp) for asset in assets]


async def asset_to_dict(db: AsyncSession, asset: ImageAsset) -> dict:
    return (await assets_to_dict(db, [asset]))[0]


async def put_character_settings(
    db: AsyncSession, user_id: str, novel_id: str, character_id: str,
    prompt: str, seed: int | None,
) -> dict:
    return await _save_character_settings(
        db, user_id, novel_id, character_id,
        {"avatar_prompt": prompt, "seed": seed}, partial=False,
    )

