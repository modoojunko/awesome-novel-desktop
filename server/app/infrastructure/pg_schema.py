"""生产 PG schema 自检：必需表/列清单单一事实源 + 探测编排。

清单按仓储层（pg_http/*_repo.py 与 payments_repo.py）实际读写的表与列人工维护；
每列标注类型族：
- "text"  字符串语义列：存在性之外再用 filter 哨兵验证类型（2026-08-31 事故实证：
          select 存在性探测检不出 bigint→varchar 漂移，device_registry.user_id 即此形态）
- "typed" 数值/时间/布尔/JSON 列：仅做存在性探测（非文本列之间的类型漂移为本方案盲区，见 design D7）

EXPECTED_DEFAULTS（design D8）：语义承重的 server_default 对拍基准（稀疏声明，只列
代码逻辑依赖其默认值的列；func.now() 类时间戳默认不纳入）。比对数据源为网关根
OpenAPI（GET 端点根路径返回 swagger definitions，列 default 字段实测可用）。
此后新增表/列的 feature change 必须同 PR 更新两份清单（design D2 约定）。
"""
from __future__ import annotations

import logging

import httpx

from app.infrastructure.repositories.pg_http.client import PgRestClient

logger = logging.getLogger("app")

# (列名, 类型族)；类型族仅 "text" / "typed" 两种
REQUIRED: dict[str, tuple[tuple[str, str], ...]] = {
    "users": (
        ("id", "typed"), ("username", "text"), ("password_hash", "text"),
        ("security_question", "text"), ("security_answer_hash", "text"),
        ("status", "text"), ("theme", "text"), ("created_at", "typed"),
        ("deletion_status", "text"), ("deletion_requested_at", "typed"),
        ("deletion_deadline", "typed"), ("deletion_waive_assets", "typed"),
    ),
    "codes": (
        ("code_id", "text"), ("tier", "text"), ("duration_days", "typed"),
        ("status", "text"), ("user_id", "typed"), ("bound_username", "text"),
        ("order_id", "typed"), ("grant_start", "typed"), ("status_detail", "text"),
        ("activated_at", "typed"), ("expires_at", "typed"),
        ("created_at", "typed"), ("created_by", "text"), ("refund_requested_at", "typed"),
        ("source", "text"),
    ),
    "device_registry": (
        ("id", "text"), ("user_id", "text"), ("fingerprint", "text"),
        ("hostname", "text"), ("os", "text"), ("os_arch", "text"),
        ("last_active_at", "typed"), ("bound_at", "typed"),
        ("created_at", "typed"), ("updated_at", "typed"),
    ),
    "device_grants": (
        ("pc_hash", "text"), ("user_id", "typed"), ("token", "text"),
        ("enrolled", "typed"), ("fingerprint", "text"),
    ),
    "global_config": (("key", "text"), ("value", "text")),
    # ── payments 域（payments_repo.py，pg_http 同通道；2026-09-01 补录）──
    "tiers": (
        ("id", "typed"), ("key", "text"), ("display_name", "text"),
        ("rank", "typed"), ("selling_points", "text"), ("entitlement", "text"),
        ("status", "text"),
        ("created_at", "typed"), ("updated_at", "typed"),
    ),
    "skus": (
        ("id", "typed"), ("sku_key", "text"), ("tier_id", "typed"),
        ("period", "text"), ("period_days", "typed"), ("base_price_fen", "typed"),
        ("discount_permille", "typed"), ("device_limit", "typed"),
        ("on_sale", "typed"), ("sort", "typed"),
        ("created_at", "typed"), ("updated_at", "typed"),
    ),
    "orders": (
        ("id", "typed"), ("order_no", "text"), ("user_id", "typed"),
        ("sku_id", "typed"), ("sku_snapshot", "typed"), ("amount_fen", "typed"),
        ("status", "text"), ("prepay_status", "text"), ("code_url", "text"),
        ("attach_sent", "text"), ("transaction_id", "text"), ("payer_openid", "text"),
        ("channel", "text"), ("agreement_version", "text"), ("agreed_at", "typed"),
        ("refund_status", "text"), ("refund_amount_fen", "typed"),
        ("refund_reason", "text"), ("refund_operator", "text"), ("refund_wx_id", "text"),
        ("refund_not_enough", "typed"), ("refund_requested_at", "typed"),
        ("refund_accepted_at", "typed"), ("created_at", "typed"), ("paid_at", "typed"),
        ("fulfilled_at", "typed"), ("refunded_at", "typed"), ("closed_at", "typed"),
        ("cooldown_ends_at", "typed"), ("updated_at", "typed"),
    ),
    "trade_events": (
        ("event_id", "typed"), ("event_key", "text"), ("event_type", "text"),
        ("order_no", "text"), ("refund_no", "text"), ("payload", "typed"),
        ("operator", "text"), ("created_at", "typed"),
    ),
    "reconciliation_reports": (
        ("bill_date", "typed"), ("internal_count", "typed"), ("wx_count", "typed"),
        ("internal_total_fen", "typed"), ("wx_total_fen", "typed"),
        ("refund_count", "typed"), ("refund_total_fen", "typed"),
        ("mismatch_detail", "typed"), ("status", "text"), ("created_at", "typed"),
    ),
    "invoices": (
        ("invoice_id", "typed"), ("order_id", "typed"), ("refund_id", "typed"),
        ("kind", "text"), ("title", "typed"), ("amount_fen", "typed"),
        ("status", "text"), ("invoice_no", "text"), ("red_invoice_no", "text"),
        ("issued_at", "typed"), ("created_at", "typed"), ("updated_at", "typed"),
    ),
}

