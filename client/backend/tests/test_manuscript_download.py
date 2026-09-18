"""成稿下载测试（c-manuscript-download）。

覆盖：内容装配边界（空章跳过 / 重写型与回退型两种旧稿都不进 / 卷章序）、
md/txt/docx 渲染结构与边界、文件名 sanitize、下载任务全链（多格式全成、
单飞 409 running_kind、目录不可写、书归属 404、未知格式 422、失败保留已完成文件）。
"""

import asyncio
import time
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from auth_local.middleware import get_current_user
from db import async_session
from main import app
from manuscript.content import build_manuscript
from manuscript.render import cn_num, render_docx, render_md, render_txt
from manuscript.service import PROBE_NAME, sanitize_filename, strip_artifact_ext
from models.chapter import Chapter, ChapterContent
from models.project import Novel
from models.volume import Volume

# ── 种子 ─────────────────────────────────────────────────────────────────────


async def _seed_user():
    from models.user import User

    async with async_session() as session:
        uid = f"ms-{uuid.uuid4().hex[:8]}"
        session.add(User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name="成稿测试员", api_key="", api_base_url="", api_model="",
        ))
        await session.commit()
        return uid


async def _seed_book(user_id: str, tmp_root: str):
    """两卷五主线章 + 两种旧稿支线（重写型 -r 形态 / 回退型保 ref 形态）。"""
    slug = f"ms-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        proj = Novel(
            user_id=user_id, name="成稿测试书", slug=slug,
            root_path=str(Path(tmp_root) / slug), source="manual",
            current_phase="write",
        )
        session.add(proj)
        await session.flush()

        async def add_vol(no: int, title: str) -> Volume:
            v = Volume(project_id=proj.id, volume_no=no, title=title)
            session.add(v)
            await session.flush()
            return v

        async def add_ch(vol: Volume, ref: str, no: int, title: str,
                         prose: str | None, ghost_of: str | None = None) -> Chapter:
            c = Chapter(
                project_id=proj.id, volume_id=vol.id, chapter_no=no, ref=ref,
                title=title, status="archived" if prose else "outline",
                word_count=len((prose or "").replace(" ", "")),
                has_prose=bool(prose), ghost_of=ghost_of,
            )
            session.add(c)
            await session.flush()
            if prose is not None:
                session.add(ChapterContent(chapter_id=c.id, prose=prose))
            return c

        v1 = await add_vol(1, "星海初航")
        v2 = await add_vol(2, "星群之间")
        await add_ch(v1, "vol-1-ch-1", 1, "锚点", "信标亮起。\n第二段。")
        await add_ch(v1, "vol-1-ch-2", 2, "跃迁", "点火。")
        await add_ch(v1, "vol-1-ch-3", 3, "空章", None)              # 拟定：无正文
        await add_ch(v1, "vol-1-ch-2-r1a2b3c", 2, "跃迁旧稿", "重写型旧稿正文",
                     ghost_of="vol-1-ch-2")                          # 重写型旧稿
        await add_ch(v2, "vol-2-ch-3", 3, "回声", "回声应答。")
        await add_ch(v2, "vol-2-ch-4", 4, "折返", "回退型旧稿正文",
                     ghost_of="vol-2-ch-3")                          # 回退型旧稿（ref 形态不变）
        await session.commit()
        return proj.id


@pytest.fixture
def seeded(tmp_path):
    user_id = asyncio.run(_seed_user())
    book_root = tmp_path / "book-root"
    book_root.mkdir()
    novel_id = asyncio.run(_seed_book(user_id, str(book_root)))
    return {"user_id": user_id, "novel_id": novel_id}


@pytest.fixture
def client(seeded):
    app.dependency_overrides[get_current_user] = lambda: {"id": seeded["user_id"]}
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── 内容装配 ─────────────────────────────────────────────────────────────────


