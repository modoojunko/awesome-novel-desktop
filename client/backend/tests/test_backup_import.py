"""备份导入测试（c-novel-backup-import-f821-fix）。

覆盖：配置包恢复（_restore_config——user 只补空、api_configs 同名跳过不覆盖、
密钥重加密落库）+ 含版本快照的书包导入（ChapterVersion 落库，F821 回归锚）。
"""

import asyncio
import io
import uuid
import zipfile

import yaml
from sqlalchemy import select

from backup.format import FORMAT_VERSION
from backup.importer import _import_single_book, _restore_config
from db import async_session


def _write_temp_zip(data: bytes) -> str:
    """zip 字节落盘为临时文件（parse_package/persist_package 吃路径）。"""
    import os
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(data)
    return path


def _config_payload():
    """与 export 侧 build_config_package_bytes 的 config.yaml 同构。"""
    return {
        "user": {
            "display_name": "导入昵称",
            "api_key": "legacy-xyz",
            "api_base_url": "https://legacy.example",
            "api_model": "deepseek-v4-flash",
        },
        "api_configs": [
            {"name": "常用", "vendor": "deepseek", "vendor_display_name": "DeepSeek",
             "vendor_override": None, "api_key": "sk-plain-1",
             "base_url": "https://api.deepseek.com/v1",
             "models": '["deepseek-v4-flash"]',
             "models_updated_at": "2026-09-05T00:00:00",
             "created_at": "2026-09-05T00:00:00"},
            {"name": "备胎", "vendor": "openai-compat", "vendor_display_name": "",
             "vendor_override": None, "api_key": "sk-plain-2",
             "base_url": "https://b.example", "models": None,
             "models_updated_at": None, "created_at": None},
        ],
    }


async def _seed_user(display_name: str = "", api_model: str = "") -> str:
    from models.user import User

    async with async_session() as session:
        uid = f"imp-{uuid.uuid4().hex[:8]}"
        session.add(User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name=display_name, api_key="", api_base_url="", api_model=api_model,
        ))
        await session.commit()
        return uid


class TestRestoreConfig:
    def test_creates_configs_and_fills_empty_user_fields(self):
        async def run():
            from models.user import User
            async with async_session() as session:
                uid = await _seed_user()
                summary = await _restore_config(session, uid, _config_payload())
                await session.commit()
                user = await session.get(User, uid)
                return summary, user, uid

        summary, user, _uid = asyncio.run(run())
        assert summary["created"] == 2 and summary["skipped"] == 0
        assert user.display_name == "导入昵称"
        assert user.api_key == "legacy-xyz"
        assert user.api_base_url == "https://legacy.example"
        assert user.api_model == "deepseek-v4-flash"
        assert sorted(summary["user_filled"]) == [
            "api_base_url", "api_key", "api_model", "display_name",
        ]

    def test_keys_reencrypted_in_db(self):
        async def run():
            from models.api_config import ApiConfig
            async with async_session() as session:
                uid = await _seed_user()
                await _restore_config(session, uid, _config_payload())
                await session.commit()
                rows = (await session.scalars(
                    select(ApiConfig).where(ApiConfig.user_id == uid)
                )).all()
                return {r.name: r for r in rows}

        rows = asyncio.run(run())
        from api_configs.crypto import decrypt_api_key
        assert decrypt_api_key(rows["常用"].api_key) == "sk-plain-1"
        assert decrypt_api_key(rows["备胎"].api_key) == "sk-plain-2"
        # 落库为密文：与明文不同、且可解密回原文
        assert rows["常用"].api_key != "sk-plain-1"

    def test_same_name_skipped_not_overwritten(self):
        async def run():
            from api_configs.crypto import encrypt_api_key
            from models.api_config import ApiConfig
            async with async_session() as session:
                uid = await _seed_user()
                session.add(ApiConfig(
                    user_id=uid, name="常用", vendor="deepseek",
                    api_key=encrypt_api_key("sk-original"),
                    models='["x"]',
                ))
                await session.commit()
                summary = await _restore_config(session, uid, _config_payload())
                await session.commit()
                rows = (await session.scalars(
                    select(ApiConfig).where(ApiConfig.user_id == uid)
                )).all()
                return summary, rows

        summary, rows = asyncio.run(run())
        assert summary["created"] == 1 and summary["skipped"] == 1
        by_name = {r.name: r for r in rows}
        assert len(by_name) == 2  # 原有 + 新建「备胎」，无覆盖
        from api_configs.crypto import decrypt_api_key
        assert decrypt_api_key(by_name["常用"].api_key) == "sk-original"

    def test_empty_config_data_noop(self):
        async def run():
            from models.user import User
            async with async_session() as session:
                uid = await _seed_user(display_name="已有昵称")
                summary = await _restore_config(session, uid, {})
                await session.commit()
                user = await session.get(User, uid)
                return summary, user

        summary, user = asyncio.run(run())
        assert summary == {"created": 0, "skipped": 0, "user_filled": []}
        assert user.display_name == "已有昵称"


class TestVersionSnapshotImport:
    def _book_zip(self) -> bytes:
        """最小单书包：project.yaml + 章 + 版本快照（触发 ChapterVersion 路径）。"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project.yaml", yaml.safe_dump({
                "name": "版本快照测试书", "slug": f"vsnap-{uuid.uuid4().hex[:6]}",
                "current_phase": "write",
            }))
            zf.writestr("volumes/vol-1.yaml", yaml.safe_dump({
                "volume": 1, "title": "第一卷",
            }))
            zf.writestr("chapters/ch-1.yaml", yaml.safe_dump({
                "volume": 1, "title": "第一章", "prose": "正文内容。",
                "status": "done",
            }))
            zf.writestr("versions/ch-1/v1.json", '{"note": "快照原文"}')
        return buf.getvalue()

    def test_version_snapshot_rows_created(self):
        async def run():
            from models.chapter import Chapter, ChapterVersion
            from models.user import User
            async with async_session() as session:
                uid = f"vsnap-{uuid.uuid4().hex[:8]}"
                session.add(User(
                    id=uid, email=f"{uid}@test.local", password_hash="x",
                ))
                await session.commit()
                zf = zipfile.ZipFile(io.BytesIO(self._book_zip()))
                # 注：book_dir="/" 前缀与单书包根路径文件不匹配是引擎既有问题（不在本变更范围），
                # 此处用空 book_dir 验证引擎主体逻辑
                novel_id = await _import_single_book(session, zf, "", uid)
                await session.commit()
                chs = (await session.scalars(
                    select(Chapter).where(Chapter.project_id == novel_id)
                )).all()
                assert len(chs) == 1
                vs = (await session.scalars(
                    select(ChapterVersion).where(ChapterVersion.chapter_id == chs[0].id)
                )).all()
                return chs[0], vs

        ch, vs = asyncio.run(run())
        assert len(vs) == 1
        assert vs[0].version == 1
        assert vs[0].snapshot == '{"note": "快照原文"}'
        assert ch.title == "第一章"


def test_format_version_above_supported_rejected():
    """格式契约演进：format_version > FORMAT_VERSION 拒绝并提示升级（防新格式包被旧应用半恢复）。"""
    import asyncio
    import os

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("backup.yaml", yaml.safe_dump({
            "format_version": FORMAT_VERSION + 1,
            "books": [],
        }))
    from backup.importer import parse_package

    async def run():
        path = _write_temp_zip(buf.getvalue())
        try:
            return await parse_package([path])
        finally:
            os.remove(path)

    try:
        asyncio.run(run())
        raise AssertionError("v2 包应被拒绝")
    except ValueError as e:
        assert "升级" in str(e)
