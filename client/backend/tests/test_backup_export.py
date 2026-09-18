"""备份导出任务化测试（c-novel-export-roundtrip PR1）。

覆盖：双包写目录（中文名+格式 v1+配置包解密回读）、单书导出、掩码预览、
legacy-db/status、单飞 409 的状态机基础。
"""

import asyncio
import io
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
from models.chapter import Chapter


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


async def _seed_book_with_archive_title(user_id: str, tmp_root: str, title: str):
    """1 卷 × 1 章 × 1 归档，归档/章标题为指定值（危险字符用例）。"""
    from models.archive import Archive
    from models.chapter import Chapter, ChapterContent
    from models.project import Novel
    from models.volume import Volume

    slug = f"dng-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        proj = Novel(
            user_id=user_id, name="危险标题书", slug=slug,
            root_path=str(Path(tmp_root) / slug), source="manual", current_phase="write",
        )
        session.add(proj)
        await session.flush()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        content = "危险标题归档正文。" * 10
        ch = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1, ref="vol-1-ch-1",
            title=title, status="archived", word_count=len(content), has_prose=True,
        )
        session.add(ch)
        await session.flush()
        session.add(ChapterContent(chapter_id=ch.id, prose=content))
        session.add(Archive(chapter_id=ch.id, title=title, summary="摘要", content=content))
        await session.commit()
        return proj.id, slug


def _arch_client_with_title(tmp_path, monkeypatch, title: str):
    user_id = asyncio.run(_seed_user_with_config())
    book_root = tmp_path / "book-root"
    book_root.mkdir()
    novel_id, slug = asyncio.run(_seed_book_with_archive_title(user_id, str(book_root), title))
    monkeypatch.setattr("backup.router.DATA_ROOT", str(tmp_path / "data-root"))
    app.dependency_overrides[get_current_user] = lambda: {"id": user_id}
    return TestClient(app), novel_id, slug


# ── c-archive-filename-safety：危险标题的书导出包条目名安全（评审四行实证的端到端面）──


async def _seed_book_with_archive_title(user_id: str, tmp_root: str, title: str):
    """1 卷 × 1 章 × 1 归档，归档/章标题为指定值（危险字符用例）。"""
    from models.archive import Archive
    from models.chapter import Chapter, ChapterContent
    from models.project import Novel
    from models.volume import Volume

    slug = f"dng-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        proj = Novel(
            user_id=user_id, name="危险标题书", slug=slug,
            root_path=str(Path(tmp_root) / slug), source="manual", current_phase="write",
        )
        session.add(proj)
        await session.flush()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        content = "危险标题归档正文。" * 10
        ch = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1, ref="vol-1-ch-1",
            title=title, status="archived", word_count=len(content), has_prose=True,
        )
        session.add(ch)
        await session.flush()
        session.add(ChapterContent(chapter_id=ch.id, prose=content))
        session.add(Archive(chapter_id=ch.id, title=title, summary="摘要", content=content))
        await session.commit()
        return proj.id, slug


@pytest.fixture
def title_client_factory(tmp_path, monkeypatch):
    """工厂 fixture（teardown 必跑）：按标题建书并返回 TestClient。"""
    monkeypatch.setattr("backup.router.DATA_ROOT", str(tmp_path / "data-root"))
    book_root = tmp_path / "book-root"
    book_root.mkdir()

    def make(title: str):
        user_id = asyncio.run(_seed_user_with_config())
        novel_id, slug = asyncio.run(
            _seed_book_with_archive_title(user_id, str(book_root), title)
        )
        app.dependency_overrides[get_current_user] = lambda: {"id": user_id}
        return TestClient(app), novel_id, slug

    yield make
    app.dependency_overrides.clear()


