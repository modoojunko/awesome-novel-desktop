"""接口格式（api_format）测试：迁移等价回填 / 显式协议优先 / 按协议探测 / 契约与 update 语义 / 备份加键 roundtrip。

Usage:
    cd client/backend && .venv/bin/python -m pytest tests/test_api_format.py -v
"""

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import ValidationError
from sqlalchemy import select

# ── Test environment（须先于 import app 模块设置） ──────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_apifmt.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_apifmt_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

# Now import the application
import ai_client as ai_client_module
from ai_client import AIClient, get_ai_client_for_user
from api_configs import connection as conn_mod
from api_configs.connection import _build_probe
from api_configs.connection import fetch_models as do_fetch_models
from api_configs.connection import test_connection as do_test_connection
from api_configs.crypto import encrypt_api_key
from api_configs.schemas import CreateApiConfigBody
from api_configs.service import create_api_config, update_api_config
from backup.export import build_config_package_bytes
from backup.importer import _restore_config
from db import Base, async_session, engine
from models.api_config import ApiConfig
from models.user import User


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module", autouse=True)
def _tables():
    _run_async(_create_tables())
    yield


async def _create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _create_user(user_id: str) -> User:
    async with async_session() as session:
        user = User(
            id=user_id,
            email=f"{user_id}@test.com",
            password_hash=hashlib.pbkdf2_hmac(
                "sha256", b"pw", b"ai-novel-salt", 600000
            ).hex(),
            display_name=user_id,
        )
        session.add(user)
        await session.commit()
        return user


async def _create_config(user_id: str, name: str, **kw) -> ApiConfig:
    async with async_session() as session:
        cfg = ApiConfig(
            user_id=user_id,
            name=name,
            vendor=kw.get("vendor", "glm"),
            api_format=kw.get("api_format", "openai"),
            api_key=encrypt_api_key(kw.get("api_key", "sk-test")),
            base_url=kw.get("base_url", "https://open.bigmodel.cn/api/paas/v4"),
            models=kw.get("models"),
            last_test_status=kw.get("last_test_status"),
        )
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
        return cfg


# ═════════════════ 1. 存量迁移：等价回填 + 幂等 ═════════════════


