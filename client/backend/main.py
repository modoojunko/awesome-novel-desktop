# backend/main.py
"""AI Novel — C/S 架构本地服务"""

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

import brand
import models  # noqa: F401
from api_configs.router import router as api_configs_router
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
from models.user import User
from novels.router import ai_router
from novels.router import router as novels_router
from prompt.router import router as prompt_router
from settings.ai_router import router as settings_ai_router
from settings.router import router as settings_router
from settings.status import router as settings_status_router
from story.arc_wizard import router as story_arc_wizard_router
from story.router import router as story_router
from update_check import router as update_check_router
from workflow.router import backfill_router as workflow_backfill_router
from workflow.router import router as workflow_router
from write.router import router as write_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 旧库留档（c-novel-export-roundtrip PR0）：必须先于任何 engine 连接 ──
    # schema 指纹不匹配 → 三件套改名留档（零接触）→ 全新空库启动。
    # 单轨升级：兼容责任在资产包 format_version，库层零迁移零召回。
    import logging as _logging
    from pathlib import Path

    import legacy_archive
    from config import DATABASE_URL

    _schema_fp = legacy_archive.compute_schema_fingerprint(Base.metadata)
    _db_path = Path(DATABASE_URL.split("///")[-1])
    _legacy_info = legacy_archive.archive_if_legacy(_db_path, _schema_fp)
    if _legacy_info["archived"]:
        _logging.getLogger("uvicorn.error").info(
            "Legacy library archived: %s (%s)",
            _legacy_info["archived_path"],
            _legacy_info["reason"],
        )

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except SQLAlchemyError as e:
        import logging

        logging.getLogger("uvicorn.error").warning("Failed to create tables: %s", e)

    # ── 给（新的）当前库打 schema 指纹戳：重启/重装同版本幂等 ───────────
    from models.app_meta import AppMeta

    try:
        async with async_session() as session:
            existing = await session.get(AppMeta, legacy_archive.SCHEMA_ID_KEY)
            if existing is None:
                session.add(
                    AppMeta(key=legacy_archive.SCHEMA_ID_KEY, value=_schema_fp)
                )
                await session.commit()
    except SQLAlchemyError:
        pass

    # ── Migrate: add source column to projects ───────────────────────
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE novels ADD COLUMN source TEXT DEFAULT 'ai'")
            )
    except Exception:
        pass  # 列已存在

    # ── Migrate: add backfill_status column ──────────────────────────
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE novels ADD COLUMN backfill_status TEXT DEFAULT 'none'")
            )
    except Exception:
        pass  # 列已存在

    # ── Migrate: drop legacy projects.index_status ────────────────────
    # 模型已删列（PR⑤），但存量库该列 NOT NULL 无默认值——不删的话
    # INSERT projects 不写此列必违反约束（建项目 500）。列不存在 /
    # sqlite < 3.35 无 DROP COLUMN 时报错，按幂等吞掉。
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE novels DROP COLUMN index_status")
            )
    except Exception:
        pass

    # ── 卷族入库：volumes 扩列（新库走 create_all；存量表幂等补列）─────
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE volumes ADD COLUMN direction_method VARCHAR(50)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE volumes ADD COLUMN template_name VARCHAR(50)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE volumes ADD COLUMN core_conflict VARCHAR(150)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE volumes ADD COLUMN emotional_arc VARCHAR(150)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE volumes ADD COLUMN arc_mode VARCHAR(50)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE volumes ADD COLUMN primary_drive VARCHAR(50)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE volumes ADD COLUMN info_gap_start VARCHAR(300)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE volumes ADD COLUMN info_gap_end VARCHAR(300)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE volumes ADD COLUMN chapter_target INTEGER")
            )
    except Exception:
        pass  # 列已存在

    # ── 章族入库：chapters 扩列（新库走 create_all；存量表幂等补列）─────
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN summary VARCHAR(300)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN location VARCHAR(200)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN story_time VARCHAR(150)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN narrative_pov VARCHAR(50)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN current_task VARCHAR(300)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN word_target INTEGER")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN primary_mood VARCHAR(50)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN mood_progression VARCHAR(300)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN intensity_peak VARCHAR(300)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN intensity_level INTEGER")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN emotional_hook VARCHAR(150)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN expectation_state VARCHAR(150)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN expectation_strategy VARCHAR(50)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN expectation_detail VARCHAR(300)")
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE chapters ADD COLUMN perspective_guidance VARCHAR(300)")
            )
    except Exception:
        pass  # 列已存在

    # ── 提示词格子：chapters/scene_cards 扩列（存在性守卫，幂等补列）──
    # DDL 标识符无法走绑定参数；列名/类型取自静态元组，不掺运行期输入。
    _ADD_COLUMNS: tuple[tuple[str, str, str], ...] = (
        ("chapters", "ladder_exit", "VARCHAR(300)"),
        ("chapter_scene_cards", "weight", "VARCHAR(10)"),
        ("chapter_scene_cards", "focus", "VARCHAR(50)"),
    )
    async with engine.begin() as conn:

        def _add_missing(sync_conn):
            from sqlalchemy import inspect

            insp = inspect(sync_conn)
            for tbl, col, col_type in _ADD_COLUMNS:
                if tbl in insp.get_table_names() and col not in (
                    c["name"] for c in insp.get_columns(tbl)
                ):
                    sync_conn.execute(
                        # nosec B608：静态元组拼接，无用户输入
                        text(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type}")
                    )

        await conn.run_sync(_add_missing)

    # ── Migrate: api_configs.api_format（接口格式显式化，幂等）────────
    # 新库走 create_all 已带列；存量表幂等补列 + 回填。回填条件与旧版运行时
    # URL 嗅探严格等价（URL 含 anthropic 或 vendor=anthropic → anthropic），
    # 升级零行为变化；UPDATE 每次启动执行，无匹配行即 no-op。
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "ALTER TABLE api_configs ADD COLUMN api_format "
                    "VARCHAR(20) NOT NULL DEFAULT 'openai'"
                )
            )
    except Exception:
        pass  # 列已存在
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE api_configs SET api_format='anthropic' "
                    "WHERE (base_url LIKE '%anthropic%' OR vendor='anthropic') "
                    "AND api_format <> 'anthropic'"
                )
            )
    except Exception:
        pass

    # ── Seed preset genres ──────────────────────────────────────────
    try:
        from genres.service import ensure_seed_genres

        await ensure_seed_genres()
    except Exception as e:
        import logging

        logging.getLogger("uvicorn.error").warning("Genre seed failed: %s", e)

    # ── Seed genre vocab（题材候选源，D19 关系化） ───────────────────
    try:
        from genres.novel_genre_service import ensure_seed_genre_vocab

        await ensure_seed_genre_vocab()
    except Exception as e:
        import logging

        logging.getLogger("uvicorn.error").warning("Genre vocab seed failed: %s", e)

    # ── Migrate: create events table ─────────────────────────────────
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS events "
                    "(id TEXT PRIMARY KEY, user_id TEXT, event_type TEXT, "
                    "payload TEXT, created_at TEXT)"
                )
            )
    except Exception:
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


app = FastAPI(title=f"{brand.BRAND_NAME} (Local)", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# License 验证路由
app.include_router(auth_local_router, prefix="/api/auth", tags=["auth"])
app.include_router(backup_router)

# 版本自报与更新检测（client-update-notify）
app.include_router(update_check_router)

# 业务路由
app.include_router(ai_router)
app.include_router(novels_router)
app.include_router(settings_status_router)  # 先注册：GET /settings/status 不能被 /{type} 抢先匹配
app.include_router(settings_router)
app.include_router(settings_ai_router)
app.include_router(chapters_router)
app.include_router(chapters_ai_draft_router)
app.include_router(prompt_router)
app.include_router(write_router)
app.include_router(archive_router)
app.include_router(archives_router)
app.include_router(chapters_versions_router)
app.include_router(story_router)
app.include_router(story_arc_wizard_router)
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
