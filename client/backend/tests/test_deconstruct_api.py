"""拆书端点族（c-deconstruct-book 1.3/3.x）：创建/清单/取消/续拆守卫/建书幂等与清洗降级/导出。

模型调用打桩：不跑 pipeline（创建后任务停在人控状态），管线逻辑由专项测试覆盖。
"""

import asyncio
import json
import os
import re
import tempfile

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix="_dec_api.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_dec_api_")
os.environ["DECONSTRUCT_DISPATCHER_OFF"] = "1"
# 建书执行体开关（c-deconstruct-import-async）在 _import_runs_sync fixture 里按用例设置：
# 本文件是「回填/清洗」类用例，建完即断言，由 fixture 同步驱动执行体、不靠后台 task 抢跑。
# 真正的异步契约（四臂/取消/收敛）见 tests/test_deconstruct_import_async.py。

from fastapi.testclient import TestClient  # noqa: E402

from auth_local import deps as _auth_deps  # noqa: E402
from auth_local.middleware import get_current_user  # noqa: E402
from db import Base, async_session, engine  # noqa: E402
from main import app  # noqa: E402
from models.deconstruct import DeconstructJob, DeconstructUnit  # noqa: E402

_UID = "dec-api-user"
_TXT = "第一卷 起\n第1章 初见\n林晚在渡口救人。\n第2章 重逢\n阿蓟归来报恩。\n"


@pytest.fixture(autouse=True)
def _tier_allow_deconstruct(monkeypatch):
    """本文件专注业务行为：统一给 MAX 档权益（deconstruct＋deconstruct-import），
    门禁矩阵另见 test_deconstruct_tier.py。"""
    async def _ensure():
        return None

    async def _no_model(user, db):
        return None

    monkeypatch.setattr(_auth_deps, "ensure_entitlement_snapshot", _ensure)
    monkeypatch.setattr(_auth_deps, "_check_writing_model_configured", _no_model)
    monkeypatch.setattr(
        _auth_deps, "check_permission",
        lambda: {
            "tier": "max", "is_member": True, "expired": False,
            "entitlement": {
                "v": 2,
                "features": ["ai-model", "ai-generate", "ai-plan", "deconstruct", "deconstruct-import"],
                "limits": {"max_projects": None},
            },
        },
    )


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


class _ImportDone:
    """建书受理后「已建完」的视图：保持旧同步契约的响应形状（book_id/warnings/skipped）。

    status_code 固定 200＝「这是建完的结果」，与真实受理的 202 区分（本文件只测回填语义）。
    """

    def __init__(self, detail):
        self._detail = detail
        self.status_code = 200
        self.text = json.dumps(detail, ensure_ascii=False)

    def json(self):
        from models.deconstruct import SETTING_DIMENSION_KEYS

        imp = self._detail.get("import") or {}
        # 请求未带勾选＝旧口径：执行体回落任务勾选的设定维度（与旧同步实现一致）
        items = list(imp.get("items") or []) or list(self._detail.get("selected_dims") or [])
        return {
            "status": self._detail["status"],
            "book_id": self._detail.get("book_id"),
            "name": self._detail.get("book_name"),
            "skipped": [d for d in SETTING_DIMENSION_KEYS if d not in items],
            "warnings": imp.get("warnings") or [],
        }


@pytest.fixture(autouse=True)
def _import_runs_sync(client, monkeypatch):
    """把 `POST …/import-book` 的受理＋后台执行体串起来（IMPORT_RUNNER_OFF=1）。

    只影响「建书回填语义」类用例：POST 成功后同步跑完执行体，并回读任务详情拼出旧形状
    响应。受理四臂（200 幂等 / 409 进行中 / 403 满额 / 202）与取消、收敛由
    test_deconstruct_import_async.py 覆盖。
    """
    from deconstruct import imports as _imports

    monkeypatch.setenv("IMPORT_RUNNER_OFF", "1")  # 只在本用例内生效，不泄漏到全仓
    orig_post = client.post
    orig_get = client.get

    def post(url, *args, **kwargs):
        resp = orig_post(url, *args, **kwargs)
        # 只有「新受理」（202 语义：status=importing）才需要驱动执行体；幂等 200 原样返回
        if (
            url.endswith("/import-book")
            and resp.status_code in (200, 202)  # 受理＝202；幂等＝200（后者不驱动执行体）
            and resp.json().get("status") == "importing"
        ):
            task_id = url.split("/tasks/")[1].split("/")[0]
            _run(_imports.run(task_id))
            return _ImportDone(orig_get(f"/api/deconstruct/tasks/{task_id}").json())
        return resp

    monkeypatch.setattr(client, "post", post, raising=False)
    yield


def _mk_completed(task_id: str, products: dict, *, book_name: str = "星海远征") -> None:
    """直插一个已完成任务。

    夹具带 `md` 键＝**旧形状**（现行新形状为 {dim: {file, data}}，md 读取侧现渲染），
    刻意钉「data 缺失回退存量 md」兜底臂（c-deconstruct-evidence-report）。
    """
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
    assert any("幂等返回" in w for w in r2.json()["warnings"])

    # 建书内容抽查：书存在、世界 factions 已 clamp、伏笔章号入文本、主线 fullstory 非空
    async def _check():
        async with async_session() as s:
            from models.project import Novel

            n = await s.get(Novel, body["book_id"])
            return n

    n = _run(_check())
    assert n is not None and n.name == "星海远征"