def test_build_manuscript_boundary(seeded):
    async def main():
        async with async_session() as db:
            project = await db.get(Novel, seeded["novel_id"])
            return await build_manuscript(db, project)

    ms = asyncio.run(main())
    # 旧稿两种形态都不进；空章跳过；卷序章序正确
    assert [(v.no, len(v.chapters)) for v in ms.volumes] == [(1, 2), (2, 1)]
    assert [c.title for c in ms.volumes[0].chapters] == ["锚点", "跃迁"]
    assert ms.volumes[1].chapters[0].title == "回声"
    full = render_md(ms)
    assert "重写型旧稿正文" not in full and "回退型旧稿正文" not in full
    assert "信标亮起" in full
    assert ms.chapter_count == 3


# ── 渲染器 ───────────────────────────────────────────────────────────────────


def _mini_ms() -> object:
    from manuscript.content import Manuscript, ManuscriptChapter, ManuscriptVolume

    return Manuscript(title="书名", volumes=[ManuscriptVolume(
        no=1, title="星海初航",
        chapters=[ManuscriptChapter(no=1, title="锚点", prose="第一段\n第二段"),
                  ManuscriptChapter(no=2, title="第三章", prose="带#号和*星号*的段落")],
    )])


def test_render_md_structure():
    text = render_md(_mini_ms())
    assert text.startswith("# 书名\n")
    assert "## 第一卷 · 星海初航" in text
    assert "### 第一章 · 锚点" in text
    assert "### 第二章" in text  # 默认序号形态（「第三章」）按程序序号显示，不重复拼
    assert "带#号和*星号*的段落" in text  # 正文原样，不转义不破坏


def test_render_txt_structure():
    text = render_txt(_mini_ms())
    assert text.splitlines()[0] == "书名"
    assert "◇ 第一卷 · 星海初航" in text
    assert "第一章 · 锚点" in text
    assert "　　第一段" in text  # 缩进段落


def test_render_docx_headings():
    data = render_docx(_mini_ms())
    import io

    import docx as docx_mod

    document = docx_mod.Document(io.BytesIO(data))
    headings = [(p.style.name, p.text) for p in document.paragraphs if p.style.name.startswith("Heading") or p.style.name == "Title"]
    assert ("Title", "书名") in headings
    assert ("Heading 1", "第一卷 · 星海初航") in headings
    assert ("Heading 2", "第一章 · 锚点") in headings
    body = [p.text for p in document.paragraphs if p.style.name == "Normal"]
    assert "第一段" in body and "第二段" in body


def test_docx_output_is_valid_zip_container():
    import io

    data = render_docx(_mini_ms())
    assert zipfile.is_zipfile(io.BytesIO(data))


# ── P3：序号 ≥1000 回退阿拉伯（曾 IndexError 整单硬失败）────────────────────


def test_cn_num_above_999_falls_back_to_arabic():
    assert cn_num(9) == "九"
    assert cn_num(12) == "十二"
    assert cn_num(21) == "二十一"
    assert cn_num(102) == "一百二"
    assert cn_num(999) == "九百九十九"
    assert cn_num(1000) == "1000"
    assert cn_num(1234) == "1234"
    assert cn_num(0) == "0" and cn_num(-3) == "-3"


def test_render_volume_with_1000_chapters_does_not_crash():
    """单卷满千章：修复前 _CN[hundreds] 越界 → md/txt/docx 全格式硬失败。"""
    from manuscript.content import Manuscript, ManuscriptChapter, ManuscriptVolume

    ms = Manuscript(title="长书", volumes=[ManuscriptVolume(
        no=1, title="第一卷",
        chapters=[ManuscriptChapter(no=i, title=f"第{i}章", prose="正文一句。") for i in range(1, 1002)],
    )])
    md = render_md(ms)
    txt = render_txt(ms)
    # 999 及以下走中文数字；≥1000 回退阿拉伯（标题「第1000章」本身是默认序号形态，
    # 不再重复拼名称）
    assert "### 第九百九十九章" in md
    assert "### 第1000章" in md
    assert "### 第1001章" in md
    assert "第1001章" in txt
    assert "第1000章 · 第1000章" not in md
    assert "undefined" not in md
    assert zipfile.is_zipfile(__import__("io").BytesIO(render_docx(ms)))


# ── P3：手输文件名自带产物扩展名不双写 ──────────────────────────────────────


