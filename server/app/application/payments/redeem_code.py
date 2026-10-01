"""redeem_code：激活码兑换（s-code-redeem）。

管理端发放的 unused 码由登录用户凭码字符串直接开通：绑定本人、按码行自带
tier/duration_days 起算（起点=顺延口径，复用订单激活的 calc_grant_start）、
CAS 落库、trade event 留痕。与订单激活（activate_code，只认 order_no）互不替代。
"""
from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

from app.application.payments.activate_code import calc_grant_start

# 管理端发码格式：AC-XXXX-XXXX-XXXX-XXXX（前缀+4 组，每组大写字母/数字——
# 与 generate_code 的 secrets 生成器逐形对齐；隔离栈冒烟实测抓过 3 组误配）
_CODE_SHAPE = re.compile(r"^AC-(?:[A-Z0-9]{4}-){3}[A-Z0-9]{4}$")


def _normalize(raw: str) -> str:
    return (raw or "").strip().upper()


def redeem_code(
    code_repo,
    event_repo,
    raw_code: str,
    user_id: int,
    today: date | None = None,
) -> dict:
    """兑换：unused 码 → active 并绑定 user_id。

    Returns:
        {code_id, tier, grant_start, expires_at}（ISO 字符串，与订单激活同形）
    错误（{"error": ...}）：
        invalid_code —— 形态不匹配/不存在/历史 0 天废码，统一口径不泄露形态
        already_used —— 已被兑换（含 CAS 失配的并发双兑）
    """
    code_id = _normalize(raw_code)
    if not _CODE_SHAPE.match(code_id):
        return {"error": "invalid_code"}
    code = code_repo.get(code_id)
    if not code or code.status != "unused":
        return {"error": "invalid_code" if code is None else "already_used"}
    if code.status == "unused" and (code.duration_days or 0) <= 0:
        # 历史双源坑（TIER_POLICY pro/max duration_days=0）：0 天码兑换无意义，
        # 按无效码拒绝，不给用户静默开通当天到期的"套餐"。
        return {"error": "invalid_code"}

    now = datetime.now(UTC).replace(tzinfo=None)  # naive UTC（表列口径）
    family = [c for c in code_repo.find_all_by_username(user_id)
              if c.status in ("active", "frozen")]
    base = calc_grant_start(family, today)
    grant_start = datetime(base.year, base.month, base.day)
    expires_at = grant_start + timedelta(days=code.duration_days)

    if not code_repo.redeem_unused(code.code_id, user_id, grant_start, expires_at, now):
        return {"error": "already_used"}

    event_repo.append({
        "event_key": f"codes:{code.code_id}:redeemed",
        "event_type": "codes.redeemed",
        "order_no": None,
        "payload": {
            "tier": code.tier,
            "grant_start": grant_start.isoformat(),
            "expires_at": expires_at.isoformat(),
            "source": "redeem",
        },
        "created_at": now,
    })

    return {
        "code_id": code.code_id,
        "tier": code.tier,
        "grant_start": grant_start.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