def test_import_book_after_book_deleted_creates_new(client):
    """删书后从同一任务再建书：按勾选新建一本，不得把软删的旧书原样返回。

    真机反馈：删掉拆书建出的作品后回来再点「建书」，旧书被原封不动打开——
    根因是 task.book_id 幂等键失效后仍直接返回软删行。
    """
    _mk_completed(
        "dec-imp-del",
        {"intro": _product("intro", "简介.md", {"intro": "一部星际远征的故事。"}, "# 简介")},
        book_name="删后重建",
    )

    r1 = client.post("/api/deconstruct/tasks/dec-imp-del/import-book")
    assert r1.status_code == 200, r1.text
    first = r1.json()["book_id"]
    assert client.delete(f"/api/novels/{first}").status_code == 200

    r2 = client.post("/api/deconstruct/tasks/dec-imp-del/import-book")
    assert r2.status_code == 200, r2.text
    second = r2.json()["book_id"]
    assert second != first
    assert any("删除" in w for w in r2.json()["warnings"])

    async def _check():
        from models.project import Novel

        async with async_session() as s:
            return (
                await s.get(Novel, first),
                await s.get(Novel, second),
                await s.get(DeconstructJob, "dec-imp-del"),
            )

    old, new, job = _run(_check())
    assert old is not None and old.status == "deleted"  # 旧书保持软删，不复活
    assert new is not None and new.status == "active" and new.name == "删后重建"
    assert job.book_id == second  # 幂等键改指新书
    ids = [p["id"] for p in client.get("/api/novels").json()]
    assert first not in ids and second in ids


def test_import_book_stale_book_id_creates_new(client):
    """幂等键指向不存在/他人书：同样重开新书，不 404、不 500。"""
    _mk_completed(
        "dec-imp-stale",
        {"intro": _product("intro", "简介.md", {"intro": "简介。"}, "# 简介")},
        book_name="悬空幂等键",
    )

    async def _point_nowhere():
        async with async_session() as s:
            job = await s.get(DeconstructJob, "dec-imp-stale")
            job.book_id = "no-such-book"
            await s.commit()

    _run(_point_nowhere())
    r = client.post("/api/deconstruct/tasks/dec-imp-stale/import-book")
    assert r.status_code == 200, r.text
    assert r.json()["book_id"] != "no-such-book"


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


def test_evidence_report_endpoint_and_clean_preview(client):
    """证据报告端点（c-deconstruct-evidence-report）：由 data 现渲染的证据账；
    存量任务（存储 md 内嵌证据）预览同口径去证据；非完成态空 dims、未知任务 404。"""
    products = {
        "style": {"file": "写作文风.md",
                  "data": {"role": "第三人称限知",
                           "rules": [{"name": "短句对话", "how": "对峙用短句",
                                      "confidence": "high", "evidence_ch": "第17章", "note": ""}]},
                  "md": "# 写作文风｜旧任务\n\n- 证据章节：第17章；可信度：高"},
    }
    _mk_completed("dec-evd-1", products)
    r = client.get("/api/deconstruct/tasks/dec-evd-1/evidence")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["task_id"] == "dec-evd-1"
    assert [d["dim"] for d in body["dims"]] == ["style"]
    dim = body["dims"][0]
    # style 契约无顶层 confidence（只在条目上），维度级留空
    assert dim["name"] == "写作文风" and dim["file"] == "写作文风.md" and dim["confidence"] == ""
    item = dim["sections"][0]["items"][0]
    assert item["head"] == "短句对话"
    assert {c["label"]: c["value"] for c in item["cells"]} == {"证据章节": "第17章", "可信度": "高"}
    # 作家 md 预览由 data 现渲染：存储 md 的证据不再出现
    p = client.get("/api/deconstruct/tasks/dec-evd-1/products/写作文风.md").json()
    assert "证据章节" not in p["content"] and "短句对话" in p["content"]
    # 非完成态（无产物）→ 空 dims；不存在/他人 → 404
    _mk_queued("dec-evd-2")
    assert client.get("/api/deconstruct/tasks/dec-evd-2/evidence").json()["dims"] == []
    assert client.get("/api/deconstruct/tasks/dec-nope/evidence").status_code == 404


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
    assert body["graph"]["error"] == ""
    _seed_graph("dec-gv-1", graph=_mini_graph())
    body = client.get("/api/deconstruct/tasks/dec-gv-1").json()
    assert body["graph"]["state"] == "ready" and body["graph"]["available"] is True
    assert isinstance(body["graph"]["warnings"], int)
    _seed_graph("dec-gv-1", graph_error="boom")
    body = client.get("/api/deconstruct/tasks/dec-gv-1").json()
    assert body["graph"]["state"] == "error" and body["graph"]["available"] is False
    assert body["graph"]["error"] == "boom"  # 失败原因随详情下发（不只导出响应）


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


