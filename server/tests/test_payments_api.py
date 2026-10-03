"""支付 Web API 端点测试：W1 目录（购买开关三态）+ W2 下单（4012/off/rehearsal）+ W3 列表。

设计依据：backend-detail-design.md §5.2 + 附录 Z；演练三态 A9。
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.base import SessionLocal
from app.models.payments import SkuORM, TierORM

AGREEMENT_VERSION = "v2026.08"


def _auth(web_user: dict) -> dict:
    return {"Authorization": f"Bearer {web_user['token']}"}


def _seed_catalog(**sku_overrides) -> None:
    """播种 PRO tier + 包年 SKU（幂等：先查再插）。"""
    s = SessionLocal()
    try:
        tier = s.query(TierORM).filter_by(key="pro").first()
        if not tier:
            tier = TierORM(key="pro", display_name="PRO", rank=20)
            s.add(tier)
            s.flush()
        sku = s.query(SkuORM).filter_by(sku_key="pro_yearly").first()
        if not sku:
            base = dict(
                sku_key="pro_yearly",
                tier_id=tier.id,
                period="yearly",
                period_days=365,
                base_price_fen=29900,
                discount_permille=800,
                device_limit=5,
                on_sale=True,
                sort=3,
            )
            base.update(sku_overrides)
            s.add(SkuORM(**base))
        s.commit()
    finally:
        s.close()


@pytest.fixture
def _catalog():
    _seed_catalog()
    yield


@pytest.fixture
def _switch_off(db_session):
    from app.models.config import GlobalConfigORM
    s = db_session
    row = s.query(GlobalConfigORM).filter_by(key="payments.purchase.enabled").first()
    if row:
        row.value = "off"
    else:
        s.add(GlobalConfigORM(key="payments.purchase.enabled", value="off"))
    s.commit()


@pytest.fixture
def _switch_rehearsal(db_session):
    from app.models.config import GlobalConfigORM
    s = db_session
    for key, value in [
        ("payments.purchase.enabled", "rehearsal"),
        ("payments.rehearsal.usernames", "rehearsal_user_a"),
    ]:
        row = s.query(GlobalConfigORM).filter_by(key=key).first()
        if row:
            row.value = value
        else:
            s.add(GlobalConfigORM(key=key, value=value))
    s.commit()


class TestPaySkus:
    def test_off_switch_reports_disabled(self, client, web_user, _catalog, _switch_off):
        r = client.get("/api/pay/skus", headers=_auth(web_user))
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["purchase_enabled"] is False
        keys = [s["sku_key"] for s in body["data"]["skus"]]
        assert "pro_yearly" in keys

    def test_on_switch_reports_enabled(self, client, web_user, _catalog, db_session):
        from app.models.config import GlobalConfigORM
        s = db_session
        row = s.query(GlobalConfigORM).filter_by(key="payments.purchase.enabled").first()
        if row:
            row.value = "on"
        else:
            s.add(GlobalConfigORM(key="payments.purchase.enabled", value="on"))
        s.commit()

        r = client.get("/api/pay/skus", headers=_auth(web_user))
        assert r.json()["data"]["purchase_enabled"] is True

    def test_contract_expansion_planned_selling_points(self, client, web_user, _catalog):
        """s-pay-plans-picker：selling_points 下发 / planned 进目录不泄 SKU / retired 不返回 /
        tier_key 来自档行而非端点默认 / popular 取 sort 序确定性 / 契约只增不删。"""
        s = SessionLocal()
        try:
            pro = s.query(TierORM).filter_by(key="pro").first()
            pro.selling_points = '["AI 生成正文（流式）","设定与章纲融入 AI"]'
            max_t = TierORM(key="max", display_name="MAX", rank=30, status="planned",
                            selling_points='["含 PRO 全部功能"]')
            old = TierORM(key="legacy", display_name="旧档", rank=10, status="retired")
            alt = TierORM(key="alt", display_name="ALT", rank=25, status="live")
            s.add_all([max_t, old, alt])
            s.flush()
            # planned 档误配 on_sale SKU 反例：不得泄入目录
            s.add(SkuORM(sku_key="max_yearly_bad", tier_id=max_t.id, period="yearly",
                         period_days=365, base_price_fen=73000, discount_permille=800,
                         device_limit=10, on_sale=True, sort=9))
            s.add(SkuORM(sku_key="old_yearly", tier_id=old.id, period="yearly",
                         period_days=365, base_price_fen=100, discount_permille=1000,
                         device_limit=1, on_sale=True, sort=8))
            # 另一 live 档：tier_key 真实性 + popular sort 序确定性（sort=0 在 pro_yearly 前）
            s.add(SkuORM(sku_key="alt_yearly", tier_id=alt.id, period="yearly",
                         period_days=365, base_price_fen=50000, discount_permille=1000,
                         device_limit=3, on_sale=True, sort=0))
            s.commit()
        finally:
            s.close()

        r = client.get("/api/pay/skus", headers=_auth(web_user))
        data = r.json()["data"]
        tiers = {t["key"]: t for t in data["tiers"]}
        assert tiers["pro"]["selling_points"] == ["AI 生成正文（流式）", "设定与章纲融入 AI"]
        assert tiers["pro"]["is_live"] is True and tiers["pro"]["is_planned"] is False
        assert tiers["max"]["is_planned"] is True and tiers["max"]["is_live"] is False
        assert "legacy" not in tiers  # retired 档不返回
        assert tiers["alt"]["selling_points"] == []  # 未配置 → 空数组
        sku_keys = {x["sku_key"] for x in data["skus"]}
        assert "max_yearly_bad" not in sku_keys  # planned 档 on_sale SKU 不泄入
        assert "old_yearly" not in sku_keys  # retired 档 SKU 同步挡住
        alt_sku = next(x for x in data["skus"] if x["sku_key"] == "alt_yearly")
        assert alt_sku["tier_key"] == "alt"  # 来自档行富集，非端点 "pro" 硬默认
        assert data["popular_sku"] == "alt_yearly"  # sort 序（0）先于 pro_yearly（3）；不命中 planned
        # 契约只增不删：既有字段齐备
        for x in data["skus"]:
            assert {"sku_key", "tier_key", "period", "period_days", "base_price_fen",
                    "discount_display", "price_fen", "device_limit"} <= set(x)
        assert {"purchase_enabled", "agreement_version", "tiers", "skus", "popular_sku"} <= set(data)
        for t in data["tiers"]:
            assert {"key", "label", "is_live"} <= set(t)


class TestCreateOrder:
    def test_off_switch_rejects_4012(self, client, web_user, _catalog, _switch_off):
        r = client.post("/api/pay/orders", headers=_auth(web_user), json={
            "sku_key": "pro_yearly", "agreement_version": AGREEMENT_VERSION,
        })
        assert r.json()["code"] == 4012

    def test_rehearsal_rejects_outside_list(self, client, web_user, _catalog, _switch_rehearsal):
        r = client.post("/api/pay/orders", headers=_auth(web_user), json={
            "sku_key": "pro_yearly", "agreement_version": AGREEMENT_VERSION,
        })
        assert r.json()["code"] == 4012

    def test_rehearsal_allows_listed_user(self, client, db_session, _catalog, _switch_rehearsal):
        """名单内用户可下单（演练全链入口）。"""
        s = db_session
        uid = f"rh{datetime.now(UTC).timestamp():.0f}"
        password = "".join(("Pa", "ss-live-", "42"))
        r = client.post("/api/web/register", json={
            "username": uid, "password": password,
            "security_question": "q?", "security_answer": "a",
        })
        assert r.json()["code"] == 0, r.text
        token = r.json()["data"]["token"]
        # 挂到演练名单
        from app.models.config import GlobalConfigORM
        row = s.query(GlobalConfigORM).filter_by(key="payments.rehearsal.usernames").first()
        row.value = f"{row.value},{uid}"
        s.commit()

        resp = client.post("/api/pay/orders", headers={"Authorization": f"Bearer {token}"}, json={
            "sku_key": "pro_yearly", "agreement_version": AGREEMENT_VERSION,
        })
        body = resp.json()
        assert body["code"] == 0, body
        assert body["data"]["order_no"]
        assert body["data"]["amount_fen"] == 23920  # 29900 × 0.8 冻结
        assert body["data"]["code_url"]

    def test_agreement_stale_4005(self, client, web_user, _catalog, db_session):
        from app.models.config import GlobalConfigORM
        s = db_session
        s.merge(GlobalConfigORM(key="payments.purchase.enabled", value="on"))
        s.commit()
        r = client.post("/api/pay/orders", headers=_auth(web_user), json={
            "sku_key": "pro_yearly", "agreement_version": "v2099.01",
        })
        assert r.json()["code"] == 4005

    def test_unknown_sku_4002(self, client, web_user, db_session):
        from app.models.config import GlobalConfigORM
        s = db_session
        s.merge(GlobalConfigORM(key="payments.purchase.enabled", value="on"))
        s.commit()
        r = client.post("/api/pay/orders", headers=_auth(web_user), json={
            "sku_key": "ghost_sku", "agreement_version": AGREEMENT_VERSION,
        })
        assert r.json()["code"] == 4002


class TestListOrders:
    def test_empty_list(self, client, web_user):
        r = client.get("/api/pay/orders", headers=_auth(web_user))
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["items"] == []

    def test_requires_auth(self, client):
        r = client.get("/api/pay/orders")
        assert r.json()["code"] == 4001


def _seed_order(db_session, web_user: dict, order_no: str, status: str, created_at: datetime) -> None:
    """直接播种订单行（列表筛选/分页测试用；绕过购买开关）。"""
    from app.infrastructure.repositories.factory import user_repo
    from app.models.payments import OrderORM
    s = db_session
    uid = user_repo(s).get_id(web_user["username"])
    s.add(OrderORM(
        order_no=order_no, user_id=uid, sku_id=1, sku_snapshot={"tier_key": "pro"},
        amount_fen=7200, status=status, agreement_version=AGREEMENT_VERSION,
        agreed_at=created_at, created_at=created_at,
    ))
    s.commit()


class TestListOrdersFilter:
    """orders-status-tabs：status 白名单筛选 + 真分页 + total 全量计数口径。"""

    @pytest.fixture
    def _five_orders(self, client, web_user, db_session):
        from uuid import uuid4
        tag = uuid4().hex[:6].upper()  # 库为会话级共享，单号带随机段防跨用例撞唯一约束
        for i, st in enumerate(["pending", "paid", "fulfilled", "refunded", "closed"]):
            _seed_order(db_session, web_user, f"S-FILTER-{tag}-{i:02d}", st,
                        datetime(2026, 9, 1, 10, i, 0))
        yield

    def test_no_param_returns_all_with_total(self, client, web_user, _five_orders):
        r = client.get("/api/pay/orders", headers=_auth(web_user))
        body = r.json()["data"]
        assert body["total"] == 5
        assert [o["status"] for o in body["items"]] == [
            "closed", "refunded", "fulfilled", "paid", "pending"]  # 创建时间倒序

    def test_status_filter_whitelist(self, client, web_user, _five_orders):
        r = client.get("/api/pay/orders?status=paid,fulfilled", headers=_auth(web_user))
        body = r.json()["data"]
        assert body["total"] == 2
        assert {o["status"] for o in body["items"]} == {"paid", "fulfilled"}

    def test_unknown_value_mixed_is_ignored(self, client, web_user, _five_orders):
        r = client.get("/api/pay/orders?status=paid,foo", headers=_auth(web_user))
        body = r.json()["data"]
        assert body["total"] == 1
        assert body["items"][0]["status"] == "paid"

    def test_all_unknown_returns_empty_not_error(self, client, web_user, _five_orders):
        r = client.get("/api/pay/orders?status=foo,bar", headers=_auth(web_user))
        body = r.json()
        assert body["code"] == 0
        assert body["data"] == {"items": [], "total": 0}

    def test_pagination_slice_keeps_total(self, client, web_user, _five_orders):
        r = client.get("/api/pay/orders?page=2&page_size=2", headers=_auth(web_user))
        body = r.json()["data"]
        assert body["total"] == 5
        assert len(body["items"]) == 2
        # 第 2 页 = 倒序第 3、4 条（fulfilled 10:02 / paid 10:01），无重复
        assert {o["status"] for o in body["items"]} == {"fulfilled", "paid"}


class TestFulfillActivateFlow:
    """到货-激活两段式全链（sqlite 端到端）：下单→D1 注入支付→查单发货→激活。"""

    def _switch_on(self, db_session):
        from app.models.config import GlobalConfigORM
        s = db_session
        s.merge(GlobalConfigORM(key="payments.purchase.enabled", value="on"))
        s.commit()

    def test_order_inject_query_activate(self, client, web_user, _catalog, db_session, admin_token):
        self._switch_on(db_session)
        auth = _auth(web_user)
        # 下单
        r = client.post("/api/pay/orders", headers=auth, json={
            "sku_key": "pro_yearly", "agreement_version": AGREEMENT_VERSION})
        body = r.json()
        assert body["code"] == 0, body
        order_no = body["data"]["order_no"]
        # D1 注入支付（mock 网关标记+发货，含 codes 台账行）
        r = client.post("/api/dev/pay/inject-payment", headers={"X-Admin-Token": admin_token},
                        json={"order_no": order_no})
        assert r.json()["code"] == 0, r.text
        assert r.json()["data"]["status"] == "fulfilled"
        # 激活
        r = client.post("/api/pay/codes/activate", headers=auth, json={"order_no": order_no})
        body = r.json()
        assert body["code"] == 0, body
        assert body["data"]["tier"] == "pro"
        assert body["data"]["expires_at"] > body["data"]["grant_start"]
        # 重复激活 → NotActivatableError（DomainError 家族=4012 拒绝）
        r = client.post("/api/pay/codes/activate", headers=auth, json={"order_no": order_no})
        assert r.json()["code"] == 4012
        # 台账行已 active 且带 grant_start/order_id
        from app.models.code import ActivationCodeORM
        from app.models.payments import OrderORM
        s = db_session
        row = s.query(ActivationCodeORM).filter(
            ActivationCodeORM.code_id == f"O-{order_no}").one()
        assert row.status == "active"
        assert row.grant_start is not None and row.order_id is not None
        order_row = s.query(OrderORM).filter(OrderORM.order_no == order_no).one()
        assert row.order_id == order_row.id
        # license 汇总出现 pro
        r = client.get("/api/pay/license", headers=auth)
        assert r.json()["data"]["tier"] == "pro"
        # 订单详情 grant 快照折出已激活
        r = client.get(f"/api/pay/orders/{order_no}", headers=auth)
        grant = r.json()["data"]["fulfillment"]
        assert grant["status"] == "active"
        assert grant["activated_at"] != "" and grant["expires_at"] != ""


class TestLicenseGrants:
    """套餐明细分页接口（license-grants-pagination）+ license 聚合视图瘦身口径：
    名下全部台账行入明细（2026-10-03 拍板：激活码兑换行与订单行同列，unused 恒排除）
    + order_no 映射 + status 白名单 + created_at 同口径。"""

    def _switch_on(self, db_session):
        from app.models.config import GlobalConfigORM
        db_session.merge(GlobalConfigORM(key="payments.purchase.enabled", value="on"))
        db_session.commit()

    def _buy_and_fulfill(self, client, web_user, db_session, admin_token, sku_key="pro_yearly"):
        """下单+注入支付，返回 order_no（_catalog 只有 pro_yearly 可买）。"""
        auth = _auth(web_user)
        r = client.post("/api/pay/orders", headers=auth, json={
            "sku_key": sku_key, "agreement_version": AGREEMENT_VERSION})
        order_no = r.json()["data"]["order_no"]
        r = client.post("/api/dev/pay/inject-payment", headers={"X-Admin-Token": admin_token},
                        json={"order_no": order_no})
        assert r.json()["code"] == 0, r.text
        return order_no

    def test_license_view_slimmed_and_grants_endpoint(self, client, web_user, _catalog, db_session, admin_token):
        self._switch_on(db_session)
        auth = _auth(web_user)
        order_no = self._buy_and_fulfill(client, web_user, db_session, admin_token)

        # license 瘦身：聚合视图无 grants 内嵌，只有行计数（与「全部」total 同口径；
        # 注册即送的 trial 已激活=active，计入行数——2026-10-03 起手工来源行同列入明细）
        d = client.get("/api/pay/license", headers=auth).json()["data"]
        assert "grants" not in d
        assert d["code_count"] == 2  # trial + 订单行
        assert d["pending_count"] == 1

        # 明细端点：trial（source=admin）与订单行同列，created_at 倒序=最新订单在前
        r = client.get("/api/pay/license/codes", headers=auth)
        assert r.json()["code"] == 0
        body = r.json()["data"]
        assert body["total"] == 2
        g = body["items"][0]
        assert g["order_no"] == order_no
        assert g["source"] == "order"
        assert g["status"] == "pending_activation"
        trial = body["items"][1]
        assert trial["tier"] == "trial" and trial["source"] == "admin" and trial["order_no"] == ""
        assert set(g) == {"code_id", "order_no", "source", "tier", "duration_days", "status",
                          "activated_at", "expires_at", "grant_start"}

        # 状态筛选
        assert client.get("/api/pay/license/codes?status=pending_activation",
                          headers=auth).json()["data"]["total"] == 1
        assert client.get("/api/pay/license/codes?status=active",
                          headers=auth).json()["data"]["total"] == 1  # trial

        # 未知值不致命：全未知=空列表+0；混合=未知忽略
        r = client.get("/api/pay/license/codes?status=bogus", headers=auth)
        assert r.json()["data"] == {"items": [], "total": 0}
        r = client.get("/api/pay/license/codes?status=pending_activation,bogus", headers=auth)
        assert r.json()["data"]["total"] == 1

        # 未登录照旧拒绝
        assert client.get("/api/pay/license/codes").json()["code"] == 4001

    def test_grants_pagination_created_desc(self, client, web_user, _catalog, db_session, admin_token):
        """分页口径：created_at 倒序（裁定不做状态分组）、total 不随翻页变。"""
        self._switch_on(db_session)
        auth = _auth(web_user)
        nos = [self._buy_and_fulfill(client, web_user, db_session, admin_token) for _ in range(3)]

        r = client.get("/api/pay/license/codes?page=1&page_size=2", headers=auth)
        body = r.json()["data"]
        assert body["total"] == 4  # 3 订单行 + 注册 trial（已激活非 unused）
        assert len(body["items"]) == 2
        assert body["items"][0]["order_no"] == nos[-1]  # 最新单在前

        r = client.get("/api/pay/license/codes?page=2&page_size=2", headers=auth)
        body = r.json()["data"]
        assert body["total"] == 4
        assert [i["order_no"] for i in body["items"]] == [nos[0], ""]  # 剩最旧一行 + trial

        # 分页钳制：page_size 上限 100、page 下限 1
        r = client.get("/api/pay/license/codes?page=-1&page_size=9999", headers=auth)
        assert r.json()["code"] == 0 and r.json()["data"]["total"] == 4

    def test_grants_listing_and_manual_code_excluded(self, client, web_user, _catalog, db_session, admin_token):
        self._switch_on(db_session)
        auth = _auth(web_user)
        order_no = self._buy_and_fulfill(client, web_user, db_session, admin_token)

        # 模拟退款收回 → 已收回灰显仍在明细、待激活计数归零
        from app.models.code import ActivationCodeORM
        s = db_session
        row = s.query(ActivationCodeORM).filter_by(code_id=f"O-{order_no}").one()
        row.status = "revoked"
        s.commit()

        d = client.get("/api/pay/license", headers=auth).json()["data"]
        assert d["code_count"] == 2 and d["pending_count"] == 0  # trial + 已收回订单行
        body = client.get("/api/pay/license/codes?status=revoked", headers=auth).json()["data"]
        assert body["total"] == 1 and body["items"][0]["status"] == "revoked"

    def test_unused_manual_code_does_not_inflate_tier(self, client, web_user, _catalog, db_session, admin_token):
        """unused 手工码不参与档位归属也不进明细（非 unused 才是套餐）：
        active pro + 未激活手工 max 码 → 档位头仍为 pro，max 码明细与计数双排除。"""
        self._switch_on(db_session)
        auth = _auth(web_user)
        order_no = self._buy_and_fulfill(client, web_user, db_session, admin_token)
        # 激活 pro（成为 active）+ 手工发一张未激活 max 码
        r = client.post("/api/pay/codes/activate", headers=auth, json={"order_no": order_no})
        assert r.json()["code"] == 0, r.text

        from app.models.code import ActivationCodeORM
        from app.models.user import UserORM
        s = db_session
        uid = s.query(UserORM).filter_by(username=web_user["username"]).one().id
        s.add(ActivationCodeORM(
            code_id="AC-MANUAL-MAX-TEST", tier="max", duration_days=365, status="unused",
            user_id=uid, created_by="admin",
        ))
        s.commit()

        d = client.get("/api/pay/license", headers=auth).json()["data"]
        assert d["tier"] == "pro"  # 未激活的 max 码不抬档
        body = client.get("/api/pay/license/codes", headers=auth).json()["data"]
        assert all(g["code_id"] != "AC-MANUAL-MAX-TEST" for g in body["items"])  # unused 不进明细
        assert d["code_count"] == 2  # 计数同口径：unused 不计入（trial + 订单行）

    def test_grant_created_at_matches_paid_at(self, client, web_user, _catalog, db_session, admin_token):
        """台账行 created_at 显式 UTC 口径：与订单 paid_at 秒级同（回归：列默认快 8h）。"""
        self._switch_on(db_session)
        auth = _auth(web_user)
        r = client.post("/api/pay/orders", headers=auth, json={
            "sku_key": "pro_yearly", "agreement_version": AGREEMENT_VERSION})
        order_no = r.json()["data"]["order_no"]
        r = client.post("/api/dev/pay/inject-payment", headers={"X-Admin-Token": admin_token},
                        json={"order_no": order_no})
        assert r.json()["code"] == 0, r.text

        from datetime import UTC

        from app.models.code import ActivationCodeORM
        from app.models.payments import OrderORM
        s = db_session
        o = s.query(OrderORM).filter_by(order_no=order_no).one()
        c = s.query(ActivationCodeORM).filter_by(code_id=f"O-{order_no}").one()
        paid = o.paid_at if o.paid_at.tzinfo is None else o.paid_at.astimezone(UTC).replace(tzinfo=None)
        created = c.created_at if c.created_at.tzinfo is None else c.created_at.astimezone(UTC).replace(tzinfo=None)
        assert abs((created - paid).total_seconds()) < 60


class TestOrderDetail:
    """W4 订单详情（Z.5）：pending 倒计时 + 时间列三形态归一。

    回归背景（2026-09-01 线上）：pg_http 行 created_at 是 ISO 字符串，
    _order_to_detail 直接做 datetime-str 减法 → 订单详情 500。
    """

    def _switch_on(self, db_session):
        from app.models.config import GlobalConfigORM
        db_session.merge(GlobalConfigORM(key="payments.purchase.enabled", value="on"))
        db_session.commit()

    def test_pending_detail_countdown(self, client, web_user, _catalog, db_session):
        """sqlite e2e：下单后 GET 详情，pending 订单带支付倒计时。"""
        self._switch_on(db_session)
        auth = _auth(web_user)
        r = client.post("/api/pay/orders", headers=auth, json={
            "sku_key": "pro_yearly", "agreement_version": AGREEMENT_VERSION})
        order_no = r.json()["data"]["order_no"]

        r = client.get(f"/api/pay/orders/{order_no}", headers=auth)
        body = r.json()
        assert body["code"] == 0, body
        assert body["data"]["status"] == "pending"
        assert 0 < body["data"]["remaining_pay_seconds"] <= 900
        # 未到货：grant 快照为空，到货/退款时间列为空串
        assert body["data"]["fulfillment"] is None
        assert body["data"]["fulfilled_at"] == ""
        assert body["data"]["refund_requested_at"] == ""

    def test_refunded_detail_shows_arrival_and_fulfillment(self, client, web_user, _catalog, db_session, admin_token):
        """已退款单详情：fulfilled_at/refund_requested_at 有值、fulfillment 折出已收回（时间线 '—' 回归）。"""
        self._switch_on(db_session)
        auth = _auth(web_user)
        r = client.post("/api/pay/orders", headers=auth, json={
            "sku_key": "pro_yearly", "agreement_version": AGREEMENT_VERSION})
        order_no = r.json()["data"]["order_no"]
        r = client.post("/api/dev/pay/inject-payment", headers={"X-Admin-Token": admin_token},
                        json={"order_no": order_no})
        assert r.json()["code"] == 0, r.text

        # 模拟退款完成（未激活全额退路径：台账行 pending_activation→revoked）
        from app.models.code import ActivationCodeORM
        from app.models.payments import OrderORM
        s = db_session
        now = datetime.now(UTC).replace(tzinfo=None)
        o = s.query(OrderORM).filter_by(order_no=order_no).one()
        o.status = "refunded"
        o.refund_status = "succeeded"
        o.refund_requested_at = now
        o.refunded_at = now
        o.refund_amount_fen = o.amount_fen
        c = s.query(ActivationCodeORM).filter_by(code_id=f"O-{order_no}").one()
        c.status = "revoked"
        s.commit()

        r = client.get(f"/api/pay/orders/{order_no}", headers=auth)
        assert r.json()["code"] == 0, r.text
        d = r.json()["data"]
        assert d["fulfilled_at"] != ""
        assert d["refund_requested_at"] != ""
        assert d["refunded_at"] != ""
        assert d["fulfillment"]["status"] == "revoked"
        assert d["fulfillment"]["activated_at"] == ""

    @pytest.mark.parametrize("form", ["pg_http_str", "sqlite_naive", "aware"])
    def test_row_datetime_forms(self, form):
        """订单行时间列三种形态（ISO 字符串/naive/aware）下倒计时均可计算。"""
        from datetime import UTC, timedelta

        from app.interfaces.web_api.payments import _order_to_detail

        created = datetime.now(UTC) - timedelta(seconds=100)
        cooldown_ends = datetime.now(UTC) + timedelta(seconds=120)
        if form == "pg_http_str":
            created_at, cooldown_ends_at = created.isoformat(), cooldown_ends.isoformat()
        elif form == "sqlite_naive":
            created_at, cooldown_ends_at = created.replace(tzinfo=None), cooldown_ends.replace(tzinfo=None)
        else:
            created_at, cooldown_ends_at = created, cooldown_ends

        order = {
            "order_no": "S-TEST", "status": "pending", "created_at": created_at,
            "refund_status": "cooldown", "cooldown_ends_at": cooldown_ends_at,
        }
        detail = _order_to_detail(order)
        assert 700 < detail["remaining_pay_seconds"] <= 800  # 900 - ~100s
        assert 0 < detail["refund"]["cooldown_remaining_seconds"] <= 180