class TestMigration:
    """main.py lifespan 里两条 SQL 的语义测试（语句与 main.py 保持镜像）。

    回填条件与旧版运行时嗅探严格等价：URL 含 anthropic 或 vendor=anthropic
    → anthropic，其余 openai。
    """

    MIGRATION_ADD = (
        "ALTER TABLE api_configs ADD COLUMN api_format "
        "VARCHAR(20) NOT NULL DEFAULT 'openai'"
    )
    MIGRATION_BACKFILL = (
        "UPDATE api_configs SET api_format='anthropic' "
        "WHERE (base_url LIKE '%anthropic%' OR vendor='anthropic') "
        "AND api_format <> 'anthropic'"
    )

    def _seed_old_db(self, path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(path)
        # 旧库：无 api_format 列
        conn.execute(
            "CREATE TABLE api_configs (id TEXT PRIMARY KEY, vendor TEXT, base_url TEXT)"
        )
        rows = [
            ("1", "glm", "https://open.bigmodel.cn/api/anthropic"),  # 嗅探→anthropic
            ("2", "glm", "https://open.bigmodel.cn/api/paas/v4"),  # openai
            ("3", "anthropic", "https://relay.example.com"),  # vendor→anthropic
            ("4", "openai", "https://api.openai.com"),  # openai
            ("5", "kimi", "https://api.moonshot.cn/anthropic"),  # 嗅探→anthropic
        ]
        conn.executemany("INSERT INTO api_configs VALUES (?,?,?)", rows)
        conn.commit()
        return conn

    def _run_migration(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute(self.MIGRATION_ADD)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # 列已存在（与 main.py try/except 幂等一致）
        conn.execute(self.MIGRATION_BACKFILL)
        conn.commit()

    def test_backfill_equivalent_to_old_sniffing(self, tmp_path):
        conn = self._seed_old_db(tmp_path / "old.db")
        self._run_migration(conn)
        got = dict(conn.execute("SELECT id, api_format FROM api_configs"))
        assert got == {
            "1": "anthropic",
            "2": "openai",
            "3": "anthropic",
            "4": "openai",
            "5": "anthropic",
        }

    def test_rerun_is_noop(self, tmp_path):
        conn = self._seed_old_db(tmp_path / "old.db")
        self._run_migration(conn)
        before = dict(conn.execute("SELECT id, api_format FROM api_configs"))
        self._run_migration(conn)  # 二次启动：ALTER 报错被吞、UPDATE 无匹配行
        after = dict(conn.execute("SELECT id, api_format FROM api_configs"))
        assert before == after


# ═════════════════ 2. AIClient：显式协议优先，嗅探仅兜底 ═════════════════


class _SentinelAnthropic:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs


class _SentinelOpenAI:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs


@pytest.fixture
def sentinel_clients(monkeypatch):
    monkeypatch.setattr(ai_client_module, "AsyncAnthropic", _SentinelAnthropic)
    monkeypatch.setattr(ai_client_module, "AsyncOpenAI", _SentinelOpenAI)


def _make_client(**kw) -> AIClient:
    return AIClient(api_key="sk-test", base_url=kw.pop("base_url", ""), **kw)


class TestAIClientFormat:
    def test_explicit_anthropic_beats_url(self, sentinel_clients):
        # 显式 anthropic + 不含关键字的 URL → Anthropic（旧嗅探会判错的方向）
        c = _make_client(base_url="https://relay.example.com/v1", api_format="anthropic")
        assert isinstance(c._client, _SentinelAnthropic)

    def test_explicit_openai_beats_url(self, sentinel_clients):
        # 显式 openai + 含 anthropic 的 URL → OpenAI（显式压过嗅探）
        c = _make_client(
            base_url="https://open.bigmodel.cn/api/anthropic", api_format="openai"
        )
        assert isinstance(c._client, _SentinelOpenAI)

    def test_none_falls_back_to_url_sniffing(self, sentinel_clients):
        c = _make_client(
            base_url="https://open.bigmodel.cn/api/anthropic", api_format=None
        )
        assert isinstance(c._client, _SentinelAnthropic)  # legacy 兜底行为不变

    def test_default_is_openai(self, sentinel_clients):
        c = _make_client(base_url="https://api.example.com")
        assert isinstance(c._client, _SentinelOpenAI)

    def test_openai_bare_base_normalized_for_sdk(self, sentinel_clients):
        """裸域名 base 归一后才传 SDK（2026-10-09 kakou 案）：SDK 直拼路径不自补版本段，
        裸传会打到官方 404／中转站网页壳；_base_url 同步归一形（留痕/禁思考记忆同形）。"""
        c = _make_client(base_url="https://api.kakouai.com")
        assert c._client.kwargs["base_url"] == "https://api.kakouai.com/v1"
        assert c._base_url == "https://api.kakouai.com/v1"

    def test_openai_versioned_base_kept_for_sdk(self, sentinel_clients):
        c = _make_client(base_url="https://generativelanguage.googleapis.com/v1beta/openai")
        assert c._client.kwargs["base_url"] == (
            "https://generativelanguage.googleapis.com/v1beta/openai"
        )

    def test_anthropic_base_not_normalized(self, sentinel_clients):
        """anthropic 惯例相反：base 不带版本段（SDK 自拼 /v1/messages），SHALL NOT 归一。"""
        c = _make_client(base_url="https://relay.example.com", api_format="anthropic")
        assert c._client.kwargs["base_url"] == "https://relay.example.com"


class TestGetAiClientForUser:
    def test_passes_config_api_format(self, sentinel_clients):
        user_id = f"u-{uuid.uuid4().hex[:8]}"
        _run_async(_create_user(user_id))
        _run_async(
            _create_config(
                user_id,
                "中转 anthropic",
                api_format="anthropic",
                base_url="https://relay.example.com/v1",
            )
        )
        client = _run_async(get_ai_client_for_user(user_id))
        assert client._provider == "anthropic"

    def test_openai_format_stays_openai(self, sentinel_clients):
        user_id = f"u-{uuid.uuid4().hex[:8]}"
        _run_async(_create_user(user_id))
        _run_async(
            _create_config(
                user_id,
                "含 anthropic 字样的 openai",
                api_format="openai",
                base_url="https://relay.anthropic-style.example.com",
            )
        )
        client = _run_async(get_ai_client_for_user(user_id))
        assert client._provider == "openai"


# ═════════════════ 3. 连接测试：按协议构造探测 + 404 降级 ═════════════════


class TestNormalizeOpenAiBase:
    """版本段归一单源（2026-10-09 kakou 中转案）：裸域名补 /v1，四消费点共用同一判据。"""

    @pytest.mark.parametrize(
        "base,expected",
        [
            # 裸域名按 OpenAI 官方惯例补 /v1
            ("https://api.kakouai.com", "https://api.kakouai.com/v1"),
            ("https://api.kakouai.com/", "https://api.kakouai.com/v1"),  # 尾斜杠先剥
            ("http://localhost:12345", "http://localhost:12345/v1"),
            # 自带版本段（行尾／中段）原样保留
            ("https://api.openai.com/v1", "https://api.openai.com/v1"),
            ("https://open.bigmodel.cn/api/paas/v4", "https://open.bigmodel.cn/api/paas/v4"),
            (
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            # 中段版本段（Gemini 官方兼容层）——行尾锚会误判「无版本段」追补出死址
            (
                "https://generativelanguage.googleapis.com/v1beta/openai",
                "https://generativelanguage.googleapis.com/v1beta/openai",
            ),
            (
                "https://generativelanguage.googleapis.com/v1beta/openai/",
                "https://generativelanguage.googleapis.com/v1beta/openai",
            ),
            # 版本段带字母后缀的行尾形态（段锚 $ 分支）
            ("https://gw.example.com/v1beta", "https://gw.example.com/v1beta"),
            ("", ""),  # 空串原样（上层自行处理缺省 base）
        ],
    )
    def test_normalize(self, base, expected):
        assert conn_mod.normalize_openai_base(base) == expected


class TestWebPageV1Hint:
    """网页体误判文案的「补 /v1」出口按格式分流（评审 2026-10-09）：
    anthropic（惯例 base 不带 /v1，探针侧剥掉）与 ollama（tags 探针剥 /v1）不出。"""

    @pytest.mark.parametrize(
        "api_format,vendor,expected",
        [
            ("openai", "openai-compat", "（若地址确认无误，尝试在末尾补 /v1）"),
            ("openai", "deepseek", "（若地址确认无误，尝试在末尾补 /v1）"),
            ("openai", "ollama", ""),
            ("anthropic", "glm", ""),
        ],
    )
    def test_v1_hint_routing(self, api_format, vendor, expected):
        assert conn_mod._v1_hint(api_format, vendor) == expected

    def test_anthropic_html_page_no_v1_hint(self, fake_http):
        """anthropic 格式探测打到网页：有「检查 Base URL」无「补 /v1」。"""
        fake_http.script = [("GET", 200, ValueError("Expecting value"), "text/html")]
        out = _run_async(
            do_test_connection("glm", "sk", "https://spa.example.com", "anthropic")
        )
        assert out["ok"] is False and out["status"] == "endpoint_mismatch"
        assert "Base URL" in out["error"]
        assert "补 /v1" not in out["error"]

    def test_generation_probe_html_page_openai_has_hint(self, fake_http):
        """对话探针 200 网页体（openai 格式）：verdict 链路文案同样带「补 /v1」出口。"""
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "m-1"}]}),
            ("POST", 200, ValueError("Expecting value"), "text/html"),
        ]
        out = _run_async(
            do_test_connection("openai-compat", "sk", "https://spa.example.com", "openai")
        )
        assert out["ok"] is False and out["status"] == "endpoint_mismatch"
        assert "补 /v1" in out["error"]