class TestArchiveFilenameSafety:
    def test_dangerous_title_export_safe_and_roundtrip(self, tmp_path, title_client_factory):
        """标题 `上/../下`：修复前条目含 `..` 路径段 → 导入端 validate_paths 拒 → 整包不可导入。

        覆盖：包内条目名安全（无分隔符/无 `..` 段与子串）+ validate_paths 实调 +
        解析器自洽 + 导入后 title == 完整条目名 stem（不再被分隔符截断为尾段）。
        """
        from backup.importer import _import_single_book, validate_paths

        client, _novel_id, slug = title_client_factory("上/../下")
        with client:
            target_dir = tmp_path / "out-safe"
            r = client.post("/api/backup/export/start", json={
                "kind": "backup", "target_dir": str(target_dir), "include_config": False,
            })
            assert r.status_code == 200, r.text
            done = _wait_done(client)
            assert done["state"] == "done", done

            exported_name = None
            with zipfile.ZipFile(target_dir / backup_zip_name()) as zf:
                arch = [n for n in zf.namelist()
                        if n.startswith(f"projects/{slug}/archives/") and n.endswith(".md")]
                assert len(arch) == 1, arch
                exported_name = arch[0]
                rel = exported_name[len(f"projects/{slug}/archives/"):]
                assert "/" not in rel and "\\" not in rel, exported_name
                assert ".." not in exported_name, exported_name
                assert ".." not in Path(exported_name).parts, exported_name
                validate_paths(zf)  # 修复前：路径段含 `..` → ValueError

                from archive.naming import parse_archive_filename

                assert parse_archive_filename(Path(exported_name).name) is not None

            # 导入空库：title == 完整条目名 stem（既有语义），修复前被 "/" 截断为「下」
            blob = (target_dir / backup_zip_name()).read_bytes()

            async def restore_one():
                async with async_session() as db:
                    new_id = await _import_single_book(
                        db, zipfile.ZipFile(io.BytesIO(blob)),
                        f"projects/{slug}/", "safe-title-user",
                    )
                    await db.commit()
                    from sqlalchemy import select as sa_select

                    from models.archive import Archive as ArchiveRow

                    rows = (await db.scalars(
                        sa_select(ArchiveRow.title).join(
                            Chapter, Chapter.id == ArchiveRow.chapter_id
                        ).where(Chapter.project_id == new_id)
                    )).all()
                    return list(rows)

            titles = asyncio.run(restore_one())
            assert len(titles) == 1, titles
            assert titles[0] == Path(exported_name).stem, titles


# ── c-backup-characters-prefix：整库包每书角色段各归其位 ──────────────────────────


async def _seed_book_with_characters(user_id: str, tmp_root: str, names: list[str]):
    """建 1 本书：1 卷 × 1 章 + names 指定角色（≥2 名时补一条关系，覆盖关系段隔离）。"""
    from models.chapter import Chapter
    from models.character import Character, CharacterRelation
    from models.project import Novel
    from models.volume import Volume

    slug = f"chr-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        proj = Novel(
            user_id=user_id, name=f"角色书-{slug[-4:]}", slug=slug,
            root_path=str(Path(tmp_root) / slug), source="manual", current_phase="write",
        )
        session.add(proj)
        await session.flush()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        session.add(Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1, ref="vol-1-ch-1",
            title="第一章", status="outline", word_count=0, has_prose=False,
        ))
        chars = []
        for i, nm in enumerate(names, start=1):
            c = Character(
                novel_id=proj.id, seq=i, name=nm, aliases="[]",
                role="主角" if i == 1 else "配角", persona=f"{nm}的一句话",
                dossier="{}", cog="{}", legacy="{}",
            )
            session.add(c)
            chars.append(c)
        await session.flush()
        if len(chars) >= 2:
            session.add(CharacterRelation(
                novel_id=proj.id, owner_id=chars[0].id, other_id=chars[1].id,
                rel_type="盟友", stance="信任",
            ))
        await session.commit()
        return proj.id, slug


@pytest.fixture
def chars_client_factory(tmp_path, monkeypatch):
    """工厂 fixture（teardown 必跑）：建多本各有角色的书。"""
    monkeypatch.setattr("backup.router.DATA_ROOT", str(tmp_path / "data-root"))
    book_root = tmp_path / "book-root"
    book_root.mkdir()

    def make(books: list[list[str]]):
        user_id = asyncio.run(_seed_user_with_config())
        out = []
        for names in books:
            nid, slug = asyncio.run(
                _seed_book_with_characters(user_id, str(book_root), names)
            )
            out.append((nid, slug, names))
        app.dependency_overrides[get_current_user] = lambda: {"id": user_id}
        return TestClient(app), user_id, out

    yield make
    app.dependency_overrides.clear()


