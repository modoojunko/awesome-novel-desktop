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
    # `or 默认值`：环境变量"存在但为空串"（如部署配置里 secret 缺失被注入空值）
    # 必须等同未设置——否则空密钥可伪造任意 token（2026-09-18 审计实测）。
    JWT_SECRET: str = os.getenv("JWT_SECRET", "") or "local-license-secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 30

    # ── Admin ──
    ADMIN_TOKEN: str = os.getenv("ADMIN_TOKEN", "") or "admin123"

    # ── 支付运维（设计 G7/B3/演练 A9）──
    # 支付网关选择：wxpay（生产）| mock（模拟，需 PAYMENTS_ALLOW_MOCK=1）| 空=未显式配置。
    # 生效值见 effective_gateway：本地（sqlite）缺省回落 mock 保持零配置可用；
    # 生产（pg_http）未显式配置即拒绝启动（main 启动门禁）——绝不允许静默以 mock 收真实付款。
    PAYMENTS_GATEWAY: str = os.getenv("PAYMENTS_GATEWAY", "") or ""
    # mock 显式开关：与 PAYMENTS_GATEWAY=mock 同时提供才允许（防误配把演练替身当生产网关）
    PAYMENTS_ALLOW_MOCK: str = os.getenv("PAYMENTS_ALLOW_MOCK", "") or ""
    # API 文档端点（/docs、/redoc、/openapi.json）：默认关闭，本地调试显式 ENABLE_API_DOCS=1
    ENABLE_API_DOCS: str = os.getenv("ENABLE_API_DOCS", "") or ""
    # 微信回调来源白名单（可选，逗号分隔 IP/CIDR；默认关=不启用）。解析失败=拒启（fail-fast）
    WXPAY_NOTIFY_ALLOWLIST: str = os.getenv("WXPAY_NOTIFY_ALLOWLIST", "") or ""
    # Server酱 SendKey：资金类告警通道；空 = 降级为仅日志（本地/CI 默认）
    SERVERCHAN_SENDKEY: str = os.getenv("SERVERCHAN_SENDKEY", "")
    # 定时扫描端点（R1-R4）令牌：pay-cron 云函数以 X-Cron-Token 头携带；空 = 端点全拒
    CRON_TOKEN: str = os.getenv("CRON_TOKEN", "")

    # s-auth-outdated-signal：authorize 分档拒绝携带的客户端版本提示（env 注入；
    # latest_version 未配置时省略字段——C端 端上有 update-check 三级回落兜底）
    CLIENT_MIN_VERSION: str = os.getenv("CLIENT_MIN_VERSION", "")
    CLIENT_DOWNLOAD_URL: str = os.getenv(
        "CLIENT_DOWNLOAD_URL", "https://github.com/modoojunko/ai-novel/releases")
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
    # 微信支付密钥 PEM 内容直注入（GitHub 代码库拉取部署形态：构建包里没有密钥
    # 文件，密钥必须走环境变量）。设置时优先于文件路径；与 CI 的
    # WXPAY_PRIVATE_KEY_PEM/WXPAY_PUB_KEY_PEM secrets 同名同值。
    WXPAY_PRIVATE_KEY_PEM: str = os.getenv("WXPAY_PRIVATE_KEY_PEM", "") or ""
    WXPAY_PUB_KEY_PEM: str = os.getenv("WXPAY_PUB_KEY_PEM", "") or ""

    # 微信回调地址硬性校验（官方要求：https 全路径、无查询参数、外网可达）
    _WXPAY_INTERNAL_HOST_SUFFIXES = (".local", ".internal", ".lan")

    def wxpay_config_errors(self) -> list[str]:
        """校验 WXPAY_* 配置齐备性与语义合法性，返回问题清单（空=可启动）。

        main.py 注入 wxpay 网关前调用；非空即 RuntimeError 列出全部问题，
        绝不允许缺配置静默回落 Mock 收真实付款。
        """
        errors: list[str] = []
        key_pem = self.WXPAY_PRIVATE_KEY_PEM.strip()
        pub_pem = self.WXPAY_PUB_KEY_PEM.strip()
        required = [
            "WXPAY_MCH_ID", "WXPAY_APPID", "WXPAY_CERT_SERIAL",
            "WXPAY_APIV3_KEY", "WXPAY_PUB_KEY_ID", "WXPAY_NOTIFY_URL",
        ]
        if not key_pem:
            required.append("WXPAY_PRIVATE_KEY_PATH")  # PEM 内容模式可缺省文件
        if not pub_pem:
            required.append("WXPAY_PUB_KEY_PATH")
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
        # 文件路径模式：密钥文件必须存在（PEM 内容模式跳过；可解析性在网关构造时校验）
        if not key_pem:
            path_value = self.WXPAY_PRIVATE_KEY_PATH
            if not Path(path_value).is_file():
                errors.append(f"WXPAY_PRIVATE_KEY_PATH 文件不存在: {path_value}")
        if not pub_pem:
            path_value = self.WXPAY_PUB_KEY_PATH
            if not Path(path_value).is_file():
                errors.append(f"WXPAY_PUB_KEY_PATH 文件不存在: {path_value}")

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

    # ── 启动门禁（s-security-baseline R1-R2）──

    @property
    def effective_gateway(self) -> str:
        """生效网关：显式配置优先；未配置时本地（sqlite）回落 mock、生产（pg_http）留空。

        生产的留空由 startup_config_errors 转为拒绝启动（fail-closed）。
        """
        if self.PAYMENTS_GATEWAY:
            return self.PAYMENTS_GATEWAY
        return "" if self.DB_BACKEND == "pg_http" else "mock"

    def startup_config_errors(self) -> list[str]:
        """生产（pg_http）启动门禁：任一项不合格即拒绝启动并列明（不回显值）。

        本地 sqlite 形态零强制（仅弱默认告警，见模块尾）——docker 本地栈/CI/pytest
        全走 sqlite，一律强制会把它们全部打死（设计 D4 分级）。
        """
        errors: list[str] = []
        allowlist = self.WXPAY_NOTIFY_ALLOWLIST.strip()
        if allowlist:
            import ipaddress

            for part in allowlist.split(","):
                try:
                    ipaddress.ip_network(part.strip(), strict=False)
                except ValueError:
                    errors.append(f"WXPAY_NOTIFY_ALLOWLIST 含非法网段：{part.strip()}（格式应为 IP 或 CIDR）")
        if self.DB_BACKEND != "pg_http":
            return errors
        if self.JWT_SECRET in ("", "local-license-secret") or len(self.JWT_SECRET) < 32:
            errors.append("JWT_SECRET 须为 ≥32 字符的强随机值（当前为空/出厂默认/过短）")
        if self.ADMIN_TOKEN in ("", "admin123") or len(self.ADMIN_TOKEN) < 16:
            errors.append("ADMIN_TOKEN 须为 ≥16 字符的强随机值（当前为空/出厂默认/过短）")
        gateway = self.PAYMENTS_GATEWAY
        if not gateway:
            errors.append("PAYMENTS_GATEWAY 未显式配置（生产必须显式选择 wxpay/mock，"
                          "禁止静默回落 mock）")
        elif gateway == "mock":
            if self.PAYMENTS_ALLOW_MOCK != "1":
                errors.append("PAYMENTS_GATEWAY=mock 需同时设置 PAYMENTS_ALLOW_MOCK=1")
        elif gateway != "wxpay":
            errors.append(f"不支持的 PAYMENTS_GATEWAY={gateway}（可选 wxpay/mock）")
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
