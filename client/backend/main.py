# backend/main.py
"""Awesome Novel — C/S 架构本地服务"""

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
from archive.dossier_router import book_router as dossier_book_router
from archive.dossier_router import router as dossier_router
from archive.reconcile_router import router as reconcile_router
from archive.router import archives_router
from archive.router import router as archive_router

# License 本地验证
from auth_local.router import router as auth_local_router
from backup.router import router as backup_router
from chapters.ai_cast import router as chapter_cast_router
from chapters.ai_draft import router as chapters_ai_draft_router
from chapters.ai_plan import router as chapter_ai_plan_router
from chapters.ai_plot import router as chapter_plot_router
from chapters.router import router as chapters_router
from chapters.versions import router as chapters_versions_router
from db import Base, async_session, engine
from genres.router import router as genres_router
from manuscript.router import router as manuscript_router
from models.user import User
from novels.events_router import router as events_router
from novels.router import ai_router
from novels.router import router as novels_router
from prompt.router import book_router as prompt_book_router
from prompt.router import router as prompt_router
from prompt_pack.router import router as prompt_pack_router  # c-prompt-pack-client
from prompts import PromptPackMissing  # c-prompt-pack-client
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
from zhuque.router import check_router as zhuque_check_router
from zhuque.router import config_router as zhuque_config_router
from zhuque.router import result_router as zhuque_result_router


