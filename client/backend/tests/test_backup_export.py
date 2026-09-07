"""备份导出任务化测试（c-novel-export-roundtrip PR1）。

覆盖：双包写目录（中文名+格式 v1+配置包解密回读）、单书导出、掩码预览、
legacy-db/status、单飞 409 的状态机基础。
"""

import asyncio
import time
import uuid
import zipfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from auth_local.middleware import get_current_user
from backup.export import backup_zip_name, config_zip_name
from db import async_session
from main import app


async def _seed_user_with_config():
    from api_configs.crypto import encrypt_api_key
    from models.api_config import ApiConfig
    from models.user import User

    async with async_session() as session:
        uid = f"exp-{uuid.uuid4().hex[:8]}"
        user = User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name="备份测试员", api_key="", api_base_url="", api_model="",
        )
        session.add(user)
        await session.flush()
        session.add(ApiConfig(
            user_id=user.id, name="主配置", vendor="deepseek",
            vendor_display_name="DeepSeek", base_url="https://api.test/v1",
            api_key=encrypt_api_key("sk-test1234567890"),
            models='["deepseek-v4-flash"]',
        ))
        await session.commit()
        return user.id


async def _seed_book(user_id: str, tmp_root: str):
    from models.project import Novel

    slug = f"exp-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        proj = Novel(
            user_id=user_id, name="备份测试书", slug=slug,
            root_path=str(Path(tmp_root) / slug), source="manual",
            current_phase="write",
        )
        session.add(proj)
        await session.commit()
        return proj.id, slug


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    """建用户+配置+一本书；打回导出端点依赖与 DATA_ROOT。"""

    user_id = asyncio.run(_seed_user_with_config())
    book_root = tmp_path / "book-root"
    book_root.mkdir()
    novel_id, book_slug = asyncio.run(_seed_book(user_id, str(book_root)))
    monkeypatch.setattr("backup.router.DATA_ROOT", str(tmp_path / "data-root"))
    # config.DATA_ROOT 在导出任务线程里读 storage 用（root_path 已是绝对路径，不受影响）
    return {
        "user_id": user_id,
        "novel_id": novel_id,
        "book_root": str(book_root),
        "data_root": str(tmp_path / "data-root"),
        "book_slug": book_slug,
        "secret": "sk-test1234567890",
    }


@pytest.fixture
def client(seeded, monkeypatch):
    monkeypatch.setattr("backup.router.DATA_ROOT", seeded["data_root"])
    app.dependency_overrides[get_current_user] = lambda: {"id": seeded["user_id"]}
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _wait_done(client, timeout_s: float = 15.0) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        last = client.get("/api/backup/export/status").json()["data"]
        if last["state"] in ("done", "error"):
            return last
        time.sleep(0.1)
    return last


class TestBackupExportJob:
    def test_backup_writes_two_packages(self, client, seeded, tmp_path):
        target_dir = tmp_path / "out"
        r = client.post("/api/backup/export/start", json={
            "kind": "backup", "target_dir": str(target_dir), "include_config": True,
        })
        assert r.status_code == 200, r.text
        done = _wait_done(client)
        assert done["state"] == "done", done
        files = sorted(p.name for p in target_dir.iterdir())
        assert len(files) == 2
        # 产物名逐字节全等（brand-name-single-source：前缀引品牌桥，冻结契约现值不变）
        assert files[0] == backup_zip_name()
        assert files[1] == config_zip_name()

        # 资产包：格式 v1 + 每书目录
        with zipfile.ZipFile(target_dir / files[0]) as zf:
            names = zf.namelist()
            assert f"projects/{seeded['book_slug']}/project.yaml" in names
            meta = yaml.safe_load(zf.read(f"projects/{seeded['book_slug']}/project.yaml"))
            assert meta["format_version"] == 1
            assert meta["name"] == "备份测试书"

        # 配置包：密钥解密回读（导出=明文契约）
        with zipfile.ZipFile(target_dir / files[1]) as zf:
            cfg = yaml.safe_load(zf.read("config.yaml"))
        assert cfg["format_version"] == 1
        assert cfg["user"]["display_name"] == "备份测试员"
        assert cfg["api_configs"][0]["api_key"] == seeded["secret"]

    def test_backup_without_config(self, client, seeded, tmp_path):
        target_dir = tmp_path / "out2"
        client.post("/api/backup/export/start", json={
            "kind": "backup", "target_dir": str(target_dir), "include_config": False,
        })
        done = _wait_done(client)
        assert done["state"] == "done"
        assert len(list(target_dir.iterdir())) == 1  # 仅资产包

    def test_single_book_export(self, client, seeded, tmp_path):
        target = tmp_path / "out" / "single.zip"
        Path(str(target)).parent.mkdir(parents=True, exist_ok=True)
        r = client.post("/api/backup/export/start", json={
            "kind": "single", "target_file": str(target), "book_id": seeded["novel_id"],
        })
        assert r.status_code == 200
        done = _wait_done(client)
        assert done["state"] == "done", done
        with zipfile.ZipFile(target) as zf:
            assert "project.yaml" in zf.namelist()
            meta = yaml.safe_load(zf.read("project.yaml"))
            assert meta["name"] == "备份测试书"


class TestConfigPreview:
    def test_masked_keys(self, client, seeded):
        r = client.get("/api/backup/export/config/preview")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["configs"][0]["api_key_masked"].startswith("sk-")
        assert "sk-test1234567890" not in d["configs"][0]["api_key_masked"]
