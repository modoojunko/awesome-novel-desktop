"""AI 客户端超时纪律 + 失败记账（ai-client-timeout-and-usage-accounting）。

- AIClient 构造必须显式传 timeout/max_retries（不依赖 SDK 默认 600s×重试）
- 网络层失败（超时/连接不通）归一为 AITimeoutError；其余异常原样透传
- _judge_chat 任何退出路径都把累计用量回填调用方（finally 单点）
- record_usage(force=True) 允许零 token 的失败记录落库
- 端点失败路径落 `*_fail` 记录；成功零 token 仍不落库
"""

import asyncio
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

import ai_client as ai_client_module
from ai_client import AIClient, AITimeoutError


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _KwargsCapture:
    """记录构造 kwargs 的 fake SDK 根。"""

    def __init__(self):
        self.init_kwargs: dict = {}


class _FakeOpenAICapture(_KwargsCapture):
    def __init__(self, **kwargs):
        super().__init__()
        self.init_kwargs = kwargs
        self.chat = type("Chat", (), {"completions": type("C", (), {"create": staticmethod(lambda **kw: (_ for _ in ()).throw(AssertionError("not called")))})()})()


class _FakeAnthropicCapture(_KwargsCapture):
    def __init__(self, **kwargs):
        super().__init__()
        self.init_kwargs = kwargs
        self.messages = type("Messages", (), {"create": staticmethod(lambda **kw: (_ for _ in ()).throw(AssertionError("not called")))})()


class TestTimeoutInjection:
    def test_openai_constructor_gets_timeout_and_retries(self, monkeypatch):
        monkeypatch.setattr(ai_client_module, "AsyncOpenAI", _FakeOpenAICapture)
        c = AIClient(api_key="sk-x", base_url="https://api.example.com/v1", model="m")
        kw = c._client.init_kwargs
        assert kw["max_retries"] == 1
        assert isinstance(kw["timeout"], httpx.Timeout)
        assert kw["timeout"].read == 90.0

    def test_anthropic_constructor_gets_timeout_and_retries(self, monkeypatch):
        monkeypatch.setattr(ai_client_module, "AsyncAnthropic", _FakeAnthropicCapture)
        c = AIClient(
            api_key="sk-x", base_url="https://x/anthropic",
            model="m", api_format="anthropic",
        )
        kw = c._client.init_kwargs
        assert kw["max_retries"] == 1
        assert isinstance(kw["timeout"], httpx.Timeout)
        assert kw["timeout"].read == 90.0

    def test_custom_timeout_overrides_default(self, monkeypatch):
        monkeypatch.setattr(ai_client_module, "AsyncOpenAI", _FakeOpenAICapture)
        custom = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        c = AIClient(api_key="sk-x", timeout=custom, max_retries=0)
        assert c._client.init_kwargs["timeout"] is custom
        assert c._client.init_kwargs["max_retries"] == 0


class _TimeoutRaisingOpenAI:
    """create 抛网络异常的 fake（chat.completions 与 messages 双分支）。"""

    def __init__(self, exc, **kwargs):
        self._exc = exc

        class _Completions:
            @staticmethod
            async def create(**kw):
                raise self._exc

        class _Messages:
            @staticmethod
            async def create(**kw):
                raise self._exc

        self.chat = type("Chat", (), {"completions": _Completions()})()
        self.messages = _Messages()


class TestAITimeoutError:
    def test_openai_timeout_normalized(self, monkeypatch):
        exc = ai_client_module.OpenAITimeoutError("timed out")
        monkeypatch.setattr(ai_client_module, "AsyncOpenAI", lambda **kw: _TimeoutRaisingOpenAI(exc))
        c = AIClient(api_key="sk-x", model="m")
        with pytest.raises(AITimeoutError):
            _run_async(c.chat(model="haiku", system="", messages=[]))

    def test_anthropic_timeout_normalized(self, monkeypatch):
        exc = ai_client_module.AnthropicConnectionError("conn refused")
        monkeypatch.setattr(ai_client_module, "AsyncAnthropic", lambda **kw: _TimeoutRaisingOpenAI(exc))
        c = AIClient(api_key="sk-x", model="m", api_format="anthropic")
        with pytest.raises(AITimeoutError):
            _run_async(c.chat(model="haiku", system="", messages=[]))

    def test_business_errors_not_normalized(self):
        class _C:
            async def chat(self, **kw):
                raise ValueError("模型未返回文本内容")

        c = AIClient.__new__(AIClient)  # 绕过构造，只测 chat 透传路径之外的分派
        # 业务异常在 _judge_chat 层原样抛，不归一为 AITimeoutError
        with pytest.raises(ValueError):
            _run_async(ai_client_module.AIClient._guarded(c, _coro_raise()))


async def _coro_raise():
    raise ValueError("业务异常")