async def stamp_current_library(schema_fp: str) -> None:
    """把 schema 指纹与版本/组件快照写入当前库 app_meta（库自证来源）。

    c-db-version-hardening：失败 MUST 记 error 日志（含库路径与异常摘要）且 MUST NOT
    静默——下次启动该库会因 schema_id 缺失被判 mismatch 改名（书架空），日志里必须
    留得住这条前因。失败不阻断启动。"""
    from db_lifecycle import SCHEMA_ID_KEY, version_stamp_payload
    from models.app_meta import AppMeta

    try:
        async with async_session() as session:
            existing = await session.get(AppMeta, SCHEMA_ID_KEY)
            if existing is None:
                session.add(AppMeta(key=SCHEMA_ID_KEY, value=schema_fp))
            elif existing.value != schema_fp:
                existing.value = schema_fp
            for _k, _v in version_stamp_payload().items():
                _row = await session.get(AppMeta, _k)
                if _row is None:
                    session.add(AppMeta(key=_k, value=_v))
                elif _row.value != _v:
                    _row.value = _v
            await session.commit()
    except SQLAlchemyError as e:
        _logger = logging.getLogger("uvicorn.error")
        _logger.error(
            "event=app.stamp result=fail db=%s error=%s hint=库指纹/版本快照未写入，下次启动可能按 mismatch 分流",
            os.environ.get("DATA_ROOT", "./data"), e,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 库文件版本治理（c-db-per-version）：先于任何 engine 连接 ──────────
    # 首启状态机（novel-v{本机版本}.db）：不存在或空壳→空库（create_all 兜底）；
    # 指纹匹配→current；指纹不符且可读→改名 .mismatch-<stamp>（可作候选带回）；
    # 不可读→.corrupt 隔离（只读可见）。**没有**代内补列路径（不再对既有库 DDL）。
    # 旧版数据的带路由 migration 端点（候选扫描）；数据目录里的 staging 残留同批清。
    import logging as _logging
    from pathlib import Path

    from config import DATABASE_URL
    from db_lifecycle import (
        clean_stale_staging,
        compute_schema_fingerprint,
    )

    _log = _logging.getLogger("uvicorn.error")
    _schema_fp = compute_schema_fingerprint(Base.metadata)
    _db_path = Path(DATABASE_URL.split("///")[-1])
    from db_lifecycle import boot_lifecycle as _boot_lifecycle

    _boot = _boot_lifecycle(_db_path, Base.metadata, _schema_fp)
    _boot_kind = _boot["boot"]
    _log.info("db_lifecycle boot=%s db=%s", _boot_kind, _db_path.name)
    if _boot_kind in ("quarantined_new", "mismatch_renamed"):
        _log.warning("db_lifecycle relocated=%s kind=%s", _boot.get("quarantined_to")
                     or _boot.get("renamed_to"), _boot_kind)
    elif _boot_kind in ("quarantine_failed", "mismatch_rename_failed"):
        _log.error("db_lifecycle 改名失败（文件原位保留，应用继续启动）：%s", _db_path.name)
    _stale = clean_stale_staging(_db_path.parent)
    if _stale:
        _log.info("db_lifecycle: cleaned %d stale staging dir(s)", _stale)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except SQLAlchemyError as e:
        import logging

        logging.getLogger("uvicorn.error").warning("Failed to create tables: %s", e)

    # ── 章档（c-chapter-dossier）：启动 sweep 悬空提取 job ＋ 存量收尾 pending 迁移 ──
    try:
        from archive.dossier import sweep_stuck_jobs

        _swept = await sweep_stuck_jobs()
        if _swept:
            _log.info("dossier: swept %d interrupted extraction job(s)", _swept)
    except Exception as _e:  # noqa: BLE001 — sweep 失败不挡启动
        _log.warning("dossier sweep failed: %s", _e)
    # ── 写作能力包（c-prompt-pack-client）：启动补偿同步（未装/档位不符才动） ──
    try:
        from prompt_pack.sync import maybe_after_auth

        maybe_after_auth()
    except Exception as _pe:  # noqa: BLE001 — 包同步失败不挡启动
        _log.warning("prompt-pack sync failed: %s", _pe)
    try:
        from archive.reconcile import migrate_legacy_pending

        _mig = await migrate_legacy_pending()
        if _mig.get("migrated") or _mig.get("char_states_rejected"):
            _log.info("dossier: legacy reconcile migrated=%(migrated)s rejected=%(char_states_rejected)s", _mig)
    except Exception as _e:  # noqa: BLE001 — 迁移失败不挡启动（下次启动重试）
        _log.warning("dossier legacy migration failed: %s", _e)

    # ── 预置题材播种（#453 重写 lifespan 时被误删，2026-09-21 补回）──────────
    # 两个都是幂等（只插缺失、不覆盖用户改动）；缺了它们**新建库的题材目录是空的**：
    # GET /genres/candidates 返回空 → 题材面板的预置词条 PUT 会 400「未知的候选词汇」，
    # 题材这一步直接确认不了（老库因为历史已播种而看不见这个问题）。
    try:
        from genres.service import ensure_seed_genres

        await ensure_seed_genres()
    except Exception as e:  # noqa: BLE001 —— 播种失败不阻断启动
        import logging

        logging.getLogger("uvicorn.error").warning("Genre seed failed: %s", e)

    try:
        from genres.novel_genre_service import ensure_seed_genre_vocab

        await ensure_seed_genre_vocab()
    except Exception as e:  # noqa: BLE001
        import logging

        logging.getLogger("uvicorn.error").warning("Genre vocab seed failed: %s", e)

    # ── 当前库打戳：schema 指纹 ＋ 本机版本/组件快照（库自证来源） ───────────
    await stamp_current_library(_schema_fp)

    # ── API Key 加密钥匙初始化（key-crypto-selfcontained）─────────────────
    # 钥匙存 app_meta 行（库自包含：搬库/备份/恢复随行）；旧 .fernet_key 文件
    # 仅首启迁移期一次性读取（合法→原样抄库零重加密；非法→新钥匙＋warning），
    # 迁移后文件保留为只读遗留（同机新旧版本混跑/回滚安全）。必须在
    # config.json→User 与 migrate_user_configs（内含 encrypt_api_key）之前、
    # 任何 AI 加解密之前——失败即快速失败（不静默降级）。
    from api_configs.crypto import init_crypto

    async with async_session() as _crypto_session:
        await init_crypto(_crypto_session)

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


# ── 代内 additive 补列机制已退役（c-db-per-version）────────────────────────
# 每版只读写自己的库文件：列/表形状变化由「新版本新建自己的库 + 从旧库副本搬运」
# 承接，不再存在任何对既有库执行 DDL 的路径（ADDITIVE_COLUMNS 一并删除）。

app = FastAPI(title=f"{brand.BRAND_NAME} (Local)", version="0.2.0", lifespan=lifespan)


@app.exception_handler(PromptPackMissing)
async def _prompts_missing_handler(request, exc):
    """写作能力（提示词包）未就绪 → 503＋专用 reason（c-prompt-pack-client 4.1）。

    唯一收敛点：API 模板消费遍历到未装包/包损坏时由 loader 抛 PromptPackMissing，
    此处统一转 503 detail={reason: prompts_missing}；前端据此出四态卡（未登录→
    去登录／失败→重新获取／档位不够→升级卡），手写正文等非模板功能不受影响。
    """
    _path = getattr(getattr(request, "url", None), "path", "-")
    logging.getLogger("uvicorn.error").info("event=prompts_missing path=%s", _path)
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "reason": "prompts_missing",
                "message": "写作能力还没就绪 — 登录后会自动获取；也可点「重新获取」重试",
            }
        },
    )


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
app.include_router(prompt_pack_router)

# 业务路由
app.include_router(ai_router)
app.include_router(novels_router)
app.include_router(events_router)  # 度量落点（PRD §7）：前端意图事件白名单收口
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
app.include_router(chapter_ai_plan_router)  # 章域 AI：拆章 3 方向/自检/进场（c-chapter-plan-ai）
app.include_router(chapter_plot_router)  # 章域 AI：剧情 3 版抽卡（c-plot-split）
app.include_router(chapter_cast_router)  # 章域 AI：人物盘点/提案抽卡（c-character-intro）
app.include_router(prompt_router)
app.include_router(prompt_book_router)  # 书级批量：prompt-summary（提示词总览 N+1 收口）
app.include_router(write_router)
app.include_router(ai_check_router)
app.include_router(archive_router)
app.include_router(archives_router)
app.include_router(style_shadow_router)
app.include_router(plot_sim_router)
app.include_router(prompt_sources_router)
app.include_router(reconcile_router)
app.include_router(dossier_router)
app.include_router(dossier_book_router)
app.include_router(chapters_versions_router)
app.include_router(story_router)
app.include_router(workflow_router)
app.include_router(workflow_backfill_router)

# API Key Config management (v1)
app.include_router(api_configs_router)
app.include_router(zhuque_config_router)
app.include_router(zhuque_check_router)
app.include_router(zhuque_result_router)

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
