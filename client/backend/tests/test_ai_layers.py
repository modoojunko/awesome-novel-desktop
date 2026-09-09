"""AI 分层与题材/简介 AI 端点契约（genre-signup-redesign tasks 6.0/6.1/6.2/7.3）。

覆盖：
- 判定层 `compute_ai_state` 纯函数矩阵（含 R8 删除残留、O-8 存量错配）
- 解析层 `effective_model` / `parse_models` 容错
- 门控层 `require_novel_model`：ready 放行、其余 503 + detail.reason 同枚举、无书 404
- 绑定校验 `set_project_model`：不成对 400、model 不在列表 400、显式 clear 放行
- `GET /novels/{id}/ai-model` 下发 ai_state/effective_model
- 题材字段 AI：归一化（候选 slug 映射 / 自定义文本 / 数值 clamp / 非法 JSON 502 / 非法字段 400）
- 简介 AI：体检归一化兜底、补缺失、润色、非法 action 400
- 计量：operation 细分 + model 记实际本书模型
"""

import asyncio
import json
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

_tmp_db = tempfile.NamedTemporaryFile(suffix="_ai_layers.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_ai_layers_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from sqlalchemy import select  # noqa: E402

import auth_local.service as _service  # noqa: E402
from ai_state import compute_ai_state, effective_model, parse_models  # noqa: E402
from auth_local.deps import require_ai_access, require_novel_model  # noqa: E402
from auth_local.middleware import get_current_user  # noqa: E402
from db import Base, async_session, engine, get_db  # noqa: E402
from main import app  # noqa: E402
from models.api_config import ApiConfig  # noqa: E402
from models.project import Novel  # noqa: E402
from models.token_log import TokenLog  # noqa: E402
from models.user import User  # noqa: E402
from settings import ai_router  # noqa: E402

USER_ID = "ai_layers_user"
_CFG_PATH = os.path.join(_tmp_data_root, "config.json")


def _set_member():
    """会员态：ai_state 的 member_required 由门控层前置，本模块测的是模型链路。"""
    from datetime import UTC, datetime, timedelta

    _service.CONFIG_FILE = _CFG_PATH
    expires = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
    _service.save_local_config({"tier": "monthly", "expires_at": expires})


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeClient:
    """记录调用参数，返回预设文本。"""

    def __init__(self, text: str = "{}"):
        self.text = text
        self.last_kwargs: dict = {}

    async def chat(self, **kwargs):
        self.last_kwargs = kwargs
        usage = kwargs.get("usage")
        if usage is not None:
            usage["tokens_in"] = 10
            usage["tokens_out"] = 20
        return self.text


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session() as session:
            session.add(
                User(
                    id=USER_ID,
                    email=f"{USER_ID}@test.com",
                    password_hash="*",
                    display_name=USER_ID,
                )
            )
            await session.commit()

    _run_async(_create())
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": USER_ID}


async def _override_true():
    return True


@pytest.fixture(autouse=True)
def _setup_overrides():
    _set_member()
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_ai_access] = _override_true
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


async def _make_novel(
    ai_config_id: str | None = None, ai_model: str | None = None
) -> str:
    async with async_session() as session:
        novel = Novel(
            user_id=USER_ID,
            name=f"AI分层-{uuid.uuid4().hex[:8]}",
            slug=f"ai-layers-{uuid.uuid4().hex[:8]}",
            root_path=f"{_tmp_data_root}/ai-layers-{uuid.uuid4().hex[:8]}",
            ai_config_id=ai_config_id,
            ai_model=ai_model,
        )
        session.add(novel)
        await session.commit()
        await session.refresh(novel)
        return novel.id


async def _make_config(models: list[str] | None = None, key: str = "sk-x") -> str:
    async with async_session() as session:
        cfg = ApiConfig(
            user_id=USER_ID,
            name=f"cfg-{uuid.uuid4().hex[:6]}",
            vendor="openai",
            api_key=key,
            base_url="https://api.example.com",
            models=json.dumps(models) if models is not None else None,
        )
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
        return cfg.id


async def _get_novel(novel_id: str) -> Novel:
    async with async_session() as session:
        return await session.get(Novel, novel_id)


async def _get_config(config_id: str) -> ApiConfig:
    async with async_session() as session:
        return await session.get(ApiConfig, config_id)


# ── 解析层 ─────────────────────────────────────────────────────────────────


class TestParseModels:
    def test_parses_json_text(self):
        assert parse_models('["a","b"]') == ["a", "b"]

    def test_tolerates_none_empty_invalid(self):
        assert parse_models(None) == []
        assert parse_models("") == []
        assert parse_models("{not json") == []
        assert parse_models('{"a":1}') == []
        assert parse_models('[1, null, "x"]') == ["x"]

    def test_effective_model_ignores_blank(self):
        novel = Novel(ai_model="  gpt-4o  ")
        assert effective_model(novel) == "gpt-4o"
        assert effective_model(None) == ""