def test_import_book_settings_field_alignment(client):
    """设定页字段对齐（2026-10-20 拍板）：拆书新契约逐字段回填——
    fullstory 全景叙述／ending 三格／style 三区（role/rules/craft）／aliases／
    关系 stance／伏笔 type+priority+resolved。"""
    chars = [
        {"name": "李耀", "aliases": ["小李", "我"], "role": "主角",
         "persona": "谨慎多疑的夜班司机", "gender": "男", "age": "三十五六",
         "race": "人类", "faction": "公交公司", "look": "风衣", "speech": "嘴硬",
         "background": "退伍兵转业", "plot": "接夜班→查旧案→揭真相", "confidence": "high"},
        {"name": "老唐", "aliases": [], "role": "反派",
         "persona": "十年前死去的司机", "gender": "男", "age": "原文未明确",
         "race": "人类", "faction": "原文未明确", "look": "原文未明确", "speech": "原文未明确",
         "background": "死于水库", "plot": "旧案核心", "confidence": "mid"},
    ]
    _mk_completed("dec-align-1", {
        "mainplot": _product("mainplot", "主线剧情.md", {
            "fullstory": "李耀被强派夜班十三路末班车，卷入十年前水库旧案，一路查到真相。",
            "arcs": [{"title": "接班车", "ch_start": 1, "ch_end": 40, "summary": "上船", "confidence": "high"}],
            "ending": {"scene": "末班车驶向黎明", "hero": "李耀活着查明真相", "tone": "释然"},
        }, "# 主线"),
        "style": _product("style", "写作文风.md", {
            "role": "第三人称限知，紧贴李耀",
            "rules": [{"name": "短对话", "how": "对峙用短句"}, {"name": "张弛", "how": "查案间插日常"}],
            "craft": [{"name": "铜钟意象", "how": "以钟声串章节"}],
            "examples": [{"example": "灯还亮着。", "evidence_ch": "第1章"}],
        }, "# 文风"),
        "characters": _product("characters", "角色设定.md", {"characters": chars}, "# 角色"),
        "relations": _product("relations", "人物关系与势力.md", {"edges": [
            {"from": "李耀", "to": "老唐", "rel_type": "敌对", "stance": "查他又不肯撒手",
             "note": "旧案对头", "evidence_ch": "第9章"},
        ]}, "# 关系"),
        "foreshadow": _product("foreshadow", "伏笔.md", {"hooks": [
            {"desc": "虎纹铜钱", "type": "clue", "priority": "high",
             "plant_ch": 5, "payoff_ch": 240, "status": "paid", "note": "以钱认主", "confidence": "high"},
            {"desc": "道癫的身世", "type": "mystery", "priority": "mid",
             "plant_ch": 12, "payoff_ch": None, "status": "active", "note": "", "confidence": "mid"},
        ]}, "# 伏笔"),
    })
    r = client.post("/api/deconstruct/tasks/dec-align-1/import-book", json={"items": [
        "mainplot", "style", "characters", "relations", "foreshadow",
    ]})
    assert r.status_code == 200, r.text
    bid = r.json()["book_id"]

    async def _check():
        from sqlalchemy import select

        from filesystem.paths import KEY_TO_PATH
        from filesystem.storage import get_storage
        from models.character import Character, CharacterRelation
        from models.hook import NovelHook
        from models.project import Novel

        async with async_session() as s:
            n = await s.get(Novel, bid)
            ch = (await s.execute(
                select(Character).where(Character.novel_id == bid, Character.name == "李耀")
            )).scalars().first()
            rel = (await s.execute(
                select(CharacterRelation).where(CharacterRelation.novel_id == bid)
            )).scalars().first()
            hooks = (await s.execute(
                select(NovelHook).where(NovelHook.novel_id == bid).order_by(NovelHook.seq)
            )).scalars().all()
        storage = get_storage()
        story = await storage.read_yaml(n.root_path, KEY_TO_PATH["story"])
        style = await storage.read_yaml(n.root_path, KEY_TO_PATH["style"])
        return story, style, ch, rel, hooks

    story, style, ch, rel, hooks = _run(_check())
    arc = story.get("story_arc") or {}
    assert "李耀被强派夜班" in arc.get("fullstory", "")  # 全景叙述直灌（不是弧条目串）
    assert arc.get("ending", {}).get("scene") == "末班车驶向黎明"
    assert arc.get("ending", {}).get("hero") == "李耀活着查明真相"
    assert arc.get("ending", {}).get("tone") == "释然"
    assert style.get("role") == "第三人称限知，紧贴李耀"
    assert "短对话：对峙用短句" in (style.get("rules") or [])
    assert "铜钟意象：以钟声串章节" in (style.get("craft") or [])
    assert json.loads(ch.aliases) == ["小李", "我"]
    assert rel.stance == "查他又不肯撒手"
    by_desc = {h.description: h for h in hooks}
    resolved = next(h for d, h in by_desc.items() if "虎纹铜钱" in d)
    active = next(h for d, h in by_desc.items() if "道癫的身世" in d)
    assert resolved.status == "resolved" and resolved.type == "clue" and resolved.priority == 1
    assert "收于第240章" in resolved.description
    assert active.status == "active" and active.priority == 2 and active.type == "mystery"


