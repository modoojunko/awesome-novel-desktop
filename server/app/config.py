from __future__ import annotations

import logging
import os
from pathlib import Path


class Settings:
    """所有配置集中读取环境变量，不可变（使用者只读）。"""

    # ── 服务 ──
    PORT: int = int(os.getenv("PORT", "19000"))
    HOST: str = os.getenv("HOST", "127.0.0.1")

    # ── 数据库 ──
    # sqlite（默认，本地开发/测试，现有测试零改动）
    # pg_http（生产：CloudBase PostgreSQL 经 PostgREST HTTP API 访问，体验版套餐无需 TCP 直连）
    DB_BACKEND: str = os.getenv("DB_BACKEND", "sqlite")
    DB_DIR: Path = Path(os.getenv("DB_DIR", Path(__file__).parent.parent))
    DB_PATH: str = str(DB_DIR / os.getenv("DB_NAME", "license.db"))

    # ── CloudBase PG（DB_BACKEND=pg_http 时）──
    TCB_PG_ENV_ID: str = os.getenv("TCB_PG_ENV_ID", "")
    TCB_PG_API_KEY: str = os.getenv("TCB_PG_API_KEY", "")

    @property
    def DATABASE_URL(self) -> str:
        """数据库连接串。显式设置 DATABASE_URL（如 postgresql://...）时使用之，
        否则回退 SQLite（路径跟随 DB_DIR/DB_NAME，便于测试覆盖 DB_PATH）。"""
        return os.getenv("DATABASE_URL", "") or f"sqlite:///{self.DB_PATH}"

    @property
    def TCB_PG_ENDPOINT(self) -> str:
        """CloudBase PG PostgREST 端点，默认按环境 ID 推导。"""
        return os.getenv("TCB_PG_ENDPOINT", "") or (
            f"https://{self.TCB_PG_ENV_ID}.api.tcloudbasegateway.com/v1/rdb/rest"
            if self.TCB_PG_ENV_ID
            else ""
        )

    # ── JWT ──
    JWT_SECRET: str = os.getenv("JWT_SECRET", "local-license-secret")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 30

    # ── Admin ──
    ADMIN_TOKEN: str = os.getenv("ADMIN_TOKEN", "admin123")

    # ── 支付运维（设计 G7/B3/演练 A9）──
    # 支付网关切换：mock（默认/空串，Change 1 全链替身+dev 注入端点注册）|
    # wxpay|alipay（Change 2，dev 注入端点自动消失）
    PAYMENTS_GATEWAY: str = os.getenv("PAYMENTS_GATEWAY", "mock") or "mock"
    # Server酱 SendKey：资金类告警通道；空 = 降级为仅日志（本地/CI 默认）
    SERVERCHAN_SENDKEY: str = os.getenv("SERVERCHAN_SENDKEY", "")
    # 定时扫描端点（R1-R4）令牌：pay-cron 云函数以 X-Cron-Token 头携带；空 = 端点全拒
    CRON_TOKEN: str = os.getenv("CRON_TOKEN", "")
    # 演练白名单：逗号分隔用户名。购买开关=rehearsal 时仅名单内用户可下单，
    # 且对账/计税报表排除名单用户（演练数据不进资金口径）
    PAYMENTS_REHEARSAL_USERNAMES: str = os.getenv("PAYMENTS_REHEARSAL_USERNAMES", "")
    # 月销免税额度标注（分）：月净额低于此值在计税报表标注"未超小规模免税额度"
    TAX_EXEMPT_THRESHOLD_FEN: int = int(os.getenv("TAX_EXEMPT_THRESHOLD_FEN", "10000000"))

    # ── 微信支付 APIv3（PAYMENTS_GATEWAY=wxpay 时全部必需，Change 2）──
    WXPAY_MCH_ID: str = os.getenv("WXPAY_MCH_ID", "")
    WXPAY_APPID: str = os.getenv("WXPAY_APPID", "")
    WXPAY_CERT_SERIAL: str = os.getenv("WXPAY_CERT_SERIAL", "")
    WXPAY_PRIVATE_KEY_PATH: str = os.getenv("WXPAY_PRIVATE_KEY_PATH", "")
    WXPAY_APIV3_KEY: str = os.getenv("WXPAY_APIV3_KEY", "")
    WXPAY_PUB_KEY_ID: str = os.getenv("WXPAY_PUB_KEY_ID", "")
    WXPAY_PUB_KEY_PATH: str = os.getenv("WXPAY_PUB_KEY_PATH", "")
    WXPAY_NOTIFY_URL: str = os.getenv("WXPAY_NOTIFY_URL", "")

    # 微信回调地址硬性校验（官方要求：https 全路径、无查询参数、外网可达）
    _WXPAY_INTERNAL_HOST_SUFFIXES = (".local", ".internal", ".lan")

    def wxpay_config_errors(self) -> list[str]:
        """校验 WXPAY_* 配置齐备性与语义合法性，返回问题清单（空=可启动）。

        main.py 注入 wxpay 网关前调用；非空即 RuntimeError 列出全部问题，
        绝不允许缺配置静默回落 Mock 收真实付款。
        """
        errors: list[str] = []
        required = (
            "WXPAY_MCH_ID", "WXPAY_APPID", "WXPAY_CERT_SERIAL",
            "WXPAY_PRIVATE_KEY_PATH", "WXPAY_APIV3_KEY",
            "WXPAY_PUB_KEY_ID", "WXPAY_PUB_KEY_PATH", "WXPAY_NOTIFY_URL",
        )
        for key in required:
            if not getattr(self, key):
                errors.append(f"{key} 未配置")
        if errors:
            return errors  # 缺项时不再做语义校验，避免连环噪音

        # APIv3 密钥固定 32 位（微信商户平台生成规则）
        if len(self.WXPAY_APIV3_KEY) != 32:
            errors.append(f"WXPAY_APIV3_KEY 长度应为 32 位，实际 {len(self.WXPAY_APIV3_KEY)}")
        # 微信支付公钥 ID 固定前缀（公钥模式标识，区别于平台证书序列号）
        if not self.WXPAY_PUB_KEY_ID.startswith("PUB_KEY_ID_"):
            errors.append("WXPAY_PUB_KEY_ID 应以 PUB_KEY_ID_ 开头（公钥模式）")
        # 密钥文件必须存在（可解析性在网关构造时校验）
        for path_key in ("WXPAY_PRIVATE_KEY_PATH", "WXPAY_PUB_KEY_PATH"):
            path_value = getattr(self, path_key)
            if not Path(path_value).is_file():
                errors.append(f"{path_key} 文件不存在: {path_value}")

        errors.extend(self._notify_url_errors(self.WXPAY_NOTIFY_URL))
        return errors

    @classmethod
    def _notify_url_errors(cls, url: str) -> list[str]:
        """notify_url 官方硬性要求：https 全路径、不带参数、非本地/内网地址。"""
        errors: list[str] = []
        if not url.startswith("https://"):
            errors.append("WXPAY_NOTIFY_URL 必须以 https:// 开头（公网域名强制 https）")
            return errors
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.query:
            errors.append("WXPAY_NOTIFY_URL 不能携带查询参数")
        if parsed.params or parsed.fragment:
            errors.append("WXPAY_NOTIFY_URL 必须是直接可访问的完整路径")
        host = (parsed.hostname or "").lower()
        if not host:
            errors.append("WXPAY_NOTIFY_URL 缺少主机名")
        elif host == "localhost" or host.endswith(cls._WXPAY_INTERNAL_HOST_SUFFIXES):
            errors.append(f"WXPAY_NOTIFY_URL 不能指向本地/内网域名: {host}")
        else:
            import ipaddress
            try:
                ip = ipaddress.ip_address(host)
                if ip.is_loopback or ip.is_private or ip.is_reserved or ip.is_link_local:
                    errors.append(f"WXPAY_NOTIFY_URL 不能指向内网/保留 IP: {host}")
            except ValueError:
                pass  # 公网域名，合法
        return errors

    # ── 日志 ──
    LOG_DIR: str = os.getenv("LOG_DIR", str(DB_DIR / "logs"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "s-server.log")
    LOG_MAX_BYTES: int = 5 * 1024 * 1024  # 5MB
    LOG_BACKUP_COUNT: int = 5

    # ── 套餐配置（硬编码，将来可迁到 DB）──
    TIER_POLICY: dict = {
        "none":     {"device_limit": 0,  "duration_days": 0,    "display": "无套餐"},
        "trial":    {"device_limit": 1,  "duration_days": 7,    "display": "试用"},
        "free":     {"device_limit": 1,  "duration_days": 0,    "display": "免费"},
        "pro":      {"device_limit": 5,  "duration_days": 0,    "display": "PRO"},   # 归一化档（monthly/quarterly/yearly → pro；取最高设备数 5）
        "max":      {"device_limit": 10, "duration_days": 0,    "display": "MAX"},   # 规划中
        "monthly":  {"device_limit": 3,  "duration_days": 30,   "display": "月付"},
        "quarterly":{"device_limit": 3,  "duration_days": 90,   "display": "季付"},
        "yearly":   {"device_limit": 5,  "duration_days": 365,  "display": "年付"},
        "lifetime": {"device_limit": 10, "duration_days": 36500,"display": "永久"},
    }
    TIER_POLICY["lifetime"]["device_limit"] = 99

    # ── 套餐权益标准配置（c-s-entitlement-sync）──
    # 与 docs/contracts/entitlement-defaults.json 同源（两端各有对拍测试）；档位行
    # 缺 entitlement 配置/坏 JSON 时 check-auth 用此兜底。feature key 词汇表 =
    # client/frontend/src/lib/features.ts，加 key 先登记 specs。
    ENTITLEMENT_DEFAULTS: dict = {
        "none":  {"features": [], "limits": {"max_projects": 1}},
        "free":  {"features": [], "limits": {"max_projects": 1}},
        "trial": {"features": ["settings-ai-fields", "outline-advanced-fields",
                               "ai-generate", "prompt-panel", "ai-model"],
                  "limits": {"max_projects": None}},
        "pro":   {"features": ["settings-ai-fields", "outline-advanced-fields",
                               "ai-generate", "prompt-panel", "ai-model"],
                  "limits": {"max_projects": None}},
        "max":   {"features": ["settings-ai-fields", "outline-advanced-fields",
                               "ai-generate", "prompt-panel", "ai-model"],
                  "limits": {"max_projects": None}},   # planned：先给 pro 同款，上线改配置即可
    }


settings = Settings()  # 模块级单例，全局引用 from app.config import settings

# #5 生产安全：检测弱默认密钥并告警（开箱即跑保留默认值，但生产须显式设置强随机值）
if settings.JWT_SECRET == "local-license-secret" or settings.ADMIN_TOKEN == "admin123":
    logging.getLogger(__name__).warning(
        "检测到弱默认密钥（JWT_SECRET/ADMIN_TOKEN）——生产环境请通过环境变量设置强随机值"
    )
