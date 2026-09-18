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
from backup.format import FORMAT_VERSION
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

        # 资产包：格式 v2（character-settings-v2 升版）+ 每书目录
        with zipfile.ZipFile(target_dir / files[0]) as zf:
            names = zf.namelist()
            assert f"projects/{seeded['book_slug']}/project.yaml" in names
            meta = yaml.safe_load(zf.read(f"projects/{seeded['book_slug']}/project.yaml"))
            assert meta["format_version"] == FORMAT_VERSION
            assert meta["name"] == "备份测试书"

        # 配置包：密钥解密回读（导出=明文契约）
        with zipfile.ZipFile(target_dir / files[1]) as zf:
            cfg = yaml.safe_load(zf.read("config.yaml"))
        assert cfg["format_version"] == FORMAT_VERSION
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


class TestBackupJobSingleFlight:
    """单飞 409 + running_kind（c-manuscript-download tasks 1.3）：

    真正的并发窗口不好稳定造（备份任务太快就 done），用「已注入 running 状态」
    的方式锁定互斥判定与 409 响应契约——这正是抽 job_runner 后的判定入口。
    """

    def test_409_carries_running_kind_backup(self, client, monkeypatch):
        import job_runner

        monkeypatch.setattr(
            job_runner, "_job",
            {"state": "running", "phase": "assets", "kind": "backup", "error": None},
        )
        r = client.post("/api/backup/export/start", json={
            "kind": "backup", "target_dir": "/tmp/whatever", "include_config": False,
        })
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["running_kind"] == "backup"
        assert "备份" in detail["message"]

    def test_409_carries_running_kind_download(self, client, monkeypatch):
        import job_runner

        monkeypatch.setattr(
            job_runner, "_job",
            {"state": "running", "phase": "render", "kind": "download", "error": None},
        )
        r = client.post("/api/backup/export/start", json={
            "kind": "backup", "target_dir": "/tmp/whatever", "include_config": False,
        })
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["running_kind"] == "download"
        assert "下载" in detail["message"]

    def test_idle_after_error_allows_restart(self, client, seeded, tmp_path, monkeypatch):
        import job_runner

        monkeypatch.setattr(
            job_runner, "_job",
            {"state": "error", "phase": "render", "kind": "download",
             "error": {"code": "io_error", "message": "x"}},
        )
        target = tmp_path / "out" / "after-error.zip"
        Path(str(target)).parent.mkdir(parents=True, exist_ok=True)
        r = client.post("/api/backup/export/start", json={
            "kind": "single", "target_file": str(target), "book_id": seeded["novel_id"],
        })
        assert r.status_code == 200
        done = _wait_done(client)
        assert done["state"] == "done", done


# ── 归档段唯一性与完整性（c-backup-archive-dedup，PR #409 评审定位的预存在缺陷）──
# 缺陷：dump_book_into 的书级归档查询与写入误置卷循环内 → N 卷书每条归档写 N 遍。
# 断言纪律（实测钉死）：zip 同名重复条目在 set() 下塌成 1——必须用 namelist list 计数。


async def _seed_book_with_archives(user_id: str, tmp_root: str, vols: int):
    """建 1 本书：vols 卷 × 每卷 1 章（有正文） × 每卷 1 条归档。"""
    from models.archive import Archive
    from models.chapter import Chapter, ChapterContent
    from models.project import Novel
    from models.volume import Volume

    slug = f"arch-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        proj = Novel(
            user_id=user_id, name="归档去重测试书", slug=slug,
            root_path=str(Path(tmp_root) / slug), source="manual",
            current_phase="write",
        )
        session.add(proj)
        await session.flush()
        for vno in range(1, vols + 1):
            vol = Volume(project_id=proj.id, volume_no=vno, title=f"第{vno}卷")
            session.add(vol)
            await session.flush()
            content = f"第{vno}卷归档正文。" * 12
            ch = Chapter(
                project_id=proj.id, volume_id=vol.id, chapter_no=1,
                ref=f"vol-{vno}-ch-1", title=f"第{vno}卷首章", status="archived",
                word_count=len(content), has_prose=True,
            )
            session.add(ch)
            await session.flush()
            session.add(ChapterContent(chapter_id=ch.id, prose=content))
            session.add(Archive(
                chapter_id=ch.id, title=f"第{vno}卷首章", summary=f"第{vno}卷摘要",
                content=content,
            ))
        await session.commit()
        return proj.id, slug


