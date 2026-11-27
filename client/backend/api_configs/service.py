"""CRUD service layer for ApiConfig management."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import async_session
from models.api_config import ApiConfig
from models.audit_log import ProjectModelAuditLog
from models.project import Novel
from models.token_log import TokenLog
from models.user import User

from .connection import fetch_models as _fetch_models
from .connection import test_connection as _test_connection
from .crypto import decrypt_api_key, encrypt_api_key
from .schemas import mask_api_key
from .vendor import detect_vendor, resolve_vendor

# ── ApiConfig CRUD ─────────────────────────────────────────────────────────


def _first_model(models_json: str | None) -> str | None:
    """models JSON 列首项（探针优先模型）；坏文/非列表/空 → None。"""
    if not models_json:
        return None
    try:
        parsed = json.loads(models_json)
    except (ValueError, TypeError):
        return None
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], str):
        return parsed[0]
    return None


# models 清单上限（c-model-list-cap-300）：手动/自动两路同源。300＝护栏（防无界
# 落库＋手动 PUT 超限确定性）与全量可见的平衡点——火山方舟 /models 现返回 137 条
# 且最老在前（2026-10-24 实测），上限 100 会把在役新模型整段截掉。
MODELS_MAX = 300

# 清单保鲜（c-model-list-auto-refresh）：ensure 端点按「上次成功时间」判断要不要真出网。
# TTL 10 分钟＝用户在任何选择器里看到的最旧程度；失败退避 5 分钟防止坏端点被反复重试。
# 自动刷新超时压到 5 秒（后台保鲜不值得让一次请求挂 10 秒）。
MODEL_LIST_TTL_SECONDS = int(os.environ.get("MODEL_LIST_TTL_SECONDS", "600"))
MODEL_LIST_FAIL_BACKOFF_SECONDS = int(
    os.environ.get("MODEL_LIST_FAIL_BACKOFF_SECONDS", "300")
)
MODEL_LIST_REFRESH_TIMEOUT = int(os.environ.get("MODEL_LIST_REFRESH_TIMEOUT", "5"))
MODEL_LIST_REFRESH_CONCURRENCY = int(
    os.environ.get("MODEL_LIST_REFRESH_CONCURRENCY", "3")
)

# 进程内保鲜状态：同一配置的单飞锁＋失败退避＋「已检查但无清单」时间。
# 单用户桌面后端单进程，内存态足够；成功与否的持久事实仍以 models_updated_at 为准
# （重启后按 TTL 重新判断）。空清单不写 models_updated_at（没清单可落），但也要按
# TTL 记为「已检查」——否则不提供 /models 的端点（anthropic 兼容口等）会在每次
# 触发时都重新出网，TTL 形同虚设。
_REFRESH_LOCKS: dict[str, asyncio.Lock] = {}
_REFRESH_FAILED_AT: dict[str, float] = {}
_REFRESH_LAST_ERROR: dict[str, str] = {}
_REFRESH_EMPTY_AT: dict[str, float] = {}


def _reset_model_refresh_state() -> None:
    """清空进程内保鲜状态（测试隔离用）。"""
    _REFRESH_LOCKS.clear()
    _REFRESH_FAILED_AT.clear()
    _REFRESH_LAST_ERROR.clear()
    _REFRESH_EMPTY_AT.clear()


def _recently_checked_empty(config_id: str) -> bool:
    """空清单结果在 TTL 内视同「已检查」——不再重复出网。"""
    checked_at = _REFRESH_EMPTY_AT.get(config_id)
    return (
        checked_at is not None
        and time.monotonic() - checked_at < MODEL_LIST_TTL_SECONDS
    )


def _normalize_models(raw: list[str], *, truncate: bool = False) -> list[str]:
    """models 写入归一化：去空白/去重保序/上限 MODELS_MAX。

    超限行为分两条路（c-api-config-auto-models 拍板，c-model-list-cap-300 抬窗）：
    手动路径（create/update 请求体）超限报错——那是用户显式行为；自动路径（连接
    测试拉回的清单落库）truncate=True 截断保留前 MODELS_MAX——供应商清单长度不受
    用户控制，原样超限落库会让之后任何手动 PUT 都 422。
    """
    seen: set[str] = set()
    cleaned: list[str] = []
    for m in raw:
        name = m.strip() if isinstance(m, str) else ""
        if name and name not in seen:
            seen.add(name)
            cleaned.append(name)
    if len(cleaned) > MODELS_MAX:
        if not truncate:
            raise ValueError(f"模型数量过多（上限 {MODELS_MAX}）")
        cleaned = cleaned[:MODELS_MAX]
    return cleaned


# ── 保存前连通门禁（c-api-config-save-gate）─────────────────────────────────


class ProbeFailed(Exception):
    """保存前探测判败：携带探测原始结论。

    router 统一转 422 detail {code: "probe_failed", status, message}——message
    即探测原文案，前端经 lib/api.ts 既有 detail.message 提取路径直达表单。
    """

    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _probe_payload(outcome: dict[str, Any] | None) -> dict[str, Any] | None:
    """保存响应里嵌套 probe 的形状（与配置对象顶层 status/models 防撞名）。"""
    if outcome is None:
        return None
    return {
        "ok": bool(outcome.get("ok")),
        "status": outcome.get("status"),
        "models": outcome.get("models"),
        "error": outcome.get("error"),
    }


async def _probe_for_save(**kwargs: Any) -> dict[str, Any]:
    """保存门禁探测：与「测试连接」同一实现同一判据；非 ok 一律 ProbeFailed。

    按「非 ok 即拦」实现（endpoint_mismatch/auth_error/timeout/network_error/
    rate_limited/unknown 均拦），不按白名单枚举。
    """
    outcome = await _test_connection(**kwargs)
    if not outcome.get("ok"):
        raise ProbeFailed(
            str(outcome.get("status") or "unknown"),
            str(outcome.get("error") or "连接测试未通过，请检查地址与 Key"),
        )
    return outcome


def _persist_probe_result(
    config: ApiConfig, outcome: dict[str, Any]
) -> dict[str, Any]:
    """把探测结果写进测试结果字段（test_api_config 与保存门禁共用同一口径）。

    写 last_test_status/last_test_error/last_tested_at；探测带回模型清单时按
    _normalize_models(truncate=True) 归一/截断并保已选首项在头（评审 P1-2），
    返回的 outcome 与落库同一份清单（评审 P1-1）。不 commit——调用方负责。
    """
    config.last_test_status = outcome.get("status")
    config.last_test_error = outcome.get("error")
    config.last_tested_at = datetime.now(UTC)
    if outcome.get("models"):
        fetched = outcome["models"]
        preferred = _first_model(config.models)
        if preferred and preferred in fetched:
            fetched = [preferred] + [m for m in fetched if m != preferred]
        normalized = _normalize_models(fetched, truncate=True)
        config.models = json.dumps(normalized, ensure_ascii=False)
        config.models_updated_at = datetime.now(UTC)
        outcome = {**outcome, "models": normalized}
    return outcome


async def _assert_name_available(db: AsyncSession, user_id: str, name: str) -> None:
    """重名校验＋软删占名让位。

    活跃（status != deleted）重名照旧拒绝；名字只被软删行占着时，把不可见的
    软删行改名腾出名字再放行——DB 有 (user_id, name) 唯一约束
    （uq_api_configs_user_name），不让位的话新建/改名必然撞约束。
    撤销窗口（前端 8s toast）内行原样保留、restore 照常复活原名；窗口过期后
    用户重建同名配置是正常诉求，不该被看不见的行堵死。改名后缀嵌行 id（PK）
    保证唯一，软删行不在任何列表出现，该形态用户不可见。
    朱雀行（vendor=zhuque）例外：保留名「朱雀 AI 检测」任何状态都拒借，见循环内注释。
    """
    existing = await db.execute(
        select(ApiConfig).where(
            ApiConfig.user_id == user_id,
            ApiConfig.name == name,
            ApiConfig.status != "deleted",
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("名称已被使用")
    blocked = await db.execute(
        select(ApiConfig).where(
            ApiConfig.user_id == user_id,
            ApiConfig.name == name,
            ApiConfig.status == "deleted",
        )
    )
    for row in blocked.scalars().all():
        # 朱雀保留名不参与让位：get_zhuque_config 按 name+vendor 单槽位查行，
        # 让普通配置借走该名，朱雀行从此查不到（zhuque 契约：active/deleted 一律 409）
        if row.vendor == "zhuque":
            raise ValueError("名称已被使用")
        row.name = f"{name[:40]}（已删除 {row.id}）"
    # flush 须在此处：让位 UPDATE 与调用方随后的改名/INSERT 不能归并进同一批次——
    # SQLite 唯一约束逐行检查，同批内「B 先取名、A 后让位」会自撞约束
    await db.flush()


async def create_api_config(
    db: AsyncSession,
    user_id: str,
    name: str,
    vendor_id: str,
    base_url: str,
    api_key: str = "",
    vendor_override: str | None = None,
    api_format: str | None = None,
    models: list[str] | None = None,
    thinking_enabled: bool = False,
    thinking_effort: str = "low",
) -> dict[str, Any]:
    """Create a new ApiConfig. Returns the created config as a dict."""
    # Check name uniqueness（软删占名自动让位，见 helper）
    await _assert_name_available(db, user_id, name)

    # Resolve vendor
    resolved_vendor_id, resolved_display_name, _ = resolve_vendor(
        base_url, vendor_override
    )

    # api_format 未显式传（旧前端）时按旧版运行时推断兜底，行为等价
    resolved_format = (
        api_format
        if api_format
        else (
            "anthropic"
            if vendor_id == "anthropic" or "anthropic" in base_url.lower()
            else "openai"
        )
    )

    # c-api-config-save-gate：保存前连通门禁（创建恒测）——探测在任何写库之前，
    # 非 ok 抛 ProbeFailed（router 转 422），与「测试连接」同一判据（含思考参数）
    normalized_models = _normalize_models(models) if models else []
    outcome = await _probe_for_save(
        vendor_id=resolved_vendor_id,
        api_key=api_key,
        base_url=base_url,
        api_format=resolved_format,
        preferred_model=(normalized_models[0] if normalized_models else None),
        thinking_enabled=bool(thinking_enabled),
        thinking_effort=thinking_effort or "low",
    )

    config = ApiConfig(
        user_id=user_id,
        name=name,
        vendor=resolved_vendor_id,
        vendor_display_name=resolved_display_name,
        vendor_override=vendor_override,
        api_format=resolved_format,
        thinking_enabled=thinking_enabled,
        thinking_effort=thinking_effort or "low",
        api_key=encrypt_api_key(api_key),
        base_url=base_url,
        status="active",
    )
    # 预填的模型名称（models 首项）随创建落库（c-api-config-vendor-defaults）
    if normalized_models:
        config.models = json.dumps(normalized_models, ensure_ascii=False)
        config.models_updated_at = datetime.now(UTC)
    # 判过：探测结果按测试连接同款持久化（探测带回清单时覆盖为归一结果）
    outcome = _persist_probe_result(config, outcome)
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return {**_config_to_dict(config), "probe": _probe_payload(outcome)}


async def get_user_api_configs(db: AsyncSession, user_id: str) -> list[dict[str, Any]]:
    """List all configs for a user（软删 status=deleted 的行不返回）。"""
    result = await db.execute(
        select(ApiConfig)
        .where(
            ApiConfig.user_id == user_id,
            ApiConfig.status != "deleted",
            # c-zhuque-ai-detect：朱雀检测配置由专用端点管理，不进大模型页签列表
            ApiConfig.vendor != "zhuque",
        )
        .order_by(ApiConfig.created_at.desc())
    )
    return [_config_to_dict(c) for c in result.scalars().all()]


async def get_api_config(
    db: AsyncSession, user_id: str, config_id: str
) -> dict[str, Any] | None:
    """Get a single config by ID. Returns None if not found or not owned by user."""
    result = await db.execute(
        select(ApiConfig).where(ApiConfig.id == config_id, ApiConfig.user_id == user_id)
    )
    config = result.scalar_one_or_none()
    return _config_to_dict(config) if config else None


async def test_api_config(
    db: AsyncSession,
    user_id: str,
    config_id: str,
    preferred_model: str | None = None,
    thinking_enabled: bool | None = None,
    thinking_effort: str | None = None,
) -> dict[str, Any]:
    """Test a config's connection, save results to DB, and return outcome.

    preferred_model：探针优先模型覆盖（编辑弹窗改选模型后试连）；缺省/空按已存
    models 首项取。thinking_enabled/thinking_effort：思考参数覆盖（表单当前值），
    None 按已存配置——测试连接与生成同判据（c-thinking-config）。
    """
    result = await db.execute(
        select(ApiConfig).where(ApiConfig.id == config_id, ApiConfig.user_id == user_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        return {
            "ok": False,
            "status": "not_found",
            "models": None,
            "error": "配置不存在",
        }

    plain_key = decrypt_api_key(config.api_key)
    # 探针优先＝调用方覆盖（表单改选）> 配置已选模型（models 首项；c-api-config-vendor-defaults 预填即它）；
    # 思考参数＝调用方覆盖（表单当前值）> 已存配置（c-thinking-config）——测试连接与生成同判据
    outcome = await _test_connection(
        vendor_id=config.vendor,
        api_key=plain_key,
        base_url=config.base_url,
        api_format=getattr(config, "api_format", None) or "openai",
        preferred_model=(preferred_model or "").strip() or _first_model(config.models),
        thinking_enabled=(
            thinking_enabled
            if thinking_enabled is not None
            else (getattr(config, "thinking_enabled", False) or False)
        ),
        thinking_effort=thinking_effort or (getattr(config, "thinking_effort", None) or "low"),
    )

    # Persist results（与保存门禁共用同一写库口径，c-api-config-save-gate）
    outcome = _persist_probe_result(config, outcome)
    await db.commit()
    await db.refresh(config)

    return outcome


async def refresh_models_with_stored_key(
    db: AsyncSession,
    user_id: str,
    config_id: str,
    timeout: int | None = None,
) -> dict[str, Any] | None:
    """用已存密钥重拉模型清单（c-model-list-auto-refresh）。

    编辑态 Key 未重填时「获取模型」的出口（此前 raw 轻探针无明文 Key 只能禁用），
    也是后台保鲜（ensure）的单配置执行体：走 fetch_models 同款「只拉清单轻探针」——
    GET 清单端点，零生成调用。成功且带回**非空**清单时按「已选首项保头」归一写库
    （与 test 落库同一口径）；清单为空（端点不提供）或探针失败一律原样透传，
    SHALL NOT 覆盖已存清单。轻探针不证对话可用，SHALL NOT 改动连接测试结果字段
    （last_test_*）。timeout 仅影响本次出网（后台保鲜用更短的 5 秒）。
    """
    result = await db.execute(
        select(ApiConfig).where(ApiConfig.id == config_id, ApiConfig.user_id == user_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        return None

    outcome = await _fetch_models(
        vendor_id=config.vendor,
        api_key=decrypt_api_key(config.api_key),
        base_url=config.base_url,
        api_format=getattr(config, "api_format", None) or "openai",
        **({"timeout": timeout} if timeout else {}),
    )
    fetched = outcome.get("models")
    if outcome.get("ok") and isinstance(fetched, list) and fetched:
        preferred = _first_model(config.models)
        if preferred and preferred in fetched:
            fetched = [preferred] + [m for m in fetched if m != preferred]
        normalized = _normalize_models(fetched, truncate=True)
        # 归一后为空（全是空白/非字符串等畸形项）视同「没拿到可用清单」：不写库，
        # 免得把可用快照清成空
        if normalized:
            config.models = json.dumps(normalized, ensure_ascii=False)
            config.models_updated_at = datetime.now(UTC)
            await db.commit()
            await db.refresh(config)
            outcome = {
                **outcome,
                "models": normalized,
                "models_updated_at": config.models_updated_at.isoformat(),
            }
    return outcome


# ── 清单后台保鲜（c-model-list-auto-refresh）─────────────────────────────────


def _models_list(raw: str | None) -> list[str]:
    """models JSON 文本 → 字符串列表（坏文/非列表 → 空）。"""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [m for m in parsed if isinstance(m, str)]


def _utcnow_naive() -> datetime:
    """SQLite DateTime 列无时区：统一按 naive UTC 比较。"""
    return datetime.now(UTC).replace(tzinfo=None)


def _as_naive_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _models_are_stale(updated_at: datetime | None, now: datetime) -> bool:
    if updated_at is None:
        return True
    return (now - _as_naive_utc(updated_at)).total_seconds() >= MODEL_LIST_TTL_SECONDS


def _ensure_result(
    config_id: str,
    models: list[str],
    updated_at: datetime | None,
    *,
    refreshed: bool,
    ok: bool,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "id": config_id,
        "models": models,
        "models_updated_at": updated_at.isoformat() if updated_at else None,
        "refreshed": refreshed,
        "ok": ok,
        "error": error,
    }


async def _latest_models_state(config_id: str, user_id: str) -> tuple[list[str], datetime | None] | None:
    """锁内复核：另一调用可能刚刷完（新会话读，避免共享 session 并发）。"""
    async with async_session() as session:
        row = (
            await session.execute(
                select(ApiConfig.models, ApiConfig.models_updated_at).where(
                    ApiConfig.id == config_id, ApiConfig.user_id == user_id
                )
            )
        ).first()
        if row is None:
            return None
        return _models_list(row[0]), row[1]


async def ensure_models_fresh(
    user_id: str,
    config_ids: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """后台保鲜：让模型清单在「用户看之前」就是新的（c-model-list-auto-refresh）。

    对每个活跃写作配置判断 `models_updated_at` 是否超过 TTL（默认 10 分钟）：过期才
    用已存密钥走只拉清单轻探针（零生成，单次超时 5 秒），成功按「已选首项保头」
    写库；未过期直接回快照。失败记 5 分钟退避（force 绕过），已存清单不清空。
    同一配置单飞（并发调用只出一次网），跨配置并发上限 3。

    每个配置用独立 session（网络等待期间不占住请求 session，也避免 AsyncSession
    并发使用）；成功/失败都以 models_updated_at 与进程内退避表为准。
    """
    async with async_session() as session:
        stmt = select(ApiConfig).where(
            ApiConfig.user_id == user_id,
            ApiConfig.status != "deleted",
            ApiConfig.vendor != "zhuque",
        )
        if config_ids is not None:
            # 空集＝不刷新任何配置（区别于 None＝全部）；.in_([]) 天然返回空
            stmt = stmt.where(ApiConfig.id.in_(config_ids))
        rows = (await session.execute(stmt.order_by(ApiConfig.created_at))).scalars().all()
        snapshots = [
            {
                "id": row.id,
                "vendor": row.vendor,
                "status": row.status,
                "has_key": bool(row.api_key),
                "models": _models_list(row.models),
                "models_updated_at": row.models_updated_at,
            }
            for row in rows
        ]

    now = _utcnow_naive()
    sem = asyncio.Semaphore(MODEL_LIST_REFRESH_CONCURRENCY)

    def skipped(snap: dict[str, Any], *, ok: bool = True, error: str | None = None) -> dict[str, Any]:
        return _ensure_result(
            snap["id"], snap["models"], snap["models_updated_at"],
            refreshed=False, ok=ok, error=error,
        )

    async def one(snap: dict[str, Any]) -> dict[str, Any]:
        config_id = snap["id"]
        if snap["status"] != "active":
            return skipped(snap)  # 禁用/非活跃配置不动（与 refresh-models 400 同口径）
        if not force and not _models_are_stale(snap["models_updated_at"], now):
            return skipped(snap)
        if not force:
            # 端点不提供清单：TTL 内算「已检查」，不重复出网
            if _recently_checked_empty(config_id):
                return skipped(snap)
            failed_at = _REFRESH_FAILED_AT.get(config_id)
            if failed_at is not None and time.monotonic() - failed_at < MODEL_LIST_FAIL_BACKOFF_SECONDS:
                return skipped(
                    snap, ok=False,
                    error=_REFRESH_LAST_ERROR.get(config_id) or "清单刷新失败，稍后重试",
                )
        if not snap["has_key"] and snap["vendor"] != "ollama":
            return skipped(snap, ok=False, error="未配置 API Key")

        async with _REFRESH_LOCKS.setdefault(config_id, asyncio.Lock()):
            if not force:
                latest = await _latest_models_state(config_id, user_id)
                if latest is None:
                    return skipped(snap, ok=False, error="配置不存在")
                latest_models, latest_updated = latest
                if not _models_are_stale(latest_updated, _utcnow_naive()):
                    return _ensure_result(
                        config_id, latest_models, latest_updated,
                        refreshed=False, ok=True,
                    )
                if _recently_checked_empty(config_id):
                    return _ensure_result(
                        config_id, latest_models, latest_updated,
                        refreshed=False, ok=True,
                    )
            async with sem, async_session() as session:
                outcome = await refresh_models_with_stored_key(
                    session, user_id, config_id, timeout=MODEL_LIST_REFRESH_TIMEOUT
                )
            if outcome is None:
                return skipped(snap, ok=False, error="配置不存在")
            if outcome.get("ok"):
                _REFRESH_FAILED_AT.pop(config_id, None)
                _REFRESH_LAST_ERROR.pop(config_id, None)
                updated = outcome.get("models_updated_at")
                if updated is None:
                    # 成功但无清单（端点不提供/空列表）：没时间戳可落，按 TTL 记
                    # 「已检查」，避免每次触发都重打供应商
                    _REFRESH_EMPTY_AT[config_id] = time.monotonic()
                else:
                    _REFRESH_EMPTY_AT.pop(config_id, None)
                return {
                    "id": config_id,
                    "models": outcome.get("models") or snap["models"],
                    "models_updated_at": updated or (
                        snap["models_updated_at"].isoformat() if snap["models_updated_at"] else None
                    ),
                    "refreshed": updated is not None,
                    "ok": True,
                    "error": None,
                }
            error = str(outcome.get("error") or "清单刷新失败")
            _REFRESH_FAILED_AT[config_id] = time.monotonic()
            _REFRESH_LAST_ERROR[config_id] = error
            _REFRESH_EMPTY_AT.pop(config_id, None)  # 最近一次是失败：交给失败退避
            return skipped(snap, ok=False, error=error)

    results = await asyncio.gather(*(one(s) for s in snapshots))
    return {"configs": results}


async def update_api_config(
    db: AsyncSession,
    user_id: str,
    config_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    """Update a config. Returns None if not found."""
    result = await db.execute(
        select(ApiConfig).where(ApiConfig.id == config_id, ApiConfig.user_id == user_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        return None

    # Check name uniqueness if changing name（软删占名自动让位，见 helper）
    if "name" in updates and updates["name"] != config.name:
        await _assert_name_available(db, user_id, updates["name"])

    # c-api-config-save-gate：编辑按「连接相关字段值变化」触发门禁——探测在任何
    # setattr 之前，判败（非 ok）抛 ProbeFailed，router 转 422、本次更新不落库。
    # 触发集＝base_url / api_format / api_key(非空) / thinking_enabled /
    # thinking_effort（探测判据含思考参数）；name / models / vendor_override
    # 单独变更不触网（vendor_override 仅在 base_url 变更时影响探测输入，已在触发内）。
    new_format = (
        updates.get("api_format")
        if updates.get("api_format") is not None
        else config.api_format
    )
    trigger = (
        ("base_url" in updates and updates["base_url"] != config.base_url)
        or (
            updates.get("api_format") is not None
            and updates["api_format"] != config.api_format
        )
        or bool(updates.get("api_key"))
        or (
            updates.get("thinking_enabled") is not None
            and bool(updates["thinking_enabled"]) != bool(config.thinking_enabled)
        )
        or (
            updates.get("thinking_effort") is not None
            and updates["thinking_effort"] != (config.thinking_effort or "low")
        )
    )
    outcome: dict[str, Any] | None = None
    if trigger:
        eff_base_url = updates.get("base_url", config.base_url)
        eff_vendor, _, _ = resolve_vendor(
            eff_base_url, updates.get("vendor_override", config.vendor_override)
        )
        # 编辑态 Key 留空＝未提供（router 不放入 updates）：探测用已存密钥解密值
        eff_key = (
            updates["api_key"]
            if updates.get("api_key")
            else decrypt_api_key(config.api_key)
        )
        eff_thinking_enabled = (
            updates["thinking_enabled"]
            if updates.get("thinking_enabled") is not None
            else bool(config.thinking_enabled or False)
        )
        eff_thinking_effort = (
            updates["thinking_effort"]
            if updates.get("thinking_effort") is not None
            else (config.thinking_effort or "low")
        )
        raw_models = updates.get("models")
        preferred = (
            next(
                (m.strip() for m in raw_models if isinstance(m, str) and m.strip()),
                None,
            )
            if isinstance(raw_models, list)
            else _first_model(config.models)
        )
        outcome = await _probe_for_save(
            vendor_id=eff_vendor,
            api_key=eff_key,
            base_url=eff_base_url,
            api_format=new_format,
            preferred_model=preferred,
            thinking_enabled=bool(eff_thinking_enabled),
            thinking_effort=str(eff_thinking_effort),
        )

    # models 是 JSON 文本列：手动写入须归一化（去空白/去重保序/上限）后序列化
    if updates.get("models") is not None:
        updates["models"] = json.dumps(_normalize_models(updates["models"]), ensure_ascii=False)
        updates["models_updated_at"] = datetime.now(UTC)

    # Apply updates
    if "api_key" in updates:
        updates["api_key"] = encrypt_api_key(updates["api_key"])
    for field in (
        "name", "api_key", "vendor_override", "models", "models_updated_at",
        "api_format", "thinking_enabled", "thinking_effort",
    ):
        if field in updates:
            setattr(config, field, updates[field])

    if "base_url" in updates:
        config.base_url = updates["base_url"]
        # Re-detect vendor if base_url changed.
        # 注意：vendor 重识别只影响 vendor 两列，不回写 api_format——
        # 协议是用户显式选择，与 URL 识别正交。
        resolved_vendor_id, resolved_display_name, _ = resolve_vendor(
            updates["base_url"], updates.get("vendor_override", config.vendor_override)
        )
        config.vendor = resolved_vendor_id
        config.vendor_display_name = resolved_display_name

    # 改接口格式让位（c-api-config-save-gate）：门禁判过＝本次重测已完成——写入
    # 本次探测结果；未触发（仅改名/改 models）时保持既有测试态不动。原「改格式
    # 清空 models/测试态」分支退役：判败在上方已抛、不落库，不存在清空路径。
    if outcome is not None:
        outcome = _persist_probe_result(config, outcome)

    await db.commit()
    await db.refresh(config)
    result = _config_to_dict(config)
    if outcome is not None:
        result["probe"] = _probe_payload(outcome)
    return result


async def delete_api_config(
    db: AsyncSession, user_id: str, config_id: str
) -> dict[str, Any] | None:
    """Soft-delete a config. Returns None if not found.

    Returns dict with affected_projects count and affected_names list.

    软删（status=deleted，行保留）：前端「撤销删除」可经 restore 复活同一 id——
    配置名/加密 key/base_url 原样回来，项目引用（已置空）由调用方撤销后另行恢复。
    项目引用仍置空（既有级联契约），AI 路径按 status==active 过滤，软删行不被使用。
    """
    result = await db.execute(
        select(ApiConfig).where(ApiConfig.id == config_id, ApiConfig.user_id == user_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        return None

    # Find affected projects
    proj_result = await db.execute(
        select(Novel).where(
            Novel.ai_config_id == config_id, Novel.status != "deleted"
        )
    )
    affected = list(proj_result.scalars().all())
    affected_names = [p.name for p in affected]

    # Nullify project references
    for p in affected:
        p.ai_config_id = None
        # ai_model is intentionally retained for history display

    config.status = "deleted"
    await db.commit()

    return {
        "ok": True,
        "affected_projects": len(affected),
        "affected_names": affected_names,
    }


async def restore_api_config(
    db: AsyncSession, user_id: str, config_id: str
) -> dict[str, Any] | None:
    """Restore a soft-deleted config (undo delete). Returns None if not found.

    仅对 status=deleted 的行生效；活跃配置 restore 视为非法（由调用方 400）。
    """
    result = await db.execute(
        select(ApiConfig).where(ApiConfig.id == config_id, ApiConfig.user_id == user_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        return None
    if config.status != "deleted":
        raise ValueError("配置未删除，无需恢复")

    config.status = "active"
    await db.commit()
    await db.refresh(config)
    return _config_to_dict(config)


# ── Status / Batch ─────────────────────────────────────────────────────────


async def get_batch_status(db: AsyncSession, user_id: str) -> list[dict[str, Any]]:
    """Return current status for all user's configs（软删行不返回）。"""
    result = await db.execute(
        select(ApiConfig).where(
            ApiConfig.user_id == user_id,
            ApiConfig.status != "deleted",
            ApiConfig.vendor != "zhuque",  # c-zhuque-ai-detect：批量状态同列表口径
        )
    )
    statuses = []
    for c in result.scalars().all():
        models_list: list[str] = []
        if c.models:
            try:
                parsed = json.loads(c.models)
                if isinstance(parsed, list):
                    models_list = parsed
            except (json.JSONDecodeError, TypeError):
                pass
        plain_key = decrypt_api_key(c.api_key)
        statuses.append(
            {
                "id": c.id,
                "status": c.status,
                "last_test_status": c.last_test_status,
                "last_test_error": c.last_test_error,
                "last_tested_at": c.last_tested_at.isoformat()
                if c.last_tested_at
                else None,
                "models": models_list,
                "models_updated_at": c.models_updated_at.isoformat()
                if c.models_updated_at
                else None,
                "api_key_masked": mask_api_key(plain_key),
                "vendor": c.vendor,
                "api_format": getattr(c, "api_format", None) or "openai",
            }
        )
    return statuses


