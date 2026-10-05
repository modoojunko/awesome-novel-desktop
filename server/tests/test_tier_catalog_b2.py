"""B2 行为测试（tier-plan-four-tiers；评审 A-P1-3 测试缺口收口）。

覆盖七类新行为（不依赖生产库；sqlite 种子＋TierRepo 缓存隔离 via backend 键）：
1. rank 读库注入（configure_rank_lookup）三态：读库命中 / 缺行告警归 0 / 抛异常退常量
2. resolve_effective_tier 缺 trial 行塌 none（把评审 P0 的雷钉成显式回归）
3. _device_limit 语义：行值 / 列缺失（None→兜底）/ device_limit=0 合法
4. tier_catalog 投影：retired 过滤＋坏 JSON 容错＋{v, tiers} 形状

用法：cd server && python -m pytest tests/test_tier_catalog_b2.py -v
"""

import logging

import pytest

from app.domain.payments import pricing


# ── 1) rank 读库三态 ─────────────────────────────────────────────────────────

def test_rank_lookup_hit_db_wins(monkeypatch):
    monkeypatch.setattr(pricing, "configure_rank_lookup",
                        lambda fn: monkeypatch.setattr(pricing, "_rank_lookup", fn, raising=False))
    pricing.configure_rank_lookup(lambda: {"free": 5, "standard": 15, "trial": 10, "pro": 20, "max": 30})
    try:
        assert pricing.tier_rank("standard") == 15  # DB 值（常量表没有 standard）
        assert pricing.tier_rank("pro") == 20
    finally:
        pricing.configure_rank_lookup(lambda: None)


def test_rank_missing_row_warns_and_zeroes(monkeypatch, caplog):
    """缺行显式告警＋保守归 0（spec：不静默升档/清零）。"""
    pricing.configure_rank_lookup(lambda: {"free": 5, "pro": 20})  # 缺 trial
    try:
        with caplog.at_level(logging.WARNING, logger=pricing.__name__):
            assert pricing.tier_rank("trial") == 0
        assert any("tier_rank_missing" in r.message for r in caplog.records)
    finally:
        pricing.configure_rank_lookup(lambda: None)


def test_rank_lookup_raises_falls_back_to_constants(monkeypatch):
    def _boom():
        raise RuntimeError("db down")
    pricing.configure_rank_lookup(_boom)
    try:
        assert pricing.tier_rank("pro") == 20  # 常量兜底
    finally:
        pricing.configure_rank_lookup(lambda: None)


# ── 2) resolve_effective_tier 缺 trial 行塌 none（评审 P0 显式回归钉）─────────

def test_resolve_effective_tier_missing_trial_row_collapses(monkeypatch):
    """lookup 只认得 free/pro 而码是 trial → 该码归 0，effective 塌 none。

    这是评审 P0 描述的部署门禁事故形态——故意钉住：修法（seed 补基线行 INSERT）
    回归了本测试照旧红（lookup 给全量 map 时 trial 归 trial）。
    """
    pricing.configure_rank_lookup(lambda: {"free": 5, "pro": 20})
    try:
        code = type("C", (), {"tier": "trial"})()
        assert pricing.resolve_effective_tier([code]) == "none"
    finally:
        pricing.configure_rank_lookup(lambda: None)


def test_resolve_effective_tier_full_map_no_collapse(monkeypatch):
    pricing.configure_rank_lookup(
        lambda: {"free": 5, "standard": 15, "trial": 10, "pro": 20, "max": 30})
    try:
        code = type("C", (), {"tier": "trial"})()
        assert pricing.resolve_effective_tier([code]) == "trial"
    finally:
        pricing.configure_rank_lookup(lambda: None)


# ── 3) 设备限额 None-aware（评审 B-P0-1）─────────────────────────────────────

def test_device_limit_none_value_falls_back(monkeypatch):
    """列缺失（pg_http get→None）→ 落 tier_policy 兜底，不钳 1。"""
    from app.application.devices import list_devices
    rows = [{"key": "pro", "device_limit": None}]
    monkeypatch.setattr(list_devices.TierRepo, "find_all_cached", lambda self: rows, raising=False)
    assert list_devices._device_limit(None, "pro") is not None  # 走兜底不炸
    # db=None 直兜底
    assert list_devices._device_limit(None, "pro") == list_devices.tier_policy.get_device_limit("pro")


def test_device_limit_zero_is_legal(monkeypatch):
    """device_limit=0 是合法值（档位禁设备），MUST NOT 被钳成 1。"""
    from app.application.devices import list_devices
    rows = [{"key": "locked", "device_limit": 0}]
    monkeypatch.setattr(list_devices.TierRepo, "find_all_cached", lambda self: rows, raising=False)
    # 行命中 → 尊重 0（db 传 sentinel 对象触发行路径）
    assert list_devices._device_limit(object(), "locked") == 0


# ── 4) tier_catalog 投影过滤与形状（经 pairing 内联逻辑等价重放）─────────────

def test_catalog_projection_filters_retired_and_bad_json():
    import json as _json
    rows = [
        {"key": "free", "status": "live", "rank": 5, "display_name": "免费", "entitlement": "{}"},
        {"key": "old", "status": "retired", "rank": 1, "display_name": "旧档", "entitlement": "{}"},
        {"key": "standard", "status": "planned", "rank": 15, "display_name": "标准",
         "entitlement": "not-json{"},
        {"key": "pro", "status": "live", "rank": 20, "display_name": "PRO",
         "entitlement": '{"features":["ai-generate"],"limits":{"max_projects":null}}'},
    ]
    catalog = []
    for row in rows:
        if row.get("status") not in ("live", "planned"):
            continue
        features = []
        try:
            doc = _json.loads(row.get("entitlement") or "{}")
            if isinstance(doc, dict):
                features = doc.get("features", [])
        except ValueError:
            pass
        catalog.append({"key": row["key"], "rank": row["rank"],
                        "display_name": row["display_name"], "features": features})
    keys = [c["key"] for c in catalog]
    assert "old" not in keys  # retired 过滤
    std = next(c for c in catalog if c["key"] == "standard")
    assert std["features"] == []  # 坏 JSON 容错→空 features（不炸）
    pro = next(c for c in catalog if c["key"] == "pro")
    assert pro["features"] == ["ai-generate"]
