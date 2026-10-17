"""c-skip-model-list：无清单端点支持——降级全集（models 4xx/5xx → 对话探针）、
skip_model_list 声明跳过（测试直探对话）、轻探针 400/403/405 无清单口径、
schema/落库/配置包兼容。

Usage:
    cd client/backend && venv/bin/python -m pytest tests/test_skip_model_list.py -v
"""

import asyncio
import os
import sqlite3
import tempfile
from typing import ClassVar

import pytest

# ── Test environment（须先于 import app 模块设置） ──────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_skiplist.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_skiplist_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from api_configs import connection as conn_mod
from api_configs.connection import fetch_models as do_fetch_models
from api_configs.connection import test_connection as do_test_connection
from api_configs.schemas import CreateApiConfigBody, UpdateApiConfigBody
from api_configs.service import create_api_config, update_api_config
from backup.export import build_config_package_bytes
from backup.importer import _restore_config
from db import Base, async_session, engine

CLOUDBASE_BASE = "https://env-test.api.tcloudbasegateway.com/v1/ai/cloudbase"
# CloudBase 网关实锤形态：对清单路由回 403 并附与清单无关的误导文案
_CLOUDBASE_403 = {
    "code": "AI_MODEL_NOT_SUPPORTED",
    "message": "Unsupported model in group cloudbase. For more information, "
    "please refer to https://docs.cloudbase.net/error-code/service/x",
    "requestId": "req-1",
}
_CHAT_OK = {"choices": [{"message": {"content": "你好！", "role": "assistant"}}]}
_ANTHROPIC_OK = {"content": [{"type": "text", "text": "你好！"}]}


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


@pytest.fixture(scope="module", autouse=True)
def _tables():
    _run_async(_create_tables())
    yield


class _FakeResp:
    """payload 可为 dict；传 Exception → json() 抛出（模拟 HTML 等非 JSON 体）。"""

    def __init__(self, status_code, payload=None, content_type="application/json"):
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self._payload = payload if payload is not None else {"data": []}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    @property
    def text(self) -> str:
        import json as _json

        if isinstance(self._payload, Exception):
            return str(self._payload)
        return _json.dumps(self._payload, ensure_ascii=False)


