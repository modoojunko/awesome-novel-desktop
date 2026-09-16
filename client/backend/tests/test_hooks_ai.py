"""伏笔 AI 端点测试（foreshadow-settings-v2 批2 tasks 6.1 / 批3 tasks 8.1）。

覆盖 POST /api/novels/{id}/settings/ai/hooks/{action}：
- draft：出参归一（type 非法降 mystery / priority 非法降 2 / 空描述丢弃）、
  无简介 400、免费 403 member_required、超时 502 + `settings_hooks_draft_fail` 记账
- audit：四类点名（超期 miss / 在期 ok / 未定期 warn / 无留痕 warn）各一断言、
  出参 status 白名单与 goto_field 合法性、模型只产 note（id/状态以服务端为准）、
  无章纲降级免调用、无活跃伏笔降级免调用
- payoff（批3）：出参形状 {resolved_chapter_ref（canonical 归一）, payoff_note}、
  作用域 400（无 hook id / 无描述 / 缺主线）、坏 ref 502、超时记账
- check（批3）：world_check 同款三上下文、三方全缺降级免调用、缺输入行强制置
  miss＋补填出口、status 白名单同 audit、成功记账
- 通用：未知 action 400、旧路径 description 400 退役文案、坏 JSON 502、404

用法：
    cd client/backend
    .venv/bin/python -m pytest tests/test_hooks_ai.py -v
"""

import asyncio
import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# ── Test environment (isolated temp DB) ───────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_hooks_ai.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_hooks_ai_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")
# 占位 Key（非真实凭据）：拼接构造，避免任何真实密钥形态的字面量
_FAKE_KEY = "".join(("sk-", "test-placeholder"))  # noqa: FLY002


def _set_tier(tier: str, expires_at: str = "", api_key: str = ""):
    _service.CONFIG_FILE = _CFG_PATH
    cfg = _service.get_local_config()
    cfg.update({"tier": tier, "expires_at": expires_at, "api_key": api_key})
    _service.save_local_config(cfg)