class TestJudgeChatFinallyFlush:
    def test_error_after_partial_usage_flushes(self):
        """首次尝试烧 token 后抛不可重试异常，caller usage 仍拿到已烧 token。"""
        from settings.ai_router import _judge_chat

        class _C:
            def __init__(self):
                self.n = 0

            async def chat(self, **kw):
                self.n += 1
                kw["usage"]["tokens_in"] = 100
                kw["usage"]["tokens_out"] = 5
                raise ValueError("严重的供应商错误")

        usage: dict = {}
        c = _C()
        with pytest.raises(ValueError, match="严重的供应商错误"):
            _run_async(_judge_chat(c, model="haiku", system="", messages=[], usage=usage))
        assert usage == {"tokens_in": 100, "tokens_out": 5}
        assert c.n == 1

    def test_timeout_after_partial_usage_flushes(self):
        """首次尝试烧 token 后超时（AITimeoutError），caller usage 仍拿到已烧 token。"""
        from settings.ai_router import _judge_chat

        class _C:
            async def chat(self, **kw):
                kw["usage"]["tokens_in"] = 42
                kw["usage"]["tokens_out"] = 3
                raise AITimeoutError("AI 服务连接超时或失败")

        usage: dict = {}
        with pytest.raises(AITimeoutError):
            _run_async(_judge_chat(_C(), model="haiku", system="", messages=[], usage=usage))
        assert usage == {"tokens_in": 42, "tokens_out": 3}

    def test_success_still_flushes(self):
        from settings.ai_router import _judge_chat

        class _C:
            async def chat(self, **kw):
                kw["usage"]["tokens_in"] = 7
                kw["usage"]["tokens_out"] = 9
                return "ok"

        usage: dict = {}
        out = _run_async(_judge_chat(_C(), model="haiku", system="", messages=[], usage=usage))
        assert out == "ok"
        assert usage == {"tokens_in": 7, "tokens_out": 9}


class TestEndpointFailureAccounting:
    """端点失败路径落 `*_fail` 记录；成功零 token 仍不落库。

    复用 conftest 的会话级共享临时库（表已建、FK 不强制）；
    鉴权与门控走 dependency_overrides。
    """

    @pytest.fixture(scope="class", autouse=True)
    def _seed_user(self):
        """TokenLog.user_id FK 指向 users——usage.py 的 commit 失败会静默 rollback。"""
        from db import async_session
        from models.user import User

        async def _create():
            async with async_session() as session:
                session.add(
                    User(
                        id="timeout-user",
                        email="timeout-user@test.com",
                        password_hash="*",
                        display_name="timeout-user",
                    )
                )
                await session.commit()

        _run_async(_create())
        yield

    @pytest.fixture
    def client(self):
        from auth_local.deps import require_ai_access, require_novel_model
        from auth_local.middleware import get_current_user
        from db import async_session, get_db
        from main import app

        async def _override_get_db():
            async with async_session() as session:
                yield session

        async def _override_user():
            return {"id": "timeout-user"}

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[require_ai_access] = lambda: True
        app.dependency_overrides[require_novel_model] = lambda: True
        yield app
        app.dependency_overrides.clear()

    def _rows_of(self, project_id):
        from sqlalchemy import select

        from db import async_session
        from models.token_log import TokenLog

        async def _rows():
            async with async_session() as session:
                result = await session.execute(
                    select(TokenLog).where(TokenLog.project_id == project_id)
                )
                return list(result.scalars())

        return _run_async(_rows())

    def _make_project(self, client) -> str:
        import tempfile

        from db import async_session
        from models import Novel

        async def _create():
            async with async_session() as session:
                proj = Novel(
                    user_id="timeout-user",
                    name="超时记账" + uuid.uuid4().hex[:6],
                    slug="timeout-" + uuid.uuid4().hex[:8],
                    root_path=tempfile.mkdtemp(prefix="timeout-novel-"),
                    source="manual",
                    current_phase="write",
                )
                session.add(proj)
                await session.commit()
                return proj.id

        return _run_async(_create())

    def test_timeout_returns_502_and_records_fail(self, monkeypatch, client):
        async def _failing_client(novel_id=None):
            return _FailingClient(fail=True)

        monkeypatch.setattr("settings.ai_router.get_ai_client_for_novel", _failing_client)
        with TestClient(client) as c:
            project_id = self._make_project(c)
            c.put(
                "/api/novels/" + project_id + "/story",
                json={"synopsis": "测试前提"},
            )
            resp = c.post(
                "/api/novels/" + project_id + "/settings/ai/world/draft",
                json={"topic": "力量体系"},
            )
            assert resp.status_code == 502, resp.text
            assert "超时" in resp.json()["detail"]

        rows = self._rows_of(project_id)
        assert [r.operation for r in rows] == ["settings_world_draft_力量体系_fail"]
        assert rows[0].tokens_in == 0 and rows[0].tokens_out == 0

    def test_success_zero_token_still_skipped(self, monkeypatch, client):
        """成功零 token 不落库（防噪音语义不变）。"""
        async def _zero_client(novel_id=None):
            return _FailingClient(tokens=0, fail=False)

        monkeypatch.setattr("settings.ai_router.get_ai_client_for_novel", _zero_client)
        with TestClient(client) as c:
            project_id = self._make_project(c)
            c.put(
                "/api/novels/" + project_id + "/story",
                json={"synopsis": "测试前提"},
            )
            resp = c.post(
                "/api/novels/" + project_id + "/settings/ai/world/draft",
                json={"topic": "力量体系"},
            )
            assert resp.status_code == 200, resp.text

        assert self._rows_of(project_id) == []


class _FailingClient:
    """draft 端点用的失败/零 token 双模式 fake。"""

    def __init__(self, tokens: int = 0, fail: bool = True):
        self.tokens = tokens
        self.fail = fail

    async def chat(self, model, system, messages, max_tokens=1024, usage=None, **kwargs):
        if self.fail:
            raise AITimeoutError("AI 服务连接超时或失败")
        if usage is not None:
            usage["tokens_in"] = self.tokens
            usage["tokens_out"] = 0
        return '{"value": "一段可用的世界设定"}'
