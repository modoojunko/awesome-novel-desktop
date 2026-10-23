"""v7 图像备份 roundtrip：current 资产 + full/thumb + 书/角色设置 + 图像配置。"""

import asyncio
import io
import uuid
import zipfile

import yaml
from PIL import Image
from sqlalchemy import select

from api_configs.crypto import decrypt_api_key, encrypt_api_key
from backup.export import build_config_package_bytes, dump_book_into
from backup.format import FORMAT_VERSION
from backup.importer import _import_images, _restore_config, persist_package
from db import async_session
from models.character import Character
from models.image_asset import (
    BookImageSettings,
    CharacterImageSettings,
    ImageAsset,
    ImageAssetBlob,
    ImageConfig,
)
from models.project import Novel
from models.user import User


def _webp(color):
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buf, format="WEBP")
    return buf.getvalue()


def _run(coro):
    return asyncio.run(coro)


def test_image_backup_roundtrip(tmp_path):
    suffix = uuid.uuid4().hex[:8]
    uid = f"imgbk-{suffix}"
    uid2 = f"imgbk2-{suffix}"
    uid3 = f"imgbk3-{suffix}"

    async def _seed():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="图备份"))
            db.add(User(id=uid2, email=f"{uid2}@t.local", password_hash="x", display_name="图恢复"))
            db.add(User(id=uid3, email=f"{uid3}@t.local", password_hash="x", display_name="图整包恢复"))
            await db.flush()
            novel = Novel(
                id=f"novel-{suffix}", user_id=uid, name="图备份书",
                slug=f"imgbk-{suffix}", root_path=str(tmp_path / "book"),
            )
            db.add(novel)
            await db.flush()
            ch = Character(id=f"char-{suffix}", novel_id=novel.id, seq=1, name="阿灯", role="主角")
            db.add(ch)
            cfg = ImageConfig(
                id=f"cfg-{suffix}", user_id=uid, name=f"图配置-{suffix}",
                provider="volcengine", base_url="https://ark.test/api/v3",
                api_key=encrypt_api_key("sk-image-secret"),
                default_model="doubao-seedream-4-0-250828",
                models='["doubao-seedream-4-0-250828"]',
                is_default=True,
            )
            db.add(cfg)
            await db.flush()
            db.add(BookImageSettings(
                novel_id=novel.id, style_key="ink", cover_prompt="一盏旧灯",
                cover_seed=321, image_config_id=cfg.id,
                image_model="doubao-seedream-4-0-250828",
            ))
            db.add(CharacterImageSettings(
                character_id=ch.id, avatar_prompt="瘦高的守灯人", seed=654,
            ))
            full = _webp((20, 50, 80))
            thumb = _webp((30, 60, 90))
            for kind, char_id in (("cover", None), ("avatar", ch.id)):
                asset = ImageAsset(
                    id=f"{kind}-{suffix}", user_id=uid, novel_id=novel.id,
                    character_id=char_id, kind=kind, status="current", version=2,
                    sha256="", mime="image/webp", width=768 if kind == "cover" else 512,
                    height=1024 if kind == "cover" else 512, bytes=len(full),
                    source="upload", style_key="ink", prompt_hash="h", prompt_text="p",
                    negative_prompt="n", prompt_template_version=3, seed=9,
                )
                import hashlib
                asset.sha256 = hashlib.sha256(full).hexdigest()
                db.add(asset)
                await db.flush()
                db.add(ImageAssetBlob(asset_id=asset.id, variant="full", data=full))
                db.add(ImageAssetBlob(asset_id=asset.id, variant="thumb", data=thumb))
            await db.commit()
            return novel.id, ch.id, cfg.id

    novel_id, char_id, _cfg_id = _run(_seed())
    assert FORMAT_VERSION == 7

    async def _export():
        async with async_session() as db:
            project = await db.get(Novel, novel_id)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                await dump_book_into(zf, db, project, prefix="")
            data = buf.getvalue()
            config_bytes, _ = await build_config_package_bytes(db, uid)
            return data, config_bytes

    zip_bytes, config_bytes = _run(_export())
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        manifest = yaml.safe_load(zf.read("images/manifest.yaml"))
        assert manifest["book"]["cover_seed"] == 321
        assert manifest["book"]["image_config_name"] == f"图配置-{suffix}"
        assert len(manifest["assets"]) == 2
        assert all(a["asset_id"] in " ".join(names) for a in manifest["assets"])
        assert "images/cover-" + suffix + "-full.webp" in names

    with zipfile.ZipFile(io.BytesIO(config_bytes)) as zf:
        cfg = yaml.safe_load(zf.read("config.yaml"))
        image_cfg = cfg["image_configs"][0]
        assert image_cfg["api_key"] == "sk-image-secret"

    async def _import():
        async with async_session() as db:
            novel2 = Novel(
                id=f"novel2-{suffix}", user_id=uid2, name="图恢复书",
                slug=f"imgbk2-{suffix}", root_path=str(tmp_path / "book2"),
            )
            db.add(novel2)
            await db.flush()
            ch2 = Character(id=f"char2-{suffix}", novel_id=novel2.id, seq=1, name="阿灯", role="主角")
            db.add(ch2)
            await db.flush()
            warnings: list[str] = []
            await _restore_config(db, uid2, cfg)
            await db.flush()
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                await _import_images(
                    db, zf, set(zf.namelist()), "", novel2, uid2,
                    {char_id: ch2.id}, warnings,
                )
            await db.commit()
            bs = await db.get(BookImageSettings, novel2.id)
            cs = await db.get(CharacterImageSettings, ch2.id)
            assets = (await db.scalars(select(ImageAsset).where(
                ImageAsset.novel_id == novel2.id
            ))).all()
            blobs = (await db.scalars(select(ImageAssetBlob).where(
                ImageAssetBlob.asset_id.in_([a.id for a in assets])
            ))).all()
            restored_cfg = (await db.scalars(select(ImageConfig).where(
                ImageConfig.user_id == uid2,
                ImageConfig.name == f"图配置-{suffix}",
            ))).one()
            return bs, cs, assets, blobs, restored_cfg, warnings

    bs, cs, assets, blobs, restored_cfg, warnings = _run(_import())
    assert warnings == []
    assert bs.style_key == "ink" and bs.cover_seed == 321
    assert bs.cover_prompt == "一盏旧灯"
    assert cs.avatar_prompt == "瘦高的守灯人" and cs.seed == 654
    assert {a.kind for a in assets} == {"cover", "avatar"}
    assert all(a.status == "current" for a in assets)
    assert len(blobs) == 4
    assert decrypt_api_key(restored_cfg.api_key) == "sk-image-secret"

    # 整包路径：single.zip + config.zip 走 persist_package（真实导入入口）
    single_path = tmp_path / "single.zip"
    config_path = tmp_path / "config.zip"
    single_path.write_bytes(zip_bytes)
    config_path.write_bytes(config_bytes)

    async def _full_import():
        async with async_session() as db:
            await persist_package(
                db, uid3, [str(single_path), str(config_path)], include_config=True,
            )
            novel3 = (await db.scalars(select(Novel).where(Novel.user_id == uid3))).one()
            bs3 = await db.get(BookImageSettings, novel3.id)
            assets3 = (await db.scalars(select(ImageAsset).where(
                ImageAsset.novel_id == novel3.id
            ))).all()
            blobs3 = (await db.scalars(select(ImageAssetBlob).where(
                ImageAssetBlob.asset_id.in_([a.id for a in assets3])
            ))).all()
            cfg3 = (await db.scalars(select(ImageConfig).where(
                ImageConfig.user_id == uid3,
                ImageConfig.name == f"图配置-{suffix}",
            ))).one()
            return bs3, assets3, blobs3, cfg3

    bs3, assets3, blobs3, cfg3 = _run(_full_import())
    assert bs3.cover_seed == 321 and bs3.cover_prompt == "一盏旧灯"
    assert bs3.image_config_id == cfg3.id
    assert {a.kind for a in assets3} == {"cover", "avatar"}
    assert len(blobs3) == 4
    assert decrypt_api_key(cfg3.api_key) == "sk-image-secret"
