# backend/main.py
"""AI Novel — C/S 架构本地服务"""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, SQLAlchemyError

import brand
import models  # noqa: F401
from api_configs.router import router as api_configs_router
from archive.reconcile_router import router as reconcile_router
from archive.router import archives_router
from archive.router import router as archive_router

# License 本地验证
from auth_local.router import router as auth_local_router
from backup.router import router as backup_router
from chapters.ai_draft import router as chapters_ai_draft_router
from chapters.router import router as chapters_router
from chapters.versions import router as chapters_versions_router
from db import Base, async_session, engine
from genres.router import router as genres_router
from manuscript.router import router as manuscript_router
from models.user import User
from novels.router import ai_router
from novels.router import router as novels_router
from prompt.router import router as prompt_router
from settings.ai_router import router as settings_ai_router
from settings.characters_ai import router as characters_ai_router
from settings.characters_router import router as characters_router
from settings.hooks_router import router as hooks_router
from settings.router import router as settings_router
from settings.status import router as settings_status_router
from settings.style_quant_router import router as style_quant_router
from story.router import router as story_router
from update_check import router as update_check_router
from volumes.ai_plan import router as volume_ai_plan_router
from workflow.router import backfill_router as workflow_backfill_router
from workflow.router import router as workflow_router
from write.ai_check import router as ai_check_router
from write.plot_sim import router as plot_sim_router
from write.prompt_sources import router as prompt_sources_router
from write.router import router as write_router
from write.style_shadow import router as style_shadow_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 库文件代数治理（db-generation）：先于任何 engine 连接 ──────────────
    # 首启状态机：novel-v{V}.db 存在→指纹校验梯（current/additive 补列/tolerant
    # 超集放行+审计/breaking·不可读→.corrupt 隔离）；不存在→空库（create_all
    # 兜底）＋迁入候选由 migration 端点扫描。「升级即整库留档重置」机制退役。
    import logging as _logging
    from pathlib import Path

    from config import DATABASE_URL
    from db_lifecycle import (
        DRIFT_ACCEPTED_KEY,
        boot_lifecycle,
        compute_schema_fingerprint,
    )
    from db_lifecycle import (
        SCHEMA_ID_KEY as _SCHEMA_ID_KEY,
    )

    _schema_fp = compute_schema_fingerprint(Base.metadata)
    _db_path = Path(DATABASE_URL.split("///")[-1])
    _boot = boot_lifecycle(_db_path, Base.metadata, _schema_fp)
    _boot_kind = _boot["boot"]
    _logging.getLogger("uvicorn.error").info(
        "db_lifecycle boot=%s db=%s", _boot_kind, _db_path.name
    )
    if _boot_kind == "tolerant_booted":
        _tolerant_extra = _boot.get("extra_cols") or {}

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except SQLAlchemyError as e:
        import logging

        logging.getLogger("uvicorn.error").warning("Failed to create tables: %s", e)

    # ── 代内 additive 补列：在打指纹戳之前补齐（补列失败不得刷戳）──────
    from db_lifecycle import apply_additive_columns

    await apply_additive_columns(engine)

    # ── 代内 additive 补列：在打指纹戳之前补齐（补列失败不得刷戳）──────
    from db_lifecycle import apply_additive_columns

    await apply_additive_columns(engine)

    # ── 给（新的）当前库打 schema 指纹戳 ───────────────────────────────
    # additive 补列完成→刷新戳；tolerant 放行不改戳（回升 newer build 即 current）
    # 并写 drift_accepted 审计键（诊断面可见——无声放行=慢性事故）。
    from models.app_meta import AppMeta

    try:
        async with async_session() as session:
            existing = await session.get(AppMeta, _SCHEMA_ID_KEY)
            if existing is None:
                session.add(AppMeta(key=_SCHEMA_ID_KEY, value=_schema_fp))
                await session.commit()
            elif _boot_kind == "tolerant_booted":
                audit = await session.get(AppMeta, DRIFT_ACCEPTED_KEY)
                if audit is None:
                    session.add(AppMeta(key=DRIFT_ACCEPTED_KEY, value="tolerant"))
                    await session.commit()
                    _logging.getLogger("uvicorn.error").warning(
                        "db_lifecycle: tolerant drift accepted (extra cols preserved): %s",
                        list(_tolerant_extra.items())[:5],
                    )
            elif existing.value != _schema_fp:
                existing.value = _schema_fp
                await session.commit()
    except SQLAlchemyError:
        pass


    # ── Migrate config.json → User table ────────────────────────────
    # 身份识别统一用 S端 用户标识：users.username 是 S端 主键，C端 User.id /
    # projects.user_id 等均取该标识（即 user_id = S端 用户名），不引入第二套
    # UUID 用户标识。root_path 按 slug 组织、与 user_id 无关，故无身份迁移需求。
    try:
        cfg_path = os.path.join(os.environ.get("DATA_ROOT", "./data"), "config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if cfg:
                async with async_session() as session:
                    result = await session.execute(select(User).limit(1))
                    user = result.scalar_one_or_none()
                    if user:
                        changed = False
                        for field in [
                            "api_key",
                            "api_base_url",
                            "api_model",
                            "token",
                            "pc_hash",
                            "pc_name",
                            "server_api",
                        ]:
                            if cfg.get(field):
                                setattr(user, field, cfg[field])
                                changed = True
                        # Map legacy license fields
                        if cfg.get("tier") and not user.plan:
                            user.plan = cfg["tier"]
                            changed = True
                        if cfg.get("expires_at") and not user.subscription_expires_at:
                            try:
                                from datetime import date

                                user.subscription_expires_at = date.fromisoformat(
                                    cfg["expires_at"][:10]
                                )
                                changed = True
                            except ValueError:
                                pass
                        if cfg.get("last_login_at") and not user.activated_at:
                            try:
                                user.activated_at = datetime.fromisoformat(
                                    cfg["last_login_at"]
                                )
                                changed = True
                            except ValueError:
                                pass
                        if changed:
                            await session.commit()
            # 不再清空 config.json —— 它是 C端 OAuth 会话的落盘处
            # （token / username / pc_hash），清空会导致每次启动都要重新登录。
    except Exception as e:
        import logging

        logging.getLogger("uvicorn.error").warning("Config migration failed: %s", e)

    # ── Migrate User old fields → ApiConfig ──────────────────────────
    try:
        from api_configs.service import migrate_user_configs

        async with async_session() as session:
            await migrate_user_configs(session)
    except Exception as e:
        import logging

        logging.getLogger("uvicorn.error").warning("ApiConfig migration failed: %s", e)

    yield


# ── 代内 additive 补列（声明式登记；幂等 checkfirst）──────────
# 新表/新列一律在此登记（新库 create_all 全量建出；旧库由 lifespan 补列）；
# 删/改列一律 SCHEMA_VERSION+1 走迁入。列名单一来源，DDL 由它派生。
ADDITIVE_VOLUME_COLS = ("plan_line",)
ADDITIVE_COLUMNS: dict[str, list[str]] = {
    "volumes": [f"ALTER TABLE volumes ADD COLUMN {c} VARCHAR(150)" for c in ADDITIVE_VOLUME_COLS]
}

app = FastAPI(title=f"{brand.BRAND_NAME} (Local)", version="0.2.0", lifespan=lifespan)


@app.exception_handler(OperationalError)
async def _storage_busy_handler(request, exc):
    """本地库瞬时 I/O 错误 → 503 可重试（不裸 500）。

    桌面端数据目录在宿主/容器共享挂载上时，外部程序触碰该目录可能让 SQLite
    短暂报 `disk I/O error`；这是瞬时态，给前端可重试的明确信号与文案。
    """
    if "disk I/O error" not in str(exc) and "database is locked" not in str(exc):
        raise exc
    logging.getLogger("uvicorn.error").warning(
        "event=storage_busy err=%s", str(exc)[:200]
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "reason": "storage_busy",
                "message": "本地数据文件暂时不可读（可能被外部程序占用），请重试",
            }
        },
    )


