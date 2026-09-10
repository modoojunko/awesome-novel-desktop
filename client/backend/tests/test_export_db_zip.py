"""导出端点 DB 打包测试（PR⑤ 大扫除）。

全量入库后 zip 内容全部由 DB 组装：project.json 元数据 + settings KV →
yaml 树 + 卷纲 + 章纲/正文 + 版本快照 + 归档 md + 生成提示词 md。
盘上项目目录为空也应导出完整内容（不再 os.walk 文件树）。

用法：
    cd client/backend
    python -m pytest tests/test_export_db_zip.py -v
"""

import asyncio
import io
import json
import os
import tempfile
import uuid
import zipfile

_tmp_db = tempfile.NamedTemporaryFile(suffix="_export_db.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_export_db_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import pytest
import yaml
from fastapi.testclient import TestClient

from auth_local.deps import (
    require_ai_access,
    require_novel_model,
    require_project_limit,
)
from auth_local.middleware import get_current_user
from db import Base, async_session, engine, get_db
from main import app
from models.user import User

LONG_TEXT = "（导出正文）灯火在雨里摇晃，她合上日志，决定明日启程。行囊里只有半册旧书，与一枚磨亮的铜哨。" * 20


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _create_user(user_id: str) -> str:
    async with async_session() as session:
        session.add(
            User(
                id=user_id,
                email=f"{user_id}@test.com",
                password_hash="*",
                display_name=user_id,
            )
        )
        await session.commit()
    return user_id


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    _run_async(_create_tables())
    _run_async(_create_user("export_user"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "export_user"}


async def _override_true():
    return True


@pytest.fixture(autouse=True)
def _setup_overrides():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_project_limit] = _override_true
    app.dependency_overrides[require_ai_access] = _override_true
    app.dependency_overrides[require_novel_model] = lambda: True
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestExportFromDb:
    def test_export_zip_contains_all_families(self, client):
        # 建项目 + 卷 + 章（HTTP 正规链路）
        name = f"exp-{uuid.uuid4().hex[:6]}"
        r = client.post("/api/novels", json={"name": name})
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]

        r2 = client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷"})
        assert r2.status_code in (200, 201), r2.text
        r3 = client.post(
            f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第一章"}
        )
        assert r3.status_code in (200, 201), r3.text
        ref = r3.json()["ref"]

        # 章纲（分段）+ 正文
        ch = client.get(f"/api/novels/{pid}/chapters/{ref}").json()
        ch["prose"] = LONG_TEXT
        ch["segments"] = [
            {"summary": "城门初见", "target_words": 800},
            {"summary": "遇到商人", "target_words": 1200},
        ]
        r4 = client.put(f"/api/novels/{pid}/chapters/{ref}", json=ch)
        assert r4.status_code == 200, r4.text

        # 生成提示词（chapter_prompts 表，整章单卡：PUT write 行）
        r5 = client.put(
            f"/api/novels/{pid}/chapters/{ref}/prompts/write",
            json={"content": "整章写作提示词（城门初见）。"},
        )
        assert r5.status_code == 200, r5.text

        # 归档（archives 表）
        r6 = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive",
            json={"full_text": LONG_TEXT},
        )
        assert r6.status_code == 200, r6.text

        # 导出 → zip 全家桶（DB 组装，不依赖盘上文件）
        r7 = client.get(f"/api/novels/{pid}/export")
        assert r7.status_code == 200, r7.text
        assert r7.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r7.content))
        names = set(zf.namelist())

        # 1. 元数据
        assert "project.json" in names
        meta = json.loads(zf.read("project.json"))
        assert meta["id"] == pid
        assert meta["name"] == name

        # 2. 设定（KV → yaml 树；建项目即种子 5 类模板行）
        assert "story.yaml" in names
        assert "settings/writing-style.yaml" in names

        # 3. 卷纲
        assert "volumes/vol-1.yaml" in names
        vol = yaml.safe_load(zf.read("volumes/vol-1.yaml"))
        assert vol["title"] == "第一卷"

        # 4. 章纲 + 正文（全量章 JSON）
        assert f"chapters/{ref}.yaml" in names
        chd = yaml.safe_load(zf.read(f"chapters/{ref}.yaml"))
        assert chd["title"] == "第一章"
        assert "灯火在雨里摇晃" in chd["prose"]
        assert [s["summary"] for s in chd["segments"]] == ["城门初见", "遇到商人"]

        # 5. 版本快照（保存正文时统一入口落快照）
        version_names = [n for n in names if n.startswith(f"versions/{ref}/")]
        assert version_names, "保存正文后应至少有一个版本快照"
        snapshot = json.loads(zf.read(version_names[0]))
        assert "灯火在雨里摇晃" in snapshot["prose"]

        # 6. 生成提示词（整章单卡，文件名形态 {ref}-write-prompt.md）
        prompt_names = sorted(n for n in names if n.startswith("prompts/"))
        assert prompt_names == [f"prompts/{ref}-write-prompt.md"]
        assert "城门初见" in zf.read(prompt_names[0]).decode("utf-8")

        # 7. 归档（派生文件名形态 vol-N-ch-M-{slug}.md）
        archive_names = [n for n in names if n.startswith("archives/")]
        assert len(archive_names) == 1
        assert archive_names[0].endswith(".md")
        assert "灯火在雨里摇晃" in zf.read(archive_names[0]).decode("utf-8")

    def test_export_empty_project_still_has_meta_and_settings(self, client):
        name = f"exp2-{uuid.uuid4().hex[:6]}"
        r = client.post("/api/novels", json={"name": name})
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]

        r2 = client.get(f"/api/novels/{pid}/export")
        assert r2.status_code == 200, r2.text
        zf = zipfile.ZipFile(io.BytesIO(r2.content))
        names = set(zf.namelist())

        # 空项目：元数据 + 种子设定；无卷/章/归档
        assert "project.json" in names
        assert "story.yaml" in names
        assert not any(n.startswith(("volumes/", "chapters/", "archives/")) for n in names)