# 语义承重的 server_default 对拍（D8）：库内默认值与代码声明不一致时按缺失处理——
# 实证形态：deletion_status 无 DEFAULT 时新注册行落 NULL，注销 CAS（eq.'正常'）
# 永远匹配不上。值用归一化字符串（bool→"true"/"false"，int→str，str 原样）。
EXPECTED_DEFAULTS: dict[str, dict[str, str]] = {
    "users": {
        "status": "active", "theme": "", "security_question": "",
        "security_answer_hash": "", "deletion_status": "正常",
        "deletion_waive_assets": "false",
    },
    "codes": {
        "status": "unused", "source": "admin",
        "status_detail": "unused", "created_by": "",
    },
    "device_registry": {
        "fingerprint": "", "hostname": "", "os": "", "os_arch": "",
    },
    "device_grants": {"enrolled": "0", "fingerprint": ""},
    "tiers": {"selling_points": "[]", "entitlement": "{}", "status": "live"},
    "skus": {
        "discount_permille": "1000", "device_limit": "1",
        "on_sale": "true", "sort": "0",
    },
    "orders": {
        "status": "pending", "prepay_status": "none", "channel": "wxpay",
        "refund_reason": "", "refund_not_enough": "0",
    },
    "reconciliation_reports": {"status": "pending"},
    "invoices": {"status": "requested"},
}

_PROBE_SENTINEL = "__pg_schema_probe__"


def _norm_default(value) -> str | None:
    """OpenAPI default 值 → 归一化字符串；缺失（键不存在/null）→ None。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _audit_defaults(defs: dict, mismatch: list[str]) -> None:
    """比对 EXPECTED_DEFAULTS 与网关 OpenAPI definitions；不一致记入 mismatch。"""
    for table, cols in EXPECTED_DEFAULTS.items():
        props = (defs.get(table) or {}).get("properties") or {}
        for col, want in cols.items():
            prop = props.get(col)
            if prop is None:
                continue  # 缺列由存在性探测负责，此处不重复记
            actual = _norm_default(prop.get("default"))
            if actual == want:
                continue
            if actual is None and want == "":
                continue  # 空串默认在元数据里可能缺省渲染
            mismatch.append(f"{table}.{col}#default({want})")


def _check_table(client: PgRestClient, table: str, cols: tuple[tuple[str, str], ...],
                 missing: list[str], probe_failed: list[str]) -> None:
    """单表探测：存在性（批量+缺失复探）→ text 列哨兵类型探测。异常只记账不抛。"""
    try:
        status, code, table_missing = client.probe_columns(table, [name for name, _ in cols])
    except httpx.TransportError:
        probe_failed.append(table)
        return
    if status == 404:
        missing.append(table)
        return
    if status == 400:
        # 表存在但批量 select 撞未知列（PGRST204）→ 复探结果即缺失清单；
        # 复探后仍无缺失属矛盾态（400 必因缺列），兜底记探测失败
        if table_missing:
            missing.extend(table_missing)
        else:
            probe_failed.append(table)
        return
    if status != 200:
        probe_failed.append(table)
        return
    for name, kind in cols:
        if kind != "text":
            continue
        try:
            col_status, code = client.probe_type(table, name, _PROBE_SENTINEL)
        except httpx.TransportError:
            probe_failed.append(f"{table}.{name}")
            continue
        if col_status == 400 and ("22P02" in code or "PGRST" in code or "42703" in code):
            # 22P02=类型不符（如 bigint 列收到文本哨兵）；PGRST204/42703=缺列
            missing.append(f"{table}.{name}")
        elif col_status != 200:
            probe_failed.append(f"{table}.{name}")


def probe_all(client: PgRestClient) -> tuple[list[str], list[str], list[str]]:
    """探测全部必需表/列，返回 (missing, probe_failed, mismatch)。

    门禁与启动自检共用的判定核心：missing=缺表/缺列/类型漂移；
    probe_failed=探测自身失败（网络/元数据不可得）；mismatch=server_default 漂移。
    """
    missing: list[str] = []
    probe_failed: list[str] = []
    for table, cols in REQUIRED.items():
        _check_table(client, table, cols, missing, probe_failed)

    mismatch: list[str] = []
    try:
        defs = client.describe()
    except httpx.TransportError:
        defs = None
    if defs is None:
        probe_failed.append("openapi")
    else:
        _audit_defaults(defs, mismatch)
    return missing, probe_failed, mismatch


def run_schema_check(client: PgRestClient) -> None:
    """探测全部必需表/列，聚合单条日志（design D3 契约）。绝不抛异常。"""
    missing, probe_failed, mismatch = probe_all(client)

    if missing or probe_failed or mismatch:
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if mismatch:
            detail.append("mismatch=" + ",".join(mismatch))
        if probe_failed:
            detail.append("probe_failed=" + ",".join(probe_failed))
        logger.warning("event=app.schema_check result=fail %s", " ".join(detail))
    else:
        logger.info(
            "event=app.schema_check result=ok tables=%d columns=%d",
            len(REQUIRED), sum(len(cols) for cols in REQUIRED.values()),
        )
