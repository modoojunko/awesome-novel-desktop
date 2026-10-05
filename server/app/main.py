"""FastAPI 应用入口。"""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import uvicorn
from fastapi import FastAPI

from app.config import settings
from app.infrastructure.logging import setup_logging
from app.interfaces.errors import register_handlers
from app.interfaces.middleware import register_middleware
from app.models.base import Base, engine
from app.infrastructure.repositories.payments_repo import TierRepo


def _collect_api_paths(routes) -> frozenset[str]:
    """递归收集 /api 前缀的路由路径（新版 FastAPI 把 include_router 包成
    _IncludedRouter 懒解析节点：自身无 .path/.routes，真实路由在其
    .original_router.routes 下）。"""
    out: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if path:
            if path.startswith("/api"):
                out.add(path)
            continue
        inner = getattr(route, "routes", None)
        if inner is None:
            inner = getattr(getattr(route, "original_router", None), "routes", None)
        if inner is not None:
            out |= _collect_api_paths(inner)
    return frozenset(out)


def init_payment_gateway(app) -> None:
    """初始化支付网关：mock=Change 1 全链替身；wxpay=真实微信支付（Change 2）；
    其他值 fail-fast 拒绝启动——绝不允许静默用 Mock 收真实付款。

    该开关同时控制 dev 注入端点的注册（见 dev_inject._MOCK_MODE）。
    独立成函数便于启动分支单测。
    """
    import logging

    from app.infrastructure.payments.gateway import MockPaymentGateway

    logger = logging.getLogger("app")
    gateway = settings.effective_gateway
    if gateway == "mock":
        app.state.payment_gateway = MockPaymentGateway()
        logger.info("event=payments.gateway type=mock")
    elif gateway == "wxpay":
        # 配置缺项/非法即拒绝启动并列出全部问题；私钥可解析性在网关构造时校验
        errors = settings.wxpay_config_errors()
        if errors:
            raise RuntimeError(
                "PAYMENTS_GATEWAY=wxpay 配置不齐或非法，拒绝启动：" + "；".join(errors)
            )
        from app.infrastructure.payments.wechatpay import WechatPayGateway
        app.state.payment_gateway = WechatPayGateway.from_settings()
        logger.info("event=payments.gateway type=wxpay mch_id=%s notify_url=%s",
                    settings.WXPAY_MCH_ID, settings.WXPAY_NOTIFY_URL)
    else:
        raise RuntimeError(
            f"PAYMENTS_GATEWAY={gateway or '<未配置>'} 不支持"
            "（可选 mock/wxpay）；拒绝以 Mock 处理真实付款"
        )


def create_app() -> FastAPI:
    """应用工厂。"""
    setup_logging()
    # API 文档端点默认关闭（s-security-baseline R3）：生产曾公开 /docs + /openapi.json
    # 全路由清单（含 admin/dev 注入端点）；本地调试显式 ENABLE_API_DOCS=1 打开。
    docs_on = settings.ENABLE_API_DOCS.strip() in ("1", "true", "yes", "on")
    app = FastAPI(
        title="AI Novel - S Server",
        version="2.0.0",
        description="License 授权与设备管理服务（重构版）",
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        openapi_url="/openapi.json" if docs_on else None,
    )

    register_handlers(app)

    from app.interfaces.admin_api import admin_router
    from app.interfaces.client_api import client_router
    from app.interfaces.web_api import web_router

    app.include_router(client_router)
    app.include_router(web_router)
    app.include_router(admin_router)

    # 路由表先收齐再注册中间件（归一化层精确匹配这张表）；
    # 限流的敏感路径判定内置两形态归一（剥 /api 前缀形态与带前缀同桶，见
    # middleware._sensitive_path）——不依赖中间件嵌套顺序，绕行面已闭合
    #（2026-09-18 审计：/web/login 曾完全绕过限流）。
    register_middleware(app, api_paths=_collect_api_paths(app.routes))

    return app


app = create_app()