class TestBuildProbe:
    def test_anthropic_format_targets_user_base(self):
        url, headers, _extract, fallback = _build_probe(
            "anthropic", "glm", "sk", "https://open.bigmodel.cn/api/anthropic"
        )
        assert url == "https://open.bigmodel.cn/api/anthropic/v1/models"
        assert headers["x-api-key"] == "sk"
        assert headers["anthropic-version"] == "2023-06-01"
        assert fallback is not None
        f_url, _f_headers, f_reply = fallback
        assert f_url == "https://open.bigmodel.cn/api/anthropic/v1/messages"
        assert f_reply is conn_mod._anthropic_reply_text

    def test_anthropic_strips_trailing_v1(self):
        url, _, _, fallback = _build_probe(
            "anthropic", "glm", "sk", "https://x.example.com/api/anthropic/v1"
        )
        assert url == "https://x.example.com/api/anthropic/v1/models"
        assert fallback[0] == "https://x.example.com/api/anthropic/v1/messages"

    @pytest.mark.parametrize(
        "base,expected",
        [
            ("https://api.openai.com", "https://api.openai.com/v1/models"),
            ("https://api.deepseek.com", "https://api.deepseek.com/v1/models"),
            ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1/models"),
            (
                "https://open.bigmodel.cn/api/paas/v4",
                "https://open.bigmodel.cn/api/paas/v4/models",
            ),
            (
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
            ),
            # 中段版本段原样保留（行尾锚旧实现会误补 /v1/models 死址）
            (
                "https://generativelanguage.googleapis.com/v1beta/openai",
                "https://generativelanguage.googleapis.com/v1beta/openai/models",
            ),
        ],
    )
    def test_openai_format_urls(self, base, expected):
        url, headers, _, fallback = _build_probe("openai", "openai", "sk", base)
        assert url == expected
        assert headers == {"Authorization": "Bearer sk"}
        # 404 同享降级（2026-10-08 拍板）：fallback＝(chat 地址, Bearer 头, openai 提取器)
        # 地址同走版本段归一（与 models 探测/对话探针主链/生成调用同源）
        assert fallback == (
            f"{conn_mod.normalize_openai_base(base)}/chat/completions",
            {"Authorization": "Bearer sk"},
            conn_mod._openai_reply_text,
        )

    def test_ollama_special_case(self):
        url, headers, _, fallback = _build_probe(
            "openai", "ollama", "", "http://localhost:11434"
        )
        assert url == "http://localhost:11434/api/tags"
        assert headers == {}
        assert fallback is None

    def test_ollama_strips_trailing_v1(self):
        """登记预填值为 …/v1（SDK 生成需版本段），tags 探针剥掉防打去 /v1/api/tags。"""
        url, _, _, fallback = _build_probe(
            "openai", "ollama", "", "http://localhost:11434/v1"
        )
        assert url == "http://localhost:11434/api/tags"
        assert fallback is None


class _FakeResp:
    """payload 可为 dict（默认 {"data": []}）；也可传 Exception → json() 抛出（模拟 HTML 等非 JSON 体）。"""

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
    """替换 httpx.AsyncClient：记录请求并按脚本回放。

    脚本条目：(method, status[, payload[, content_type]])，依次弹出。
    """

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