@pytest.fixture
def arch_client_factory(tmp_path, monkeypatch):
    """工厂 fixture：按 vols 建「用户 + vols 卷带归档的书」。

    teardown 必跑（yield 后清 dependency_overrides）——评审 P1：裸 helper 的
    clear() 只在成功路径执行，断言失败即泄漏 get_current_user 覆盖污染后续用例。
    """
    monkeypatch.setattr("backup.router.DATA_ROOT", str(tmp_path / "data-root"))
    book_root = tmp_path / "book-root"
    book_root.mkdir()

    def make(vols: int):
        user_id = asyncio.run(_seed_user_with_config())
        novel_id, slug = asyncio.run(
            _seed_book_with_archives(user_id, str(book_root), vols)
        )
        app.dependency_overrides[get_current_user] = lambda: {"id": user_id}
        return TestClient(app), novel_id, slug

    yield make
    app.dependency_overrides.clear()


def _read_backup_archives(target_dir: Path, slug: str):
    """从整库资产包读归档条目与 manifest（返回值即数据，不留句柄）。"""
    with zipfile.ZipFile(target_dir / backup_zip_name()) as zf:
        arch = [
            n for n in zf.namelist()
            if n.startswith(f"projects/{slug}/archives/") and n.endswith(".md")
        ]
        man = yaml.safe_load(zf.read(f"projects/{slug}/archives/manifest.yaml"))["archives"]
        return arch, man


class TestArchiveDedup:
    def test_multi_volume_archives_unique(self, tmp_path, arch_client_factory):
        """2 卷 × 每卷 1 归档：条目恰 2（修复前 4，必红）、manifest 恰 2 且无重复 filename。

        断言必须用 list 计数（set 会掩盖重复）；manifest 字段集与排序（卷序，全序键）
        一并锁定——排序是 spec 条款，删 order_by 该断言必红。
        """
        client, _novel_id, slug = arch_client_factory(2)
        with client:
            target_dir = tmp_path / "out"
            r = client.post("/api/backup/export/start", json={
                "kind": "backup", "target_dir": str(target_dir), "include_config": False,
            })
            assert r.status_code == 200, r.text
            done = _wait_done(client)
            assert done["state"] == "done", done

            arch, man = _read_backup_archives(target_dir, slug)
            assert len(arch) == 2, f"归档条目应恰 2（namelist 计数）: {arch}"  # 修复前 4
            assert len(set(arch)) == 2
            assert len(man) == 2, f"manifest 应恰 2 条: {man}"
            assert len({m["filename"] for m in man}) == 2
            assert set(man[0]) == {"filename", "ref", "title", "summary", "archived_at"}
            # 排序锁：卷序（ref 兜底，ghost tie 场景亦确定）
            assert [m["ref"] for m in man] == ["vol-1-ch-1", "vol-2-ch-1"], man

    def test_single_volume_bytes_unchanged(self, tmp_path, arch_client_factory):
        """1 卷 1 归档：条目名/内容字节/manifest 字段集不变（对接 spec「单卷书行为不变」）；
        并覆盖 kind=single（单书交付导出，归档段在包根、无 projects/ 前缀）。"""
        client, novel_id, slug = arch_client_factory(1)
        with client:
            target_dir = tmp_path / "out1"
            r = client.post("/api/backup/export/start", json={
                "kind": "backup", "target_dir": str(target_dir), "include_config": False,
            })
            assert r.status_code == 200, r.text
            done = _wait_done(client)
            assert done["state"] == "done", done

            arch, man = _read_backup_archives(target_dir, slug)
            assert len(arch) == 1 and len(man) == 1
            # 条目名 = ref + slug(标题)（_archive_filename 形态，tasks 1.3 逐条对账）
            assert arch[0] == f"projects/{slug}/archives/vol-1-ch-1-第1卷首章.md"
            with zipfile.ZipFile(target_dir / backup_zip_name()) as zf:
                content = zf.read(arch[0]).decode("utf-8")
            assert content == "第1卷归档正文。" * 12
            assert set(man[0]) == {"filename", "ref", "title", "summary", "archived_at"}

            # kind=single：单书交付导出（评审 P2-4——requirement 明写覆盖两种包）
            single = tmp_path / "single" / "book.zip"
            Path(str(single)).parent.mkdir(parents=True, exist_ok=True)
            r2 = client.post("/api/backup/export/start", json={
                "kind": "single", "target_file": str(single), "book_id": novel_id,
            })
            assert r2.status_code == 200, r2.text
            done2 = _wait_done(client)
            assert done2["state"] == "done", done2
            with zipfile.ZipFile(single) as zf:
                s_arch = [n for n in zf.namelist()
                          if n.startswith("archives/") and n.endswith(".md")]
                assert s_arch == ["archives/vol-1-ch-1-第1卷首章.md"]
                s_man = yaml.safe_load(zf.read("archives/manifest.yaml"))["archives"]
                assert len(s_man) == 1 and s_man[0]["ref"] == "vol-1-ch-1"