def test_import_book_unfinished_ending_cells_cleared(client):
    """未完结书：ending 三格「原文未明确」置空（与角色格同口径，不硬填）。"""
    _mk_completed("dec-align-2", {
        "mainplot": _product("mainplot", "主线剧情.md", {
            "fullstory": "故事仍在连载。",
            "arcs": [],
            "ending": {"scene": "原文未明确", "hero": "原文未明确", "tone": "原文未明确"},
        }, "# 主线"),
    }, book_name="连载书")
    r = client.post("/api/deconstruct/tasks/dec-align-2/import-book", json={"items": ["mainplot"]})
    assert r.status_code == 200, r.text

    async def _check():
        from filesystem.paths import KEY_TO_PATH
        from filesystem.storage import get_storage
        from models.project import Novel

        async with async_session() as s:
            n = await s.get(Novel, r.json()["book_id"])
        return await get_storage().read_yaml(n.root_path, KEY_TO_PATH["story"])

    story = _run(_check())
    ending = (story.get("story_arc") or {}).get("ending") or {}
    assert all(v == "" for v in ending.values()), "三格「原文未明确」应置空"


def test_import_book_legacy_ending_string_fallback(client):
    """旧产物（arcs 空＋ending 字符串）：fullstory 兜底链保住结局文案，不落「原文未明确」。"""
    _mk_completed("dec-align-3", {
        "mainplot": _product("mainplot", "主线剧情.md", {
            "arcs": [], "ending": "抵达新星系。",
        }, "# 主线"),
    }, book_name="旧任务书")
    r = client.post("/api/deconstruct/tasks/dec-align-3/import-book", json={"items": ["mainplot"]})
    assert r.status_code == 200, r.text

    async def _check():
        from filesystem.paths import KEY_TO_PATH
        from filesystem.storage import get_storage
        from models.project import Novel

        async with async_session() as s:
            n = await s.get(Novel, r.json()["book_id"])
        return await get_storage().read_yaml(n.root_path, KEY_TO_PATH["story"])

    story = _run(_check())
    assert story["story_arc"]["fullstory"] == "抵达新星系。"


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


def _mk_unit(task_id: str, stage: str, status: str, *, updated_min_ago: float | None = None,
             duration_ms: int = 0, tokens_out: int = 0, tokens_in: int = 0, error_kind: str = "",
             dim: str = "", unit_key: str | None = None) -> None:
    """直插单元账行（updated_at 可控——监控速度窗按它算）。"""
    from datetime import UTC, datetime, timedelta

    async def _go():
        async with async_session() as s:
            updated = None
            if updated_min_ago is not None:
                updated = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=updated_min_ago * 60)
            s.add(DeconstructUnit(
                task_id=task_id, stage=stage, dim=dim,
                unit_key=unit_key or f"{stage}-{updated_min_ago}-{tokens_out}-{error_kind}-{duration_ms}",
                status=status, attempts=1, error_kind=error_kind,
                duration_ms=duration_ms, tokens_out=tokens_out, tokens_in=tokens_in,
                created_at=updated or datetime.now(UTC).replace(tzinfo=None),
                updated_at=updated or datetime.now(UTC).replace(tzinfo=None),
            ))
            await s.commit()

    _run(_go())


def test_monitor_view_running_aggregates(client):
    """运行态监控账：在途（running 行调度即现）、批次 done/total、速度窗、流水倒序带调度对象。"""
    from deconstruct.service import source_path_of

    async def _go():
        async with async_session() as s:
            s.add(DeconstructJob(
                id="dec-mon-1", user_id=_UID, status="running", queue_seq=99,
                book_name="监控书", source_path=source_path_of("dec-mon-1"),
                encoding="utf-8", api_config_id="cfg-1", ai_model="m1",
            ))
            await s.commit()

    _run(_go())
    # 单元账：l1 3 done（窗内 2＋窗外 1）＋1 failed（窗内）＋2 running（派发未完）；
    # card done 一行验调度对象；reduce_state 2 行不进账
    _mk_unit("dec-mon-1", "l1", "done", updated_min_ago=1.0, duration_ms=40000, tokens_out=3000,
             tokens_in=2100, dim="foreshadow")
    _mk_unit("dec-mon-1", "l1", "done", updated_min_ago=2.0, duration_ms=60000, tokens_out=5000,
             tokens_in=3200, dim="foreshadow")
    _mk_unit("dec-mon-1", "l1", "failed", updated_min_ago=3.0, duration_ms=10000, error_kind="invalid_output", dim="foreshadow")
    _mk_unit("dec-mon-1", "l1", "done", updated_min_ago=10.0, duration_ms=90000, tokens_out=9000, dim="foreshadow")
    _mk_unit("dec-mon-1", "l1", "running", updated_min_ago=0.2, dim="foreshadow")
    _mk_unit("dec-mon-1", "l1", "running", updated_min_ago=0.4, dim="foreshadow")
    _mk_unit("dec-mon-1", "card", "done", updated_min_ago=7.0, duration_ms=42000, tokens_out=2100, unit_key="137")  # 窗外
    _mk_unit("dec-mon-1", "reduce_state", "done", updated_min_ago=0.5)
    _mk_unit("dec-mon-1", "reduce_state", "done", updated_min_ago=0.6)
    d = client.get("/api/deconstruct/tasks/dec-mon-1").json()
    m = d["monitor"]
    assert m is not None
    assert m["in_flight"] == 2  # 派发未完成＝真实在途
    assert m["batches"] == {"done": 3, "total": 6}  # running 行计入 total、不计 done
    assert m["concurrency"] >= 1
    assert m["tokens"] == {"in": 5300, "out": 19100, "total": 24400}  # 任务总消耗＝全部完成行（窗内外都算；running/failed 不计）
    sp = m["speed"]
    assert sp["done"] == 2 and sp["fail"] == 1 and sp["total"] == 7  # reduce_state 排除；running 只进调度总数
    assert sp["avg_ms"] == 50000  # (40000+60000)//2
    assert sp["out_tokens"] == 8000
    recent = m["recent"]
    assert len(recent) == 7  # 全部调用行（含 running），reduce_state 不进流水
    assert [r["running"] for r in recent[:2]] == [True, True]  # 派发即现：在途行置顶
    assert recent[0]["label"] == "伏笔·归并"
    assert [r["label"] for r in recent] .count("第137章") == 1
    assert recent[2]["ok"] is True and recent[2]["tokens_out"] == 3000
    assert [r["ok"] for r in recent if r["running"]] == [False, False]
    failed_rows = [r for r in recent if not r["ok"] and not r["running"]]
    assert failed_rows[0]["reason"] == "invalid_output"
    times = [r["at"] for r in recent]
    assert times == sorted(times, reverse=True)


