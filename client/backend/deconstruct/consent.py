"""拆书使用承诺（c-deconstruct-compliance-guard）——用户级一次性签署 + 服务端存证。

只在服务端存"谁、哪一版、什么时间"（见 S端 s-deconstruct-consent）；本机多存
同步状态与重试账。签署覆盖所有拆书任务：签一次，之后每次拆书只看状态。

状态：
- pending：已本机签署，还没同步到账号（断网/超时/5xx）
- synced：服务端已存证
- login：登录态失效（401），重新登录后自动重试
- local：S端 未上线存证端点（404），按本机签署处理，不硬门
- failed：服务端拒收（如版本不支持），需升级客户端
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from db import async_session
from models.deconstruct import DeconstructConsent

log = logging.getLogger(__name__)

CONSENT_VERSION = "deconstruct-consent-v1"

CONSENT_TEXT = (
    "拆书是给你自己学写法用的。签之前，请确认三件事：\n\n"
    "1. 这本书我有权使用——自己买的、自己写的，或作者授权。\n"
    "2. 拆出来的内容只给自己写作用，不发布、不售卖。\n"
    "3. 我知道正文会发给我选的模型服务商处理。\n\n"
    "签了之后，换设备不用重签；承诺版本升级时会再请你确认。"
)

CONSENT_TEXT_SHA256 = hashlib.sha256(CONSENT_TEXT.encode("utf-8")).hexdigest()

# 换设备恢复的短超时：S端 冷启动可到 60s，但页面加载不能等那么久；
# 超时按未签署返回，用户本机签署后由后台 sync 幂等补齐。
RESTORE_TIMEOUT_SECONDS = 8

# 建书硬门：synced 或 local（S端 未上线降级）才允许；pending/login/failed 挡住。
BUILD_ALLOWED_STATES = frozenset({"synced", "local"})

_sync_lock = asyncio.Lock()


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _current_username() -> str:
    """本机当前登录账号（config.json）；未登录/读取失败返回空串。"""
    try:
        from auth_local.service import load_or_create_config

        return str(load_or_create_config().get("username") or "")
    except Exception:  # noqa: BLE001 — 读配置失败按未登录处理
        return ""


def view(row: DeconstructConsent | None) -> dict:
    state = row.sync_state if row is not None else "unsigned"
    return {
        "version": CONSENT_VERSION,
        "text": CONSENT_TEXT,
        "text_sha256": CONSENT_TEXT_SHA256,
        "signed": row is not None,
        "signed_at": _iso(row.signed_at) if row is not None else None,
        "server_ts": _iso(row.server_ts) if row is not None else None,
        "sync_state": state,
        "can_build": row is not None and state in BUILD_ALLOWED_STATES,
        "can_export": row is not None,
        "last_error": (row.last_error if row is not None else "") or "",
    }


async def _current(db, user_id: str) -> DeconstructConsent | None:
    return (
        await db.scalars(
            select(DeconstructConsent)
            .where(
                DeconstructConsent.user_id == user_id,
                DeconstructConsent.agreement_version == CONSENT_VERSION,
            )
            .order_by(DeconstructConsent.created_at.desc())
            .limit(1)
        )
    ).first()


async def get_status(db, user_id: str, *, restore: bool = False) -> dict:
    """本地承诺状态；restore=True 时本机无记录则从 S端 取回（换设备/重装）。

    只在 GET /consent（页面加载）走 restore：网络不可达时最多等一次 S端 调用，
    不阻塞创建/详情等热路径。
    """
    row = await _current(db, user_id)
    if row is None and restore:
        row = await _restore_from_server(db, user_id)
    return view(row)


async def _restore_from_server(db, user_id: str) -> DeconstructConsent | None:
    """从 S端 GET 取回当前版本的签署记录；版本与文本哈希都匹配才回填。

    S端 只返回版本/哈希/时间（不返回作品信息）；哈希不匹配＝文本已变但版本
    未升，按未签署处理，要求重新确认。
    """
    from auth_local.service import call_server_api

    try:
        resp = await asyncio.wait_for(
            call_server_api("deconstruct/consents", method="GET", with_token=True),
            timeout=RESTORE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        log.info("event=deconstruct_consent.restore_timeout user=%s", user_id)
        return None
    if resp.get("code") != 0:
        return None
    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    items = data.get("items") if isinstance(data, dict) else []
    if not isinstance(items, list):
        return None
    match = next(
        (
            item for item in items
            if isinstance(item, dict)
            and item.get("version") == CONSENT_VERSION
            and item.get("agreement_text_sha256") == CONSENT_TEXT_SHA256
        ),
        None,
    )
    if match is None:
        return None
    raw_ts = match.get("server_ts")
    try:
        server_ts = datetime.fromisoformat(str(raw_ts)) if raw_ts else None
    except ValueError:
        server_ts = None
    row = DeconstructConsent(
        user_id=user_id,
        agreement_version=CONSENT_VERSION,
        agreement_text_sha256=CONSENT_TEXT_SHA256,
        signed_at=server_ts or _now(),
        server_ts=server_ts,
        sync_state="synced",
    )
    from sqlalchemy.exc import IntegrityError

    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        # 并发恢复（两个窗口同时 GET）撞唯一键：回滚后返回已存在行，恢复也幂等
        await db.rollback()
        existing = await _current(db, user_id)
        if existing is not None:
            return existing
        raise
    await db.refresh(row)
    log.info("event=deconstruct_consent.restored user=%s", user_id)
    return row


async def sign(db, user_id: str) -> dict:
    """本机签署（幂等）；后台尝试同步，不阻塞请求。"""
    row = await _current(db, user_id)
    if row is None:
        row = DeconstructConsent(
            user_id=user_id,
            agreement_version=CONSENT_VERSION,
            agreement_text_sha256=CONSENT_TEXT_SHA256,
            signed_at=_now(),
            sync_state="pending",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    _schedule_sync(user_id)
    return view(row)


async def retry(user_id: str) -> dict:
    """手动重试：后台同步，立即返回当前状态（前端轮询刷新）。"""
    _schedule_sync(user_id)
    async with async_session() as db:
        return await get_status(db, user_id)


def _schedule_sync(user_id: str) -> None:
    try:
        asyncio.get_running_loop().create_task(sync(user_id))
    except RuntimeError:
        # 无运行中事件循环（脚本/测试直调）：留给启动 sweep 或手动 retry
        log.info("event=deconstruct_consent.sync_deferred user=%s", user_id)


async def sync(user_id: str) -> dict:
    """把本机签署上报 S端；按返回码更新状态。失败不抛，留给重试。"""
    async with _sync_lock, async_session() as db:
            row = await _current(db, user_id)
            if row is None or row.sync_state == "synced":
                return view(row)
            current = _current_username()
            if current != user_id:
                # 未登录，或本机残留其他账号的签署行：不能用当前令牌替它上报
                log.info(
                    "event=deconstruct_consent.sync_skipped user=%s current=%s",
                    user_id, current,
                )
                return view(row)
            from auth_local.service import call_server_api

            resp = await call_server_api(
                "deconstruct/consents",
                method="POST",
                json_body={
                    "agreement_version": row.agreement_version,
                    "agreement_text_sha256": row.agreement_text_sha256,
                },
                with_token=True,
            )
            code = resp.get("code")
            row.attempts = int(row.attempts or 0) + 1
            row.last_attempt_at = _now()
            if code == 0:
                data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
                raw_ts = data.get("server_ts") if isinstance(data, dict) else None
                try:
                    row.server_ts = (
                        datetime.fromisoformat(str(raw_ts)) if raw_ts else None
                    )
                except ValueError:
                    row.server_ts = None
                row.sync_state = "synced"
                row.last_error = ""
            elif code == 401:
                row.sync_state = "login"
                row.last_error = "登录状态失效，请重新登录"
            elif code == 404:
                row.sync_state = "local"
                row.last_error = ""
            elif code == 400:
                row.sync_state = "failed"
                row.last_error = str(resp.get("msg") or "承诺版本不被服务端接受")[:300]
            else:
                row.sync_state = "pending"
                row.last_error = str(resp.get("msg") or "服务暂时不可达")[:300]
            await db.commit()
            log.info(
                "event=deconstruct_consent.sync user=%s state=%s attempts=%s",
                user_id, row.sync_state, row.attempts,
            )
            return view(row)


async def sync_pending() -> int:
    """启动/定时补偿：把所有未同步的签署再试一遍。返回尝试条数。"""
    current = _current_username()
    async with async_session() as db:
        stmt = select(DeconstructConsent).where(
            DeconstructConsent.sync_state.in_(["pending", "login", "local", "failed"])
        )
        if current:
            stmt = stmt.where(DeconstructConsent.user_id == current)
        rows = (await db.scalars(stmt)).all()
        user_ids = [r.user_id for r in rows]
    for uid in user_ids:
        try:
            await sync(uid)
        except Exception:  # noqa: BLE001 — 单条失败不拖垮其余
            log.exception("event=deconstruct_consent.sync_failed user=%s", uid)
    return len(user_ids)


async def retry_loop(interval_seconds: int = 600) -> None:
    """常驻补偿（dispatcher 线程内）：每 10 分钟把未同步的签署再试一遍。"""
    while True:
        try:
            await sync_pending()
        except Exception:  # noqa: BLE001 — 下轮再试
            log.exception("event=deconstruct_consent.retry_loop_failed")
        await asyncio.sleep(interval_seconds)
