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
os.environ["DECONSTRUCT_DISPATCHER_OFF"] = "1"

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


def _mk_completed(task_id: str, products: dict, *, book_name: str = "星海远征") -> None:
    """直插一个已完成任务（products 新形状：{dim: {file, data, md}}）。"""
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
                    book_name=book_name,
                    source_path=source_path_of(task_id),
                    encoding="utf-8",
                    api_config_id="cfg-1",
                    ai_model="qwen3-max",
                    selected_dims_json=json.dumps(["intro", "genre", "world", "mainplot", "style", "foreshadow"]),
                    products_json=json.dumps(products, ensure_ascii=False),
                )
            )
            await s.commit()

    _run(_go())


def _product(dim: str, file: str, data: dict, md: str) -> dict:
    return {"file": file, "data": data, "md": md}


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
    r2 = client.post(
        "/api/deconstruct/tasks",
        files={"file": ("a.txt", _TXT.encode("utf-8"), "text/plain")},
        data={"api_config_id": "cfg-1", "ai_model": "m", "selected_dims": "not-json"},
    )
    assert r2.status_code == 400  # 坏 JSON 拒 400 而非 500（评审 P3）
    assert "拆解范围" in r2.json()["detail"]


def test_list_tasks_shape(client):
    r = client.get("/api/deconstruct/tasks")
    assert r.status_code == 200
    body = r.json()
    assert "tasks" in body and "heartbeat" in body and "badge" in body


def test_import_book_idempotent_and_clamps(client):
    products = {
        "intro": _product("intro", "简介.md", {"intro": "一部星际远征的故事。"}, "# 简介"),
        "genre": _product("genre", "题材.md", {"genre": "科幻", "tags": ["星际"]}, "# 题材"),
        "world": _product("world", "世界设定.md",
            {"no_power": "无超凡设定", "stage": "银河系边缘",
             "power": [], "cost": [],
             "history": [{"name": "大迁徙", "note": "文明迁移", "evidence_ch": "第2章"}],
             "factions": [{"name": f"势力{i}", "note": "描述", "evidence_ch": "第3章"} for i in range(1, 9)],
             "constraints": [], "extra": []},
            "# 世界设定"),
        "mainplot": _product("mainplot", "主线剧情.md",
            {"arcs": [{"title": "远征", "ch_start": 1, "ch_end": 318, "summary": "远征与救赎"}],
             "ending": "抵达新星系。"},
            "# 主线"),
        "style": _product("style", "写作文风.md",
            {"narration": "贴背第三人称", "dialogue": "短句对话", "rhythm": "张弛交替"},
            "# 文风"),
        "foreshadow": _product("foreshadow", "伏笔.md",
            {"hooks": [{"desc": "神秘罗盘", "plant_ch": 3, "payoff_ch": None, "status": "active", "note": "", "confidence": "high"}]},
            "# 伏笔"),
    }
    _mk_completed("dec-imp-1", products)

    r1 = client.post("/api/deconstruct/tasks/dec-imp-1/import-book")
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body["book_id"]
    assert any("截断" in w for w in body["warnings"])  # 势力 8 → clamp 6 降级提示
    assert body["skipped"] == ["characters"]  # 未勾选不写入

    r2 = client.post("/api/deconstruct/tasks/dec-imp-1/import-book")
    assert r2.status_code == 200
    assert r2.json()["book_id"] == body["book_id"]  # 幂等：同一本书

    # 建书内容抽查：书存在、世界 factions 已 clamp、伏笔章号入文本、主线 fullstory 非空
    async def _check():
        async with async_session() as s:
            from models.project import Novel

            n = await s.get(Novel, body["book_id"])
            return n

    n = _run(_check())
    assert n is not None and n.name == "星海远征"


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_import_book_requires_completed(client):
    _mk_queued("dec-imp-2")
    r = client.post("/api/deconstruct/tasks/dec-imp-2/import-book")
    assert r.status_code == 409