class TestConnectionFlow:
    def test_models_200_no_fallback(self, fake_http):
        """anthropic 列表可用：不走降级（无 note/candidates），但仍发「你好」探针（判据双格式统一）。"""
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "claude-x"}]}),
            ("POST", 200, {"content": [{"type": "text", "text": "你好！"}]}),
        ]
        out = _run_async(
            do_test_connection(
                "glm", "sk", "https://open.bigmodel.cn/api/anthropic", "anthropic"
            )
        )
        assert out["ok"] is True and out["models"] == ["claude-x"]
        assert "note" not in out and "candidates" not in out
        assert [c[0] for c in fake_http.calls] == ["GET", "POST"]
        assert fake_http.calls[1][1].endswith("/v1/messages")
        assert fake_http.calls[1][3]["model"] == "claude-x"  # 列表首个作探针 id

    def test_models_404_falls_back_to_messages(self, fake_http):
        fake_http.script = [
            ("GET", 404),
            ("POST", 200, {"content": [{"type": "text", "text": "你好！"}]}),
        ]
        out = _run_async(
            do_test_connection(
                "glm", "sk", "https://open.bigmodel.cn/api/anthropic", "anthropic"
            )
        )
        assert out["ok"] is True and out["models"] == []
        kinds = [c[0] for c in fake_http.calls]
        assert kinds == ["GET", "POST"]
        assert fake_http.calls[1][1].endswith("/v1/messages")
        payload = fake_http.calls[1][3]
        assert payload["messages"][0]["content"] == "你好"  # 「你好」最小生成（2026-10-05 拍板）
        assert payload["thinking"] == {"type": "disabled"}
        # 无已选模型、glm 无候选 → 链尾垫占位 id（anthropic 专属）
        assert payload["model"] == conn_mod._ANTHROPIC_PROBE_MODEL
        # note 为 anthropic 版（含「改成 openai」尾句）
        assert out["note"] == conn_mod.NO_MODEL_LIST_NOTE_ANTHROPIC

    def test_anthropic_404_fallback_prefers_selected_model(self, fake_http):
        """降级探针 id 链：已选模型优先于占位 id（存量分歧修齐，2026-10-08 评审）。"""
        fake_http.script = [
            ("GET", 404),
            ("POST", 200, {"content": [{"type": "text", "text": "你好！"}]}),
        ]
        out = _run_async(
            do_test_connection(
                "glm",
                "sk",
                "https://open.bigmodel.cn/api/anthropic",
                "anthropic",
                preferred_model="glm-4.7",
            )
        )
        assert out["ok"] is True
        assert fake_http.calls[1][3]["model"] == "glm-4.7"

    def test_openai_404_degrades_with_selected_model(self, fake_http):
        """openai 格式 404 同享降级（Gemini 官方兼容层主路径）：手填模型 id → 生成探针通过。"""
        fake_http.script = [
            ("GET", 404),
            ("POST", 200, {"choices": [{"message": {"content": "你好！"}}]}),
        ]
        out = _run_async(
            do_test_connection(
                "openai-compat",
                "sk",
                "https://generativelanguage.googleapis.com/v1beta/openai",
                "openai",
                preferred_model="gemini-2.5-pro",
            )
        )
        assert out["ok"] is True and out["models"] == []
        # 与生成调用同址（base 直拼 chat/completions）＋ openai 契约提取
        assert fake_http.calls[1][1] == (
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        )
        payload = fake_http.calls[1][3]
        assert payload["model"] == "gemini-2.5-pro"
        assert payload["thinking"] == {"type": "disabled"}
        # note 为 openai 版（无「改成 openai」尾句）
        assert out["note"] == conn_mod.NO_MODEL_LIST_NOTE_OPENAI

    def test_openai_404_no_id_no_degrade(self, fake_http):
        """openai 格式 404 且无已选模型、无候选 → 不发无 id 的生成探针，判负提示填写模型名。"""
        fake_http.script = [("GET", 404)]
        out = _run_async(
            do_test_connection("openai", "sk", "https://api.openai.com", "openai")
        )
        assert out["ok"] is False
        assert "模型名称" in out["error"]
        assert [c[0] for c in fake_http.calls] == ["GET"]

    def test_openai_404_degrade_probe_404_judges_failed(self, fake_http):
        """降级探针也 404 → 判连接失败并点名实际请求地址（Base URL 指向处不提供对话接口）。"""
        fake_http.script = [("GET", 404), ("POST", 404)]
        out = _run_async(
            do_test_connection(
                "openai-compat",
                "sk",
                "https://relay.example.com/v1beta/openai",
                "openai",
                preferred_model="gemini-2.5-pro",
            )
        )
        assert out["ok"] is False and out["status"] == "endpoint_mismatch"
        assert "/chat/completions" in out["error"]

    def test_fallback_auth_failure(self, fake_http):
        fake_http.script = [("GET", 404), ("POST", 401)]
        out = _run_async(
            do_test_connection(
                "glm", "sk", "https://open.bigmodel.cn/api/anthropic", "anthropic"
            )
        )
        assert out["ok"] is False and out["status"] == "auth_error"

    def test_openai_format_uses_user_base_not_official(self, fake_http):
        fake_http.script = [("GET", 200)]
        _run_async(
            do_test_connection("openai", "sk", "https://my-relay.example.com", "openai")
        )
        assert fake_http.calls[0][1] == "https://my-relay.example.com/v1/models"

    def test_bare_base_full_chain_targets_v1(self, fake_http):
        """kakou 案主钉（2026-10-09）：裸域名 base 全链路同归一——models GET /v1/models、
        对话探针 POST /v1/chat/completions；SHALL NOT 清单打归一地址、对话打裸路径网页
        （「清单绿、测试红」半通形态）。"""
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "gpt-6-astra"}]}),
            ("POST", 200, {"choices": [{"message": {"content": "你好！"}}]}),
        ]
        out = _run_async(
            do_test_connection(
                "openai-compat", "sk", "https://api.kakouai.com", "openai"
            )
        )
        assert out["ok"] is True and out["models"] == ["gpt-6-astra"]
        assert fake_http.calls[0][1] == "https://api.kakouai.com/v1/models"
        assert fake_http.calls[1][1] == "https://api.kakouai.com/v1/chat/completions"

    def test_empty_key_rejected(self, fake_http):
        out = _run_async(do_test_connection("glm", "  ", "https://x.example.com", "openai"))
        assert out["ok"] is False and out["status"] == "auth_error"
        assert fake_http.calls == []

    # ── 内测 405 案收紧：「通」必须真能对话（非 JSON 判败 / 对话探针 / 降级 405 判败）──

    def test_models_200_html_page_fails(self, fake_http):
        """Base URL 填成网站首页（SPA 对任意路径回 200 HTML）→ 不算通；文案带补 /v1 出口。"""
        fake_http.script = [("GET", 200, ValueError("Expecting value"), "text/html")]
        out = _run_async(
            do_test_connection("openai-compat", "sk", "https://blog.example.com", "openai")
        )
        assert out["ok"] is False and out["status"] == "endpoint_mismatch"
        assert "Base URL" in out["error"]
        assert "补 /v1" in out["error"]

    def test_models_200_error_envelope_fails(self, fake_http):
        """200 但体是错误信封（部分中转站的软错误形态）→ 不算通。"""
        fake_http.script = [("GET", 200, {"error": {"message": "invalid key"}})]
        out = _run_async(
            do_test_connection("glm", "sk", "https://relay.example.com/v4", "openai")
        )
        assert out["ok"] is False and out["status"] == "endpoint_mismatch"
        assert "invalid key" in out["error"]

    def test_openai_chat_probe_ok_and_same_path_as_generation(self, fake_http):
        """模型列表可用 → 「你好」最小生成探针走与生成完全相同的地址（{base}/chat/completions）。"""
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "m-1"}]}),
            ("POST", 200, {"choices": [{"message": {"content": "你好！"}}]}),
        ]
        out = _run_async(
            do_test_connection("openai-compat", "sk", "https://relay.example.com/v1", "openai")
        )
        assert out["ok"] is True and out["models"] == ["m-1"]
        assert [c[0] for c in fake_http.calls] == ["GET", "POST"]
        assert fake_http.calls[1][1] == "https://relay.example.com/v1/chat/completions"
        payload = fake_http.calls[1][3]
        assert payload["max_tokens"] == 32
        assert payload["messages"][0]["content"] == "你好"
        assert payload["thinking"] == {"type": "disabled"}

    def test_openai_chat_probe_405_fails_with_actual_url(self, fake_http):
        """对话探针 405（地址/格式错）→ 判败，错误文案点名实际请求地址（裸域名已归一）。"""
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "m-1"}]}),
            ("POST", 405, {"detail": "Method Not Allowed"}),
        ]
        out = _run_async(
            do_test_connection("openai-compat", "sk", "https://api.example.com", "openai")
        )
        assert out["ok"] is False and out["status"] == "endpoint_mismatch"
        assert "405" in out["error"]
        assert "https://api.example.com/v1/chat/completions" in out["error"]

    def test_openai_chat_probe_model_rejected_strict(self, fake_http):
        """探针模型 id 被拒（400）判失败并点名所试 id——原「400 宽松不拦」口径作废（2026-10-05 拍板）。

        探针失败仍带回已提取的清单（评审 P1 自恢复闭环）：落库后书内选择面板有正确
        候选，用户手填错 id 后不必删配置重建。
        400 与思考参数无关 → 去参重试同败（c-thinking-config），仍回**原始**响应——
        原始文案更能代表配置的问题。"""
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "embed-only"}, {"id": "good-model"}]}),
            ("POST", 400, {"error": {"message": "model not supported"}}),
            ("POST", 400, {"error": {"message": "model not supported"}}),
        ]
        out = _run_async(
            do_test_connection("openai-compat", "sk", "https://relay.example.com/v1", "openai")
        )
        assert out["ok"] is False and out["status"] == "unknown"
        assert "embed-only" in out["error"]
        assert out["models"] == ["embed-only", "good-model"]  # 失败信封携带真实清单

    def test_openai_probe_uses_vendor_candidate_when_no_models(self, fake_http):
        """模型列表为空 → 用 vendor 候选 id 做探针（deepseek 实测候选）。"""
        fake_http.script = [
            ("GET", 200, {"data": []}),
            ("POST", 200, {"choices": [{"message": {"content": "好的"}}]}),
        ]
        out = _run_async(
            do_test_connection("deepseek", "sk", "https://api.deepseek.com", "openai")
        )
        assert out["ok"] is True
        assert fake_http.calls[1][3]["model"] == "deepseek-flash"

    def test_probe_uses_preferred_model_first(self, fake_http):
        """探针模型 id：配置已选模型（preferred）压过列表首个——预填模型名直通探针。"""
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "m-list"}]}),
            ("POST", 200, {"choices": [{"message": {"content": "好的"}}]}),
        ]
        out = _run_async(
            do_test_connection(
                "deepseek",
                "sk",
                "https://api.deepseek.com",
                "openai",
                preferred_model="deepseek-v4-pro",
            )
        )
        assert out["ok"] is True
        assert fake_http.calls[1][3]["model"] == "deepseek-v4-pro"

    def test_probe_preferred_model_blank_falls_back(self, fake_http):
        """preferred 空白 → 回落列表首个。"""
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "m-list"}]}),
            ("POST", 200, {"choices": [{"message": {"content": "好的"}}]}),
        ]
        _run_async(
            do_test_connection(
                "deepseek",
                "sk",
                "https://api.deepseek.com",
                "openai",
                preferred_model="   ",
            )
        )
        assert fake_http.calls[1][3]["model"] == "m-list"

    # ── 2026-10-05 拍板：「你好」最小生成，格式正确回复才算通 ──

    def test_chat_probe_empty_reply_fails(self, fake_http):
        """2xx 但回复文本为空 → 不算通（「大模型回复了正确格式的数据才算连接正常」）。"""
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "m-1"}]}),
            ("POST", 200, {"choices": [{"message": {"content": ""}}]}),
        ]
        out = _run_async(
            do_test_connection("openai-compat", "sk", "https://api.example.com", "openai")
        )
        assert out["ok"] is False and out["status"] == "unknown"
        assert "回复" in out["error"]

    def test_chat_probe_wrong_shape_fails(self, fake_http):
        """2xx 但体不符合 openai 契约（无 choices[0].message）→ 不算通。"""
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "m-1"}]}),
            ("POST", 200, {"choices": []}),
        ]
        out = _run_async(
            do_test_connection("openai-compat", "sk", "https://api.example.com", "openai")
        )
        assert out["ok"] is False and out["status"] == "unknown"

    def test_chat_probe_thinking_rejected_retries_without_thinking(self, fake_http):
        """端点拒绝 thinking 参数 → 去参重试一次（ai_client 同款约定），重试成功即通。"""
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "m-1"}]}),
            ("POST", 400, {"error": {"message": "Unrecognized request argument: thinking"}}),
            ("POST", 200, {"choices": [{"message": {"content": "你好！"}}]}),
        ]
        out = _run_async(
            do_test_connection("openai-compat", "sk", "https://api.example.com", "openai")
        )
        assert out["ok"] is True
        assert [c[0] for c in fake_http.calls] == ["GET", "POST", "POST"]
        assert "thinking" in fake_http.calls[1][3]
        assert "thinking" not in fake_http.calls[2][3]

    def test_chat_probe_glm_forced_thinking_rejected_retries_stripped(self, fake_http, caplog):
        """GLM-5.3 实锤回归钉（c-thinking-config 定诊）：强制思考模型拒「关思考」，
        报错是**纯中文**——去参重试不看文案措辞，重试成功即通；重试体不带思考参数
        且预算放大（去参后推理会吃 max_tokens，32 只够思考、正文为空）。
        被拒的首个请求落一行 llm_probe（result=thinking_rejected，评审 P2：重试不造
        隐身请求）。"""
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "glm-5.3-flashx"}]}),
            (
                "POST",
                400,
                {
                    "error": {
                        "message": "1005:该模型始终思考，不支持关闭思考；请使用 low、high 或 max"
                    }
                },
            ),
            ("POST", 200, {"choices": [{"message": {"content": "你好！"}}]}),
        ]
        with caplog.at_level(logging.WARNING, logger="llm_probe"):
            out = _run_async(
                do_test_connection("glm", "sk", "https://open.bigmodel.cn/api/paas/v4", "openai")
            )
        assert out["ok"] is True
        assert [c[0] for c in fake_http.calls] == ["GET", "POST", "POST"]
        stripped = fake_http.calls[2][3]
        assert "thinking" not in stripped
        assert "reasoning_effort" not in stripped
        assert stripped["max_tokens"] == conn_mod._PROBE_MAX_TOKENS_THINKING
        rejected = [
            r for r in caplog.records
            if r.name == "llm_probe" and "thinking_rejected" in r.getMessage()
        ]
        assert len(rejected) == 1, "被拒的首个请求恰一行留痕"
        assert "status=400" in rejected[0].getMessage()

    def test_chat_probe_thinking_enabled_sends_effort(self, fake_http):
        """思考开启（c-thinking-config）：探针按配置发 thinking:enabled＋reasoning_effort，
        预算放大——测试连接与生成同判据。"""
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "glm-5.3-flashx"}]}),
            ("POST", 200, {"choices": [{"message": {"content": "你好！"}}]}),
        ]
        out = _run_async(
            do_test_connection(
                "glm",
                "sk",
                "https://open.bigmodel.cn/api/paas/v4",
                "openai",
                thinking_enabled=True,
                thinking_effort="high",
            )
        )
        assert out["ok"] is True
        payload = fake_http.calls[1][3]
        assert payload["thinking"] == {"type": "enabled"}
        assert payload["reasoning_effort"] == "high"
        assert payload["max_tokens"] == conn_mod._PROBE_MAX_TOKENS_THINKING

    def test_no_model_id_fails_with_prompt(self, fake_http):
        """模型列表为空且无候选 → 判失败提示填模型名（不再只凭可达性报通）。"""
        fake_http.script = [("GET", 200, {"data": []})]
        out = _run_async(
            do_test_connection("openai-compat", "sk", "https://api.example.com", "openai")
        )
        assert out["ok"] is False
        assert "模型名称" in out["error"]
        assert [c[0] for c in fake_http.calls] == ["GET"]

    def test_fallback_empty_reply_fails(self, fake_http):
        """anthropic 降级探针：2xx 但无 text 块 → 不算通。"""
        fake_http.script = [
            ("GET", 404),
            ("POST", 200, {"content": [{"type": "thinking", "thinking": "…"}]}),
        ]
        out = _run_async(
            do_test_connection(
                "glm", "sk", "https://open.bigmodel.cn/api/anthropic", "anthropic"
            )
        )
        assert out["ok"] is False and out["status"] == "unknown"
        assert "回复" in out["error"]

    def test_chat_probe_429_rate_limited(self, fake_http):
        fake_http.script = [
            ("GET", 200, {"data": [{"id": "m-1"}]}),
            ("POST", 429),
        ]
        out = _run_async(
            do_test_connection("openai-compat", "sk", "https://api.example.com", "openai")
        )
        assert out["ok"] is False and out["status"] == "rate_limited"

    def test_probe_within_real_client_lifecycle(self, monkeypatch):
        """P0 回归钉：探针必须在 client 关闭前发出——真 httpx 生命周期（fake 不模拟关闭语义）。

        修前：探针在 async with 之外调用，已关闭的 client 抛 RuntimeError 炸掉
        openai 成功路径；fake client 无关闭语义，测不出也拦不住。
        """
        import httpx as _httpx

        real_client = _httpx.AsyncClient
        seen: list[str] = []

        def handler(request: _httpx.Request) -> _httpx.Response:
            seen.append(str(request.url))
            if request.url.path.endswith("/models"):
                return _httpx.Response(200, json={"data": [{"id": "m-1"}]})
            return _httpx.Response(
                200, json={"choices": [{"message": {"content": "你好！"}}]}
            )

        monkeypatch.setattr(
            conn_mod.httpx,
            "AsyncClient",
            lambda **kw: real_client(transport=_httpx.MockTransport(handler), **kw),
        )
        out = _run_async(
            do_test_connection("deepseek", "sk", "https://api.deepseek.com", "openai")
        )
        assert out["ok"] is True and out["models"] == ["m-1"]
        assert any(u.endswith("/chat/completions") for u in seen)

    def test_anthropic_fallback_405_fails(self, fake_http):
        """anthropic 降级探针 404/405 = 对话接口不可达 → 判败（旧实现误报「连接正常」）。"""
        fake_http.script = [("GET", 404), ("POST", 405, {"detail": "Method Not Allowed"})]
        out = _run_async(
            do_test_connection("glm", "sk", "https://wrong.example.com", "anthropic")
        )
        assert out["ok"] is False and out["status"] == "endpoint_mismatch"
        assert "405" in out["error"]