def test_strip_artifact_ext():
    assert strip_artifact_ext("我的小说.md") == "我的小说"
    assert strip_artifact_ext("我的小说.MD") == "我的小说"
    assert strip_artifact_ext("我的小说.docx") == "我的小说"
    assert strip_artifact_ext("我的小说.txt") == "我的小说"
    assert strip_artifact_ext("  我的小说.md  ") == "我的小说"
    assert strip_artifact_ext("我的小说") == "我的小说"
    assert strip_artifact_ext("我的小说.v2") == "我的小说.v2"
    assert strip_artifact_ext(".md") == ""


def test_filename_with_artifact_ext_not_doubled(client, seeded, tmp_path):
    out = tmp_path / "out"
    r = client.post("/api/manuscript/download/start", json={
        "book_id": seeded["novel_id"],
        "target_dir": str(out),
        "filename": "我的稿子.md",
        "formats": ["md", "docx"],
    })
    assert r.status_code == 200, r.text
    data = _wait_done(client)
    assert data["state"] == "done", data
    names = sorted(p.name for p in out.iterdir())
    assert names == ["我的稿子.docx", "我的稿子.md"], names


# ── P3：探针不留残渣、历史残留不致撞名 ──────────────────────────────────────


def test_probe_leaves_no_residue(client, seeded, tmp_path):
    out = tmp_path / "out"
    # 模拟上一次进程被 SIGKILL 留下的固定名残渣（老实现的名字）
    out.mkdir()
    (out / PROBE_NAME).write_text("stale")
    r = _start(client, seeded, tmp_path)
    assert r.status_code == 200, r.text
    assert _wait_done(client)["state"] == "done"
    # 唯一名探针已清理；老残渣不参与（唯一名不会撞上，也不再新增同类文件）
    fresh = [p.name for p in out.iterdir() if p.name.startswith(PROBE_NAME) and p.name != PROBE_NAME]
    assert fresh == []
    assert (out / PROBE_NAME).read_text() == "stale"  # 别人的残渣不越权删


# ── sanitize ────────────────────────────────────────────────────────────────


def test_sanitize_filename():
    assert sanitize_filename('a/b\\c:d*e?f"g<h>i|j') == "abcdefghij"
    assert sanitize_filename("///") == "未命名"
    assert sanitize_filename("x" * 100) == "x" * 60
    assert "/" not in sanitize_filename("第一卷/第二章")


# ── 下载任务全链 ─────────────────────────────────────────────────────────────


def _wait_done(client, timeout_s: float = 15.0) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        last = client.get("/api/manuscript/download/status").json()["data"]
        if last.get("state") in ("done", "error"):
            return last
        time.sleep(0.1)
    return last


def _start(client, seeded, tmp_path, formats=("md", "txt", "docx"), **kw):
    return client.post("/api/manuscript/download/start", json={
        "book_id": seeded["novel_id"],
        "target_dir": str(tmp_path / "out"),
        "filename": "成稿测试书 · 主线全稿",
        "formats": list(formats),
        **kw,
    })


def test_download_all_formats(seeded, client, tmp_path):
    out = tmp_path / "out"
    r = _start(client, seeded, tmp_path)
    assert r.status_code == 200, r.text
    done = _wait_done(client)
    assert done["state"] == "done", done
    assert done["chapter_count"] == 3 and done["word_count"] > 0
    assert done["pct"] == 100
    steps = {s["format"]: s["state"] for s in done["steps"]}
    assert steps == {"md": "完成", "txt": "完成", "docx": "完成"}
    names = sorted(p.name for p in out.iterdir())
    assert names == ["成稿测试书 · 主线全稿.docx", "成稿测试书 · 主线全稿.md", "成稿测试书 · 主线全稿.txt"]
    assert "信标亮起" in (out / "成稿测试书 · 主线全稿.md").read_text(encoding="utf-8")
    # 完成态弹层读回：status 保留 done 快照
    again = client.get("/api/manuscript/download/status").json()["data"]
    assert again["state"] == "done" and again["files"]


def test_download_singleflight_conflict_with_running_download(seeded, client, tmp_path, monkeypatch):
    import job_runner

    monkeypatch.setattr(
        job_runner, "_job",
        {"state": "running", "phase": "render", "kind": "download", "error": None},
    )
    r = _start(client, seeded, tmp_path)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["running_kind"] == "download"
    assert "下载" in detail["message"]