# ── 判定层矩阵 ─────────────────────────────────────────────────────────────


class TestComputeAiState:
    def test_no_novel_missing_model(self):
        assert compute_ai_state(None, None, True) == "missing_model"

    def test_r8_delete_leftover_invalid(self):
        """删配置后 ai_config_id 空、ai_model 保留 → invalid（不是 missing_model）。"""
        novel = Novel(ai_config_id=None, ai_model="gpt-4o")
        assert compute_ai_state(novel, None, True) == "invalid"

    def test_no_key(self):
        novel = Novel(ai_config_id="c1", ai_model="gpt-4o")
        assert compute_ai_state(novel, None, False) == "no_key"

    def test_missing_model_when_unbound(self):
        novel = Novel(ai_config_id=None, ai_model=None)
        assert compute_ai_state(novel, None, True) == "missing_model"
        novel2 = Novel(ai_config_id="c1", ai_model=None)
        assert compute_ai_state(novel2, None, True) == "missing_model"

    def test_config_deleted_invalid(self):
        novel = Novel(ai_config_id="gone", ai_model="gpt-4o")
        assert compute_ai_state(novel, None, True) == "invalid"

    def test_model_not_in_config_invalid(self):
        """O-8 存量错配：model ∉ config.models 不再报 ready。"""
        novel = Novel(ai_config_id="c1", ai_model="removed-model")
        cfg = ApiConfig(models=json.dumps(["gpt-4o"]))
        assert compute_ai_state(novel, cfg, True) == "invalid"

    def test_empty_models_invalid(self):
        novel = Novel(ai_config_id="c1", ai_model="gpt-4o")
        cfg = ApiConfig(models=None)
        assert compute_ai_state(novel, cfg, True) == "invalid"

    def test_ready(self):
        novel = Novel(ai_config_id="c1", ai_model="gpt-4o")
        cfg = ApiConfig(models=json.dumps(["gpt-4o", "gpt-4o-mini"]))
        assert compute_ai_state(novel, cfg, True) == "ready"


# ── 门控层 require_novel_model ─────────────────────────────────────────────