class TestFetchModels:
    """只拉清单轻探针（c-api-config-auto-models）：GET-only、零生成调用。"""

    def test_openai_200_no_generation_probe(self, fake_http):
        """openai 格式拉清单成功：只发一条 GET，SHALL NOT 追加对话探针（与连接测试的关键差异）。"""
        fake_http.script = [("GET", 200, {"data": [{"id": "m-1"}, {"id": "m-2"}]})]
        out = _run_async(
            do_fetch_models("kimi", "sk", "https://api.moonshot.cn/v1", "openai")
        )
        assert out["ok"] is True and out["models"] == ["m-1", "m-2"]
        assert out["status"] == "ok"
        assert [c[0] for c in fake_http.calls] == ["GET"]
        assert fake_http.calls[0][1].endswith("/v1/models")

    def test_anthropic_404_returns_candidates_without_generation(self, fake_http):
        """anthropic 404 → 空清单＋候选＋说明，且不发降级生成请求（轻探针不发生成）。"""
        fake_http.script = [("GET", 404)]
        out = _run_async(
            do_fetch_models(
                "deepseek", "sk", "https://api.deepseek.com/anthropic", "anthropic"
            )
        )
        assert out["ok"] is True and out["models"] == []
        assert out["candidates"] == ["deepseek-flash", "deepseek-v4-pro"]
        assert out["note"]
        assert [c[0] for c in fake_http.calls] == ["GET"]  # 无 POST

    def test_html_page_fails(self, fake_http):
        """200 但体是网页 → 判败并提示核对 Base URL（填错网址提前暴露，无需等测试连接）。"""
        fake_http.script = [("GET", 200, ValueError("not json"), "text/html")]
        out = _run_async(
            do_fetch_models("openai", "sk", "https://platform.deepseek.com", "openai")
        )
        assert out["ok"] is False and out["status"] == "endpoint_mismatch"
        assert "不是 API 数据" in out["error"]

    def test_empty_key_no_network(self, fake_http):
        """非 ollama 且 Key 为空 → 鉴权失败，零网络请求。"""
        out = _run_async(
            do_fetch_models("openai", "", "https://api.openai.com", "openai")
        )
        assert out["ok"] is False and out["status"] == "auth_error"
        assert fake_http.calls == []

    def test_ollama_tags_free_of_key(self, fake_http):
        """ollama 免 Key：GET /api/tags，按 tags 形态提取。"""
        fake_http.script = [("GET", 200, {"models": [{"name": "llama3:8b"}]})]
        out = _run_async(do_fetch_models("ollama", "", "http://localhost:11434", "openai"))
        assert out["ok"] is True and out["models"] == ["llama3:8b"]
        assert fake_http.calls[0][1].endswith("/api/tags")

    def test_auth_401_fails(self, fake_http):
        fake_http.script = [("GET", 401)]
        out = _run_async(
            do_fetch_models("glm", "sk", "https://open.bigmodel.cn/api/paas/v4", "openai")
        )
        assert out["ok"] is False and out["status"] == "auth_error"

    def test_openai_404_is_error_not_no_list(self, fake_http):
        """openai 格式 404＝Base URL 路径可疑（异常响应），SHALL NOT 误诊为「无清单端点」（评审 P1）。"""
        fake_http.script = [("GET", 404)]
        out = _run_async(
            do_fetch_models("openai", "sk", "https://api.example.com/wrong-path", "openai")
        )
        assert out["ok"] is False and out["status"] == "unknown"
        assert "404" in out["error"]
        assert "note" not in out and "candidates" not in out

    def test_rate_limited_429(self, fake_http):
        fake_http.script = [("GET", 429)]
        out = _run_async(
            do_fetch_models("openai", "sk", "https://api.openai.com/v1", "openai")
        )
        assert out["ok"] is False and out["status"] == "rate_limited"

    def test_server_error_500(self, fake_http):
        fake_http.script = [("GET", 500, {"error": {"message": "upstream down"}})]
        out = _run_async(
            do_fetch_models("qwen", "sk", "https://dashscope.aliyuncs.com/compatible-mode/v1", "openai")
        )
        assert out["ok"] is False and out["status"] == "network_error"
        assert "upstream down" in out["error"]

    def test_ollama_custom_port_respected(self, fake_http):
        """ollama 自定义端口的 base 一律照打——旧实现见 "localhost" 硬替 11434（评审 P2 实锤）。"""
        fake_http.script = [("GET", 200, {"models": [{"name": "llama3:8b"}]})]
        out = _run_async(
            do_fetch_models("ollama", "", "http://localhost:12345", "openai")
        )
        assert out["ok"] is True and out["models"] == ["llama3:8b"]
        assert fake_http.calls[0][1] == "http://localhost:12345/api/tags"


