"""激活码激活/续费。"""
from __future__ import annotations

from datetime import UTC, datetime

from app.domain.licensing import tier_policy
from app.infrastructure.repositories.base import CodeRepo


def activate_code(code_repo: CodeRepo, username: str, code_id: str) -> dict:
    code = code_repo.get(code_id)
    if not code:
        return {"code": 1, "msg": "无效的激活码"}
    if not code.can_activate():
        return {"code": 1, "msg": "激活码已被使用"}

    today = datetime.now(UTC).date()  # UTC 日期口径，不依赖容器 TZ
    # 顺延基准把冻结行（退款处理中）也算上：冻结只暂停可用性，不动排队位，
    # 取消退款后排队终点不变（s-pay-refund-freeze）。merge 会跳过 frozen，
    # 故此处直接在 active+frozen 全家族上取最远到期日。
    family = [c for c in code_repo.find_all_by_username(username)
              if c.status in ("active", "frozen")]
    max_exp = max((c.expires_at for c in family if c.expires_at), default=None)
    base = max_exp.date() if (max_exp and max_exp.date() > today) else today
    new_expires = tier_policy.calc_expires_at(code.tier, base)

    code_repo.activate(code_id, username, new_expires)

    return {"code": 0, "data": {"new_expires_at": new_expires.isoformat()}}
