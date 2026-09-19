"""WXPAY_* 配置校验单测：缺项列举 + notify_url 官方硬性要求 + 密钥语义。

覆盖 s-pay-wechat-gateway 任务 1.1/1.2 的验证项：
配置缺省值为空串、wxpay_config_errors 非空清单即拒绝启动。
"""
from __future__ import annotations

from app.config import Settings

# 合法基线（文件路径由 tmp_path 临时生成）
BASE = {
    "WXPAY_MCH_ID": "1749993584",
    "WXPAY_APPID": "wx41899938fa14c26d",
    "WXPAY_CERT_SERIAL": "1AEE63CDDC185649611F9C7B49FECED290DACD09",
    "WXPAY_APIV3_KEY": "x" * 32,
    "WXPAY_PUB_KEY_ID": "PUB_KEY_ID_0117499935842026090100381880001403",
    "WXPAY_NOTIFY_URL": "https://www.example.com/api/pay/notify",
}


def _settings(tmp_path, **overrides) -> Settings:
    values = {**BASE, **overrides}
    if "WXPAY_PRIVATE_KEY_PATH" not in overrides:
        key_file = tmp_path / "apiclient_key.pem"
        key_file.write_text("-----BEGIN PRIVATE KEY-----\nplaceholder\n-----END PRIVATE KEY-----\n")
        values["WXPAY_PRIVATE_KEY_PATH"] = str(key_file)
    if "WXPAY_PUB_KEY_PATH" not in overrides:
        pub_file = tmp_path / "pub_key.pem"
        pub_file.write_text("-----BEGIN PUBLIC KEY-----\nplaceholder\n-----END PUBLIC KEY-----\n")
        values["WXPAY_PUB_KEY_PATH"] = str(pub_file)
    s = Settings()
    for k, v in values.items():
        setattr(s, k, v)
    return s


class TestWxpayConfigErrors:

    def test_all_missing_lists_eight(self, tmp_path):
        """全缺省（空串）→ 恰好 8 条「未配置」。"""
        s = Settings()
        errors = s.wxpay_config_errors()
        assert len([e for e in errors if "未配置" in e]) == 8

    def test_valid_baseline_passes(self, tmp_path):
        assert _settings(tmp_path).wxpay_config_errors() == []

    def test_apiv3_key_length(self, tmp_path):
        s = _settings(tmp_path, WXPAY_APIV3_KEY="short")
        assert any("WXPAY_APIV3_KEY" in e and "32" in e for e in s.wxpay_config_errors())

    def test_pub_key_id_prefix(self, tmp_path):
        s = _settings(tmp_path, WXPAY_PUB_KEY_ID="CERT_123")
        assert any("PUB_KEY_ID_" in e for e in s.wxpay_config_errors())

    def test_missing_key_file(self, tmp_path):
        s = _settings(tmp_path, WXPAY_PRIVATE_KEY_PATH="/nonexistent/key.pem")
        assert any("WXPAY_PRIVATE_KEY_PATH" in e and "不存在" in e for e in s.wxpay_config_errors())

    def test_missing_pub_file(self, tmp_path):
        s = _settings(tmp_path, WXPAY_PUB_KEY_PATH="/nonexistent/pub.pem")
        assert any("WXPAY_PUB_KEY_PATH" in e and "不存在" in e for e in s.wxpay_config_errors())


class TestNotifyUrlRules:
    """notify_url 官方硬性要求：https 全路径、无 query、非本地/内网。"""

    def test_http_rejected(self, tmp_path):
        s = _settings(tmp_path, WXPAY_NOTIFY_URL="http://www.example.com/api/pay/notify")
        assert any("https://" in e for e in s.wxpay_config_errors())

    def test_query_string_rejected(self, tmp_path):
        s = _settings(tmp_path, WXPAY_NOTIFY_URL="https://www.example.com/api/pay/notify?from=wx")
        assert any("查询参数" in e for e in s.wxpay_config_errors())

    def test_localhost_rejected(self, tmp_path):
        s = _settings(tmp_path, WXPAY_NOTIFY_URL="https://localhost/api/pay/notify")
        assert any("本地/内网域名" in e for e in s.wxpay_config_errors())

    def test_private_ip_rejected(self, tmp_path):
        for host in ("192.168.1.10", "10.0.0.5", "172.16.0.9", "127.0.0.1", "169.254.1.1"):
            s = _settings(tmp_path, WXPAY_NOTIFY_URL=f"https://{host}/api/pay/notify")
            assert any("内网/保留 IP" in e for e in s.wxpay_config_errors()), host

    def test_public_domain_ok(self, tmp_path):
        s = _settings(tmp_path, WXPAY_NOTIFY_URL="https://www.xingweitouzi.cn/api/pay/notify")
        assert s.wxpay_config_errors() == []


class TestWxpayKeyPemFromEnv:
    """密钥 PEM 环境变量注入（代码库拉取部署形态）：PEM 内容与文件路径二选一。"""

    def test_env_pem_passes_without_key_files(self, tmp_path):
        """PEM 内容已提供 → 文件路径豁免（构建包里没有密钥文件也能过门禁）。"""
        s = _settings(tmp_path,
                      WXPAY_PRIVATE_KEY_PEM="-----BEGIN PRIVATE KEY-----\nX\n-----END PRIVATE KEY-----\n",
                      WXPAY_PUB_KEY_PEM="-----BEGIN PUBLIC KEY-----\nY\n-----END PUBLIC KEY-----\n",
                      WXPAY_PRIVATE_KEY_PATH="/nonexistent/key.pem",
                      WXPAY_PUB_KEY_PATH="/nonexistent/pub.pem")
        assert s.wxpay_config_errors() == []

    def test_file_mode_still_requires_existing_files(self, tmp_path):
        """PEM 内容缺省 → 走文件路径模式，文件缺失照常报错。"""
        s = _settings(tmp_path,
                      WXPAY_PRIVATE_KEY_PEM="", WXPAY_PUB_KEY_PEM="",
                      WXPAY_PRIVATE_KEY_PATH="/nonexistent/key.pem",
                      WXPAY_PUB_KEY_PATH="/nonexistent/pub.pem")
        errs = s.wxpay_config_errors()
        assert any("WXPAY_PRIVATE_KEY_PATH" in e for e in errs)
        assert any("WXPAY_PUB_KEY_PATH" in e for e in errs)
