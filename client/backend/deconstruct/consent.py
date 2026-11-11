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

# 建书硬门：synced 或 local（S端 未上线降级）才允许；pending/login/failed 挡住。
BUILD_ALLOWED_STATES = frozenset({"synced", "local"})

_sync_lock = asyncio.Lock()


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


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


async def get_status(db, user_id: str) -> dict:
    return view(await _current(db, user_id))


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
    async with async_session() as db:
        rows = (
            await db.scalars(
                select(DeconstructConsent).where(
                    DeconstructConsent.sync_state.in_(
                        ["pending", "login", "failed"]
                    )
                )
            )
        ).all()
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