def _future_iso(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


from auth_local.deps import require_novel_model
from auth_local.middleware import get_current_user
from db import Base, async_session, engine, get_db
from main import app
from models.user import User


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
    _run_async(_create_user("hkai"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "hkai"}


@pytest.fixture(autouse=True)
def _setup_overrides():
    # 不覆盖 require_ai_access：AI 端点要测真实会员门控
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_novel_model] = lambda: True
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_config():
    yield
    if os.path.exists(_CFG_PATH):
        os.remove(_CFG_PATH)


@pytest.fixture
def client():
    # 默认会员 + 占位 Key（AI happy path 可过门控；AI client 由各用例打桩）
    _set_tier("monthly", _future_iso(), api_key=_FAKE_KEY)
    with TestClient(app) as c:
        yield c


def _create_project(client) -> str:
    import uuid

    r = client.post("/api/novels", json={"name": f"hkai-{uuid.uuid4().hex[:6]}"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _seed_chapters(novel_id: str, written: int = 5, total: int = 6) -> list[str]:
    """种两卷章行：前 written 章章纲已写（outline_status=filled + summary），
    其后章 outline_status=unfilled。返回章 id 列表（书序）。"""
    from models.chapter import Chapter
    from models.volume import Volume

    async def _seed():
        async with async_session() as session:
            vol1 = Volume(project_id=novel_id, volume_no=1, title="第一卷")
            session.add(vol1)
            await session.flush()
            ids = []
            for no in range(1, total + 1):
                filled = no <= written
                ch = Chapter(
                    project_id=novel_id,
                    volume_id=vol1.id,
                    chapter_no=no,
                    ref=f"vol-1-ch-{no}",
                    title=f"第{no}章",
                    status="outline",
                    outline_status="filled" if filled else "unfilled",
                    summary=f"第{no}章概要：林拾追查残卷。" if filled else None,
                )
                session.add(ch)
                await session.flush()
                ids.append(ch.id)
            await session.commit()
            return ids

    return _run_async(_seed())


def _add_hook(novel_id: str, **fields) -> str:
    from settings import hooks_service as svc

    async def _add():
        async with async_session() as session:
            h = await svc.create_hook(session, novel_id, fields)
            return h.id

    return _run_async(_add())


class _FakeAI:
    def __init__(self, text: str):
        self._text = text
        self.calls: list[dict] = []

    async def chat(self, **kw):
        self.calls.append(kw)
        return self._text


@pytest.fixture
def stub_ai(monkeypatch):
    """打桩 AI 客户端；返回 fake 供断言（如调用是否发生、prompt 内容）。"""

    def _stub(text: str):
        import settings.ai_router as air

        fake = _FakeAI(text)

        async def get_client(novel_id=None):
            return fake

        monkeypatch.setattr(air, "get_ai_client_for_novel", get_client)
        return fake

    return _stub


# ── 门控与通用 ─────────────────────────────────────────────────────────────


class TestHooksAiGate:
    def test_free_user_403(self, client):
        pid = _create_project(client)
        _set_tier("none", api_key=_FAKE_KEY)
        for action in ("draft", "payoff", "audit", "check"):
            r = client.post(f"/api/novels/{pid}/settings/ai/hooks/{action}", json={})
            assert r.status_code == 403, (action, r.text)
            assert r.json()["detail"]["reason"] == "member_required"

    def test_unknown_action_400(self, client):
        pid = _create_project(client)
        r = client.post(f"/api/novels/{pid}/settings/ai/hooks/bogus", json={})
        assert r.status_code == 400

    def test_retired_description_400(self, client):
        """旧单字段路径 /ai/hooks/description → 400 专门退役文案（tasks 9.1）。"""
        pid = _create_project(client)
        r = client.post(f"/api/novels/{pid}/settings/ai/hooks/description", json={})
        assert r.status_code == 400
        assert "退役" in r.json()["detail"]

    def test_404_project(self, client):
        r = client.post("/api/novels/no-such/settings/ai/hooks/draft", json={})
        assert r.status_code == 404

    def test_bad_json_502(self, client, stub_ai):
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "有简介"})
        stub_ai("这不是 JSON")
        r = client.post(f"/api/novels/{pid}/settings/ai/hooks/draft", json={})
        assert r.status_code == 502


# ── draft：出参归一 / 前置缺项 400 / 超时记账 ──────────────────────────────


class TestHooksDraft:
    def test_missing_synopsis_400(self, client):
        pid = _create_project(client)
        r = client.post(f"/api/novels/{pid}/settings/ai/hooks/draft", json={})
        assert r.status_code == 400
        assert "简介" in r.json()["detail"]

    def test_output_normalization(self, client, stub_ai):
        """出参归一：非法 type 降 mystery、非法 priority 降 2（中）、空描述丢弃。"""
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "陆征是私家侦探，姐姐找他查妹妹失踪。"})
        stub_ai(
            '{"candidates": ['
            '{"description": "姐姐失踪前留下的半张车票", "type": "clue", "priority": "low"},'
            '{"description": "警队内部有人压下旧案", "type": "horror", "priority": 9},'
            '{"description": "", "type": "promise", "priority": 1},'
            '{"description": "旧卷宗编号被人划掉", "type": "mystery", "priority": "高"}'
            "]}"
        )
        r = client.post(f"/api/novels/{pid}/settings/ai/hooks/draft", json={})
        assert r.status_code == 200, r.text
        cands = r.json()["candidates"]
        # 空描述丢弃 → 3 条；非法 type/priority 降默认
        assert len(cands) == 3
        assert cands[0] == {"description": "姐姐失踪前留下的半张车票", "type": "clue", "priority": 3}
        assert cands[1]["type"] == "mystery"
        assert cands[1]["priority"] == 2
        assert cands[2]["priority"] == 1  # 「高」归一 Integer

    def test_all_invalid_candidates_502(self, client, stub_ai):
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "有简介"})
        stub_ai('{"candidates": [{"description": "", "type": "clue", "priority": 1}]}')
        r = client.post(f"/api/novels/{pid}/settings/ai/hooks/draft", json={})
        assert r.status_code == 502

    def test_more_than_three_clamped(self, client, stub_ai):
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "有简介"})
        stub_ai(
            '{"candidates": ['
            + ",".join(
                f'{{"description": "候选{i}", "type": "clue", "priority": 2}}' for i in range(5)
            )
            + "]}"
        )
        r = client.post(f"/api/novels/{pid}/settings/ai/hooks/draft", json={})
        assert r.status_code == 200
        assert len(r.json()["candidates"]) == 3

    def test_timeout_records_fail(self, monkeypatch, client):
        """超时 502 + `settings_hooks_draft_fail` 记账（零 token 也留痕）。"""
        from sqlalchemy import select

        from ai_client import AITimeoutError
        from models.token_log import TokenLog

        class _TimeoutClient:
            async def chat(self, **kw):
                raise AITimeoutError("AI 服务连接超时或失败")

        async def _failing(novel_id=None):
            return _TimeoutClient()

        monkeypatch.setattr("settings.ai_router.get_ai_client_for_novel", _failing)
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "测试前提"})
        resp = client.post(f"/api/novels/{pid}/settings/ai/hooks/draft", json={})
        assert resp.status_code == 502, resp.text
        assert "超时" in resp.json()["detail"]

        async def _rows():
            async with async_session() as session:
                result = await session.execute(
                    select(TokenLog).where(TokenLog.project_id == pid)
                )
                return list(result.scalars())

        rows = _run_async(_rows())
        assert [r.operation for r in rows] == ["settings_hooks_draft_fail"]
        assert rows[0].tokens_in == 0 and rows[0].tokens_out == 0

    def test_success_records_usage(self, client):
        """成功调用落 `settings_hooks_draft` 记账（token 逐条落库）。"""
        from unittest import mock

        from sqlalchemy import select

        from models.token_log import TokenLog

        class _UsageAI(_FakeAI):
            async def chat(self, **kw):
                kw["usage"]["tokens_in"] = 11
                kw["usage"]["tokens_out"] = 7
                return self._text

        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "有简介"})

        import settings.ai_router as air

        fake = _UsageAI('{"candidates": [{"description": "甲", "type": "clue", "priority": 2}]}')

        async def get_client(novel_id=None):
            return fake

        with mock.patch.object(air, "get_ai_client_for_novel", get_client):
            r = client.post(f"/api/novels/{pid}/settings/ai/hooks/draft", json={})
        assert r.status_code == 200, r.text

        async def _rows():
            async with async_session() as session:
                result = await session.execute(
                    select(TokenLog).where(TokenLog.project_id == pid)
                )
                return list(result.scalars())

        rows = _run_async(_rows())
        assert [r.operation for r in rows] == ["settings_hooks_draft"]
        assert rows[0].tokens_in == 11 and rows[0].tokens_out == 7