def test_monitor_batch_products_are_not_calls(client):
    """合批产物行不冒充调用（2026-10-21 真机：整屏流水全是 0s/0.0k）。

    card_product 是一批 N 章成功后逐章落的产物行（无耗时/token）；流水/速度/Token
    只认真实调用行——合批调用的耗时与产出在 card_batch 行上，label 带章号区间。
    """
    from deconstruct.service import source_path_of

    async def _go():
        async with async_session() as s:
            s.add(DeconstructJob(
                id="dec-mon-batch", user_id=_UID, status="running", queue_seq=95,
                book_name="合批书", source_path=source_path_of("dec-mon-batch"),
                encoding="utf-8", api_config_id="cfg-1", ai_model="m1",
            ))
            await s.commit()

    _run(_go())
    _mk_unit("dec-mon-batch", "card_batch", "done", updated_min_ago=0.2,
             duration_ms=48000, tokens_in=6000, tokens_out=3000, unit_key="abc123:17-32")
    for no in ("17", "18", "19", "20"):
        _mk_unit("dec-mon-batch", "card_product", "done", updated_min_ago=0.1,
                 unit_key=f"p-{no}")
    m = client.get("/api/deconstruct/tasks/dec-mon-batch").json()["monitor"]
    assert m["in_flight"] == 0
    assert [r["label"] for r in m["recent"]] == ["拆卡合批·第17-32章"]
    assert m["recent"][0]["duration_ms"] == 48000 and m["recent"][0]["tokens_out"] == 3000
    # 速度/Token 不被 4 条 0 值产物行冲淡：成功 1 次、平均 48s、合计只算真实调用
    assert m["speed"] == {"window_s": 300, "done": 1, "fail": 0, "avg_ms": 48000,
                          "out_tokens": 3000, "total": 1}
    assert m["tokens"] == {"in": 6000, "out": 3000, "total": 9000}


def test_unit_label_card_batch_span():
    """合批流水 label：带章号区间；单章批同号合并；旧账行（无区间后缀）回落阶段名。"""
    from deconstruct.service import _unit_label

    assert _unit_label("card_batch", "", "abc123:17-32") == "拆卡合批·第17-32章"
    assert _unit_label("card_batch", "", "abc123:5-5") == "拆卡合批·第5章"
    assert _unit_label("card_batch", "", "deadbeef") == "拆卡合批"
    assert _unit_label("card", "", "137") == "第137章"


def test_monitor_sweep_running_on_finish(client):
    """终局清扫：running 残留（取消/熔断余波）→ failed(cancelled)，防在途账虚高。"""
    from deconstruct.pipeline import _sweep_running
    from deconstruct.service import source_path_of

    async def _go():
        async with async_session() as s:
            s.add(DeconstructJob(
                id="dec-mon-4", user_id=_UID, status="cancelled", queue_seq=96,
                book_name="清扫书", source_path=source_path_of("dec-mon-4"),
                encoding="utf-8", api_config_id="cfg-1", ai_model="m1",
            ))
            await s.commit()

    _run(_go())
    _mk_unit("dec-mon-4", "l1", "running", updated_min_ago=0.1, dim="world")
    _mk_unit("dec-mon-4", "card", "done", updated_min_ago=1.0)
    _run(_sweep_running("dec-mon-4"))
    d = client.get("/api/deconstruct/tasks/dec-mon-4").json()
    assert d["monitor"] is None  # 终态无监控块
    from sqlalchemy import select  # noqa: E402

    from models.deconstruct import DeconstructUnit as U  # noqa: E402

    async def _rows():
        async with async_session() as s:
            return [
                (r.stage, r.status, r.error_kind)
                for r in (await s.execute(select(U))).scalars().all()
            ]

    rows = {st: (status, kind) for st, status, kind in _run(_rows())}
    assert rows["l1"] == ("failed", "cancelled")
    assert rows["card"] == ("done", "")


