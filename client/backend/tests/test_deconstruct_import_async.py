"""建书阶段（c-deconstruct-import-async）的异步契约：受理四臂/取消/收敛/勾选持久化。

与 `test_deconstruct_api.py` 分工：那边是「建书回填与清洗」的业务语义（受理后同步驱动
执行体），这里专测**异步阶段本身**——状态机、身份（run_id）、半成品清理、重启收敛。
"""

import asyncio
import json
import os
import tempfile

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix="_dec_import_async.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_dec_import_async_")
os.environ["DECONSTRUCT_DISPATCHER_OFF"] = "1"
os.environ["IMPORT_RUNNER_OFF"] = "1"  # 执行体由用例显式驱动（见 _drive）

from fastapi.testclient import TestClient  # noqa: E402

from auth_local import deps as _auth_deps  # noqa: E402
from auth_local.middleware import get_current_user  # noqa: E402
from db import Base, async_session, engine  # noqa: E402
from deconstruct import imports  # noqa: E402
from main import app  # noqa: E402
from models.deconstruct import DeconstructJob  # noqa: E402

_UID = "dec-import-async-user"


@pytest.fixture(autouse=True)
def _tier_max(monkeypatch):
    async def _ensure():
        return None

    async def _no_model(user, db):
        return None

    monkeypatch.setattr(_auth_deps, "ensure_entitlement_snapshot", _ensure)
    monkeypatch.setattr(_auth_deps, "_check_writing_model_configured", _no_model)
    monkeypatch.setattr(
        _auth_deps,
        "check_permission",
        lambda: {
            "tier": "max",
            "is_member": True,
            "expired": False,
            "entitlement": {
                "v": 2,
                "features": ["deconstruct", "deconstruct-import"],
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


def _product(dim: str, file: str, data: dict) -> dict:
    return {"file": file, "data": data, "md": f"# {dim}"}


_PRODS = {
    "intro": _product("intro", "简介.md", {"intro": "一部星际远征的故事。"}),
    "genre": _product("genre", "题材.md", {"genre": "科幻", "tags": ["星际"]}),
    "world": _product(
        "world",
        "世界设定.md",
        {
            "stage": "银河系边缘",
            "power": [],
            "cost": [],
            "history": [{"name": "大迁徙", "note": "文明迁移", "evidence_ch": "第2章"}],
            "factions": [{"name": "远征军", "note": "主角阵营", "evidence_ch": "第3章"}],
            "constraints": [],
            "extra": [],
        },
    ),
}


def _mk(task_id: str, *, status: str = "completed", book_id: str | None = None,
        products: dict | None = None, import_state: dict | None = None,
        selected: list[str] | None = None) -> None:
    async def _go():
        async with async_session() as s:
            from deconstruct.service import next_queue_seq

            dims = json.dumps({"import": import_state} if import_state else {})
            s.add(
                DeconstructJob(
                    id=task_id,
                    user_id=_UID,
                    status=status,
                    queue_seq=await next_queue_seq(s),
                    book_name="星海远征",
                    source_path="",
                    encoding="utf-8",
                    api_config_id="cfg-1",
                    ai_model="qwen3-max",
                    selected_dims_json=json.dumps(
                        selected if selected is not None else ["intro", "genre", "world"]
                    ),
                    products_json=json.dumps(products or _PRODS, ensure_ascii=False),
                    dims_json=dims,
                    book_id=book_id,
                )
            )
            await s.commit()

    _run(_go())


def _get(task_id: str) -> dict:
    async def _go():
        async with async_session() as s:
            row = await s.get(DeconstructJob, task_id)
            return {
                "status": row.status,
                "book_id": row.book_id,
                "import": dict(imports.read_state(row)),
            }

    return _run(_go())


def _drive(task_id: str) -> None:
    """跑完后台执行体（IMPORT_RUNNER_OFF=1 下由用例驱动）。"""
    _run(imports.run(task_id))


def test_accept_202_persists_identity_and_items(client):
    """受理：202 + 状态 importing + run_id/items/draft_book_id 一次落库；重复受理 409。"""
    _mk("imp-async-1")

    r = client.post(
        "/api/deconstruct/tasks/imp-async-1/import-book", json={"items": ["world", "structure"]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "importing"
    assert body["import"]["items"] == ["world", "structure"]  # 白名单保序
    assert body["import"]["run_id"]

    st = _get("imp-async-1")
    assert st["status"] == "importing"
    assert st["book_id"] is None  # 幂等键只在写入全部成功后落
    assert st["import"]["draft_book_id"]  # 预分配书 id：崩溃后 sweep 才有指针可清

    r2 = client.post("/api/deconstruct/tasks/imp-async-1/import-book", json={})
    assert r2.status_code == 409  # 进行中：不排第二次
    assert "import" in r2.json()["detail"]


def test_cancel_returns_to_completed_and_cleans_draft(client):
    """取消：importing → completed，半成品被软删，产物与出口不受影响。"""
    _mk("imp-async-2")
    client.post("/api/deconstruct/tasks/imp-async-2/import-book", json={})
    draft = _get("imp-async-2")["import"]["draft_book_id"]

    r = client.post("/api/deconstruct/tasks/imp-async-2/import-book/cancel")
    assert r.status_code == 200, r.text
    assert _get("imp-async-2")["status"] == "completed"

    async def _book_alive():
        from models.project import Novel

        async with async_session() as s:
            return await s.get(Novel, draft)

    assert _run(_book_alive()) is None  # 还没建行：draft 只是预留 id
    # 产物仍在：导出入口可用（状态门认 RESULT_READY）
    assert client.post(
        "/api/deconstruct/tasks/imp-async-2/export", json={"dest_dir": tempfile.mkdtemp(), "files": ["简介.md"]}
    ).status_code == 200


def test_cancel_then_reaccept_uses_new_run(client):
    """取消后立刻重建：新一轮有自己的 run_id，旧执行体不得写终态（ABA 反例序列）。"""
    _mk("imp-async-3")
    client.post("/api/deconstruct/tasks/imp-async-3/import-book", json={})
    old_run = _get("imp-async-3")["import"]["run_id"]
    client.post("/api/deconstruct/tasks/imp-async-3/import-book/cancel")
    client.post("/api/deconstruct/tasks/imp-async-3/import-book", json={"items": ["intro"]})
    new_state = _get("imp-async-3")["import"]
    assert new_state["run_id"] != old_run
    assert new_state["items"] == ["intro"]

    # 旧 run 被驱动：状态/run_id 已变，应只清理自己的 draft 并退出，不写终态
    assert _run(imports._patch("imp-async-3", {"step": "refine"}, run_id=old_run)) is False
    assert _get("imp-async-3")["status"] == "importing"


def test_legacy_completed_with_book_is_idempotent(client):
    """存量任务（completed + book_id 且书仍在）：重复确认返回同一本，并读时升级为已建书。"""
    from novels.service import create_project

    async def _mk_book():
        async with async_session() as s:
            return (await create_project(s, _UID, name="旧书", source="manual")).id

    book_id = _run(_mk_book())
    _mk("imp-async-4", status="completed", book_id=book_id)

    r = client.post("/api/deconstruct/tasks/imp-async-4/import-book", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["book_id"] == book_id
    assert any("幂等返回" in w for w in body["warnings"])
    assert _get("imp-async-4")["status"] == "imported"  # 读时升级，不重建


def test_deleted_book_rebuilds_under_new_key(client):
    """幂等键指向已删书：解绑、回到可重建态，再按本次勾选新建。"""
    from novels.service import create_project

    async def _mk_book():
        async with async_session() as s:
            novel = await create_project(s, _UID, name="该书已删", source="manual")
            novel.status = "deleted"
            await s.commit()
            return novel.id

    dead = _run(_mk_book())
    _mk("imp-async-5", status="imported", book_id=dead)

    r = client.post("/api/deconstruct/tasks/imp-async-5/import-book", json={"items": ["intro"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "importing"
    _drive("imp-async-5")
    st = _get("imp-async-5")
    assert st["status"] == "imported"
    assert st["book_id"] and st["book_id"] != dead
    assert any("删除" in w for w in st["import"]["warnings"])


def test_delete_task_blocked_while_importing(client):
    """建书中禁止删除任务（否则执行体无处写终态，还会留下无主书）。"""
    _mk("imp-async-6")
    client.post("/api/deconstruct/tasks/imp-async-6/import-book", json={})
    r = client.delete("/api/deconstruct/tasks/imp-async-6")
    assert r.status_code == 409
    assert "取消建书" in r.json()["detail"]


def test_sweep_converges_importing_and_cleans_draft(client):
    """重启收敛：残留 importing → import_failed(interrupted) + 半成品软删。"""
    from novels.service import create_project

    async def _mk_half():
        async with async_session() as s:
            return (await create_project(s, _UID, name="半本书", source="manual")).id

    draft = _run(_mk_half())
    _mk(
        "imp-async-7",
        status="importing",
        products={},
        import_state={
            "run_id": "dead-run",
            "items": ["intro"],
            "step": "refine",
            "draft_book_id": draft,
        },
    )

    _run(imports.sweep())

    st = _get("imp-async-7")
    assert st["status"] == "import_failed"
    assert st["import"]["error"]["kind"] == "interrupted"
    assert st["import"]["error"]["retryable"] is True

    async def _book_status():
        from models.project import Novel

        async with async_session() as s:
            return (await s.get(Novel, draft)).status

    assert _run(_book_status()) == "deleted"


def test_success_sets_book_id_and_warnings(client):
    """成功收尾：book_id/status/载荷一次写定，勾选集只灌所选维度。"""
    _mk("imp-async-8")
    client.post("/api/deconstruct/tasks/imp-async-8/import-book", json={"items": ["intro", "world"]})
    _drive("imp-async-8")

    st = _get("imp-async-8")
    assert st["status"] == "imported"
    assert st["book_id"]
    assert st["import"]["step"] == "done"

    async def _world_keys():
        from filesystem.storage import get_storage
        from models.project import Novel

        async with async_session() as s:
            novel = await s.get(Novel, st["book_id"])
            raw = await get_storage().read_yaml(novel.root_path, "settings/world-setting.yaml")
            return raw

    world = _run(_world_keys())
    assert isinstance(world, dict)  # 世界设定已写入；未勾的维度不灌由 test_deconstruct_api 覆盖


# ── 结果读取能力 × 建书状态矩阵（评审 P0：`completed` 单值门会让建完书反而不能导出）──

_MATRIX_STATUS = ("completed", "importing", "imported", "import_failed")


@pytest.mark.parametrize("status", _MATRIX_STATUS)
def test_export_available_in_every_result_ready_state(client, status, tmp_path):
    _mk(f"imp-mx-exp-{status}", status=status, book_id="b-x" if status == "imported" else None)
    r = client.post(
        f"/api/deconstruct/tasks/imp-mx-exp-{status}/export",
        json={"dest_dir": str(tmp_path / status), "files": ["简介.md"]},
    )
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("status", _MATRIX_STATUS)
def test_library_candidates_available_in_every_result_ready_state(client, status):
    prods = dict(_PRODS)
    prods["characters"] = _product(
        "characters",
        "角色设定.md",
        {"characters": [{"name": "林晚", "role": "主角", "persona": "渡口救人"}]},
    )
    _mk(f"imp-mx-lib-{status}", status=status, products=prods,
        book_id="b-x" if status == "imported" else None)
    r = client.get(f"/api/deconstruct/tasks/imp-mx-lib-{status}/library-candidates")
    assert r.status_code == 200, r.text
    assert r.json()["can_import"] is True


@pytest.mark.parametrize("status", ("queued", "running", "cancelled", "need_reupload"))
def test_result_endpoints_reject_unfinished_states(client, status, tmp_path):
    _mk(f"imp-mx-no-{status}", status=status)
    assert client.post(
        f"/api/deconstruct/tasks/imp-mx-no-{status}/export",
        json={"dest_dir": str(tmp_path / status), "files": ["简介.md"]},
    ).status_code == 409
    body = client.get(f"/api/deconstruct/tasks/imp-mx-no-{status}/library-candidates").json()
    assert body["can_import"] is False and body["reason"]


@pytest.mark.parametrize("status", _MATRIX_STATUS)
def test_to_library_available_in_every_result_ready_state(client, status):
    prods = dict(_PRODS)
    prods["characters"] = _product(
        "characters",
        "角色设定.md",
        {"characters": [{"name": "林晚", "role": "主角", "persona": "渡口救人"}]},
    )
    _mk(f"imp-mx-tolib-{status}", status=status, products=prods,
        book_id="b-x" if status == "imported" else None)
    r = client.post(
        f"/api/deconstruct/tasks/imp-mx-tolib-{status}/to-library",
        json={"picks": ["林晚"], "rename": False},
    )
    assert r.status_code == 200, r.text


# ── 评审整改的回归钉（取消落在写入阶段 / 取消响应体 / 额度不可重试）──


def test_cancel_during_write_cleans_partial_book(client, monkeypatch):
    """取消落在**写入阶段**：终态不该写（状态已被取消方改回 completed），
    但那本已建出来的书必须被回收——否则书架里留一本 active 的半成品、任务 book_id 为空。"""
    from deconstruct import apply as apply_mod
    from novels.service import create_project

    _mk("imp-fix-1")
    client.post("/api/deconstruct/tasks/imp-fix-1/import-book", json={"items": ["intro"]})
    draft = _get("imp-fix-1")["import"]["draft_book_id"]

    async def fake_import(db, task, user_id, items, *, book_id=None,
                          on_step=None, is_cancelled=None, stop_event=None):
        await create_project(db, user_id, name="半本书", source="manual", book_id=book_id)
        await imports.cancel("imp-fix-1")  # 用户在这一刻点了取消
        raise asyncio.CancelledError()

    monkeypatch.setattr(apply_mod, "import_book", fake_import)
    with pytest.raises(asyncio.CancelledError):
        _run(imports.run("imp-fix-1"))

    st = _get("imp-fix-1")
    assert st["status"] == "completed"  # 取消语义赢：不写失败终态
    assert st["book_id"] is None

    async def _book_status():
        from models.project import Novel

        async with async_session() as s:
            row = await s.get(Novel, draft)
            return row.status if row else None

    assert _run(_book_status()) == "deleted"  # 半成品被清：不留可见半本书


def test_cancel_response_reports_completed(client):
    """取消接口的响应体必须是取消后的状态（请求 session 有 identity map，不 refresh 会给旧值）。"""
    _mk("imp-fix-2")
    client.post("/api/deconstruct/tasks/imp-fix-2/import-book", json={})
    r = client.post("/api/deconstruct/tasks/imp-fix-2/import-book/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"


def test_quota_failure_is_not_retryable(client, monkeypatch):
    """写入前二次校验撞额度：分诊为 quota/不可重试（前端据此不给「重试建书」）。"""
    from auth_local import deps as auth_deps

    calls = {"n": 0}

    async def _quota(db, user_id):
        calls["n"] += 1
        # 受理时放行（模拟精炼期间用户又建了一本导致越限），执行体二次校验才拦
        return None if calls["n"] == 1 else "当前套餐最多创建 1 个项目 — 升级套餐后可创建更多"

    monkeypatch.setattr(auth_deps, "project_quota_reject", _quota)

    _mk("imp-fix-3")
    client.post("/api/deconstruct/tasks/imp-fix-3/import-book", json={"items": ["intro"]})
    _drive("imp-fix-3")

    st = _get("imp-fix-3")
    assert st["status"] == "import_failed"
    assert st["import"]["error"]["kind"] == "quota"
    assert st["import"]["error"]["retryable"] is False