# ── audit：四类点名 / 白名单 / 降级免调用 ──────────────────────────────────

_AUDIT_OK = '{"reasons": [{"no": 1, "reason": "第4章旧案听证正适合收"}, {"no": 2, "reason": "还剩两章余量"}, {"no": 3, "reason": "按章纲节奏定在第6章"}, {"no": 4, "reason": "补一句怎么收的"}]}'


class TestHooksAudit:
    def _seed_full(self, client) -> tuple[str, list[str]]:
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "陆征查旧案。"})
        ch_ids = _seed_chapters(pid, written=5, total=6)
        # ① 超期：计划收束章（第2章，已写）已过还没收
        h_overdue = _add_hook(pid, description="第2章许下的 verification 之约", planned_chapter_id=ch_ids[1])
        # ② 在期：计划第6章（未写）→ ok
        h_ontrack = _add_hook(pid, description="第6章的摊牌局", planned_chapter_id=ch_ids[5])
        # ③ 未定期：无计划
        h_noplan = _add_hook(pid, description="没人解释过钟声为谁而响")
        # ④ 无留痕：已收束但没留「怎么收的」
        h_noreceipt = _add_hook(
            pid, description="半张地图的另一半", status="resolved", payoff_note=""
        )
        # 已收束且留痕齐全（收束章＋怎么收的）→ 不点名
        _add_hook(
            pid,
            description="留痕齐全的旧线",
            status="resolved",
            payoff_note="用假死收束",
            resolved_chapter_id=ch_ids[4],
        )
        return pid, [h_overdue, h_ontrack, h_noplan, h_noreceipt]

    def test_four_categories_and_whitelist(self, client, stub_ai):
        pid, hook_ids = self._seed_full(client)
        stub_ai(_AUDIT_OK)
        r = client.post(f"/api/novels/{pid}/settings/ai/hooks/audit", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["degraded"] is False
        checks = data["checks"]
        # 四类点名各一（留痕齐全的那条不进名单）
        assert [c["hook_id"] for c in checks] == hook_ids
        by_id = {c["hook_id"]: c for c in checks}
        # ① 超期 → miss，跳计划收束字段
        assert by_id[hook_ids[0]]["status"] == "miss"
        assert by_id[hook_ids[0]]["goto_field"] == "planned"
        # ② 在期 → ok，无需跳转
        assert by_id[hook_ids[1]]["status"] == "ok"
        assert by_id[hook_ids[1]]["goto_field"] is None
        # ③ 未定期 → warn，跳计划收束字段
        assert by_id[hook_ids[2]]["status"] == "warn"
        assert by_id[hook_ids[2]]["goto_field"] == "planned"
        # ④ 无留痕 → warn，跳收束记录字段
        assert by_id[hook_ids[3]]["status"] == "warn"
        assert by_id[hook_ids[3]]["goto_field"] == "payoff"
        # code 由服务端给出（#H-####），与 hooks 列表口径一致
        assert by_id[hook_ids[0]]["code"] == "#H-0001"
        # 出参白名单：status ∈ ok/warn/miss，goto ∈ planned/payoff/None
        for c in checks:
            assert c["status"] in ("ok", "warn", "miss")
            assert c["goto_field"] in ("planned", "payoff", None)
            assert c["note"]
        # 模型 note 被采纳（模型只产 note；id/状态以服务端为准）
        assert by_id[hook_ids[0]]["note"] == "第4章旧案听证正适合收"

    def test_model_garbage_falls_back_to_server_note(self, client, stub_ai):
        """模型编号写岔/缺行 → 该行回退服务端默认 note，点名不丢。"""
        pid, hook_ids = self._seed_full(client)
        stub_ai('{"reasons": [{"no": 99, "reason": "编不进的行"}, {"no": 1, "reason": "只有这条有效"}]}')
        r = client.post(f"/api/novels/{pid}/settings/ai/hooks/audit", json={})
        assert r.status_code == 200, r.text
        checks = {c["hook_id"]: c for c in r.json()["checks"]}
        assert checks[hook_ids[0]]["note"] == "只有这条有效"
        for hid in hook_ids[1:]:
            assert checks[hid]["note"], f"{hid} 缺默认 note"

    def test_no_outline_degrades_without_ai(self, client, stub_ai):
        """章纲未写 → 降级纯台账自检（点名 未定期/无留痕），零 AI 调用。"""

        class _Boom:
            async def chat(self, *a, **k):
                raise AssertionError("降级路径不得调用 AI")

        async def _fake(novel_id=None):
            return _Boom()

        from unittest import mock

        import settings.ai_router as air

        pid = _create_project(client)
        _add_hook(pid, description="没有计划的坑")
        _add_hook(pid, description="收了但没留痕", status="resolved", payoff_note="")
        _add_hook(pid, description="有计划的坑")
        with mock.patch.object(air, "get_ai_client_for_novel", _fake):
            r = client.post(f"/api/novels/{pid}/settings/ai/hooks/audit", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["degraded"] is True
        assert data["degraded_reasons"] == ["章纲还没写"]
        kinds = {(c["status"], c["goto_field"]) for c in data["checks"]}
        assert ("warn", "planned") in kinds and ("warn", "payoff") in kinds
        assert all(c["status"] != "ok" for c in data["checks"])  # 无章纲不判在期/超期
        assert "章纲" in data["verdict"]

    def test_no_active_hooks_degrades_without_ai(self, client, stub_ai):
        """无活跃伏笔（台账全空）→ 降级免调用，checks 空。"""

        class _Boom:
            async def chat(self, *a, **k):
                raise AssertionError("降级路径不得调用 AI")

        async def _fake(novel_id=None):
            return _Boom()

        from unittest import mock

        import settings.ai_router as air

        pid = _create_project(client)
        _seed_chapters(pid, written=2, total=2)  # 有章纲但没伏笔
        with mock.patch.object(air, "get_ai_client_for_novel", _fake):
            r = client.post(f"/api/novels/{pid}/settings/ai/hooks/audit", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["degraded"] is True
        assert data["degraded_reasons"] == ["还没有活跃伏笔"]
        assert data["checks"] == []
        assert "先埋一条" in data["verdict"]

    def test_audit_ignores_abandoned(self, client, stub_ai):
        """废弃条目不进体检（扫 active/resolved）。"""
        pid, _ = self._seed_full(client)
        _add_hook(pid, description="废弃的线", status="abandoned")
        stub_ai(_AUDIT_OK)
        r = client.post(f"/api/novels/{pid}/settings/ai/hooks/audit", json={})
        assert r.status_code == 200, r.text
        assert len(r.json()["checks"]) == 4

    def test_timeout_records_fail(self, monkeypatch, client):
        from sqlalchemy import select

        from ai_client import AITimeoutError
        from models.token_log import TokenLog

        class _TimeoutClient:
            async def chat(self, **kw):
                raise AITimeoutError("AI 服务连接超时或失败")

        async def _failing(novel_id=None):
            return _TimeoutClient()

        monkeypatch.setattr("settings.ai_router.get_ai_client_for_novel", _failing)
        pid, _ = self._seed_full(client)
        resp = client.post(f"/api/novels/{pid}/settings/ai/hooks/audit", json={})
        assert resp.status_code == 502, resp.text

        async def _rows():
            async with async_session() as session:
                result = await session.execute(
                    select(TokenLog).where(TokenLog.project_id == pid)
                )
                return list(result.scalars())

        rows = _run_async(_rows())
        assert [r.operation for r in rows] == ["settings_hooks_audit_fail"]


# ── payoff（批3）：出参形状 / 作用域 400 / ref 归一 / 记账 ──────────────────

_PAYOFF_OK = '{"resolved_chapter_ref": "1-3", "payoff_note": "第3章听证会上残卷笔迹对上，林拾当场对质"}'


def _seed_story_fields(novel_id: str, **fields) -> None:
    """直写 story.yaml（genre 等无独立测试端点的字段；read 侧同源）。"""
    from filesystem.storage import get_storage
    from novels.service import get_novel

    async def _write():
        async with async_session() as session:
            project = await get_novel(session, novel_id, "hkai")
        story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
        story.update(fields)
        await get_storage().write_yaml(project.root_path, "story.yaml", story)

    _run_async(_write())


def _seed_world(novel_id: str, data: dict) -> None:
    """直写 settings/world-setting.yaml（check 的世界侧输入）。"""
    from filesystem.storage import get_storage
    from novels.service import get_novel

    async def _write():
        async with async_session() as session:
            project = await get_novel(session, novel_id, "hkai")
        await get_storage().write_yaml(
            project.root_path, "settings/world-setting.yaml", data
        )

    _run_async(_write())


class TestHooksPayoff:
    def _seed(self, client) -> tuple[str, str]:
        pid = _create_project(client)
        r = client.put(
            f"/api/novels/{pid}/story/arc", json={"fullstory": "三幕：寻妹—揭盖—收网。"}
        )
        assert r.status_code in (200, 201), r.text
        hid = _add_hook(pid, description="姐姐失踪前留下的半张车票")
        return pid, hid

    def test_missing_hook_id_400(self, client):
        pid, _ = self._seed(client)
        r = client.post(
            f"/api/novels/{pid}/settings/ai/hooks/payoff", json={"description": "有描述"}
        )
        assert r.status_code == 400
        assert "先选一条伏笔" in r.json()["detail"]

    def test_missing_description_400(self, client):
        pid, hid = self._seed(client)
        r = client.post(
            f"/api/novels/{pid}/settings/ai/hooks/payoff",
            json={"hook_id": hid, "description": "   "},
        )
        assert r.status_code == 400
        assert "描述" in r.json()["detail"]

    def test_missing_fullstory_400(self, client):
        """缺主线 → 400 中文原因（收束方案要按全书走向定收束点）。"""
        pid = _create_project(client)
        hid = _add_hook(pid, description="半张车票")
        r = client.post(
            f"/api/novels/{pid}/settings/ai/hooks/payoff",
            json={"hook_id": hid, "description": "半张车票"},
        )
        assert r.status_code == 400
        assert "主线" in r.json()["detail"]

    def test_output_shape_and_ref_canonicalization(self, client, stub_ai):
        """出参 {resolved_chapter_ref, payoff_note}；模板短格式 ref 归一成规范形；
        prompt 作用域＝body 传的当前编辑值＋主线（intro 先例，不读库旧文）。"""
        pid, hid = self._seed(client)
        fake = stub_ai(_PAYOFF_OK)
        r = client.post(
            f"/api/novels/{pid}/settings/ai/hooks/payoff",
            json={
                "hook_id": hid,
                "description": "姐姐失踪前留下的半张车票",
                "type": "clue",
                "priority": "高",
                "code": "#H-0001",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json() == {
            "resolved_chapter_ref": "vol-1-ch-3",
            "payoff_note": "第3章听证会上残卷笔迹对上，林拾当场对质",
        }
        prompt = fake.calls[0]["messages"][0]["content"]
        assert "姐姐失踪前留下的半张车票" in prompt  # 当前编辑值进 prompt
        assert "三幕" in prompt  # 主线进 prompt
        assert "#H-0001" in prompt and "线索" in prompt and "高" in prompt

    def test_bad_ref_502(self, client, stub_ai):
        pid, hid = self._seed(client)
        stub_ai('{"resolved_chapter_ref": "第36章", "payoff_note": "在酒馆对上"}')
        r = client.post(
            f"/api/novels/{pid}/settings/ai/hooks/payoff",
            json={"hook_id": hid, "description": "半张车票"},
        )
        assert r.status_code == 502
        assert "vol-N-ch-M" in r.json()["detail"]

    def test_missing_note_502(self, client, stub_ai):
        pid, hid = self._seed(client)
        stub_ai('{"resolved_chapter_ref": "vol-1-ch-3", "payoff_note": ""}')
        r = client.post(
            f"/api/novels/{pid}/settings/ai/hooks/payoff",
            json={"hook_id": hid, "description": "半张车票"},
        )
        assert r.status_code == 502

    def test_timeout_records_fail(self, monkeypatch, client):
        """超时 502 + `settings_hooks_payoff_fail` 记账。"""
        from sqlalchemy import select

        from ai_client import AITimeoutError
        from models.token_log import TokenLog

        class _TimeoutClient:
            async def chat(self, **kw):
                raise AITimeoutError("AI 服务连接超时或失败")

        async def _failing(novel_id=None):
            return _TimeoutClient()

        monkeypatch.setattr("settings.ai_router.get_ai_client_for_novel", _failing)
        pid, hid = self._seed(client)
        resp = client.post(
            f"/api/novels/{pid}/settings/ai/hooks/payoff",
            json={"hook_id": hid, "description": "半张车票"},
        )
        assert resp.status_code == 502

        async def _rows():
            async with async_session() as session:
                result = await session.execute(
                    select(TokenLog).where(TokenLog.project_id == pid)
                )
                return list(result.scalars())

        rows = _run_async(_rows())
        assert [r.operation for r in rows] == ["settings_hooks_payoff_fail"]


# ── check（批3）：三上下文 / 降级免调用 / 白名单 / 记账 ─────────────────────

_CHECK_FULL = (
    '{"checks": ['
    '{"name": "简介", "status": "ok", "note": "车票在简介第一段有根"},'
    '{"name": "题材", "status": "warn", "note": "刑侦线偏日常，往悬疑靠"},'
    '{"name": "世界", "status": "miss", "note": "车票笔迹与世界铁律笔迹说矛盾"}'
    "]}"
)


class TestHooksCheck:
    def test_missing_hook_id_400(self, client):
        pid = _create_project(client)
        r = client.post(
            f"/api/novels/{pid}/settings/ai/hooks/check", json={"description": "有描述"}
        )
        assert r.status_code == 400
        assert "先选一条伏笔" in r.json()["detail"]

    def test_missing_description_400(self, client):
        pid = _create_project(client)
        hid = _add_hook(pid, description="半张车票")
        r = client.post(
            f"/api/novels/{pid}/settings/ai/hooks/check",
            json={"hook_id": hid, "description": ""},
        )
        assert r.status_code == 400
        assert "描述" in r.json()["detail"]

    def test_all_missing_degrades_without_ai(self, client):
        """三方全缺（简介/题材/世界）→ D7 降级免调用，全部行置 miss＋补填出口。"""

        class _Boom:
            async def chat(self, *a, **k):
                raise AssertionError("降级路径不得调用 AI")

        async def _fake(novel_id=None):
            return _Boom()

        from unittest import mock

        import settings.ai_router as air

        pid = _create_project(client)
        hid = _add_hook(pid, description="半张车票")
        with mock.patch.object(air, "get_ai_client_for_novel", _fake):
            r = client.post(
                f"/api/novels/{pid}/settings/ai/hooks/check",
                json={"hook_id": hid, "description": "半张车票"},
            )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["degraded"] is True
        assert data["degraded_reasons"] == ["简介未填", "题材未确认", "世界设定还空着"]
        assert [c["name"] for c in data["checks"]] == ["简介 × 伏笔", "题材 × 伏笔", "世界 × 伏笔"]
        assert all(c["status"] == "miss" for c in data["checks"])
        assert all("先去" in c["note"] for c in data["checks"])  # 每行都有补填出口
        assert "先补" in data["verdict"]

    def test_partial_missing_forces_miss_row(self, client, stub_ai):
        """部分缺输入 → AI 照常体检其余项；缺输入行强制置 miss（world_check D7 同款）。"""
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "陆征查旧案。"})
        _seed_story_fields(pid, genre="悬疑", sub_genre="社会派")
        # 世界设定不种 → 世界行该置 miss
        hid = _add_hook(pid, description="半张车票")
        stub_ai(_CHECK_FULL)
        r = client.post(
            f"/api/novels/{pid}/settings/ai/hooks/check",
            json={"hook_id": hid, "description": "半张车票"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["degraded"] is True
        assert data["degraded_reasons"] == ["世界设定还空着"]
        by_name = {c["name"]: c for c in data["checks"]}
        assert by_name["简介 × 伏笔"]["status"] == "ok"  # 其余项正常出判定
        assert by_name["题材 × 伏笔"]["status"] == "warn"
        assert by_name["世界 × 伏笔"]["status"] == "miss"  # 强制置 miss
        assert "世界设定还空着" in by_name["世界 × 伏笔"]["note"]  # 不采信模型对空输入的判定

    def test_whitelist_and_name_normalization(self, client, stub_ai):
        """status 白名单同 audit；模型回名「简介 × 伏笔」「世界×伏笔」都归一；
        status 写岔的行丢弃 → 回退「AI 未给出该项，可重试」。"""
        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "陆征查旧案。"})
        _seed_story_fields(pid, genre="悬疑")
        _seed_world(pid, {"stage": "九十年代滨江轮埠"})
        hid = _add_hook(pid, description="半张车票")
        stub_ai(
            '{"checks": ['
            '{"name": "简介 × 伏笔", "status": "ok", "note": "对得上"},'
            '{"name": "题材", "status": "特别差", "note": "非法状态应被丢弃"},'
            '{"name": "世界×伏笔", "status": "miss", "note": "笔迹与铁律矛盾"}'
            "]}"
        )
        r = client.post(
            f"/api/novels/{pid}/settings/ai/hooks/check",
            json={"hook_id": hid, "description": "半张车票"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["degraded"] is False
        by_name = {c["name"]: c for c in data["checks"]}
        assert by_name["简介 × 伏笔"] == {"name": "简介 × 伏笔", "status": "ok", "note": "对得上"}
        assert by_name["题材 × 伏笔"] == {
            "name": "题材 × 伏笔", "status": "miss", "note": "AI 未给出该项，可重试",
        }
        assert by_name["世界 × 伏笔"]["status"] == "miss"
        assert by_name["世界 × 伏笔"]["note"] == "笔迹与铁律矛盾"
        for c in data["checks"]:
            assert c["status"] in ("ok", "warn", "miss")

    def test_success_records_usage(self, client):
        """成功调用落 `settings_hooks_check` 记账（token 逐条落库）。"""
        from unittest import mock

        from sqlalchemy import select

        from models.token_log import TokenLog

        class _UsageAI(_FakeAI):
            async def chat(self, **kw):
                kw["usage"]["tokens_in"] = 9
                kw["usage"]["tokens_out"] = 5
                return self._text

        pid = _create_project(client)
        client.put(f"/api/novels/{pid}/story", json={"synopsis": "陆征查旧案。"})
        _seed_story_fields(pid, genre="悬疑")
        _seed_world(pid, {"stage": "九十年代滨江轮埠"})
        hid = _add_hook(pid, description="半张车票")

        import settings.ai_router as air

        fake = _UsageAI(_CHECK_FULL)

        async def get_client(novel_id=None):
            return fake

        with mock.patch.object(air, "get_ai_client_for_novel", get_client):
            r = client.post(
                f"/api/novels/{pid}/settings/ai/hooks/check",
                json={"hook_id": hid, "description": "半张车票"},
            )
        assert r.status_code == 200, r.text

        async def _rows():
            async with async_session() as session:
                result = await session.execute(
                    select(TokenLog).where(TokenLog.project_id == pid)
                )
                return list(result.scalars())

        rows = _run_async(_rows())
        assert [r.operation for r in rows] == ["settings_hooks_check"]
        assert rows[0].tokens_in == 9 and rows[0].tokens_out == 5