class TestRequireNovelModel:
    async def _call(self, novel_id: str):
        async with async_session() as session:
            return await require_novel_model(novel_id, {"id": USER_ID}, session)

    def test_ready_passes(self):
        cid = _run_async(_make_config(["gpt-4o"]))
        nid = _run_async(_make_novel(cid, "gpt-4o"))
        assert _run_async(self._call(nid)) is True

    def test_missing_model_503_reason(self):
        from fastapi import HTTPException

        nid = _run_async(_make_novel(None, None))
        with pytest.raises(HTTPException) as ei:
            _run_async(self._call(nid))
        assert ei.value.status_code == 503
        assert ei.value.detail["reason"] == "missing_model"

    def test_invalid_503_reason(self):
        from fastapi import HTTPException

        gone = _run_async(_make_config(["gpt-4o"]))
        nid = _run_async(_make_novel(gone, "gpt-4o"))

        async def _delete_cfg():
            async with async_session() as session:
                row = await session.get(ApiConfig, gone)
                await session.delete(row)
                await session.commit()

        _run_async(_delete_cfg())
        with pytest.raises(HTTPException) as ei:
            _run_async(self._call(nid))
        assert ei.value.status_code == 503
        assert ei.value.detail["reason"] == "invalid"

    def test_unknown_novel_404(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as ei:
            _run_async(self._call("nope"))
        assert ei.value.status_code == 404


# ── 绑定校验 ───────────────────────────────────────────────────────────────


class TestModelBinding:
    def test_set_valid_pair(self, client):
        cid = _run_async(_make_config(["gpt-4o"]))
        nid = _run_async(_make_novel())
        r = client.put(
            f"/api/v1/novels/{nid}/ai-model",
            json={"api_config_id": cid, "model": "gpt-4o"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["ai_model"] == "gpt-4o"

    def test_unpaired_rejected_400(self, client):
        cid = _run_async(_make_config(["gpt-4o"]))
        nid = _run_async(_make_novel())
        r = client.put(
            f"/api/v1/novels/{nid}/ai-model", json={"api_config_id": cid, "model": None}
        )
        assert r.status_code == 400, r.text

    def test_model_not_in_config_400(self, client):
        cid = _run_async(_make_config(["gpt-4o"]))
        nid = _run_async(_make_novel())
        r = client.put(
            f"/api/v1/novels/{nid}/ai-model",
            json={"api_config_id": cid, "model": "not-listed"},
        )
        assert r.status_code == 400, r.text

    def test_empty_models_400(self, client):
        cid = _run_async(_make_config(None))
        nid = _run_async(_make_novel())
        r = client.put(
            f"/api/v1/novels/{nid}/ai-model",
            json={"api_config_id": cid, "model": "gpt-4o"},
        )
        assert r.status_code == 400, r.text

    def test_explicit_clear_allowed(self, client):
        cid = _run_async(_make_config(["gpt-4o"]))
        nid = _run_async(_make_novel(cid, "gpt-4o"))
        r = client.put(
            f"/api/v1/novels/{nid}/ai-model",
            json={"api_config_id": None, "model": None},
        )
        assert r.status_code == 200, r.text


# ── ai-model 读端点下发 ai_state ──────────────────────────────────────────


class TestGetAiModel:
    def test_ready_payload(self, client):
        cid = _run_async(_make_config(["gpt-4o"]))
        nid = _run_async(_make_novel(cid, "gpt-4o"))
        r = client.get(f"/api/v1/novels/{nid}/ai-model")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ai_state"] == "ready"
        assert body["effective_model"] == "gpt-4o"
        assert body["model"] == "gpt-4o"
        assert body["reason"] == "ready"

    def test_missing_model_payload(self, client):
        nid = _run_async(_make_novel())
        body = client.get(f"/api/v1/novels/{nid}/ai-model").json()
        assert body["ai_state"] == "missing_model"


# ── 题材字段 AI ────────────────────────────────────────────────────────────


class TestGenreFieldAi:
    def _novel_ready(self) -> str:
        cid = _run_async(_make_config(["gpt-4o"]))
        nid = _run_async(_make_novel(cid, "gpt-4o"))
        self._seed_story(nid)
        return nid

    def _seed_story(self, novel_id: str) -> None:
        from filesystem.storage import get_storage

        async def _write():
            novel = await _get_novel(novel_id)
            await get_storage().write_yaml(
                novel.root_path, "story.yaml", {"synopsis": "一个凡人逆袭的故事"}
            )

        _run_async(_write())

    def _patch_client(self, monkeypatch, text: str):
        fake = _FakeClient(text)

        async def _get(novel_id):
            return fake

        monkeypatch.setattr(ai_router, "get_ai_client_for_novel", _get)
        return fake

    def test_core_promise_returns_value_and_note(self, client, monkeypatch):
        nid = self._novel_ready()
        self._patch_client(
            monkeypatch, '{"value": "以弱破强的痛快", "note": "读者要看弱者翻盘"}'
        )
        r = client.post(
            f"/api/novels/{nid}/settings/ai/genre/core_promise", json={"title": "书"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["value"] == {"value": "以弱破强的痛快", "note": "读者要看弱者翻盘"}

    def test_forbidden_list_maps_slug_and_custom(self, client, monkeypatch):
        nid = self._novel_ready()
        self._patch_client(
            monkeypatch,
            '["no-villain-idiot", {"text": "禁穿越"}, {"tagId": "forbidden:no-foresight"}]',
        )
        r = client.post(
            f"/api/novels/{nid}/settings/ai/genre/forbidden_list", json={"title": "书"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["value"] == [
            {"tagId": "forbidden:no-villain-idiot"},
            {"text": "禁穿越"},
            {"tagId": "forbidden:no-foresight"},
        ]

    def test_cost_ratio_clamped(self, client, monkeypatch):
        nid = self._novel_ready()
        self._patch_client(monkeypatch, '{"value": 42}')
        r = client.post(
            f"/api/novels/{nid}/settings/ai/genre/cost_ratio", json={"title": "书"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["value"] == 10

    def test_battlefield_and_track(self, client, monkeypatch):
        nid = self._novel_ready()
        self._patch_client(monkeypatch, '["resources", {"text": "街口那条巷子"}]')
        r = client.post(
            f"/api/novels/{nid}/settings/ai/genre/battlefield", json={"title": "书"}
        )
        assert r.json()["value"] == [
            {"tagId": "battlefield:resources"},
            {"text": "街口那条巷子"},
        ]

        self._patch_client(monkeypatch, '{"value": "凡人流——每卷突破一个大境界"}')
        r2 = client.post(
            f"/api/novels/{nid}/settings/ai/genre/track", json={"title": "书"}
        )
        assert r2.json()["value"] == "凡人流——每卷突破一个大境界"

    def test_invalid_json_502(self, client, monkeypatch):
        nid = self._novel_ready()
        self._patch_client(monkeypatch, "这不是 JSON")
        r = client.post(
            f"/api/novels/{nid}/settings/ai/genre/track", json={"title": "书"}
        )
        assert r.status_code == 502, r.text

    def test_unknown_genre_field_400(self, client, monkeypatch):
        nid = self._novel_ready()
        self._patch_client(monkeypatch, "{}")
        r = client.post(
            f"/api/novels/{nid}/settings/ai/genre/promise_note", json={"title": "书"}
        )
        assert r.status_code == 400, r.text

    def test_usage_records_operation_and_actual_model(self, client, monkeypatch):
        nid = self._novel_ready()
        self._patch_client(monkeypatch, '{"value": "x"}')
        client.post(f"/api/novels/{nid}/settings/ai/genre/track", json={"title": "书"})

        async def _rows():
            async with async_session() as session:
                res = await session.execute(
                    select(TokenLog).where(TokenLog.project_id == nid)
                )
                return res.scalars().all()

        rows = _run_async(_rows())
        assert rows and rows[-1].operation == "settings_genre_track"
        assert rows[-1].model == "gpt-4o"

    def test_json_mode_and_temperature_passed(self, client, monkeypatch):
        nid = self._novel_ready()
        fake = self._patch_client(monkeypatch, '{"value": "x"}')
        client.post(f"/api/novels/{nid}/settings/ai/genre/track", json={"title": "书"})
        assert fake.last_kwargs["json_mode"] is True
        assert fake.last_kwargs["temperature"] <= 0.3
        assert fake.last_kwargs["max_tokens"] >= 2048


# ── 简介 AI ────────────────────────────────────────────────────────────────


class TestIntroAi:
    def _novel_ready(self) -> str:
        cid = _run_async(_make_config(["gpt-4o"]))
        return _run_async(_make_novel(cid, "gpt-4o"))

    def _patch_client(self, monkeypatch, text: str):
        fake = _FakeClient(text)

        async def _get(novel_id):
            return fake

        monkeypatch.setattr(ai_router, "get_ai_client_for_novel", _get)
        return fake

    def test_unknown_action_400(self, client):
        nid = self._novel_ready()
        r = client.post(
            f"/api/novels/{nid}/settings/ai/intro/nope",
            json={"title": "书", "content": "内容"},
        )
        assert r.status_code == 400, r.text

    def test_empty_content_400(self, client):
        nid = self._novel_ready()
        r = client.post(
            f"/api/novels/{nid}/settings/ai/intro/introspect",
            json={"title": "书", "content": "   "},
        )
        assert r.status_code == 400, r.text

    def test_introspect_normalizes_names_status_verdict(self, client, monkeypatch):
        nid = self._novel_ready()
        self._patch_client(
            monkeypatch,
            json.dumps(
                {
                    "six_segments": [
                        {"name": "主角身份", "status": "ok", "excerpt": "外门杂徒"},
                        {"name": "瞎编的段名", "status": "weird"},
                    ],
                    "taboo": {"hits": [{"rule": "结局剧透", "excerpts": ["他最后死了"]}]},
                    "verdict": "unknown",
                },
                ensure_ascii=False,
            ),
        )
        r = client.post(
            f"/api/novels/{nid}/settings/ai/intro/introspect",
            json={"title": "书", "content": "内容"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert [s["name"] for s in body["six_segments"]] == [
            "主角身份",
            "本来的生活",
            "突发状况",
            "必须面对的矛盾",
            "不做的后果",
            "做了的可能结局",
        ]
        assert body["six_segments"][0]["status"] == "ok"
        assert body["six_segments"][1]["status"] == "missing"
        assert body["taboo"]["hits"][0]["rule"] == "剧透"  # 归一化到白名单
        assert body["verdict"] in ("strong", "ok", "weak")

    def test_fill_returns_missing_candidates(self, client, monkeypatch):
        nid = self._novel_ready()
        self._patch_client(
            monkeypatch,
            json.dumps(
                {"missing": [{"name": "不做的后果", "candidate": "三个月后丹田枯竭。"}]},
                ensure_ascii=False,
            ),
        )
        r = client.post(
            f"/api/novels/{nid}/settings/ai/intro/fill",
            json={"title": "书", "content": "内容", "missing_segments": ["不做的后果"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["missing"][0]["name"] == "不做的后果"
        assert r.json()["act"] == "insert"

    def test_polish_returns_before_after(self, client, monkeypatch):
        nid = self._novel_ready()
        fake = self._patch_client(
            monkeypatch,
            json.dumps({"original": "原文", "polished": "改后"}, ensure_ascii=False),
        )
        r = client.post(
            f"/api/novels/{nid}/settings/ai/intro/polish",
            json={"title": "书", "content": "原文"},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"original": "原文", "polished": "改后", "act": "replace"}
        # 长文生成类：temperature 0.7（与 JSON 判定类区分）
        assert fake.last_kwargs["temperature"] == 0.7