# ── loginless-data-exit 三层防护之二：CORS 收窄 ──────────────────────────────
# 生产=同源（SPA 由本进程 StaticFiles 伺服，通配符是纯遗留）；开发=vite 白名单。
# 收窄后「JSON POST 必触发预检 + 预检不批 + 响应不可读」封死浏览器 drive-by
# 对免登端点（免登导出/迁入）的读写两端。
import os as _os

_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
_allow_origins = _DEV_ORIGINS if _os.getenv("DEV_CORS", "") else []

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 之三：回环来源中间件——免登端点只许本机调用（Docker 0.0.0.0 部署的硬边界）
from fastapi import Request as _Request

_LOGINLESS_PATHS = (
    "/api/backup/export/start",
    "/api/backup/export/status",
    "/api/backup/legacy-db/status",
    "/api/backup/db-migration",  # c-db-generation-migration 免登面前缀
    "/api/update-check",
)


@app.middleware("http")
async def _loginless_loopback_guard(request: _Request, call_next):
    if request.url.path in _LOGINLESS_PATHS or request.url.path.startswith(
        "/api/backup/db-migration"
    ):
        host = request.client.host if request.client else ""
        # 回环＋Docker 端口映射网关（172.x/192.168.x——宿主→容器的正常路径；
        # 外部机器不可能经此网段到达本容器）＋测试客户端
        import ipaddress as _ip

        def _is_local(h: str) -> bool:
            if h in ("127.0.0.1", "::1", "testclient"):
                return True
            try:
                addr = _ip.ip_address(h)
                return addr.is_private or addr.is_loopback
            except ValueError:
                return False

        if not _is_local(host):
            return JSONResponse(status_code=403, content={"detail": "仅限本机访问"})
    return await call_next(request)