# ═════════════════ 4. 契约：create/update 语义 ═════════════════


class TestContract:
    def test_create_without_format_derives_like_old_runtime(self):
        user_id = f"u-{uuid.uuid4().hex[:8]}"
        _run_async(_create_user(user_id))

        async def _go():
            async with async_session() as db:
                a = await create_api_config(
                    db, user_id, "官方", "anthropic", "https://api.anthropic.com"
                )
                b = await create_api_config(
                    db,
                    user_id,
                    "GLM anthropic",
                    "glm",
                    "https://open.bigmodel.cn/api/anthropic",
                )
                c = await create_api_config(
                    db, user_id, "GLM openai", "glm", "https://open.bigmodel.cn/api/paas/v4"
                )
            return a, b, c

        a, b, c = _run_async(_go())
        assert a["api_format"] == "anthropic"  # vendor=anthropic → anthropic
        assert b["api_format"] == "anthropic"  # URL 嗅探兜底（旧前端等价）
        assert c["api_format"] == "openai"

    def test_create_explicit_format_wins(self):
        user_id = f"u-{uuid.uuid4().hex[:8]}"
        _run_async(_create_user(user_id))

        async def _go():
            async with async_session() as db:
                return await create_api_config(
                    db,
                    user_id,
                    "中转",
                    "openai-compat",
                    "https://relay.example.com/v1",
                    api_format="anthropic",
                )

        assert _run_async(_go())["api_format"] == "anthropic"

    def test_body_rejects_unknown_format(self):
        with pytest.raises(ValidationError):
            CreateApiConfigBody(
                name="x", vendor_id="glm", base_url="https://x", api_format="graphql"
            )

    async def _seed_and_update(self, updates: dict):
        user_id = f"u-{uuid.uuid4().hex[:8]}"
        await _create_user(user_id)
        async with async_session() as session:
            cfg = ApiConfig(
                user_id=user_id,
                name="配置",
                vendor="glm",
                api_format="anthropic",
                api_key=encrypt_api_key("sk"),
                base_url="https://open.bigmodel.cn/api/anthropic",
                models=json.dumps(["glm-4.7"]),
                last_test_status="ok",
            )
            session.add(cfg)
            await session.commit()
            cid = cfg.id
        async with async_session() as db:
            out = await update_api_config(db, user_id, cid, updates)
        return out

    def test_update_format_clears_models_and_test_state(self):
        out = _run_async(self._seed_and_update({"api_format": "openai"}))
        assert out["api_format"] == "openai"
        assert out["models"] == []
        assert out["last_test_status"] is None

    def test_update_without_format_touches_nothing(self):
        out = _run_async(self._seed_and_update({"name": "改名"}))
        assert out["api_format"] == "anthropic"
        assert out["models"] == ["glm-4.7"]
        assert out["last_test_status"] == "ok"

    def test_update_base_url_keeps_format(self):
        out = _run_async(
            self._seed_and_update({"base_url": "https://open.bigmodel.cn/api/paas/v4"})
        )
        # vendor 被重识别也仍是 glm，且协议不被回写
        assert out["vendor"] == "glm"
        assert out["api_format"] == "anthropic"