class _FakeAsyncClient:
    """替换 httpx.AsyncClient：记录请求并按脚本回放（条目＝(method, status[, payload])）。"""

    script: ClassVar[list] = []
    calls: ClassVar[list] = []

    def __init__(self, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        type(self).calls.append(("GET", url, headers))
        entry = type(self).script.pop(0)
        assert entry[0] == "GET", f"脚本期望 {entry[0]}，实际收到 GET"
        return _FakeResp(*entry[1:])

    async def post(self, url, headers=None, json=None):
        type(self).calls.append(("POST", url, headers, json))
        entry = type(self).script.pop(0)
        assert entry[0] == "POST", f"脚本期望 {entry[0]}，实际收到 POST"
        return _FakeResp(*entry[1:])


@pytest.fixture
def fake_http(monkeypatch):
    _FakeAsyncClient.script = []
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(
        conn_mod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(**kw)
    )
    return _FakeAsyncClient


# ── 降级全集：models 凡未带回可用清单 → 对话探针判定（判定以探针为准） ────────


class TestDegradeFullSet:
    def test_models_403_degrades_to_green(self, fake_http):
        """CloudBase 案：清单路由 403＋误导文案，对话正常 → 测试转绿，不判认证失败。"""
        fake_http.script = [
            ("GET", 403, _CLOUDBASE_403),
            ("POST", 200, _CHAT_OK),
        ]
        out = _run_async(
            do_test_connection(
                "openai-compat", "sk", CLOUDBASE_BASE, "openai",
                preferred_model="hy3",
            )
        )
        assert out["ok"] is True and out["models"] == []
        assert out["note"] == conn_mod.NO_MODEL_LIST_NOTE_OPENAI
        assert out["candidates"] == []
        kinds = [c[0] for c in fake_http.calls]
        assert kinds == ["GET", "POST"]
        assert fake_http.calls[1][1] == f"{CLOUDBASE_BASE}/chat/completions"
        assert fake_http.calls[1][3]["model"] == "hy3"  # 已选模型优先作探针 id
        assert fake_http.calls[1][3]["thinking"] == {"type": "disabled"}

    def test_models_400_degrades_to_green(self, fake_http):
        fake_http.script = [
            ("GET", 400, {"code": "BAD_REQUEST", "message": "Bad request."}),
            ("POST", 200, _CHAT_OK),
        ]
        out = _run_async(
            do_test_connection(
                "openai-compat", "sk", "https://relay.example.com/v1", "openai",
                preferred_model="m1",
            )
        )
        assert out["ok"] is True and out["models"] == []

    def test_models_5xx_degrades_to_green(self, fake_http):
        fake_http.script = [
            ("GET", 502),
            ("POST", 200, _CHAT_OK),
        ]
        out = _run_async(
            do_test_connection(
                "openai-compat", "sk", "https://relay.example.com/v1", "openai",
                preferred_model="m1",
            )
        )
        assert out["ok"] is True

    def test_models_403_bad_key_probe_auth_passthrough(self, fake_http):
        """清单 403 且 Key 确实无效：探针同址同鉴权回 401 → 认证失败如实透传。"""
        fake_http.script = [
            ("GET", 403, _CLOUDBASE_403),
            ("POST", 401, {"error": {"message": "Invalid API key"}}),
        ]
        out = _run_async(
            do_test_connection(
                "openai-compat", "sk-bad", CLOUDBASE_BASE, "openai",
                preferred_model="hy3",
            )
        )
        assert out["ok"] is False
        assert out["status"] == "auth_error"
        assert "认证失败" in out["error"] and "HTTP 401" in out["error"]
        assert "Invalid API key" in out["error"]  # 探针错误详情透传

    def test_models_401_403_no_id_keeps_auth_verdict(self, fake_http):
        """无 id 不降级：401/403 维持「认证失败」（鉴权层语义明确，与清单无关）。"""
        for status in (401, 403):
            fake_http.script = [(("GET"), status, _CLOUDBASE_403)]
            fake_http.calls.clear()
            out = _run_async(
                do_test_connection(
                    "openai-compat", "sk", "https://relay.example.com/v1", "openai"
                )
            )
            assert out["ok"] is False, status
            assert out["status"] == "auth_error", status
            assert f"HTTP {status}" in out["error"]
            # 无 id：不发生对话探针
            assert [c[0] for c in fake_http.calls] == ["GET"], status

    def test_models_4xx_5xx_no_id_prompts_model_name(self, fake_http):
        """无 id 不降级：400/405/429/502 按提示填写模型名判负。"""
        for status in (400, 405, 429, 502):
            fake_http.script = [(("GET"), status, {"message": "x"})]
            fake_http.calls.clear()
            out = _run_async(
                do_test_connection(
                    "openai-compat", "sk", "https://relay.example.com/v1", "openai"
                )
            )
            assert out["ok"] is False, status
            assert "请填写模型名称" in out["error"], (status, out["error"])
            assert f"HTTP {status}" in out["error"], status
            assert [c[0] for c in fake_http.calls] == ["GET"], status

    def test_models_403_degraded_probe_endpoint_mismatch(self, fake_http):
        """降级探针判「对话端点不存在」（404）→ 透传探针对话地址的核对文案。"""
        fake_http.script = [
            ("GET", 403, _CLOUDBASE_403),
            ("POST", 404),
        ]
        out = _run_async(
            do_test_connection(
                "openai-compat", "sk", CLOUDBASE_BASE, "openai",
                preferred_model="hy3",
            )
        )
        assert out["ok"] is False
        assert out["status"] == "endpoint_mismatch"
        assert "/chat/completions" in out["error"]

    def test_models_200_webpage_no_id_keeps_original_verdict(self, fake_http):
        """200 网页体＋无 id：保留体判废原文案（含补 /v1 指引），不发生成探针。"""
        fake_http.script = [("GET", 200, ValueError("Expecting value"), "text/html")]
        out = _run_async(
            do_test_connection(
                "openai-compat", "sk", "https://relay.example.com", "openai"
            )
        )
        assert out["ok"] is False
        assert out["status"] == "endpoint_mismatch"
        assert "不是 API 数据" in out["error"]
        assert "补 /v1" in out["error"]
        assert [c[0] for c in fake_http.calls] == ["GET"]

    def test_models_404_still_degrades(self, fake_http):
        """既有 404 降级在统一闸下不回归。"""
        fake_http.script = [
            ("GET", 404),
            ("POST", 200, _CHAT_OK),
        ]
        out = _run_async(
            do_test_connection(
                "openai-compat", "sk", "https://relay.example.com/v1", "openai",
                preferred_model="m1",
            )
        )
        assert out["ok"] is True


# ── skip_model_list：清单请求不出网，直探对话 ─────────────────────────────────


class TestSkipModelListFlag:
    def test_skip_skips_get_and_probes_chat(self, fake_http):
        fake_http.script = [("POST", 200, _CHAT_OK)]
        out = _run_async(
            do_test_connection(
                "openai-compat", "sk", CLOUDBASE_BASE, "openai",
                preferred_model="hy3", skip_model_list=True,
            )
        )
        assert out["ok"] is True and out["models"] == []
        assert out["note"] == conn_mod.SKIP_MODEL_LIST_NOTE
        # 清单请求不出网：只有对话探针一发
        assert [c[0] for c in fake_http.calls] == ["POST"]
        assert fake_http.calls[0][1] == f"{CLOUDBASE_BASE}/chat/completions"
        assert fake_http.calls[0][3]["model"] == "hy3"

    def test_skip_no_id_prompts_model_name(self, fake_http):
        out = _run_async(
            do_test_connection(
                "openai-compat", "sk", CLOUDBASE_BASE, "openai",
                skip_model_list=True,
            )
        )
        assert out["ok"] is False
        assert "已跳过模型清单接口" in out["error"]
        assert "请填写模型名称" in out["error"]
        assert fake_http.calls == []  # 无 id：连探针都不发

    def test_skip_anthropic_uses_placeholder(self, fake_http):
        fake_http.script = [("POST", 200, _ANTHROPIC_OK)]
        out = _run_async(
            do_test_connection(
                "glm", "sk", "https://open.bigmodel.cn/api/anthropic", "anthropic",
                skip_model_list=True,
            )
        )
        assert out["ok"] is True
        assert [c[0] for c in fake_http.calls] == ["POST"]
        assert fake_http.calls[0][1].endswith("/v1/messages")
        assert fake_http.calls[0][3]["model"] == conn_mod._ANTHROPIC_PROBE_MODEL

    def test_skip_probe_model_rejected(self, fake_http):
        # 探针 payload 恒带思考参数：400 触发去参重试一次（两次都 400 回原始，
        # 原始文案与思考无关）→ 错误点名所试模型 hy9
        fake_http.script = [
            ("POST", 400, {"error": {"message": "model not found: hy9"}}),
            ("POST", 400, {"error": {"message": "model not found: hy9"}}),
        ]
        out = _run_async(
            do_test_connection(
                "openai-compat", "sk", CLOUDBASE_BASE, "openai",
                preferred_model="hy9", skip_model_list=True,
            )
        )
        assert out["ok"] is False
        assert "hy9" in out["error"]

    def test_ollama_ignores_skip_flag(self, fake_http):
        """ollama 走自有 tags 端点，skip 声明不改变其探测形态。"""
        fake_http.script = [
            ("GET", 200, {"models": [{"name": "q3"}]}),
        ]
        out = _run_async(
            do_test_connection(
                "ollama", "", "http://localhost:11434/v1", "openai",
                skip_model_list=True,
            )
        )
        assert out["ok"] is True and out["models"] == ["q3"]
        assert fake_http.calls[0][1].endswith("/api/tags")


# ── 轻探针：400/403/405 按「端点未提供模型清单」口径返回（零生成调用） ────────


class TestFetchModelsNoListVerdict:
    def test_fetch_models_403_no_list_verdict(self, fake_http):
        fake_http.script = [("GET", 403, _CLOUDBASE_403)]
        out = _run_async(
            do_fetch_models("openai-compat", "sk", CLOUDBASE_BASE, "openai")
        )
        assert out["ok"] is True and out["models"] == []
        assert "403" in out["note"]
        assert "认证失败" not in out["note"]  # SHALL NOT 标「认证失败」
        assert "测试连接" in out["note"]  # 补救出口
        assert [c[0] for c in fake_http.calls] == ["GET"]  # 零生成调用

    def test_fetch_models_400_no_list_verdict(self, fake_http):
        fake_http.script = [("GET", 400, {"code": "BAD_REQUEST"})]
        out = _run_async(
            do_fetch_models("openai-compat", "sk", "https://relay.example.com/v1", "openai")
        )
        assert out["ok"] is True
        assert "HTTP 400" in out["note"]

    def test_fetch_models_405_no_list_verdict(self, fake_http):
        fake_http.script = [("GET", 405)]
        out = _run_async(
            do_fetch_models("openai-compat", "sk", "https://relay.example.com/v1", "openai")
        )
        assert out["ok"] is True

    def test_fetch_models_401_still_auth_error(self, fake_http):
        fake_http.script = [("GET", 401, {"error": {"message": "bad key"}})]
        out = _run_async(
            do_fetch_models("openai-compat", "sk", "https://relay.example.com/v1", "openai")
        )
        assert out["ok"] is False
        assert out["status"] == "auth_error"


# ── schema／落库／配置包兼容 ───────────────────────────────────────────────────


async def _ensure_user(user_id: str) -> None:
    """api_configs.user_id 有 FK 到 users.id——落库测试先垫用户行。"""
    from models.user import User

    async with async_session() as db:
        exists = await db.get(User, user_id)
        if exists is None:
            db.add(
                User(
                    id=user_id,
                    email=f"{user_id}@test.local",
                    password_hash="x",
                )
            )
            await db.commit()


class TestSchemaAndPersistence:
    def test_create_body_default_off_and_accepts_on(self):
        body = CreateApiConfigBody(
            name="n", vendor_id="openai-compat", base_url="https://x.example.com/v1"
        )
        assert body.skip_model_list is False
        body_on = CreateApiConfigBody(
            name="n", vendor_id="openai-compat", base_url="https://x.example.com/v1",
            skip_model_list=True,
        )
        assert body_on.skip_model_list is True

    def test_update_body_none_means_not_provided(self):
        body = UpdateApiConfigBody()
        assert body.skip_model_list is None

    def test_create_persists_flag_and_ollama_coerced_off(self):
        _run_async(_ensure_user("u-skip-1"))

        async def _go():
            async with async_session() as db:
                cfg = await create_api_config(
                    db, "u-skip-1", "cloud", "openai-compat", CLOUDBASE_BASE,
                    api_key="sk", skip_model_list=True,
                )
                ollama = await create_api_config(
                    db, "u-skip-1", "local", "ollama", "http://localhost:11434/v1",
                    skip_model_list=True,
                )
                return cfg, ollama

        cfg, ollama = _run_async(_go())
        assert cfg["skip_model_list"] is True
        assert ollama["skip_model_list"] is False  # ollama 防御性归零

    def test_saved_config_test_uses_stored_flag(self, fake_http):
        """已存配置测试端点按已存 skip 值分流：勾选过的配置不再发清单请求。"""
        _run_async(_ensure_user("u-skip-2"))

        async def _create():
            async with async_session() as db:
                return await create_api_config(
                    db, "u-skip-2", "cloud2", "openai-compat", CLOUDBASE_BASE,
                    api_key="sk", models=["hy3"], skip_model_list=True,
                )

        async def _test(config_id):
            from api_configs.service import test_api_config

            async with async_session() as db:
                return await test_api_config(db, "u-skip-2", config_id)

        cfg = _run_async(_create())
        fake_http.script = [("POST", 200, _CHAT_OK)]
        out = _run_async(_test(cfg["id"]))
        assert out["ok"] is True
        assert [c[0] for c in fake_http.calls] == ["POST"]
        assert out["note"] == conn_mod.SKIP_MODEL_LIST_NOTE

    def test_update_toggles_flag(self):
        _run_async(_ensure_user("u-skip-3"))

        async def _go():
            async with async_session() as db:
                cfg = await create_api_config(
                    db, "u-skip-3", "cloud3", "openai-compat", CLOUDBASE_BASE,
                    api_key="sk",
                )
                assert cfg["skip_model_list"] is False
                updated = await update_api_config(
                    db, "u-skip-3", cfg["id"], {"skip_model_list": True}
                )
                return updated

        assert _run_async(_go())["skip_model_list"] is True

    def test_config_package_roundtrip_and_legacy_default(self):
        import io
        import zipfile

        import yaml

        for uid in ("u-skip-4", "u-skip-4-restore", "u-skip-4-legacy"):
            _run_async(_ensure_user(uid))

        async def _go():
            async with async_session() as db:
                await create_api_config(
                    db, "u-skip-4", "pkg", "openai-compat", CLOUDBASE_BASE,
                    api_key="sk", models=["hy3"], skip_model_list=True,
                )
                return await build_config_package_bytes(db, "u-skip-4")

        async def _restore(user_id, data):
            async with async_session() as db:
                return await _restore_config(db, user_id, data)

        pkg_bytes, _name = _run_async(_go())
        with zipfile.ZipFile(io.BytesIO(pkg_bytes)) as zf:
            payload = yaml.safe_load(zf.read("config.yaml"))
        entry = payload["api_configs"][0]
        assert entry["skip_model_list"] is True
        # 新包导入：还原为开
        assert _run_async(_restore("u-skip-4-restore", payload))["created"] == 1
        # 旧包缺键：默认关
        legacy_entry = {**entry}
        legacy_entry.pop("skip_model_list")
        legacy_entry["name"] = "legacy-name"
        legacy = {**payload, "api_configs": [legacy_entry]}
        assert _run_async(_restore("u-skip-4-legacy", legacy))["created"] == 1

    def test_carry_plan_backfills_missing_column(self, tmp_path):
        """旧世代表无该列：带回引擎列交集计划以 server_default 兜底（无 blocker）。"""
        old_db = tmp_path / "old.db"
        con = sqlite3.connect(old_db)
        con.execute(
            "CREATE TABLE api_configs (id TEXT PRIMARY KEY, user_id TEXT, name TEXT,"
            " vendor TEXT, vendor_display_name TEXT, base_url TEXT, api_key TEXT)"
        )
        con.execute(
            "INSERT INTO api_configs (id, user_id, name, vendor, base_url, api_key)"
            " VALUES ('c1', 'u1', 'n', 'openai-compat', 'https://x', 'k')"
        )
        con.commit()
        con.close()
        from migration.engine import build_plan

        plan = build_plan(old_db)
        entry = next(t for t in plan["tables"] if t["table"] == "api_configs")
        assert "skip_model_list" in entry["missing_target_cols"]
        assert "skip_model_list" not in entry["columns"]  # 交集里没有，INSERT 不显式给值
        assert entry["backfill"].get("skip_model_list") is None or \
            "skip_model_list" not in entry["backfill"]
