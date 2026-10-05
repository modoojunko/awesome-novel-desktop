"""设备配对：`POST /api/pair/exchange`（挑战-应答换令牌）+ 授权刷新快照装配。

s-security-hardening：check-auth 不再携带令牌——令牌只发给能报出本机配对密钥的请求
（SHA-256 恒定时间比对授权记录里的 challenge）。统一失败形态，MUST NOT 区分
无记录/未升级/密钥不符（不可枚举）。已在登录类限流清单（middleware.SENSITIVE_PATHS）。
"""
from __future__ import annotations

import hashlib
import secrets

from fastapi import Depends

from app.domain.licensing import License
from app.infrastructure.repositories.factory import (
    code_repo,
    device_repo,
    grant_repo,
    user_repo,
)
from app.interfaces.client_api.router import router as r
from app.interfaces.deps import Db, get_db
from app.interfaces.dto import PairExchangeRequest
from app.interfaces.guards import guard_identifiers


def build_license_snapshot(db, username: str) -> dict:
    """授权态刷新数据（tier/expires_at/entitlement/days_remaining/attention）——不含令牌。

    check-auth（轮询刷新）与 pair/exchange（配对/刷新令牌）共用同一装配，
    保证两条通道的套餐口径永不漂移。
    """
    codes = code_repo(db).find_active_by_username(username)
    license_ = License(username=username).merge(codes)

    # 权益快照（c-s-entitlement-sync 契约 v1）：档位目录配置 → ENTITLEMENT_DEFAULTS 兜底
    from app.config import settings as _settings
    from app.infrastructure.repositories.payments_repo import TierRepo

    tier_cfg = TierRepo(db).find_entitlement_by_key(license_.effective_tier)

    # 档位目录投影（tier-catalog）：live/planned 档的精简投影供 C端 兜底判定与
    # 档位名渲染；不含 retired 与售卖字段。60s TTL 缓存（find_all_cached）。
    import json as _json

    tier_catalog = []
    for row in TierRepo(db).find_all_cached():
        if row.get("status") not in ("live", "planned"):
            continue
        features = []
        try:
            doc = _json.loads(row.get("entitlement") or "{}")
            if isinstance(doc, dict):
                features = doc.get("features", [])
        except ValueError:
            pass
        tier_catalog.append({
            "key": row.get("key"),
            "rank": row.get("rank"),
            "display_name": row.get("display_name"),
            "features": features,
        })

    data = {
        "tier": license_.effective_tier,
        "expires_at": license_.max_expires_at.isoformat() if license_.max_expires_at else "",
        "tier_catalog": {"v": 1, "tiers": tier_catalog},
    }
    ent = tier_cfg or _settings.ENTITLEMENT_DEFAULTS.get(
        license_.effective_tier, _settings.ENTITLEMENT_DEFAULTS["none"])
    data["entitlement"] = {"v": 1, **ent}

    # A4 扩展（可选字段，无支付数据时省略）：days_remaining（北京自然日口径）
    from datetime import datetime, timedelta, timezone

    if license_.max_expires_at and license_.effective_tier not in ("none", "free"):
        bj_tz = timezone(timedelta(hours=8))
        expires_bj = license_.max_expires_at.astimezone(bj_tz)
        today0_bj = datetime.now(bj_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        data["days_remaining"] = max((expires_bj - today0_bj).days, 0)

    # attention：账号动态（退款进行中含冷静期 / 冻结待核对）
    uid = user_repo(db).get_id(username)
    if uid:
        from app.infrastructure.repositories.payments_repo import OrderRepo

        flags = OrderRepo(db).attention_flags(uid)
        if flags["refund_processing"] or flags["verify_pending"]:
            data["attention"] = flags
    return data


def _fail() -> dict:
    """统一失败形态：MUST NOT 区分 无记录/未升级/密钥不符（不可枚举）。"""
    return {"code": 1, "msg": "配对失败，请在桌面端重新发起授权"}


@r.post("/api/pair/exchange",
        dependencies=[guard_identifiers(body=("pc_hash",))])
async def api_pair_exchange(req: PairExchangeRequest, db: Db = Depends(get_db)):
    """以本机配对密钥换取令牌（挑战-应答）。

    仅本机持有 device_secret（≥256 位随机、只存本地、绝不经 URL/日志）可换；
    429（限流）视为可重试，客户端 MUST NOT 因失败清空本地凭据。
    """
    pc_hash = (req.pc_hash or "").strip()
    secret = (req.device_secret or "").strip()
    if not pc_hash or not secret:
        return _fail()

    grant = grant_repo(db).get(pc_hash)
    if not grant or not grant.challenge:
        return _fail()  # 无记录 / 存量未升级：同一形态
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    if not secrets.compare_digest(digest, grant.challenge):
        return _fail()

    # 与 check-auth 同款注销门禁：到期惰性执行后再取（design D2 主路径）
    from app.application.identity.deletion_service import lazy_execute_if_due

    lazy_execute_if_due(user_repo(db), code_repo(db), device_repo(db), grant_repo(db),
                        grant.username)
    if not user_repo(db).get(grant.username):
        return _fail()

    data = build_license_snapshot(db, grant.username)
    data["token"] = grant.token
    data["username"] = grant.username
    return {"code": 0, "data": data}