# ═════════════════ 5. 备份 roundtrip：加键 + 旧包默认 ═════════════════


class TestBackupRoundtrip:
    def test_export_includes_api_format(self):
        import io
        import zipfile

        import yaml

        user_id = f"u-{uuid.uuid4().hex[:8]}"
        _run_async(_create_user(user_id))
        _run_async(
            _create_config(
                user_id,
                "anthropic 行",
                api_format="anthropic",
                base_url="https://open.bigmodel.cn/api/anthropic",
            )
        )

        async def _go():
            async with async_session() as db:
                return await build_config_package_bytes(db, user_id)

        payload_bytes, _name = _run_async(_go())
        with zipfile.ZipFile(io.BytesIO(payload_bytes)) as zf:
            data = yaml.safe_load(zf.read("config.yaml"))
        entries = data["api_configs"]
        assert entries[0]["api_format"] == "anthropic"

    def test_import_old_package_without_key_defaults_openai(self):
        user_id = f"u-{uuid.uuid4().hex[:8]}"
        _run_async(_create_user(user_id))
        old_entry = {
            "name": "旧包配置",
            "vendor": "glm",
            "vendor_display_name": "GLM",
            "api_key": "sk-old",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
        }

        async def _go():
            async with async_session() as db:
                out = await _restore_config(db, user_id, {"api_configs": [old_entry]})
                await db.commit()  # _restore_config 只 flush 不 commit（router 侧收口）
                return out

        out = _run_async(_go())
        assert out["created"] == 1

        async def _read():
            async with async_session() as db:
                cfg = (
                    await db.scalars(
                        select(ApiConfig).where(ApiConfig.user_id == user_id)
                    )
                ).first()
                return cfg.api_format

        assert _run_async(_read()) == "openai"

    def test_import_new_package_preserves_anthropic(self):
        user_id = f"u-{uuid.uuid4().hex[:8]}"
        _run_async(_create_user(user_id))
        entry = {
            "name": "新包 anthropic",
            "vendor": "glm",
            "api_key": "sk",
            "base_url": "https://open.bigmodel.cn/api/anthropic",
            "api_format": "anthropic",
        }

        async def _go():
            async with async_session() as db:
                await _restore_config(db, user_id, {"api_configs": [entry]})
                await db.commit()  # _restore_config 只 flush 不 commit
                await db.commit()
                cfg = (
                    await db.scalars(
                        select(ApiConfig).where(ApiConfig.user_id == user_id)
                    )
                ).first()
                return cfg.api_format

        assert _run_async(_go()) == "anthropic"