def test_monitor_view_absent_for_terminal(client):
    """终态 monitor=None；排队态有账块（空账归零）。"""
    from deconstruct.service import source_path_of

    async def _go():
        async with async_session() as s:
            s.add(DeconstructJob(
                id="dec-mon-2", user_id=_UID, status="completed", queue_seq=98,
                book_name="完书", source_path=source_path_of("dec-mon-2"),
                encoding="utf-8", api_config_id="cfg-1", ai_model="m1",
                products_json="{}",
            ))
            s.add(DeconstructJob(
                id="dec-mon-3", user_id=_UID, status="queued", queue_seq=97,
                book_name="排队书", source_path=source_path_of("dec-mon-3"),
                encoding="utf-8", api_config_id="cfg-1", ai_model="m1",
            ))
            await s.commit()

    _run(_go())
    assert client.get("/api/deconstruct/tasks/dec-mon-2").json()["monitor"] is None
    m = client.get("/api/deconstruct/tasks/dec-mon-3").json()["monitor"]
    assert m is not None and m["speed"]["total"] == 0 and m["recent"] == []
    assert m["speed"]["avg_ms"] is None and m["batches"] == {"done": 0, "total": 0}


def _import_style(client, task_id: str, data: dict, book_name: str = "文风书") -> dict:
    _mk_completed(task_id, {
        "style": _product("style", "写作文风.md", data, "# 写作文风"),
    }, book_name=book_name)
    r = client.post(f"/api/deconstruct/tasks/{task_id}/import-book", json={"items": ["style"]})
    assert r.status_code == 200, r.text
    return r.json()


def _read_style(book_id: str) -> dict:
    async def _go():
        from filesystem.paths import KEY_TO_PATH
        from filesystem.storage import get_storage
        from models.project import Novel
        from settings.style_model import read_style

        async with async_session() as s:
            n = await s.get(Novel, book_id)
        raw = await get_storage().read_yaml(n.root_path, KEY_TO_PATH["style"])
        return read_style(raw)

    return _run(_go())


def test_import_style_legacy_features_and_evidence(client):
    """旧提示词包产物（narration/dialogue/rhythm＋features）双认：
    features→craft 不丢；role 只取第一句；证据章标不进文风设定（会注入写作提示词）。"""
    body = _import_style(client, "dec-style-legacy", {
        "narration": "全书采用第一人称限知视角，紧贴司机李耀，恐惧靠生理细节外化（第76章）。第二句不该进身份。",
        "dialogue": "对话是信息推进主力（第12章）。东北方言腔浓重，人物声口区分度高（第3、9章）。",
        "rhythm": "日常烟火气与灵异惊悚双线交替【第20章】。章末必留钩子（第1-258章）。",
        "features": [
            {"name": "第一人称限知口述体", "example": "以『我』的所见所感叙述（第2章）",
             "evidence_ch": "第1-258章", "confidence": "high"},
            {"name": "章末惊悚钩子", "example": "结尾短句急转留悬念",
             "evidence_ch": "第19章", "confidence": "high"},
        ],
    }, book_name="旧文风书")
    style = _read_style(body["book_id"])
    assert style["role"] == "全书采用第一人称限知视角，紧贴司机李耀，恐惧靠生理细节外化。"
    assert "第二句不该进身份" not in style["role"]
    assert "对话：对话是信息推进主力。东北方言腔浓重，人物声口区分度高。" in style["rules"]
    assert "节奏：日常烟火气与灵异惊悚双线交替。章末必留钩子。" in style["rules"]
    assert "第一人称限知口述体：以『我』的所见所感叙述" in style["craft"]
    assert "章末惊悚钩子：结尾短句急转留悬念" in style["craft"]
    joined = "".join([style["role"], *style["rules"], *style["craft"]])
    for mark in ("第76章", "第12章", "第3、9章", "第2章", "第1-258章"):
        assert mark not in joined


def test_import_style_accepts_string_and_single_object(client):
    """模型把数组写成字符串/单对象时按一条处理——逐字符迭代会产出一串单字条目。"""
    body = _import_style(client, "dec-style-shape", {
        "role": "第一人称限知。另有第二句。",
        "rules": "短句为主，少用长句（第4章）",
        "craft": {"name": "雨意象", "how": "以雨串场（第7章）"},
    }, book_name="形状容错书")
    style = _read_style(body["book_id"])
    assert style["role"] == "第一人称限知。"
    assert style["rules"] == ["短句为主，少用长句"]
    assert style["craft"] == ["雨意象：以雨串场"]


def test_import_style_empty_product_keeps_seeded_defaults(client):
    """产物为空不写空数组：新书种子的默认硬约束/手法保留，文风页不被清空。"""
    body = _import_style(client, "dec-style-empty", {}, book_name="空文风书")
    assert any("写作文风产物为空" in w for w in body["warnings"])
    style = _read_style(body["book_id"])
    assert style["role"].strip()
    assert style["rules"] and style["craft"]


def test_render_md_style_role_label():
    """文风产物的 role 是「叙事身份」，不能沿用角色卡的「定位」标签。"""
    from deconstruct.mdrender import render_md

    md = render_md(
        "写作文风",
        {"role": "第三人称限知，紧贴李耀", "rules": [{"name": "短对话", "how": "对峙用短句"}]},
        "书名",
        "第1-258章",
    )
    assert "\n## 叙事身份\n" in md
    assert "\n## 定位\n" not in md


