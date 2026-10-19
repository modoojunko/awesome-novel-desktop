"""拆书端点族（c-deconstruct-book 1.3/3.x）：创建/清单/取消/续拆守卫/建书幂等与清洗降级/导出。

模型调用打桩：不跑 pipeline（创建后任务停在人控状态），管线逻辑由专项测试覆盖。
"""

import asyncio
import json
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
    assert body["thinking"] == "off"  # 思考档位默认关（D10）


def test_create_task_thinking_mode_persisted(client):
    """思考档位：表单可选 低/跟随配置，落任务行并回显；非法值归一为关（D10）。"""
    r = client.post(
        "/api/deconstruct/tasks",
        files={"file": ("雪落无声.txt", _TXT.encode("utf-8"), "text/plain")},
        data={"book_name": "雪落无声", "api_config_id": "cfg-1", "ai_model": "qwen3-max",
              "selected_dims": '["intro"]', "thinking": "low"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["thinking"] == "low"
    r2 = client.post(
        "/api/deconstruct/tasks",
        files={"file": ("a.txt", _TXT.encode("utf-8"), "text/plain")},
        data={"api_config_id": "cfg-1", "ai_model": "m", "thinking": "max"},
    )
    assert r2.status_code == 200 and r2.json()["thinking"] == "off"  # 白名单外归一默认关


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


def test_create_structure_verdict_risk_and_utf16_rejected(client):
    # 无章标题大部头：判定 risk 且问题清单前置进 parse_warnings（不拦截，risk 由前端确认闸放行）
    big_text = "这是一本没有章节标题的书。" + "内容" * 20000  # 4 万字整本单章
    r = client.post(
        "/api/deconstruct/tasks",
        files={"file": ("无章.txt", big_text.encode("utf-8"), "text/plain")},
        data={"api_config_id": "cfg-1", "ai_model": "m"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["structure"]["level"] == "risk"
    assert body["structure"]["chapter_count"] == 1
    assert any("未识别到章节标题" in w for w in body["parse_warnings"])

    # UTF-16（Windows「Unicode」格式）：400 且文案点名 UTF-16，不进创建流程
    r2 = client.post(
        "/api/deconstruct/tasks",
        files={"file": ("u16.txt", "第1章 试\n正文".encode("utf-16"), "text/plain")},
        data={"api_config_id": "cfg-1", "ai_model": "m"},
    )
    assert r2.status_code == 400
    assert "UTF-16" in r2.json()["detail"]


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


def test_import_book_requires_completed(client):
    _mk_queued("dec-imp-2")
    r = client.post("/api/deconstruct/tasks/dec-imp-2/import-book")
    assert r.status_code == 409


def test_get_product_content_and_unknown_404(client):
    """产物全文端点（结果目录预览用）：清单内回全文，清单外/穿越名一律 404。"""
    _mk_completed("dec-prev-1", {"intro": _product("intro", "简介.md", {}, "# 简介\n\n林晚在渡口。")})
    r = client.get("/api/deconstruct/tasks/dec-prev-1/products/简介.md")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filename"] == "简介.md"
    assert body["content"] == "# 简介\n\n林晚在渡口。"
    assert client.get("/api/deconstruct/tasks/dec-prev-1/products/不存在.md").status_code == 404
    assert client.get("/api/deconstruct/tasks/dec-prev-1/products/..%2Fsource.txt").status_code == 404


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
    assert written == ["README.md", "世界设定.md", "导出清单.json", "简介.md"]  # 未勾选的伏笔不导出；清单随包
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


def test_export_tilde_dest_expands(client, monkeypatch):
    """~/ 开头先 expanduser 再校验（真机实证：~/download/chaishu/ 被拒导出目录非法）。"""
    home = tempfile.mkdtemp(prefix="dec-export-home-")
    monkeypatch.setenv("HOME", home)
    _mk_completed("dec-exp-tilde", {"intro": _product("intro", "简介.md", {}, "# 简介")})
    r = client.post(
        "/api/deconstruct/tasks/dec-exp-tilde/export",
        json={"dest_dir": "~/chaishu-out/", "files": ["简介.md"]},
    )
    assert r.status_code == 200, r.text
    out = os.path.join(home, "chaishu-out")
    assert os.path.isdir(out) and "简介.md" in os.listdir(out)


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


def test_retry_upload_rejects_utf16_same_as_create(client):
    # 重传走同一条探测守卫：UTF-16/空字节等坏编码与首传同口径拒收（c-deconstruct-book 11）
    _mk_queued("dec-ru-2")

    async def _lose():
        async with async_session() as s:
            t = await s.get(DeconstructJob, "dec-ru-2")
            os.remove(t.source_path)
            t.status = "need_reupload"
            await s.commit()

    _run(_lose())
    r = client.post(
        "/api/deconstruct/tasks/dec-ru-2/retry-upload",
        files={"file": ("u16.txt", "第1章 试\n正文".encode("utf-16"), "text/plain")},
    )
    assert r.status_code == 400
    assert "UTF-16" in r.json()["detail"]


def test_resume_guard_requires_failed_or_cancelled(client):
    _mk_queued("dec-rs-1")
    r = client.post("/api/deconstruct/tasks/dec-rs-1/resume")
    assert r.status_code == 409


# ── 图谱三件套导出（10.4）────────────────────────────────────────────

def _seed_graph(task_id: str, *, graph: dict | None = None, graph_error: str = "") -> None:
    import json as _json

    async def _go():
        async with async_session() as s:
            t = await s.get(DeconstructJob, task_id)
            state = {"cards": {}, "dims": {}}
            if graph is not None:
                state["graph"] = graph
            if graph_error:
                state["graph_error"] = graph_error
            t.dims_json = _json.dumps(state, ensure_ascii=False)
            await s.commit()

    _run(_go())


def _mini_graph() -> dict:
    from deconstruct.graph import assemble

    cards = {"1": {"summary": "开场", "characters": [{"name": "林晚", "role": "主角", "traits": "", "alias": ""}],
                   "places": [{"name": "渡口", "parent": "", "note": ""}],
                   "presence": [{"who": "林晚", "where": "渡口"}],
                   "intro": [], "genre": [], "world": [], "relations": [], "mainplot": [],
                   "structure": [], "style": [], "techniques": [], "foreshadow": []}}
    products = {"characters": {"data": {"characters": [
        {"name": "林晚", "role": "主角", "plot": "", "evidence_ch": "第1章"}]}},
        "intro": {"data": {"intro": "渡口开场"}}}
    return assemble(book_name="星海远征", chapter_count=1, words=10, cards=cards,
                    products=products, place_merge=None, source_text="第1章 开场\n林晚在渡口。")


def test_export_with_graph_trio_and_manifest(client):
    import hashlib
    import json as _json

    products = {"intro": _product("intro", "简介.md", {}, "# 简介\n\n正文A")}
    _mk_completed("dec-exp-g", products)
    _seed_graph("dec-exp-g", graph=_mini_graph())
    dest = tempfile.mkdtemp(prefix="dec-export-g-")
    r = client.post("/api/deconstruct/tasks/dec-exp-g/export",
                    json={"dest_dir": dest, "files": ["简介.md"]})
    assert r.status_code == 200, r.text
    body = r.json()
    names = sorted(os.listdir(dest))
    for f in ("图谱.json", "图谱.html", "图谱.svg", "导出清单.json", "README.md", "简介.md"):
        assert f in names, names
    assert body["graph"] == ["图谱.json", "图谱.html", "图谱.svg"]
    with open(os.path.join(dest, "导出清单.json"), encoding="utf-8") as f:
        manifest = _json.load(f)
    assert manifest["contract"] == "deconstruct-graph/6" and manifest["task"] == "dec-exp-g"
    for name, sha in manifest["files"].items():
        with open(os.path.join(dest, name), encoding="utf-8") as f:
            assert hashlib.sha256(f.read().encode("utf-8")).hexdigest() == sha, name
    with open(os.path.join(dest, "README.md"), encoding="utf-8") as f:
        readme = f.read()
    assert "不会回流" in readme and "图谱.html" in readme
    # html 可自包含打开（含数据岛）
    with open(os.path.join(dest, "图谱.html"), encoding="utf-8") as f:
        assert '<script id="graphdata"' in f.read()


def test_export_backup_rotation(client):
    products = {"intro": _product("intro", "简介.md", {}, "# A")}
    _mk_completed("dec-exp-bak", products)
    _seed_graph("dec-exp-bak", graph=_mini_graph())
    dest = tempfile.mkdtemp(prefix="dec-export-bak-")

    r1 = client.post("/api/deconstruct/tasks/dec-exp-bak/export",
                     json={"dest_dir": dest, "files": ["简介.md"]})
    assert r1.status_code == 200 and r1.json()["backups"] == []
    # 用户手改 图谱.json → 再导出必留 .bak
    with open(os.path.join(dest, "图谱.json"), "a", encoding="utf-8") as f:
        f.write("\n用户手改\n")
    r2 = client.post("/api/deconstruct/tasks/dec-exp-bak/export",
                     json={"dest_dir": dest, "files": ["简介.md"]})
    assert r2.status_code == 200
    assert any(b.startswith("图谱.json.bak-") for b in r2.json()["backups"])
    assert any(".bak-" in n for n in os.listdir(dest))


def test_export_graph_error_falls_back_to_docs(client):
    """评审 P1-2：装配失败回落文档版（md 永不互拖），响应携 graph_error 注记。"""
    products = {"intro": _product("intro", "简介.md", {}, "# A")}
    _mk_completed("dec-exp-gerr", products)
    _seed_graph("dec-exp-gerr", graph_error="装配期异常")
    dest = tempfile.mkdtemp(prefix="dec-export-gerr-")
    r = client.post("/api/deconstruct/tasks/dec-exp-gerr/export",
                    json={"dest_dir": dest, "files": ["简介.md"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["graph_error"] == "装配期异常" and body["graph"] == []
    names = os.listdir(dest)
    assert "简介.md" in names and "图谱.json" not in names and "导出清单.json" in names
    with open(os.path.join(dest, "导出清单.json"), encoding="utf-8") as f:
        assert json.load(f)["contract"] == "document-only"


def test_export_switch_off_suppresses_cached_graph(client, monkeypatch):
    """评审 P2-1 关径全实现：开关关＝缓存图谱也不发，且 graph_error 不再影响导出。"""
    products = {"intro": _product("intro", "简介.md", {}, "# A")}
    _mk_completed("dec-exp-off", products)
    _seed_graph("dec-exp-off", graph=_mini_graph())
    monkeypatch.setenv("DECONSTRUCT_GRAPH_EXPORT", "0")
    dest = tempfile.mkdtemp(prefix="dec-export-off-")
    r = client.post("/api/deconstruct/tasks/dec-exp-off/export",
                    json={"dest_dir": dest, "files": ["简介.md"]})
    assert r.status_code == 200, r.text
    assert r.json()["graph"] == [] and r.json()["graph_error"] == ""
    assert "图谱.html" not in os.listdir(dest)


# ── 能力戳与图谱视图（10.5）──────────────────────────────────────────

def test_create_reports_graph_caps(client, monkeypatch):
    import prompts as _prompts

    monkeypatch.setattr(_prompts, "load_layers", lambda name: ("含 presence 契约的 system", "u"))
    r1 = client.post(
        "/api/deconstruct/tasks",
        files={"file": ("caps.txt", _TXT.encode("utf-8"), "text/plain")},
        data={"api_config_id": "cfg-1", "ai_model": "m"},
    )
    assert r1.status_code == 200 and r1.json()["graph_caps"] is True
    monkeypatch.setattr(_prompts, "load_layers", lambda name: ("老包 system 无该字段", "u"))
    r2 = client.post(
        "/api/deconstruct/tasks",
        files={"file": ("caps2.txt", _TXT.encode("utf-8"), "text/plain")},
        data={"api_config_id": "cfg-1", "ai_model": "m"},
    )
    assert r2.status_code == 200 and r2.json()["graph_caps"] is False


def test_task_view_graph_states(client):
    products = {"intro": _product("intro", "简介.md", {}, "# A")}
    _mk_completed("dec-gv-1", products)
    body = client.get("/api/deconstruct/tasks/dec-gv-1").json()
    assert body["graph"]["state"] == "absent" and body["graph"]["available"] is False
    _seed_graph("dec-gv-1", graph=_mini_graph())
    body = client.get("/api/deconstruct/tasks/dec-gv-1").json()
    assert body["graph"]["state"] == "ready" and body["graph"]["available"] is True
    assert isinstance(body["graph"]["warnings"], int)
    _seed_graph("dec-gv-1", graph_error="boom")
    body = client.get("/api/deconstruct/tasks/dec-gv-1").json()
    assert body["graph"]["state"] == "error" and body["graph"]["available"] is False


# ── 阶段三进度账透出（graph_phase：补写/地点归并/装配）──────────────────

def _seed_dims(task_id: str, state: dict) -> None:
    import json as _json

    async def _go():
        async with async_session() as s:
            t = await s.get(DeconstructJob, task_id)
            t.dims_json = _json.dumps(state, ensure_ascii=False)
            await s.commit()

    _run(_go())


def test_task_view_includes_graph_phase(client):
    _mk_queued("dec-gp-1", with_source=False)
    _seed_dims("dec-gp-1", {
        "cards": {"state": "completed", "done": 3, "entries": {}},
        "dims": {},
        "graph_phase": {"step": "presence", "done": 2, "total": 5},
    })
    d = client.get("/api/deconstruct/tasks/dec-gp-1").json()
    assert d["graph_phase"] == {"step": "presence", "done": 2, "total": 5}


def test_task_view_graph_phase_absent_is_none(client):
    _mk_queued("dec-gp-2", with_source=False)
    d = client.get("/api/deconstruct/tasks/dec-gp-2").json()
    assert d["graph_phase"] is None


def test_import_world_v2_product_shapes(client):
    """建书 world 映射对齐 v2 产物形状（真机实证：power/cost 列表→repr 乱码、
    history/constraints 因 key 缺失整条被丢、faction note 因 rule 键错配全丢）。"""
    _mk_completed("dec-imp-w", {"world": _product("world", "世界设定.md", {
        "no_power": "",
        "stage": "北方某市",
        "power": [{"name": "鬼与邪祟体系", "rule": "溺亡者成水鬼需拉替死鬼"}],
        "cost": [{"name": "折寿", "rule": "过阴寻人需折寿"}],
        "history": [{"name": "十年前连环车祸", "note": "三任司机坠水库", "evidence_ch": "第1章"}],
        "factions": [{"name": "公交公司", "rule": "老吴知情并隐瞒"}],
        "constraints": [{"name": "诅咒绑定", "rule": "开了第一遭走不了"}],
    }, "# 世界设定")})
    r = client.post("/api/deconstruct/tasks/dec-imp-w/import-book")
    assert r.status_code == 200, r.text
    bid = r.json()["book_id"]

    async def _world(book_id):
        from filesystem.paths import KEY_TO_PATH
        from filesystem.storage import get_storage
        from models.project import Novel

        async with async_session() as s:
            n = await s.get(Novel, book_id)
        return await get_storage().read_yaml(n.root_path, KEY_TO_PATH["world"])

    w = _run(_world(bid))
    assert "鬼与邪祟体系：溺亡者成水鬼需拉替死鬼" in w["power"]  # 段落化
    assert "'name'" not in w["power"]  # 不再是 repr 串
    assert "折寿" in w["cost"]
    assert w["history"] and w["history"][0]["key"] == "十年前连环车祸"
    assert "坠水库" in w["history"][0]["value"] and w["history"][0].get("origin") == "第1章"
    assert w["constraints"] and w["constraints"][0]["key"] == "诅咒绑定"
    assert "走不了" in w["constraints"][0]["value"]
    assert w["factions"][0]["name"] == "公交公司" and w["factions"][0]["note"] == "老吴知情并隐瞒"


def test_import_book_items_structure_relations_techniques(client):
    """勾选导入三项扩展：卷行创建／关系别名解析＋未入库跳过／技法并入文风 rules。"""
    chars = [
        {"name": "李耀", "role": "主角", "plot": "p", "traits": "", "alias": "小李/我",
         "persona": "谨慎多疑的夜班司机，嘴硬心软", "gender": "男", "age": "三十五六", "race": "人类"},
        {"name": "老吴", "role": "配角", "plot": "p", "traits": "", "alias": ""},
        {"name": "队长", "role": "配角", "plot": "p", "traits": "", "alias": ""},
    ]
    _mk_completed("dec-items-1", {
        "characters": _product("characters", "角色设定.md", {"characters": chars}, "# 角色"),
        "structure": _product("structure", "章卷结构.md", {"volumes": [
            {"title": "夜班车鬼线", "ch_range": "第1-13章", "note": "开局至铜钟事件"},
            {"title": "原文未明确", "ch_range": "第14-40章", "note": "水库收束"},
        ]}, "# 章卷"),
        "relations": _product("relations", "人物关系与势力.md", {"edges": [
            {"from": "老吴", "to": "李耀", "rel_type": "主从", "note": "强塞夜班车", "evidence_ch": "第1章"},
            {"from": "队长", "to": "小李/我", "rel_type": "主从", "note": "别名命中"},
            {"from": "名单外人", "to": "李耀", "rel_type": "敌对", "note": "未入库跳过"},
        ]}, "# 关系"),
        "techniques": _product("techniques", "写作技法.md", {"techniques": [
            {"name": "短句急促", "how": "惊悚段落用短句"},
            {"name": "动作描写", "how": "身体动作展示情绪"},
        ]}, "# 技法"),
    })
    items = ["world", "characters", "structure", "relations", "techniques"]
    r = client.post("/api/deconstruct/tasks/dec-items-1/import-book", json={"items": items})
    assert r.status_code == 200, r.text
    body = r.json()
    bid = body["book_id"]
    assert any("角色未入库" in w for w in body["warnings"])  # 名单外人被跳过留痕

    async def _check():
        from sqlalchemy import select

        from filesystem.paths import KEY_TO_PATH
        from filesystem.storage import get_storage
        from models.character import Character, CharacterRelation
        from models.project import Novel
        from models.volume import Volume

        async with async_session() as s:
            vols = (await s.execute(select(Volume).where(Volume.project_id == bid))).scalars().all()
            rels = (await s.execute(select(CharacterRelation).where(CharacterRelation.novel_id == bid))).scalars().all()
            c = (await s.execute(select(Character).where(Character.novel_id == bid, Character.name == "李耀"))).scalars().first()
            n = await s.get(Novel, bid)
        style = await get_storage().read_yaml(n.root_path, KEY_TO_PATH["style"])
        return vols, rels, c, style

    vols, rels, c, style = _run(_check())
    assert c.persona == "谨慎多疑的夜班司机，嘴硬心软"  # 小传入卡
    d = json.loads(c.dossier)
    assert d.get("gender") == "男" and d.get("age") == "三十五六"  # 档案格随建书入库
    assert [v.title for v in sorted(vols, key=lambda v: v.volume_no)] == ["夜班车鬼线", "第2卷"]  # 「原文未明确」→服务端兜底
    assert "水库收束" in vols[1].summary
    assert len(rels) == 2  # 队长（别名命中）＋老吴
    assert all(r.owner_id == c.id or r.other_id == c.id for r in rels)
    assert "短句急促：惊悚段落用短句" in (style.get("rules") or [])


def test_import_book_default_items_legacy(client):
    """缺省 items＝旧口径：任务维度里的设定项——structure/relations/techniques 不灌。"""
    _mk_completed("dec-items-2", {
        "structure": _product("structure", "章卷结构.md", {"volumes": [
            {"title": "不该出现的卷", "ch_range": "第1-9章", "note": ""},
        ]}, "# 章卷"),
        "relations": _product("relations", "人物关系与势力.md", {"edges": [
            {"from": "甲", "to": "乙", "rel_type": "敌对", "note": ""},
        ]}, "# 关系"),
    })
    r = client.post("/api/deconstruct/tasks/dec-items-2/import-book")
    assert r.status_code == 200, r.text
    bid = r.json()["book_id"]

    async def _check():
        from sqlalchemy import select

        from models.character import CharacterRelation
        from models.volume import Volume

        async with async_session() as s:
            vols = (await s.execute(select(Volume).where(Volume.project_id == bid))).scalars().all()
            rels = (await s.execute(select(CharacterRelation).where(CharacterRelation.novel_id == bid))).scalars().all()
        return vols, rels

    vols, rels = _run(_check())
    assert vols == [] and rels == []  # 未勾不灌（旧行为不变）


def test_import_world_strips_evidence_and_cuts_sentences(client):
    """世界正文清洗：证据章标（【第N章】分析工件）剥除；超长段落在句号处截断不留半句。"""
    long_stage = "北方某市为舞台，唐洼子水库是核心怪谈地标，十年间事故不断。" + "阴气在冬夜最盛，说书人不敢细讲。" * 130 + "末尾半句被截断的字"
    _mk_completed("dec-imp-clean", {"world": _product("world", "世界设定.md", {
        "no_power": "",
        "stage": f"北方某市【第1-2/177/180章】；虎腰山村有封印古井【第14/172章】。{long_stage}",
        "power": [{"name": "鬼与邪祟体系", "rule": "溺亡者成水鬼需拉替死鬼【第5/19/32章】"}],
        "constraints": [{"name": "诅咒绑定", "rule": "开了第一遭走不了【第12/39章】"}],
    }, "# 世界设定")})
    r = client.post("/api/deconstruct/tasks/dec-imp-clean/import-book")
    assert r.status_code == 200, r.text
    bid = r.json()["book_id"]

    async def _world(book_id):
        from filesystem.paths import KEY_TO_PATH
        from filesystem.storage import get_storage
        from models.project import Novel

        async with async_session() as s:
            n = await s.get(Novel, book_id)
        return await get_storage().read_yaml(n.root_path, KEY_TO_PATH["world"])

    w = _run(_world(bid))
    for field in ("stage", "power", "constraints"):
        text = json.dumps(w.get(field), ensure_ascii=False)
        assert "【第" not in text, f"{field} 仍带证据章标"
    assert w["stage"].startswith("北方某市；虎腰山村有封印古井。")
    assert len(w["stage"]) <= 2000 and (w["stage"][-1] in "。！？；\n")
    assert "替死鬼" in w["power"] and "走不了" in w["constraints"][0]["value"]


# ── 建书 AI 精炼（世界设定超字段契约时压缩成合规形态）────────────────────

def _mk_condense_stubs(monkeypatch, *, chat, resolve_raises=False):
    import deconstruct.service

    class _Client:
        async def chat(self, **kw):
            return chat(kw)

    async def fake_resolve(user_id, cfg, model, thinking="inherit"):
        if resolve_raises:
            raise ValueError("no cfg")
        return _Client(), "m-1"

    monkeypatch.setattr(deconstruct.service, "resolve_client", fake_resolve)
    monkeypatch.setattr("prompts.load_layers", lambda name: ("sys", "u {source_json}"))


def test_import_book_condenses_over_contract_world(client, monkeypatch):
    """产物超字段契约 → 一次 AI 精炼按字段形态重写（经 normalize 收敛进契约）。"""
    _mk_completed("dec-cd-1", {"world": _product("world", "世界设定.md", {
        "no_power": "",
        "stage": "超长分析稿。" * 60 + "【第1章】",
        "power": [{"name": "鬼与邪祟体系", "rule": "规则" * 150}],
        "constraints": [{"name": "诅咒绑定", "rule": "规则" * 150}],
    }, "# 世界设定")})

    def fake_chat(kw):
        assert kw["operation"] == "deconstruct_condense"
        return json.dumps({
            "stage": "精炼后的世界舞台，一句话立住。",
            "power": "精炼后的力量体系。",
            "cost": "精炼后的代价。",
            "history": [{"key": "十年前车祸", "value": "三任司机坠水库"}],
            "constraints": [{"key": "诅咒绑定", "value": "开了第一遭走不了"}],
            "factions": [], "extra": [], "no_power": False,
        })

    _mk_condense_stubs(monkeypatch, chat=fake_chat)
    r = client.post("/api/deconstruct/tasks/dec-cd-1/import-book")
    assert r.status_code == 200, r.text
    assert not [w for w in r.json()["warnings"] if "精炼" in w]  # 精炼成功无降级提示

    async def _world(book_id):
        from filesystem.paths import KEY_TO_PATH
        from filesystem.storage import get_storage
        from models.project import Novel

        async with async_session() as s:
            n = await s.get(Novel, book_id)
        return await get_storage().read_yaml(n.root_path, KEY_TO_PATH["world"])

    w = _run(_world(r.json()["book_id"]))
    assert w["stage"] == "精炼后的世界舞台，一句话立住。"
    assert w["power"] == "精炼后的力量体系。"
    assert w["constraints"][0]["key"] == "诅咒绑定"


def test_import_book_condense_unavailable_falls_back(client, monkeypatch):
    """模型不可用 → 机械句界截断兜底＋提示条（不中断建书）。"""
    _mk_completed("dec-cd-2", {"world": _product("world", "世界设定.md", {
        "no_power": "",
        "stage": "北方某市为舞台。" + "阴气冬夜最盛，说书人不敢细讲。" * 30,
    }, "# 世界设定")})
    _mk_condense_stubs(monkeypatch, chat=lambda kw: "{}", resolve_raises=True)
    r = client.post("/api/deconstruct/tasks/dec-cd-2/import-book")
    assert r.status_code == 200, r.text
    assert any("AI 精炼不可用" in w for w in r.json()["warnings"])

    async def _world(book_id):
        from filesystem.paths import KEY_TO_PATH
        from filesystem.storage import get_storage
        from models.project import Novel

        async with async_session() as s:
            n = await s.get(Novel, book_id)
        return await get_storage().read_yaml(n.root_path, KEY_TO_PATH["world"])

    w = _run(_world(r.json()["book_id"]))
    assert len(w["stage"]) <= 800 and w["stage"].endswith("。")


def test_import_book_within_contract_no_condense_call(client, monkeypatch):
    """契约内内容零精炼调用（resolve 根本不该被碰）。"""
    _mk_completed("dec-cd-3", {"world": _product("world", "世界设定.md", {
        "no_power": "", "stage": "短舞台。",
    }, "# 世界设定")})

    from deconstruct import service as dc_service

    def _boom(*a, **k):
        raise AssertionError("契约内不应触发精炼调用")

    monkeypatch.setattr(dc_service, "resolve_client", _boom)
    r = client.post("/api/deconstruct/tasks/dec-cd-3/import-book")
    assert r.status_code == 200, r.text


def test_import_dedupes_batch_duplicate_characters(client):
    """L1 分批同名卡归并：字段互补合并（非空优先）、路人过滤——13路实测 135 条重名膨胀。"""
    chars = [
        {"name": "李耀", "role": "主角", "plot": "批1剧情", "alias": "小李", "confidence": "mid"},
        {"name": "李耀", "role": "主角", "persona": "谨慎多疑的夜班司机", "gender": "男",
         "age": "三十出头", "plot": "", "confidence": "high"},
        {"name": "甲乙丙", "role": "路人", "plot": "打酱油", "confidence": "low"},
    ]
    _mk_completed("dec-dp-1", {
        "characters": _product("characters", "角色设定.md", {"characters": chars}, "# 角色"),
        "world": _product("world", "世界设定.md", {"stage": "短舞台。"}, "# 世界"),
    })
    r = client.post("/api/deconstruct/tasks/dec-dp-1/import-book", json={"items": ["characters", "world"]})
    assert r.status_code == 200, r.text

    async def _chars():
        from sqlalchemy import select

        from models.character import Character

        async with async_session() as s:
            return (await s.execute(select(Character).where(Character.novel_id == r.json()["book_id"]))).scalars().all()

    rows = _run(_chars())
    assert len(rows) == 1  # 重名归并成一张＋路人被滤
    row = rows[0]
    assert row.name == "李耀"
    assert row.persona == "谨慎多疑的夜班司机"  # 互补：persona 来自 high 批
    d = json.loads(row.dossier)
    assert d.get("gender") == "男" and "批1剧情" in d.get("plot", "")  # 字段互补合并
    assert "小李" in row.aliases


# ── 进度可视：activity 账＋ETA（「除了等还是等」治理）────────────────────

def test_task_view_activity_and_eta(client):
    """运行中任务透出 activity（label＋距今秒）与 cards/dims eta_seconds。

    时间口径（c-deconstruct-resilience）：pipeline._now() 是 UTC naive——种子数据
    必须同口径，本地时区时间会把 age/ETA 推出时区差。
    """
    _mk_queued("dec-act-1", with_source=False)

    async def _seed():
        import json as _json
        from datetime import UTC, datetime, timedelta

        async with async_session() as s:
            t = await s.get(DeconstructJob, "dec-act-1")
            now_utc = datetime.now(UTC).replace(tzinfo=None)
            start = (now_utc - timedelta(seconds=120)).isoformat(timespec="seconds")
            t.dims_json = _json.dumps({
                "cards": {"state": "completed", "done": 3, "entries": {}, "started_at": start},
                "dims": {"world": {"state": "running", "seg_done": 2, "seg_total": 9,
                                   "error": "", "started_at": start}},
                "activity": {"label": "正在归并 世界设定（已完成 2/9 批）",
                             "at": (now_utc - timedelta(seconds=20)).isoformat(timespec="seconds")},
            }, ensure_ascii=False)
            await s.commit()

    _run(_seed())
    d = client.get("/api/deconstruct/tasks/dec-act-1").json()
    a = d["activity"]
    assert a["label"] == "正在归并 世界设定（已完成 2/9 批）"
    assert a["age_seconds"] is not None and 10 <= a["age_seconds"] <= 120
    assert d["cards"]["eta_seconds"] is None  # cards 已完成不外推
    dw = d["dims"]["world"]
    assert dw["eta_seconds"] is not None  # 速率外推有基准


def test_eta_seconds_math(monkeypatch):
    """ETA 数学：无基准/已完成 None；正常按速率外推并除以并发度。

    并发度显式钉死——DECONSTRUCT_CONCURRENCY 被其他测试模块的环境变量污染时
    本测试不受连坐（历史顺序依赖 flake 的根治）。
    """
    from datetime import UTC, datetime, timedelta

    from deconstruct import service as dec_service

    monkeypatch.setattr(dec_service, "CONCURRENCY", 4)
    start = (datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=100)).isoformat(timespec="seconds")
    assert dec_service._eta_seconds(None, 5, 10) is None
    assert dec_service._eta_seconds(start, 0, 10) is None
    assert dec_service._eta_seconds(start, 10, 10) is None
    eta = dec_service._eta_seconds(start, 5, 10)
    # 100s/5×5 剩余 ÷ 并发4 → ≈25s（±扰动容忍）
    assert 5 <= eta <= 60


def test_task_view_activity_absent(client):
    _mk_queued("dec-act-2", with_source=False)
    d = client.get("/api/deconstruct/tasks/dec-act-2").json()
    assert d["activity"] is None