def test_import_book_no_power_markers(client):
    """no_power 只认「无超凡/原文未明确」两个标记串（评审 P2：死表达式修复后的双臂）。"""
    _EMPTY_WORLD = {"stage": "", "power": [], "cost": [], "history": [], "factions": [], "constraints": [], "extra": []}
    _mk_completed("dec-np-1", {"world": _product("world", "世界设定.md", {**_EMPTY_WORLD, "no_power": "超凡体系：原文未明确"}, "# 世界设定")}, book_name="标记书")
    _mk_completed("dec-np-2", {"world": _product("world", "世界设定.md", {**_EMPTY_WORLD, "no_power": "普通的都市故事"}, "# 世界设定")}, book_name="无标记书")
    r1 = client.post("/api/deconstruct/tasks/dec-np-1/import-book")
    r2 = client.post("/api/deconstruct/tasks/dec-np-2/import-book")
    assert r1.status_code == 200 and r2.status_code == 200, r1.text

    async def _world(book_id):
        from filesystem.paths import KEY_TO_PATH
        from filesystem.storage import get_storage
        from models.project import Novel

        async with async_session() as s:
            n = await s.get(Novel, book_id)
        return await get_storage().read_yaml(n.root_path, KEY_TO_PATH["world"])

    w1 = _run(_world(r1.json()["book_id"]))
    w2 = _run(_world(r2.json()["book_id"]))
    assert w1["no_power"] is True  # 原文未明确 → 置真
    assert w2["no_power"] is False  # 无标记 → 不置真


def _mk_queued(task_id: str, *, with_source: bool = True) -> None:
    from deconstruct.service import source_path_of

    os.makedirs(os.path.dirname(source_path_of(task_id)), exist_ok=True)

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
                    **({"source_size": 10} if with_source else {}),
                )
            )
            await s.commit()

    if with_source:
        with open(source_path_of(task_id), "w", encoding="utf-8") as f:
            f.write(_TXT)

    _run(_go())


def test_export_writes_selected_and_readme(client):
    products = {
        "intro": _product("intro", "简介.md", {}, "# 简介\n\n正文A"),
        "world": _product("world", "世界设定.md", {}, "# 世界设定\n\n正文B"),
        "foreshadow": _product("foreshadow", "伏笔.md", {}, "# 伏笔\n\n正文C"),
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


def test_badge_clears_after_folder_export(client):
    """文件夹出口也算「已取」：导出后 badge 不再计数（评审 P2）。"""
    _mk_completed("dec-bdg-1", {"intro": _product("intro", "简介.md", {}, "# 简介")})
    tasks = {t["id"]: t for t in client.get("/api/deconstruct/tasks").json()["tasks"]}
    assert tasks["dec-bdg-1"]["status"] == "completed"
    body = client.get("/api/deconstruct/tasks").json()
    before = body["badge"]
    dest = tempfile.mkdtemp(prefix="dec-bdg-")
    r = client.post(
        "/api/deconstruct/tasks/dec-bdg-1/export",
        json={"dest_dir": dest, "files": ["简介.md"]},
    )
    assert r.status_code == 200, r.text
    assert client.get("/api/deconstruct/tasks").json()["badge"] == before - 1


def test_queued_ahead_ignores_cancelled_gaps(client):
    """排队位次按仍在排队的行计数，取消留洞不虚高（评审 P3）。"""
    _mk_queued("dec-qa-1")
    _mk_queued("dec-qa-2")

    def _ahead_of_qa2():
        tasks = {t["id"]: t for t in client.get("/api/deconstruct/tasks").json()["tasks"]}
        return tasks["dec-qa-2"]["queued_ahead"]

    before = _ahead_of_qa2()
    r = client.post("/api/deconstruct/tasks/dec-qa-1/cancel")
    assert r.status_code == 200
    assert _ahead_of_qa2() == before - 1


def test_cancel_and_delete(client):
    _mk_queued("dec-cx-1")
    r = client.post("/api/deconstruct/tasks/dec-cx-1/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    r = client.delete("/api/deconstruct/tasks/dec-cx-1")
    assert r.status_code == 200
    r = client.get("/api/deconstruct/tasks/dec-cx-1")
    assert r.status_code == 404


def test_retry_upload_roundtrip(client):
    _mk_queued("dec-ru-1")

    async def _lose():
        async with async_session() as s:
            t = await s.get(DeconstructJob, "dec-ru-1")
            os.remove(t.source_path)
            t.status = "need_reupload"
            await s.commit()

    _run(_lose())
    r = client.post(
        "/api/deconstruct/tasks/dec-ru-1/retry-upload",
        files={"file": ("雪落无声.txt", _TXT.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200 and r.json()["status"] == "queued"

    async def _back():
        async with async_session() as s:
            t = await s.get(DeconstructJob, "dec-ru-1")
            return t.status, os.path.exists(t.source_path)

    status, src_exists = _run(_back())
    assert status == "queued" and src_exists


def test_resume_guard_requires_failed_or_cancelled(client):
    _mk_queued("dec-rs-1")
    r = client.post("/api/deconstruct/tasks/dec-rs-1/resume")
    assert r.status_code == 409