# 迁入端点（db-generation）：免登（回环中间件已覆盖本前缀）
from migration.router import router as migration_router

app.include_router(migration_router)

# License 验证路由
app.include_router(auth_local_router, prefix="/api/auth", tags=["auth"])
app.include_router(backup_router)
app.include_router(manuscript_router)

# 版本自报与更新检测（client-update-notify）
app.include_router(update_check_router)

# 业务路由
app.include_router(ai_router)
app.include_router(novels_router)
app.include_router(settings_status_router)  # 先注册：GET /settings/status 不能被 /{type} 抢先匹配
app.include_router(characters_router)  # 角色端点同理：不能被 GET /settings/{type} 兜底吃掉
app.include_router(hooks_router)  # 伏笔端点同理：不能被 GET /settings/{type} 兜底吃掉
app.include_router(style_quant_router)  # style-quant 同理：专用端点不能被 /{type} 兜底吃掉
app.include_router(characters_ai_router)
app.include_router(settings_router)
app.include_router(settings_ai_router)
app.include_router(chapters_router)
app.include_router(chapters_ai_draft_router)
app.include_router(volume_ai_plan_router)  # 卷域 AI：3 套方案/展开/体检（volume-plan-ai）
app.include_router(prompt_router)
app.include_router(write_router)
app.include_router(ai_check_router)
app.include_router(archive_router)
app.include_router(archives_router)
app.include_router(style_shadow_router)
app.include_router(plot_sim_router)
app.include_router(prompt_sources_router)
app.include_router(reconcile_router)
app.include_router(chapters_versions_router)
app.include_router(story_router)
app.include_router(workflow_router)
app.include_router(workflow_backfill_router)

# API Key Config management (v1)
app.include_router(api_configs_router)

# 全局题材库
app.include_router(genres_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "mode": "local"}


# 挂载前端静态文件 — 放在最后避免拦截 API 路由
# 开发态: client/backend/../frontend/dist
# 打包态: 通过 FRONTEND_DIST 环境变量指定（由 pywebview_app.py 设置）
frontend_dist = os.environ.get("FRONTEND_DIST") or os.path.join(
    os.path.dirname(__file__), "..", "frontend", "dist"
)
if frontend_dist and os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