@app.on_event("startup")
def on_startup():
    """启动时自动建表 + 检查 Alembic 迁移版本（仅 sqlite 后端；pg_http 表已预建）。"""
    import hashlib
    import logging
    logger = logging.getLogger("app")
    logger.info("event=app.start db_backend=%s db_path=%s", settings.DB_BACKEND, settings.DB_PATH)

    # tier-catalog：rank 单源注入 tiers.rank 列（TierRepo 类级 60s TTL 缓存）；
    # 读库失败/不可用 → pricing 退 _TIER_RANK 常量并告警（tier_policy 兜底口径）。
    from app.domain.payments import pricing as _tier_pricing

    def _tier_rank_lookup():
        if settings.DB_BACKEND == "pg_http":
            from app.infrastructure.repositories.pg_http import get_pg_client
            db = get_pg_client()
        else:
            from app.models.base import SessionLocal
            db = SessionLocal()
        try:
            rows = TierRepo(db).find_all_cached()
            return {r["key"]: int(r["rank"]) for r in rows if r.get("key")}
        finally:
            close = getattr(db, "close", None)
            if callable(close):
                close()

    _tier_pricing.configure_rank_lookup(_tier_rank_lookup)

    # 生产启动门禁（s-security-baseline R1-R2）：密钥/网关不合格即拒绝启动（fail-closed），
    # 列明不合格项但绝不回显密钥本体；本地 sqlite 形态零强制（仅弱默认告警）。
    config_errors = settings.startup_config_errors()
    if config_errors:
        raise RuntimeError("生产配置门禁未通过，拒绝启动（修复后重启）：" + "；".join(config_errors))

    # env 指纹探针（key 轮换/传输排查用）：只记哈希与长度，绝不落 key 本体。
    # 与 GitHub secret 指纹、生成配置指纹、CloudBase 存储指纹四点对拍，
    # 任一环不一致即定位字符被转译/替换的环节。
    _k = settings.TCB_PG_API_KEY
    # 凭据卫生（R6）：只记长度与哈希，不含任何明文片段（曾含 tail4，已移除）
    logger.info(
        "event=env_fingerprint name=TCB_PG_API_KEY len=%d sha256=%s",
        len(_k), hashlib.sha256(_k.encode()).hexdigest(),
    )

    # 初始化支付网关（mock/wxpay/未知 fail-fast 三分支，见 init_payment_gateway）
    init_payment_gateway(app)

    # 告警通道单例（Server酱；未配置 key 时降级为日志）
    from app.infrastructure.notify import NotifyService
    app.state.notify_service = NotifyService(send_key=settings.SERVERCHAN_SENDKEY)

    if settings.DB_BACKEND == "pg_http":
        # CloudBase PG 表结构由管理端 MCP applyMigration 预建，应用启动不迁移；
        # 但"代码上线、DDL 漏执行"的漂移无法靠迁移链兜底——启动时探测一次必需
        # 表/列，缺失打告警日志（不阻断启动，spec：缺失告警/探测失败不阻断）。
        from app.infrastructure.pg_schema import run_schema_check
        from app.infrastructure.repositories.pg_http import get_pg_client
        try:
            run_schema_check(get_pg_client())
        except Exception as exc:  # 自检自身异常不得影响启动
            logger.warning("event=app.schema_check result=probe_failed error=%s", exc)
        logger.info("event=app.started version=%s db_backend=pg_http", "2.1.0")
        return

    # 先跑 alembic 迁移（空库上正常建表并打标 alembic_version），
    # 再 create_all 兜底（checkfirst 默认跳过已存在表）——避免 fresh DB 上
    # create_all 先建表导致 alembic 迁移的 create_table 冲突。
    # c-s-db-migrate-pipeline：迁移失败 fail-closed——坏迁移带伤启动会把缺列/缺表
    # 拖到请求期才炸（no such column），且 create_all 不 ALTER 已存在表，漂移被静默固化。
    alembic_dir = Path(__file__).parent.parent / "alembic"
    if alembic_dir.exists():
        from alembic.config import Config

        from alembic import command
        server_dir = Path(__file__).parent.parent
        # 不加载 alembic.ini（config_file_name=None）：env.py 里 fileConfig(ini)
        # 默认 disable_existing_loggers=True，会把 app/api/uvicorn 的 logger 全部禁用，
        # 而 dictConfig(disable_existing_loggers=False) 无法复活未显式配置的子 logger
        # （如 api.access），导致访问日志全程失声。script_location 显式传入即可。
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", str(server_dir / "alembic"))
        try:
            command.upgrade(alembic_cfg, "head")
        except Exception as e:
            setup_logging()
            fail_logger = logging.getLogger("app")
            fail_logger.error(
                "event=app.migration action=alembic_upgrade result=fail error=%s "
                "hint=先查 server/alembic/versions 是否多头（alembic heads 应恰一个）；修复迁移后重启",
                e,
            )
            raise SystemExit(1) from e
        setup_logging()
        logger = logging.getLogger("app")
        logger.info("event=app.migration action=alembic_upgrade result=ok")

    logger.info("event=app.migration action=create_all")
    Base.metadata.create_all(bind=engine)

    logger.info("event=app.started version=%s db_path=%s", "2.1.0", settings.DB_PATH)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=False)
