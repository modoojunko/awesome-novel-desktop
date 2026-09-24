"""商品目录视图组装（Z.2/Z.4，s-payments-application）：业务规则单点。

三态开关、selling_points 解析、折扣展示/实付价换算、热门位选择、retired 档位
过滤——全部收在本服务；web_api 层只做 HTTP 适配。响应形状与既有 Z.4 契约
逐键一致（tests/test_payments_api.py 守卫）。
"""
from __future__ import annotations

import json

from app.domain.payments.pricing import calc_discount_display

AGREEMENT_VERSION = "v2026.08"


def _selling_points(raw) -> list[str]:
    """tiers.selling_points 列（JSON 数组文本）→ 字符串数组；失败/空回 []。"""
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        v = json.loads(raw or "[]")
        return [str(x) for x in v] if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


def build_skus_view(sku_repo, tier_repo, config_repo) -> dict:
    skus = sku_repo.find_on_sale()
    tiers = tier_repo.find_all()

    # 三态开关
    enabled = config_repo.get("payments.purchase.enabled") or "off"

    sku_list = []
    for s in skus:
        sku_list.append({
            "sku_key": s.get("sku_key", ""),
            "tier_key": s.get("tier_key", ""),
            "period": s.get("period", ""),
            "period_days": s.get("period_days", 0),
            "base_price_fen": s.get("base_price_fen", 0),
            "discount_display": calc_discount_display(s.get("discount_permille", 1000)),
            "price_fen": s.get("base_price_fen", 0) * s.get("discount_permille", 1000) // 1000,
            "device_limit": s.get("device_limit", 1),
        })

    popular = next((s["sku_key"] for s in sku_list if s.get("sku_key", "").endswith("yearly")), "")

    return {
        "purchase_enabled": enabled != "off",
        "agreement_version": AGREEMENT_VERSION,
        "tiers": [
            {"key": t.get("key"), "label": t.get("display_name"),
             "is_live": t.get("status") == "live",
             "is_planned": t.get("status") == "planned",
             "selling_points": _selling_points(t.get("selling_points"))}
            for t in tiers if t.get("status") != "retired"
        ],
        "skus": sku_list,
        "popular_sku": popular,
    }
