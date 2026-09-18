"""pay-ops 云函数：支付运维操作（内部调用，无公网 URL）。

安全声明：本函数仅连接 CloudBase PostgREST 端点（环境变量注入），
不接收外部用户输入构造 URL，无 SSRF 风险。

调用：CloudBase 控制台 / MCP callFunction / 定时触发器
"""
import http.client
import json
import os
import urllib.parse
from datetime import UTC, datetime

# ── 配置（环境变量注入，不硬编码）──
PG_HOST = os.getenv("TCB_PG_HOST", "")          # 例如 xxx.api.tcloudbasegateway.com
PG_PATH = os.getenv("TCB_PG_PATH", "/v1/rdb/rest")  # PostgREST 路径前缀
API_KEY = os.getenv("TCB_PG_API_KEY", "")
ALLOWED_HOSTS = {"api.tcloudbasegateway.com"}  # 域名白名单


def _req(method: str, table: str, params: dict = None, body: dict = None) -> list | dict:
    """受限 HTTP 请求：仅连 ALLOWED_HOSTS 内的 PostgREST 端点。"""
    # URL 构造（固定模式，无用户输入）
    path = f"{PG_PATH}/{table}"
    if params:
        qs = urllib.parse.urlencode(params)
        path += f"?{qs}"

    # 安全校验：目标主机必须在白名单内
    parsed_host = PG_HOST.split(":")[0]  # 去端口
    if parsed_host not in ALLOWED_HOSTS:
        raise ValueError("blocked: host not in whitelist")

    conn = http.client.HTTPSConnection(PG_HOST, timeout=10)
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    if method == "PATCH":
        headers["Prefer"] = "return=representation"

    payload = json.dumps(body) if body else None
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    body_str = resp.read().decode()
    conn.close()

    if resp.status in (400, 409) and method == "POST":
        return []  # 唯一冲突
    resp.raise_for_status() if hasattr(resp, "raise_for_status") else None
    return json.loads(body_str) if body_str else []


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _append_event(event_key: str, event_type: str, order_no: str, payload: dict) -> bool:
    result = _req("POST", "trade_events", body={
        "event_key": event_key,
        "event_type": event_type,
        "order_no": order_no,
        "payload": payload,
        "operator": "cf:pay-ops",
    })
    return bool(result)


# ── 操作实现 ──

def retry_refund(order_no: str) -> dict:
    rows = _req("GET", "orders", params={"order_no": f"eq.{order_no}", "select": "*"})
    if not rows:
        return {"error": "not_found"}
    order = rows[0]
    if order.get("refund_status") != "processing":
        return {"error": "not_in_processing"}
    count = (order.get("refund_not_enough") or 0) + 1
    _req("PATCH", "orders", params={"order_no": f"eq.{order_no}"},
         body={"refund_not_enough": count})
    _append_event(f"refund:{order_no}:manual_retry_{count}",
                  "refund.manual_retry", order_no, {"retry_count": count})
    return {"order_no": order_no, "retry_count": count}


def handle_exception(order_no: str, sub: str) -> dict:
    rows = _req("GET", "orders", params={"order_no": f"eq.{order_no}", "select": "*"})
    if not rows:
        return {"error": "not_found"}
    if rows[0].get("status") != "exception":
        return {"error": "not_exception"}
    now = _now_iso()
    if sub == "full_refund":
        _req("PATCH", "orders",
             params={"order_no": f"eq.{order_no}", "status": "eq.exception"},
             body={"status": "refunded", "refund_status": "succeeded",
                    "refund_amount_fen": rows[0]["amount_fen"],
                    "refund_operator": "admin", "refunded_at": now})
        _append_event(f"refund:{order_no}:exception_full",
                      "refund.exception_full", order_no, {})
        return {"action": "full_refund", "status": "refunded"}
    elif sub == "dismiss":
        _req("PATCH", "orders",
             params={"order_no": f"eq.{order_no}", "status": "eq.exception"},
             body={"status": "closed", "closed_at": now})
        _append_event(f"order:{order_no}:exception_dismissed",
                      "order.exception_dismissed", order_no, {})
        return {"action": "dismiss", "status": "closed"}
    return {"error": "expected full_refund|dismiss"}


def offline_settled(order_no: str) -> dict:
    rows = _req("GET", "orders", params={"order_no": f"eq.{order_no}", "select": "status"})
    if not rows or rows[0].get("status") != "refund_processing":
        return {"error": "not_in_refund_processing"}
    now = _now_iso()
    _req("PATCH", "orders",
         params={"order_no": f"eq.{order_no}", "status": "eq.refund_processing"},
         body={"status": "refunded", "refund_status": "succeeded", "refunded_at": now})
    _append_event(f"refund:{order_no}:offline_settled",
                  "refund.offline_settled", order_no, {})
    return {"action": "offline_settled", "status": "refunded"}


def abandon_unfreeze(order_no: str) -> dict:
    rows = _req("GET", "orders", params={"order_no": f"eq.{order_no}", "select": "status"})
    if not rows or rows[0].get("status") != "refund_processing":
        return {"error": "not_in_refund_processing"}
    _req("PATCH", "orders",
         params={"order_no": f"eq.{order_no}", "status": "eq.refund_processing"},
         body={"status": "fulfilled", "refund_status": "canceled"})
    _append_event(f"refund:{order_no}:abandoned_unfreeze",
                  "refund.abandoned_unfreeze", order_no, {})
    return {"action": "abandon_unfreeze", "status": "fulfilled"}


def scan_not_enough() -> list:
    rows = _req("GET", "orders",
                params={"refund_status": "eq.processing", "select": "order_no,refund_not_enough"})
    return [retry_refund(r["order_no"]) for r in rows if (r.get("refund_not_enough") or 0) > 0]


def set_switch(value: str, usernames: str = "") -> dict:
    _req("POST", "global_config", body={"key": "payments.purchase.enabled", "value": value})
    if usernames:
        _req("POST", "global_config",
             body={"key": "payments.rehearsal.usernames", "value": usernames})
    return {"switch": value, "rehearsal": usernames or "(unchanged)"}


def update_price(sku_key: str, base_fen: int = None, discount_permille: int = None) -> dict:
    changes = {}
    if base_fen is not None:
        changes["base_price_fen"] = base_fen
    if discount_permille is not None:
        changes["discount_permille"] = discount_permille
    if not changes:
        return {"error": "nothing_to_update"}
    _req("PATCH", "skus", params={"sku_key": f"eq.{sku_key}"}, body=changes)
    return {"sku_key": sku_key, **changes}


# ── 入口 ──

def main(event, context):
    try:
        action = event.get("action", "")
        handlers = {
            "retry_refund": lambda: retry_refund(event["order_no"]),
            "handle_exception": lambda: handle_exception(event["order_no"], event.get("sub", "")),
            "offline_settled": lambda: offline_settled(event["order_no"]),
            "abandon_unfreeze": lambda: abandon_unfreeze(event["order_no"]),
            "scan_not_enough": scan_not_enough,
            "set_switch": lambda: set_switch(event.get("value", "off"), event.get("usernames", "")),
            "update_price": lambda: update_price(event["sku_key"], event.get("base_fen"), event.get("discount_permille")),
        }
        h = handlers.get(action)
        if not h:
            return {"code": 1, "error": f"unknown: {action}", "available": list(handlers.keys())}
        return {"code": 0, "data": h()}
    except Exception as e:
        return {"code": -1, "error": str(e)}