class TestCharactersPrefix:
    def test_two_books_characters_own_prefix(self, tmp_path, chars_client_factory):
        """两书各有角色：各自 projects/{slug}/characters/ 均在且内容互异；包根无 characters/。"""
        client, _uid, books = chars_client_factory([["甲", "乙"], ["丙"]])
        target_dir = tmp_path / "out-chr"
        r = client.post("/api/backup/export/start", json={
            "kind": "backup", "target_dir": str(target_dir), "include_config": False,
        })
        assert r.status_code == 200, r.text
        assert _wait_done(client)["state"] == "done"

        with zipfile.ZipFile(target_dir / backup_zip_name()) as zf:
            names = zf.namelist()
            for _nid, slug, _nm in books:
                assert f"projects/{slug}/characters/characters.yaml" in names, names
                assert f"projects/{slug}/characters/relations.yaml" in names, names
            # 包根不得出现 characters/（namelist list 计数——zip 保留重复条目，set 会掩盖）
            assert [n for n in names if n.startswith("characters/")] == []
            # 两书内容互异
            a = zf.read(f"projects/{books[0][1]}/characters/characters.yaml")
            b = zf.read(f"projects/{books[1][1]}/characters/characters.yaml")
            assert a != b

    def test_two_books_characters_roundtrip_per_book(self, tmp_path, chars_client_factory):
        """整库包逐书导入：姓名集合与关系集合逐书对拍（防「最后一本发给每本书」）。"""
        from sqlalchemy import select as sa_select

        from backup.importer import _import_single_book
        from models.character import Character, CharacterRelation

        client, uid, books = chars_client_factory([["甲", "乙"], ["丙"]])
        target_dir = tmp_path / "out-rt"
        r = client.post("/api/backup/export/start", json={
            "kind": "backup", "target_dir": str(target_dir), "include_config": False,
        })
        assert r.status_code == 200, r.text
        assert _wait_done(client)["state"] == "done"

        blob = (target_dir / backup_zip_name()).read_bytes()

        async def restore_all():
            results = {}
            for _nid, slug, expected in books:
                async with async_session() as db:
                    new_id = await _import_single_book(
                        db, zipfile.ZipFile(io.BytesIO(blob)), f"projects/{slug}/", uid
                    )
                    await db.commit()
                    got = set((await db.scalars(
                        sa_select(Character.name).where(Character.novel_id == new_id)
                    )).all())
                    rels = set((await db.scalars(
                        sa_select(CharacterRelation.rel_type).join(
                            Character, Character.id == CharacterRelation.owner_id
                        ).where(Character.novel_id == new_id)
                    )).all())
                    chapters = len((await db.scalars(
                        sa_select(Chapter.id).where(Chapter.project_id == new_id)
                    )).all())
                    results[slug] = (got, set(expected), rels, chapters)
            return results

        results = asyncio.run(restore_all())
        for slug, (got, expected, rels, chapters) in results.items():
            assert got == expected, f"{slug}: {got} != {expected}"
            # 正向对照：书确实落库（负向/隔离结论不建立在空跑上）
            assert chapters >= 1, f"{slug}: chapters={chapters}"
            # 关系段逐书隔离：books[0] 种 1 条盟友、books[1] 无；串书/漏段必红
            assert rels == ({"盟友"} if expected == {"甲", "乙"} else set()), f"{slug}: {rels}"

    def test_legacy_root_characters_not_fallback(self, tmp_path, chars_client_factory):
        """负向锁定（Non-Goal）：角色仅存包根的旧形态包 → 导入后每书角色为 0，不回退包根取值。"""
        from sqlalchemy import select as sa_select

        from backup.importer import _import_single_book
        from models.character import Character

        client, uid, books = chars_client_factory([["甲"], ["丙"]])
        target_dir = tmp_path / "out-legacy"
        client.post("/api/backup/export/start", json={
            "kind": "backup", "target_dir": str(target_dir), "include_config": False,
        })
        assert _wait_done(client)["state"] == "done"

        with zipfile.ZipFile(target_dir / backup_zip_name()) as src:
            legacy = io.BytesIO()
            with zipfile.ZipFile(legacy, "w") as out:
                for n in src.namelist():
                    if "/characters/" in n:
                        continue
                    out.writestr(n, src.read(n))
                out.writestr(
                    "characters/characters.yaml",
                    src.read(f"projects/{books[1][1]}/characters/characters.yaml"),
                )
        legacy_bytes = legacy.getvalue()

        async def restore_each():
            out = {}
            for _nid, slug, _nm in books:
                async with async_session() as db:
                    new_id = await _import_single_book(
                        db, zipfile.ZipFile(io.BytesIO(legacy_bytes)),
                        f"projects/{slug}/", uid,
                    )
                    await db.commit()
                    got = set((await db.scalars(
                        sa_select(Character.name).where(Character.novel_id == new_id)
                    )).all())
                    chapters = len((await db.scalars(
                        sa_select(Chapter.id).where(Chapter.project_id == new_id)
                    )).all())
                    out[slug] = (got, chapters)
            return out

        counts = asyncio.run(restore_each())
        for slug, (got, chapters) in counts.items():
            assert got == set(), f"{slug}: 旧包不回退包根取值，应 0 角色，实得 {got}"
            # 正向对照：书确实落库（负向结论不建立在空跑上）
            assert chapters >= 1, f"{slug}: chapters={chapters}"