def test_download_conflict_with_running_backup(seeded, client, tmp_path, monkeypatch):
    import job_runner

    monkeypatch.setattr(
        job_runner, "_job",
        {"state": "running", "phase": "assets", "kind": "backup", "error": None},
    )
    r = _start(client, seeded, tmp_path)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["running_kind"] == "backup"
    assert "备份" in detail["message"]


def test_download_target_dir_is_file_errors(seeded, client, tmp_path):
    """目标路径是文件 → 目录探针失败，错误归因到路径且不产文件。"""
    blocker_file = tmp_path / "file-blocker"
    blocker_file.write_text("x")
    r = client.post("/api/manuscript/download/start", json={
        "book_id": seeded["novel_id"],
        "target_dir": str(blocker_file / "sub"),  # 文件路径当目录 → NotADirectoryError
        "filename": "x", "formats": ["md"],
    })
    assert r.status_code == 200
    done = _wait_done(client)
    assert done["state"] == "error", done
    assert done["error"]["code"] in ("invalid_path", "permission_denied")
    assert "file-blocker" in done["error"]["message"]


def test_download_book_not_owned_404(seeded, client, tmp_path):
    r = client.post("/api/manuscript/download/start", json={
        "book_id": "nonexistent-id", "target_dir": str(tmp_path / "out"),
        "filename": "x", "formats": ["md"],
    })
    assert r.status_code == 404


def test_download_unknown_format_422(seeded, client, tmp_path):
    r = _start(client, seeded, tmp_path, formats=("pdf",))
    assert r.status_code == 422


def test_download_format_case_normalized(seeded, client, tmp_path):
    """大写/混写格式按白名单小写归一（未命中白名单的才 422）。"""
    out = tmp_path / "out-case"
    r = client.post("/api/manuscript/download/start", json={
        "book_id": seeded["novel_id"], "target_dir": str(out),
        "filename": "x", "formats": ["MD", "Docx"],
    })
    assert r.status_code == 200, r.text
    done = _wait_done(client)
    assert done["state"] == "done", done
    assert done["files"] == ["x.md", "x.docx"]


def test_status_kind_filter_non_download_reads_idle(seeded, client, monkeypatch):
    """/manuscript/download/status 只关心下载：backup 任务在跑/完成时按 idle 口径返回。"""
    import job_runner

    client.get("/api/manuscript/download/status")  # 端点可达性
    for state in ("running", "done"):
        monkeypatch.setattr(
            job_runner, "_job",
            {"state": state, "phase": "assets", "kind": "backup", "error": None},
        )
        data = client.get("/api/manuscript/download/status").json()["data"]
        assert data == {"state": "idle"}


def test_run_thread_survives_base_exception(monkeypatch):
    """CancelledError/SystemExit 穿透 except Exception 时也必须落 error——
    否则单飞槽永久卡 running（备份/下载全锁死，只能重启应用）。"""
    import job_runner

    def _body():
        raise asyncio.CancelledError()

    job_runner.run_thread(_body)
    st = job_runner.status()
    assert st["state"] == "error", st
    assert st["error"]["code"] == "cancelled"
    # 槽位可复用：error 态不挡新任务
    assert job_runner.start("download", lambda p, u: None, "u") is not None
    job_runner.set_job(state="idle")


def test_download_render_failure_keeps_done_files(seeded, client, tmp_path, monkeypatch):
    from manuscript import service

    monkeypatch.setitem(
        service.FORMATS["docx"], "render", lambda m: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    # docx 渲染器惰性 import 后走 render_docx；直接替换 FORMATS 里的 lambda
    r = _start(client, seeded, tmp_path)
    assert r.status_code == 200
    done = _wait_done(client)
    assert done["state"] == "error", done
    states = {s["format"]: s["state"] for s in done["steps"]}
    assert states["md"] == "完成" and states["txt"] == "完成" and states["docx"] == "失败"
    out = tmp_path / "out"
    # 已完成的 md/txt 保留；docx 的 part 已清理
    assert (out / "成稿测试书 · 主线全稿.md").exists()
    assert not list(out.glob("*.part"))