def test_import_all_dimensions_contract_safe(client, monkeypatch):
    """全维度建书契约：多主角/同对多关系不中断；证据不进设定；丢字段有映射或留痕。"""
    from deconstruct import apply as apply_mod

    async def _no_condense(task, body, warnings):
        warnings.append("verify: skip condense")

    monkeypatch.setattr(apply_mod, "_condense_world", _no_condense)

    products = {
        "intro": _product("intro", "简介.md", {
            "intro": "公交司机李耀被强派夜班（第1章—第258章）。",
        }, "# 简介"),
        "genre": _product("genre", "题材.md", {
            "genre": "灵异志怪",
            "tags": ["灵异"],
            "promise": "带读者进入鬼怪世界（第1、10章）。",
        }, "# 题材"),
        "world": _product("world", "世界设定.md", {
            "no_power": "有超凡设定",
            "stage": "北方某市（第1章）",
            "power": [{"name": "鬼魂", "rule": "人死后成鬼（第45章）"}],
            "cost": [{"name": "绑定", "rule": "离开即死（第20章）"}],
            "history": [{"name": "旧案", "note": "三任司机出事（第1章），confidence: low，note: 分歧"}],
            "factions": [{"name": "公交公司", "note": "队长强派（第1章）"}],
            "constraints": [{"name": "必须开车", "note": "不能辞职（第20章）"}],
            "extra": [{"key": "13路", "value": "夜班郊区线（第4章）"}],
        }, "# 世界设定"),
        "mainplot": _product("mainplot", "主线剧情.md", {
            "fullstory": "李耀被强派夜班（第1-3章），一路查到真相（第258章）。",
            "ending": {"scene": "末班车驶向黎明（第258章）", "hero": "原文未明确", "tone": "开放"},
        }, "# 主线"),
        "style": _product("style", "写作文风.md", {
            "role": "第一人称限知叙述（第1章）",
            "rules": [{"name": "短句急收", "how": "惊悚段用短句加速，如第10、71章"}],
            "craft": [{"name": "反差写法", "how": "轻松段与惊悚段对照，如第3章"}],
            "examples": [
                {"example": "我心里一紧。", "evidence_ch": "第2章"},
                {"example": "他脚下没有影子。", "evidence_ch": "第75章"},
            ],
            "taboo": [{"name": "全知视角", "how": "始终锁在第一人称限知，原文未明确反例"}],
        }, "# 文风"),
        "characters": _product("characters", "角色设定.md", {"characters": [
            {"name": "李耀", "aliases": ["小李"], "role": "主角", "persona": "夜班司机",
             "background": "原文未明确", "plot": "被强派开末班车（第1章）", "evidence_ch": "第1章"},
            {"name": "老吴", "aliases": ["吴队"], "role": "主角", "persona": "队长",
             "background": "公交公司队长", "plot": "强派李耀开车（第1章）", "evidence_ch": "第1章"},
            {"name": "白帆", "aliases": [], "role": "核心", "persona": "HR",
             "background": "六叔孙女", "plot": "与李耀相识（第3章）", "evidence_ch": "第3章"},
        ]}, "# 角色"),
        "relations": _product("relations", "人物关系.md", {"edges": [
            {"from": "李耀", "to": "老吴", "rel_type": "同僚", "stance": "服从但怀疑",
             "note": "强派开车（第1章）", "evidence_ch": "第1章"},
            {"from": "小李", "to": "吴队", "rel_type": "恩义", "stance": "求助后信任破裂",
             "note": "多次指路（第2章）", "evidence_ch": "第2章"},
        ]}, "# 关系"),
        "structure": _product("structure", "章卷结构.md", {"volumes": [
            {"title": "原文未明确（材料仅见第1-258章未分卷）", "ch_range": "第1-258章"},
        ]}, "# 章卷"),
        "foreshadow": _product("foreshadow", "伏笔.md", {"hooks": [
            {"desc": "三任司机冲水库（第1章）", "note": "取档案见日期都是十五（第10章）",
             "type": "mystery", "priority": "high", "plant_ch": 1, "payoff_ch": 10,
             "status": "paid", "confidence": "high"},
        ]}, "# 伏笔"),
        "techniques": _product("techniques", "写作技法.md", {
            "techniques": [{
                "name": "身份悬念翻转",
                "repro_steps": ["让读者以为某角色是活人（第3章）", "用第三方证词翻转（第6章）"],
                "emotion_chain": ["怀疑", "惊悚", "反转快感"],
            }],
            "borrowable": [{"item": "开篇用门卫惊恐定格收章（第1章）"}],
            "avoid": [{"item": "靠第三方转告交付关键信息（第164章）"}],
            "reader_needs": [{"need": "身份悬念", "how": "层层翻转"}],
        }, "# 技法"),
    }
    _mk_completed("dec-contract-all", products, book_name="契约书")
    r = client.post(
        "/api/deconstruct/tasks/dec-contract-all/import-book",
        json={"items": list(apply_mod.IMPORT_ITEM_KEYS)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    bid = body["book_id"]
    warnings = body["warnings"]
    assert any("2 个主角" in w for w in warnings)
    assert any("关系边按角色对合并" in w for w in warnings)

    async def _check():
        from sqlalchemy import select

        from filesystem.paths import KEY_TO_PATH
        from filesystem.storage import get_storage
        from models.character import Character, CharacterRelation
        from models.hook import NovelHook
        from models.novel_genre import (
            NovelGenre,
            NovelGenreBattlefield,
            NovelGenreForbidden,
        )
        from models.project import Novel
        from models.volume import Volume
        from settings.style_model import read_style

        async with async_session() as s:
            n = await s.get(Novel, bid)
            chars = (await s.execute(select(Character).where(Character.novel_id == bid))).scalars().all()
            rels = (await s.execute(select(CharacterRelation).where(CharacterRelation.novel_id == bid))).scalars().all()
            vols = (await s.execute(select(Volume).where(Volume.project_id == bid))).scalars().all()
            hooks = (await s.execute(select(NovelHook).where(NovelHook.novel_id == bid))).scalars().all()
            ng = await s.get(NovelGenre, bid)
            forbids = (await s.execute(
                select(NovelGenreForbidden).where(NovelGenreForbidden.novel_id == bid)
                .order_by(NovelGenreForbidden.sort)
            )).scalars().all()
            fields = (await s.execute(
                select(NovelGenreBattlefield).where(NovelGenreBattlefield.novel_id == bid)
                .order_by(NovelGenreBattlefield.sort)
            )).scalars().all()
        storage = get_storage()
        story = await storage.read_yaml(n.root_path, KEY_TO_PATH["story"])
        world = await storage.read_yaml(n.root_path, KEY_TO_PATH["world"])
        style = read_style(await storage.read_yaml(n.root_path, KEY_TO_PATH["style"]))
        return story, world, style, chars, rels, vols, hooks, ng, forbids, fields

    story, world, style, chars, rels, vols, hooks, ng, forbids, fields = _run(_check())

    # 题材/简介：02–05 全字段都要有值
    assert story["genre"] == "灵异志怪"
    assert story["synopsis"] == "公交司机李耀被强派夜班。"
    assert ng is not None and ng.promise_note == "带读者进入鬼怪世界。"
    assert ng.core_promise and ng.cost_ratio == 8
    assert [f.vocab_id for f in forbids] == [
        "forbidden:no-deus-ex-machina", "forbidden:no-villain-idiot",
    ]
    assert [f.vocab_id for f in fields] == [
        "battlefield:truth", "battlefield:external-enemy",
    ]

    # 世界：extra 形状修好；自由文本无证据/confidence
    assert world["extra"] == [{"key": "13路", "value": "夜班郊区线"}]
    assert world["power"] == "鬼魂：人死后成鬼"
    assert world["history"][0]["value"] == "三任司机出事"
    assert "confidence" not in world["history"][0]["value"]

    # 主线
    assert story["story_arc"]["fullstory"] == "李耀被强派夜班，一路查到真相。"
    assert story["story_arc"]["ending"] == {"scene": "末班车驶向黎明", "hero": "", "tone": "开放"}

    # 角色：多主角降级；plot 保留一条 evidence，其余格不留原文未明确
    roles = {c.name: c.role for c in chars}
    assert roles["李耀"] == "主角" and roles["老吴"] == "配角" and roles["白帆"] == "配角"
    dossier = json.loads(chars[0].dossier)
    assert dossier.get("background", "") == ""
    assert dossier["plot"].endswith("（第1章）")
    assert "（第1章）" not in dossier["plot"].removesuffix("（第1章）")

    # 关系：同对多关系合并成一条，ch_ref 保留证据
    assert len(rels) == 1
    assert rels[0].rel_type == "同僚、恩义"
    assert rels[0].ch_ref == "第1章、第2章"
    assert "强派开车" in rels[0].note and "多次指路" in rels[0].note

    # 文风：三区/示范段/taboo；自由文本无证据（例句改投 style_samples，c-deconstruct-style-transfer）
    assert style["role"] == "第一人称限知叙述"
    assert "短句急收：惊悚段用短句加速" in style["rules"]
    assert "避免全知视角：始终锁在第一人称限知" in style["rules"]
    assert "反差写法：轻松段与惊悚段对照" in style["craft"]
    assert style["style_samples"] == ["我心里一紧。", "他脚下没有影子。"]
    assert not style.get("few_shot_examples")  # 例句提炼专属键不再被拆书写入
    artifact = re.compile(
        r"(?:【[^】]{0,50}章】|[（(][^）)]*第\s*[0-9][0-9,，、\-—~～至\s]*章[^）)]*[）)]"
        r"|第\s*[0-9][0-9,，、\-—~～至\s]*章|原文未明确|confidence|evidence_ch)",
        re.IGNORECASE,
    )
    for text in [style["role"], *style["rules"], *style["craft"], *style["style_samples"]]:
        assert artifact.search(text) is None, text

    # 技法：repro_steps 组成 how；borrowable→craft；avoid→rules
    assert any(r.startswith("身份悬念翻转：让读者以为某角色是活人") for r in style["rules"])
    assert any("情绪链：怀疑→惊悚→反转快感" in r for r in style["rules"])
    assert "开篇用门卫惊恐定格收章" in style["craft"]
    assert any(r.startswith("避免：靠第三方转告") for r in style["rules"])

    # 章卷：原文未明确的标题交给服务端兜底
    assert len(vols) == 1 and vols[0].title == "第1卷" and vols[0].summary == "第1-258章"

    # 伏笔：note 并入描述，埋设/回收章保留
    assert len(hooks) == 1
    assert "取档案见日期都是十五" in hooks[0].description
    assert "埋设于第1章" in hooks[0].description and "收于第10章" in hooks[0].description
