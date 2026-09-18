"""配置层单元测试：DATABASE_URL 方言选择 + 支付网关开关语义。"""

from __future__ import annotations

from app.config import settings


class TestDatabaseUrl:
    def test_default_is_sqlite(self):
        """未设置 DATABASE_URL 时回退 SQLite（本地/测试默认）。

        集成 conftest 已把 DATABASE_URL 指向临时 SQLite，这里只验证方言。"""
        assert settings.DATABASE_URL.startswith("sqlite:///")

    def test_follows_db_path_override(self, monkeypatch):
        """测试覆盖 DB_PATH 后（契约测试模式），连接串跟随新路径。

        需先摘掉集成 conftest 注入的 DATABASE_URL（属性在 env 缺省时才回退 DB_PATH）。"""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        original = settings.DB_PATH
        try:
            settings.DB_PATH = "/tmp/license-test.db"
            assert settings.DATABASE_URL == "sqlite:////tmp/license-test.db"
        finally:
            settings.DB_PATH = original


class TestPaymentsGateway:
    """网关选择语义（s-security-hardening R2）：本地缺省 mock、空串=未配置、显式优先。"""

    def test_local_default_gateway_is_mock(self):
        """本地（sqlite）缺省：生效网关回落 mock（dev 端点注册），零配置可用。"""
        assert settings.DB_BACKEND != "pg_http"
        assert settings.effective_gateway == "mock"

    def test_pg_http_without_explicit_gateway_has_none(self, monkeypatch):
        """生产未显式配置 → 无生效网关（由启动门禁拒绝，不再静默回落 mock）。"""
        monkeypatch.setattr(settings, "DB_BACKEND", "pg_http")
        monkeypatch.setattr(settings, "PAYMENTS_GATEWAY", "")
        assert settings.effective_gateway == ""

    def test_explicit_gateway_wins(self, monkeypatch):
        monkeypatch.setattr(settings, "PAYMENTS_GATEWAY", "wxpay")
        assert settings.effective_gateway == "wxpay"

    def test_dev_endpoints_registered_in_local_mock(self):
        from app.interfaces.web_api import dev_inject

        assert dev_inject._MOCK_MODE is True  # 测试环境（sqlite）缺省 mock
        assert len(dev_inject.r.routes) > 0


class TestStartupGate:
    """生产启动门禁（s-security-hardening R1-R2）：pg_http 严格、sqlite 零强制。"""

    def test_local_form_never_blocks(self):
        assert settings.startup_config_errors() == []  # sqlite 测试环境

    def test_pg_http_empty_secrets_and_gateway_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "DB_BACKEND", "pg_http")
        monkeypatch.setattr(settings, "JWT_SECRET", "")
        monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
        monkeypatch.setattr(settings, "PAYMENTS_GATEWAY", "")
        errs = settings.startup_config_errors()
        assert any("JWT_SECRET" in e for e in errs), errs
        assert any("ADMIN_TOKEN" in e for e in errs), errs
        assert any("PAYMENTS_GATEWAY" in e for e in errs), errs

    def test_pg_http_default_secrets_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "DB_BACKEND", "pg_http")
        monkeypatch.setattr(settings, "JWT_SECRET", "local-license-secret")
        monkeypatch.setattr(settings, "ADMIN_TOKEN", "admin123")
        errs = settings.startup_config_errors()
        assert len(errs) == 3  # 两个密钥 + 网关未配置

    def test_pg_http_mock_requires_allow_flag(self, monkeypatch):
        monkeypatch.setattr(settings, "DB_BACKEND", "pg_http")
        monkeypatch.setattr(settings, "JWT_SECRET", "x" * 48)
        monkeypatch.setattr(settings, "ADMIN_TOKEN", "y" * 24)
        monkeypatch.setattr(settings, "PAYMENTS_GATEWAY", "mock")
        monkeypatch.setattr(settings, "PAYMENTS_ALLOW_MOCK", "")
        assert any("PAYMENTS_ALLOW_MOCK" in e for e in settings.startup_config_errors())
        monkeypatch.setattr(settings, "PAYMENTS_ALLOW_MOCK", "1")
        assert settings.startup_config_errors() == []

    def test_pg_http_valid_config_passes(self, monkeypatch):
        monkeypatch.setattr(settings, "DB_BACKEND", "pg_http")
        monkeypatch.setattr(settings, "JWT_SECRET", "x" * 48)
        monkeypatch.setattr(settings, "ADMIN_TOKEN", "y" * 24)
        monkeypatch.setattr(settings, "PAYMENTS_GATEWAY", "wxpay")
        assert settings.startup_config_errors() == []

    def test_unsupported_gateway_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "DB_BACKEND", "pg_http")
        monkeypatch.setattr(settings, "JWT_SECRET", "x" * 48)
        monkeypatch.setattr(settings, "ADMIN_TOKEN", "y" * 24)
        monkeypatch.setattr(settings, "PAYMENTS_GATEWAY", "alipay")
        assert any("alipay" in e for e in settings.startup_config_errors())

    def test_error_messages_never_echo_secret_values(self, monkeypatch):
        monkeypatch.setattr(settings, "DB_BACKEND", "pg_http")
        monkeypatch.setattr(settings, "JWT_SECRET", "short-secret-abc")
        monkeypatch.setattr(settings, "ADMIN_TOKEN", "short-admin-xyz")
        joined = "；".join(settings.startup_config_errors())
        assert "short-secret-abc" not in joined and "short-admin-xyz" not in joined

    def test_real_startup_refuses_with_bad_production_config(self, monkeypatch):
        """端到端：pg_http + 空密钥时应用启动即 RuntimeError（fail-closed 实证）。"""
        import pytest
        from fastapi.testclient import TestClient

        # 模块级 app：startup 处理器（app.on_event）只挂在它上面（create_app 返回的新实例不带）
        from app.main import app as real_app

        monkeypatch.setattr(settings, "DB_BACKEND", "pg_http")
        monkeypatch.setattr(settings, "JWT_SECRET", "")
        monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
        monkeypatch.setattr(settings, "PAYMENTS_GATEWAY", "")
        with pytest.raises(RuntimeError, match="拒绝启动"), TestClient(real_app):
            pass


class TestApiDocsGate:
    """文档端点默认关闭（s-security-hardening R3）。"""

    def test_docs_endpoints_404_by_default(self, client):
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404, path

    def test_docs_endpoints_available_when_explicitly_enabled(self, monkeypatch):
        from fastapi.testclient import TestClient

        from app.main import create_app

        monkeypatch.setattr(settings, "ENABLE_API_DOCS", "1")
        with TestClient(create_app()) as c:
            assert c.get("/openapi.json").status_code == 200
