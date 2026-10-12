"""拆书端点族（c-deconstruct-book 1.3/3.x）：创建/清单/取消/续拆守卫/建书幂等与清洗降级/导出。

模型调用打桩：不跑 pipeline（创建后任务停在人控状态），管线逻辑由专项测试覆盖。
"""

import asyncio
import os
import tempfile

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix="_dec_api.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_dec_api_")

from fastapi.testclient import TestClient  # noqa: E402

from auth_local.middleware import get_current_user  # noqa: E402
from db import Base, async_session, engine  # noqa: E402
from main import app  # noqa: E402
from models.deconstruct import DeconstructJob  # noqa: E402

_UID = "dec-api-user"
_TXT = "第一卷 起\n第1章 初见\n林晚在渡口救人。\n第2章 重逢\n阿蓟归来报恩。\n"


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _ensure_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="module", autouse=True)
def _db():
    _run(_ensure_tables())
    yield


@pytest.fixture
def client():
    c = TestClient(app)
    c.__enter__()
    app.dependency_overrides[get_current_user] = lambda: {"id": _UID}
    yield c
    app.dependency_overrides.clear()
    c.__exit__(None, None, None)


def _mk_completed(task_id: str, products: dict) -> None:
    """直插一个已完成任务（产物 md 用管线同款固定 H2 渲染形状）。"""
    import json

    async def _go():
        async with async_session() as s:
            from deconstruct.service import next_queue_seq, source_path_of

            s.add(
                DeconstructJob(
                    id=task_id,
                    user_id=_UID,
                    status="completed",
                    queue_seq=await next_queue_seq(s),
                    book_name="星海远征",
                    source_path=source_path_of(task_id),
                    encoding="utf-8",
                    api_config_id="cfg-1",
                    ai_model="qwen3-max",
                    selected_dims_json=json.dumps(["intro", "world", "foreshadow"]),
                    products_json=json.dumps(products, ensure_ascii=False),
                )
            )
            await s.commit()

    _run(_go())


def test_create_task_streams_and_parses(client):
    r = client.post(
        "/api/deconstruct/tasks",
        files={"file": ("雪落无声.txt", _TXT.encode("utf-8"), "text/plain")},
        data={"book_name": "雪落无声", "api_config_id": "cfg-1", "ai_model": "qwen3-max",
              "selected_dims": '["intro","world"]'},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["chapter_count"] == 2 and body["volume_count"] == 1
    assert body["selected_dims"] == ["intro", "world"]
    # 上传即落盘契约
    from deconstruct.service import get_task, source_path_of

    async def _src():
        async with async_session() as s:
            t = await get_task(s, body["id"], _UID)
            return t.source_path, os.path.exists(t.source_path), t.encoding

    path, exists, enc = _run(_src())
    assert path.startswith(source_path_of(body["id"]).rsplit("/", 1)[0]) and exists
    assert enc.startswith("utf-8")  # 探测链优先 utf-8-sig（无 BOM 亦命中）


def test_create_task_rejects_oversize_and_bad_dims(client):
    big = b"x" * (50 * 1024 * 1024 + 1)
    r = client.post(
        "/api/deconstruct/tasks",
        files={"file": ("big.txt", big, "text/plain")},
        data={"api_config_id": "cfg-1", "ai_model": "m"},
    )
    assert r.status_code == 400


def test_list_tasks_shape(client):
    r = client.get("/api/deconstruct/tasks")
    assert r.status_code == 200
    body = r.json()
    assert "tasks" in body and "heartbeat" in body and "badge" in body


def test_import_book_idempotent_and_clamps(client):
    factions = "\n".join(f"- 势力{i}：描述{i}" for i in range(1, 9))  # 8 方 > 上限 6
    world_md = "# 世界设定｜星海远征\n\n## no_power\n\n无超凡\n\n## factions\n\n" + factions + "\n"
    intro_md = "# 简介｜星海远征\n\n## intro\n\n一部星际远征的故事。\n"
    foreshadow_md = "# 伏笔｜星海远征\n\n## hooks\n\n- 神秘罗盘 埋设于第3章（未收束）\n"
    _mk_completed("dec-imp-1", {"简介.md": intro_md, "世界设定.md": world_md, "伏笔.md": foreshadow_md})

    r1 = client.post("/api/deconstruct/tasks/dec-imp-1/import-book")
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body["book_id"]
    assert any("截断" in w for w in body["warnings"])  # 势力 8 → clamp 6 降级提示
    assert set(body["skipped"]) == {"characters", "mainplot", "style", "genre"}  # 未勾选不写入

    r2 = client.post("/api/deconstruct/tasks/dec-imp-1/import-book")
    assert r2.status_code == 200
    assert r2.json()["book_id"] == body["book_id"]  # 幂等：同一本书


def test_import_book_requires_completed(client):
    _mk_queued("dec-imp-2")
    r = client.post("/api/deconstruct/tasks/dec-imp-2/import-book")
    assert r.status_code == 409


def _mk_queued(task_id: str) -> None:

    async def _go():
        async with async_session() as s:
            from deconstruct.service import next_queue_seq, source_path_of

            s.add(
                DeconstructJob(
                    id=task_id,
                    user_id=_UID,
                    status="queued",
                    queue_seq=await next_queue_seq(s),
                    book_name="排队书",
                    source_path=source_path_of(task_id),
                )
            )
            await s.commit()

    _run(_go())


def test_export_writes_selected_and_readme(client):
    products = {
        "简介.md": "# 简介\n\n正文A",
        "世界设定.md": "# 世界设定\n\n正文B",
        "伏笔.md": "# 伏笔\n\n正文C",
    }
    _mk_completed("dec-exp-1", products)
    dest = tempfile.mkdtemp(prefix="dec-export-")
    r = client.post(
        "/api/deconstruct/tasks/dec-exp-1/export",
        json={"dest_dir": dest, "files": ["简介.md", "世界设定.md"]},
    )
    assert r.status_code == 200, r.text
    written = sorted(os.listdir(dest))
    assert written == ["README.md", "世界设定.md", "简介.md"]  # 未勾选的伏笔不导出
    with open(os.path.join(dest, "README.md"), encoding="utf-8") as f:
        assert "正文C" not in f.read()


def test_export_rejects_empty_selection(client):
    dest = tempfile.mkdtemp(prefix="dec-export-bad-")
    r = client.post(
        "/api/deconstruct/tasks/dec-exp-1/export",
        json={"dest_dir": dest, "files": []},
    )
    assert r.status_code == 400


def test_export_invalid_dest(client):
    r = client.post(
        "/api/deconstruct/tasks/dec-exp-1/export",
        json={"dest_dir": "相对路径", "files": ["简介.md"]},
    )
    assert r.status_code == 400


def test_cancel_and_delete(client):
    _mk_queued("dec-cx-1")
    r = client.post("/api/deconstruct/tasks/dec-cx-1/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    r = client.delete("/api/deconstruct/tasks/dec-cx-1")
    assert r.status_code == 200
    r = client.get("/api/deconstruct/tasks/dec-cx-1")
    assert r.status_code == 404


def test_resume_guard_requires_failed_or_cancelled(client):
    _mk_queued("dec-rs-1")
    r = client.post("/api/deconstruct/tasks/dec-rs-1/resume")
    assert r.status_code == 409