# ── Project AI Model ───────────────────────────────────────────────────────


async def set_project_model(
    db: AsyncSession,
    user_id: str,
    project_id: str,
    api_config_id: str | None,
    model: str | None,
) -> dict[str, Any] | None:
    """Set a project's AI model. Returns updated project or None if not found."""
    result = await db.execute(
        select(Novel).where(
            Novel.id == project_id,
            Novel.user_id == user_id,
            Novel.status != "deleted",
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        return None

    # ── 绑定校验（D12）：模型与供应商必须来自同一配置 ──
    # (None, None) 显式 clear 放行；不成对（缺一）拒绝；model 必须在配置的模型列表内。
    if (api_config_id is None) != (model is None):
        raise ValueError("api_config_id 与 model 必须成对提供（清除请两者都传 null）")

    if api_config_id:
        config_result = await db.execute(
            select(ApiConfig).where(
                ApiConfig.id == api_config_id, ApiConfig.user_id == user_id
            )
        )
        config = config_result.scalar_one_or_none()
        if not config:
            return None  # Will be interpreted as 404 by caller
        # 复用判定层谓词（写入校验与 ready 判据同源）
        from ai_state import parse_models

        if model not in parse_models(config.models):
            raise ValueError("该模型不属于这个 API 配置的模型列表，请重新选择")

    # Record audit log before changing
    old_config_id = project.ai_config_id
    old_model = project.ai_model

    # 幂等（9.2.13）：同值重复提交不写审计、不改状态，直接返回
    if old_config_id == api_config_id and old_model == model:
        return {
            "id": project.id,
            "ai_config_id": project.ai_config_id,
            "ai_model": project.ai_model,
        }

    # Determine change_type
    if old_config_id is None and old_model is None:
        change_type = "initial"
    elif api_config_id is None and model is None:
        change_type = "clear"
    else:
        change_type = "switch"

    # Create audit log entry
    log_entry = ProjectModelAuditLog(
        project_id=project_id,
        user_id=user_id,
        field="ai_model",
        old_api_config_id=old_config_id,
        new_api_config_id=api_config_id,
        old_model=old_model,
        new_model=model,
        change_type=change_type,
    )
    db.add(log_entry)

    # Update project
    project.ai_config_id = api_config_id
    project.ai_model = model
    await db.commit()
    await db.refresh(project)

    return {
        "id": project.id,
        "ai_config_id": project.ai_config_id,
        "ai_model": project.ai_model,
    }


async def get_project_ai_model(
    db: AsyncSession, user_id: str, project_id: str
) -> dict[str, Any] | None:
    """Get project's current AI model config."""
    result = await db.execute(
        select(Novel).where(
            Novel.id == project_id,
            Novel.user_id == user_id,
            Novel.status != "deleted",
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        return None

    config_name = None
    cfg = None
    if project.ai_config_id:
        cfg_result = await db.execute(
            select(ApiConfig).where(ApiConfig.id == project.ai_config_id)
        )
        cfg = cfg_result.scalar_one_or_none()
        if cfg:
            config_name = cfg.name

    # D13：前端门控只读 ai_state 一个字段、一次分派（不再本地推导四态）
    from ai_state import ai_state_for_novel

    state = await ai_state_for_novel(db, project, user_id)

    return {
        "api_config_id": project.ai_config_id,
        "model": project.ai_model,
        "config_name": config_name,
        **state,
    }


async def apply_model_to_all_projects(
    db: AsyncSession, user_id: str, api_config_id: str, model: str
) -> dict[str, Any]:
    """Apply a model to all non-deleted projects for a user."""
    # Verify config exists（c-zhuque-ai-detect：朱雀检测配置 SHALL NOT 可绑为写作模型）
    cfg_result = await db.execute(
        select(ApiConfig).where(
            ApiConfig.id == api_config_id,
            ApiConfig.user_id == user_id,
            ApiConfig.vendor != "zhuque",
        )
    )
    if not cfg_result.scalar_one_or_none():
        return {"ok": False, "error": "Config not found"}

    proj_result = await db.execute(
        select(Novel).where(Novel.user_id == user_id, Novel.status != "deleted")
    )
    projects = list(proj_result.scalars().all())

    succeeded = []
    failed = []
    for p in projects:
        if p.status == "archived":
            failed.append({"id": p.id, "reason": "Project is archived"})
            continue
        try:
            old_config_id = p.ai_config_id
            old_model = p.ai_model

            log_entry = ProjectModelAuditLog(
                project_id=p.id,
                user_id=user_id,
                field="ai_model",
                old_api_config_id=old_config_id,
                new_api_config_id=api_config_id,
                old_model=old_model,
                new_model=model,
                change_type="switch",
            )
            db.add(log_entry)
            p.ai_config_id = api_config_id
            p.ai_model = model
            succeeded.append(p.id)
        except Exception as e:  # noqa: BLE001
            failed.append({"id": p.id, "reason": str(e)})

    await db.commit()
    return {"succeeded": succeeded, "failed": failed}


# ── Model History ──────────────────────────────────────────────────────────


async def get_model_history(
    db: AsyncSession,
    user_id: str,
    project_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Get model change history for a project."""
    # Verify project ownership
    proj_result = await db.execute(
        select(Novel).where(
            Novel.id == project_id,
            Novel.user_id == user_id,
            Novel.status != "deleted",
        )
    )
    if not proj_result.scalar_one_or_none():
        return []

    result = await db.execute(
        select(ProjectModelAuditLog)
        .where(ProjectModelAuditLog.project_id == project_id)
        .order_by(ProjectModelAuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    entries = []
    for log in result.scalars().all():
        old_config_name = None
        new_config_name = None
        if log.old_api_config_id:
            cfg = await db.execute(
                select(ApiConfig).where(ApiConfig.id == log.old_api_config_id)
            )
            cfg_obj = cfg.scalar_one_or_none()
            if cfg_obj:
                old_config_name = cfg_obj.name
        if log.new_api_config_id:
            cfg = await db.execute(
                select(ApiConfig).where(ApiConfig.id == log.new_api_config_id)
            )
            cfg_obj = cfg.scalar_one_or_none()
            if cfg_obj:
                new_config_name = cfg_obj.name

        entries.append(
            {
                "id": log.id,
                "changed_at": log.created_at.isoformat() if log.created_at else "",
                "old_config_name": old_config_name,
                "new_config_name": new_config_name,
                "old_model": log.old_model,
                "new_model": log.new_model,
                "change_type": log.change_type,
            }
        )
    return entries


async def restore_model_history(
    db: AsyncSession,
    user_id: str,
    project_id: str,
    entry_id: str,
) -> dict[str, Any] | None:
    """Restore a project's model from a history entry."""
    # Verify project ownership
    proj_result = await db.execute(
        select(Novel).where(
            Novel.id == project_id,
            Novel.user_id == user_id,
            Novel.status != "deleted",
        )
    )
    project = proj_result.scalar_one_or_none()
    if not project:
        return None

    # Get history entry
    entry_result = await db.execute(
        select(ProjectModelAuditLog).where(ProjectModelAuditLog.id == entry_id)
    )
    entry = entry_result.scalar_one_or_none()
    if not entry:
        return None

    # Check target config still exists
    if entry.new_api_config_id:
        cfg_result = await db.execute(
            select(ApiConfig).where(ApiConfig.id == entry.new_api_config_id)
        )
        if not cfg_result.scalar_one_or_none():
            return {
                "error": "config_not_found",
                "message": "该配置关联的 API Key 已不存在",
            }

    # Restore
    old_config_id = project.ai_config_id
    old_model = project.ai_model

    log_entry = ProjectModelAuditLog(
        project_id=project_id,
        user_id=user_id,
        field="ai_model",
        old_api_config_id=old_config_id,
        new_api_config_id=entry.new_api_config_id,
        old_model=old_model,
        new_model=entry.new_model,
        change_type="restore",
    )
    db.add(log_entry)

    project.ai_config_id = entry.new_api_config_id
    project.ai_model = entry.new_model
    await db.commit()

    return {
        "ok": True,
        "ai_config_id": project.ai_config_id,
        "ai_model": project.ai_model,
    }


# ── Usage ──────────────────────────────────────────────────────────────────


async def get_usage_summary(db: AsyncSession, user_id: str) -> dict[str, Any]:
    """Get global usage summary."""
    from sqlalchemy import func as sa_func

    # All time
    result = await db.execute(
        select(
            sa_func.coalesce(sa_func.sum(TokenLog.tokens_in + TokenLog.tokens_out), 0)
        ).where(
            TokenLog.user_id == user_id,
            ~TokenLog.operation.like("zhuque-%"),  # c-zhuque-quota-ledger：朱雀消耗（检测/测试）不混写作模型用量
        )
    )
    total_all = result.scalar()

    # This month
    first_of_month = datetime.now(UTC).date().replace(day=1)
    result = await db.execute(
        select(
            sa_func.coalesce(sa_func.sum(TokenLog.tokens_in + TokenLog.tokens_out), 0)
        ).where(
            TokenLog.user_id == user_id,
            TokenLog.created_at >= first_of_month,
            ~TokenLog.operation.like("zhuque-%"),  # c-zhuque-quota-ledger：朱雀消耗（检测/测试）不混写作模型用量
        )
    )
    total_month = result.scalar()

    # Today
    today = datetime.now(UTC).date()
    result = await db.execute(
        select(
            sa_func.coalesce(sa_func.sum(TokenLog.tokens_in + TokenLog.tokens_out), 0)
        ).where(
            TokenLog.user_id == user_id,
            sa_func.date(TokenLog.created_at) == today,
            ~TokenLog.operation.like("zhuque-%"),  # c-zhuque-quota-ledger：朱雀消耗（检测/测试）不混写作模型用量
        )
    )
    total_today = result.scalar()

    return {
        "total_all_time": total_all or 0,
        "total_this_month": total_month or 0,
        "total_today": total_today or 0,
        "by_config": [],
        "queried_at": datetime.now(UTC).isoformat(),
    }


async def get_config_usage(
    db: AsyncSession, user_id: str, config_id: str
) -> dict[str, Any]:
    """Get usage for a specific config."""
    from sqlalchemy import func as sa_func

    result = await db.execute(
        select(
            TokenLog.model,
            sa_func.coalesce(sa_func.sum(TokenLog.tokens_in + TokenLog.tokens_out), 0),
        )
        .where(
            TokenLog.user_id == user_id,
            TokenLog.api_config_id == config_id,
            ~TokenLog.operation.like("zhuque-%"),  # c-zhuque-quota-ledger：朱雀消耗（检测/测试）不混写作模型用量
        )
        .group_by(TokenLog.model)
    )
    rows = result.all()

    total = sum(row[1] for row in rows)
    breakdown = [{"model": row[0], "tokens": row[1]} for row in rows]

    return {"total_tokens": total or 0, "breakdown": breakdown}


async def get_project_usage(
    db: AsyncSession, user_id: str, project_id: str
) -> dict[str, Any] | None:
    """Get usage for a specific project（软删书按不存在处理：调用方 404）。"""
    from sqlalchemy import func as sa_func

    project = (
        await db.execute(
            select(Novel).where(
                Novel.id == project_id,
                Novel.user_id == user_id,
                Novel.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if project is None:
        return None

    # By model
    result = await db.execute(
        select(
            TokenLog.model,
            sa_func.coalesce(sa_func.sum(TokenLog.tokens_in + TokenLog.tokens_out), 0),
        )
        .where(
            TokenLog.user_id == user_id,
            TokenLog.project_id == project_id,
            ~TokenLog.operation.like("zhuque-%"),  # c-zhuque-quota-ledger：朱雀消耗（检测/测试）不混写作模型用量
        )
        .group_by(TokenLog.model)
    )
    by_model = [{"model": row[0], "tokens": row[1]} for row in result.all()]

    # By operation
    result = await db.execute(
        select(
            TokenLog.operation,
            sa_func.coalesce(sa_func.sum(TokenLog.tokens_in + TokenLog.tokens_out), 0),
        )
        .where(
            TokenLog.user_id == user_id,
            TokenLog.project_id == project_id,
        )
        .group_by(TokenLog.operation)
    )
    by_operation = [{"operation": row[0], "tokens": row[1]} for row in result.all()]

    total = sum(item["tokens"] for item in by_model)

    return {
        "total_tokens": total or 0,
        "by_model": by_model,
        "by_operation": by_operation,
    }


# ── Migration ──────────────────────────────────────────────────────────────


async def migrate_user_configs(db: AsyncSession) -> None:
    """Migrate User.api_key / api_base_url / api_model -> ApiConfig.

    Runs in FastAPI lifespan. Idempotent.
    """
    result = await db.execute(select(ApiConfig.__table__.c.user_id).distinct())
    migrated_user_ids = {row[0] for row in result.fetchall()}

    user_result = await db.execute(
        select(User).where(
            User.api_key != "",
            User.api_key.isnot(None),
        )
    )
    for user in user_result.scalars().all():
        if user.id in migrated_user_ids:
            # Already has api_configs, skip
            continue

        detected = detect_vendor(user.api_base_url)
        vendor_id = detected.vendor_id if detected else "openai-compat"
        vendor_name = detected.display_name if detected else "OpenAI 兼容"

        config = ApiConfig(
            user_id=user.id,
            name=f"{vendor_name} 默认配置",
            vendor=vendor_id,
            vendor_display_name=vendor_name,
            api_key=encrypt_api_key(user.api_key),
            base_url=user.api_base_url,
            status="active",
        )
        db.add(config)
        await db.flush()

        # Apply model to existing projects
        if user.api_model:
            proj_result = await db.execute(
                select(Novel).where(
                    Novel.user_id == user.id, Novel.status != "deleted"
                )
            )
            for project in proj_result.scalars().all():
                project.ai_config_id = config.id
                project.ai_model = user.api_model

                log_entry = ProjectModelAuditLog(
                    project_id=project.id,
                    user_id=user.id,
                    field="ai_model",
                    old_api_config_id=None,
                    new_api_config_id=config.id,
                    old_model=None,
                    new_model=user.api_model,
                    change_type="initial",
                )
                db.add(log_entry)

        user.migrated = True

    await db.commit()


# ── Helpers ────────────────────────────────────────────────────────────────


def _config_to_dict(config: ApiConfig) -> dict[str, Any]:
    plain_key = decrypt_api_key(config.api_key)
    models_list: list[str] = []
    if config.models:
        try:
            parsed = json.loads(config.models)
            if isinstance(parsed, list):
                models_list = parsed
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "id": config.id,
        "name": config.name,
        "vendor": config.vendor,
        "vendor_display_name": config.vendor_display_name,
        "vendor_override": config.vendor_override,
        "api_format": getattr(config, "api_format", None) or "openai",
        "thinking_enabled": bool(getattr(config, "thinking_enabled", False)),
        "thinking_effort": getattr(config, "thinking_effort", None) or "low",
        "base_url": config.base_url,
        "api_key": mask_api_key(plain_key),
        "api_key_masked": mask_api_key(plain_key),
        "status": config.status,
        "last_test_status": config.last_test_status,
        "last_test_error": config.last_test_error,
        "last_tested_at": config.last_tested_at.isoformat()
        if config.last_tested_at
        else None,
        "models": models_list,
        "models_updated_at": config.models_updated_at.isoformat()
        if config.models_updated_at
        else None,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }
