"""WechatPayGateway：微信支付 APIv3 适配层（s-pay-wechat-gateway）。

实现 PaymentGateway 协议全部 6 方法，微信语义 → 领域结果的归一化要点
（与官方文档逐条核对过的口径，详见 change design.md §2）：

- 下单带 ``time_expire``（RFC3339 北京时区）与本地订单 TTL（15 分钟）对齐，
  微信侧原生截断支付窗口，消除「本地已过期、关单未执行前仍可付款」竞态
- 关单先查单确认未付（官方查询接口使用时机明文）；403 ``ORDERPAID`` →
  ``already_paid``（官方原话「请当作已支付的正常交易」）；已关闭类返回 →
  幂等成功；下单后 5 分钟内微信拒绝关单（官方最短间隔，TTL 15 分钟满足）
- 查单 ``REFUND``（转入退款）显式归一，防对账误判 UNKNOWN
- 退款受理≠成功；请求带 ``notify_url`` 开通退款回调（漏传则只剩查询兜底）；
  错误分类：FREQUENCY_LIMITED/ORDER_NOT_READY → retryable（原退款单号间隔
  重试），NOT_ENOUGH/USER_ACCOUNT_ABNORMAL → manual（告警转人工不空转）
- 账单 ``tradebill`` 接口 ALL 与 REFUND 两张分下（退款明细不混在 ALL），
  CSV 逗号分隔 + 剥反引号前缀 + 金额元→分换算 + 下载内容 SHA1 与申请接口
  返回的 hash_value 比对；download_url 仅 5 分钟有效即取即下

不让 SDK/网络异常穿透应用层：所有调用点捕获后归一为领域结果；
仅 download_bill 允许抛错（T4 上层有重试+error 报告兜底，静默空列表
反而会把下载失败伪装成对账平衡）。
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import requests

from app.application.payments.create_order import ORDER_TTL_SECONDS
from app.config import settings
from app.infrastructure.payments.gateway import (
    BillLine,
    CloseResult,
    PaymentResult,
    PaymentStatus,
    QueryResult,
    RefundGatewayResult,
    RefundQueryResult,
    RefundStatus,
)

logger = logging.getLogger("app.payments")

_BJ = timezone(timedelta(hours=8))

# trade_state 归一（官方枚举：SUCCESS/REFUND/NOTPAY/CLOSED/REVOKED/USERPAYING/
# PAYERROR/ACCEPT；USERPAYING/ACCEPT 属刷卡与代扣场景，Native 不会出现 → UNKNOWN）
_PAY_STATUS_MAP = {
    "SUCCESS": PaymentStatus.SUCCESS,
    "NOTPAY": PaymentStatus.NOTPAY,
    "CLOSED": PaymentStatus.CLOSED,
    "REFUND": PaymentStatus.REFUND,
    "REVOKED": PaymentStatus.PAYERROR,
    "PAYERROR": PaymentStatus.PAYERROR,
}

# 退款单状态归一（查询接口四态全覆盖）
_REFUND_STATUS_MAP = {
    "SUCCESS": RefundStatus.SUCCESS,
    "PROCESSING": RefundStatus.PROCESSING,
    "CLOSED": RefundStatus.CLOSED,
    "ABNORMAL": RefundStatus.ABNORMAL,
}

# 退款申请错误分类（官方错误码语义，非受理即按此二分）
_REFUND_RETRYABLE_CODES = {"FREQUENCY_LIMITED", "ORDER_NOT_READY", "SYSTEMERROR", "BIZERR_NEED_RETRY"}
_REFUND_MANUAL_CODES = {"NOT_ENOUGH", "USER_ACCOUNT_ABNORMAL", "TRADE_OVERDUE", "NOAUTH", "CERT_ERROR", "ERROR"}
# 关单幂等语义：已关闭的订单再关单不算事故（V2 ORDERCLOSED，V3 同语义）
_CLOSE_IDEMPOTENT_CODES = {"ORDERCLOSED", "ORDER_CLOSED"}


def _fen_from_yuan(cell: str) -> int:
    """账单金额（元，2 位小数）→ 分。空/非法返回 0（调用方跳过 0 行）。"""
    text = (cell or "").strip().lstrip("`")
    if not text:
        return 0
    try:
        return int((Decimal(text) * 100).quantize(Decimal(1)))
    except (InvalidOperation, ValueError):
        return 0


class _RateLimiter:
    """批量扫描退避：保证同类微信调用最小间隔。

    官方限频口径：退款申请失败仅 6QPS、退款查询 300QPS 且建议间隔起步
    1 分钟——网关层按调用间距限速（T3 扫描一轮几十笔时自然摊开），比在
    上层散布 sleep 可靠。
    """

    def __init__(self, min_interval_sec: float):
        self._min_interval = min_interval_sec
        self._last_call = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()


class WechatPayGateway:
    """微信支付 APIv3 网关。SDK client 由 from_settings 构造（测试可注入假 client）。"""

    def __init__(self, client, notify_url: str):
        self._client = client
        self._notify_url = notify_url
        # 退款类调用最小间距 0.25s（=4 QPS < 官方失败限频 6QPS）
        self._refund_limiter = _RateLimiter(min_interval_sec=0.25)

    @classmethod
    def from_settings(cls) -> WechatPayGateway:
        """按 WXPAY_* 配置构造。调用前 main.py 已用 wxpay_config_errors 拦截缺项。"""
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from wechatpayv3 import WeChatPay, WeChatPayType

        # 密钥来源二选一：环境变量 PEM 内容（代码库拉取部署形态，构建包无密钥文件）
        # 优先；回退文件路径（CI 上传包形态，部署时写入 /app/secrets/）。
        private_key_pem = (
            settings.WXPAY_PRIVATE_KEY_PEM.strip() or Path_read(settings.WXPAY_PRIVATE_KEY_PATH))
        public_key_pem = (
            settings.WXPAY_PUB_KEY_PEM.strip() or Path_read(settings.WXPAY_PUB_KEY_PATH))
        # fail-fast：私钥必须可解析（错配商户/截断文件在启动时暴露，而非首笔下单）
        load_pem_private_key(private_key_pem.encode("UTF-8"), password=None)

        client = WeChatPay(
            wechatpay_type=WeChatPayType.NATIVE,
            mchid=settings.WXPAY_MCH_ID,
            private_key=private_key_pem,
            cert_serial_no=settings.WXPAY_CERT_SERIAL,
            appid=settings.WXPAY_APPID,
            apiv3_key=settings.WXPAY_APIV3_KEY,
            notify_url=settings.WXPAY_NOTIFY_URL,
            public_key=public_key_pem,
            public_key_id=settings.WXPAY_PUB_KEY_ID,
            timeout=(3.05, 10),  # SDK 缺省无超时（请求可永久挂起），显式收紧
        )
        return cls(client, notify_url=settings.WXPAY_NOTIFY_URL)

    # ── 协议实现 ──

    def create_payment(
        self, out_trade_no: str, amount_fen: int, description: str, attach: str,
        notify_url: str,
    ) -> PaymentResult:
        expire = (datetime.now(_BJ) + timedelta(seconds=ORDER_TTL_SECONDS)).isoformat()
        try:
            code, message = self._client.pay(
                description=description,
                out_trade_no=out_trade_no,
                amount={"total": amount_fen, "currency": "CNY"},
                time_expire=expire,
                attach=attach or None,
                notify_url=notify_url or self._notify_url,
            )
        except requests.exceptions.RequestException as e:
            logger.warning("event=wxpay.create_payment error_kind=timeout error=%s", e)
            return PaymentResult(success=False, error_kind="timeout")
        except Exception as e:  # noqa: BLE001 — SDK 应答验签失败等，不让异常穿透
            logger.warning("event=wxpay.create_payment error_kind=prepay_failed error=%s", e)
            return PaymentResult(success=False, error_kind="prepay_failed")

        if code != 200:
            logger.warning(
                "event=wxpay.create_payment rejected http=%s wx_code=%s",
                code, _error_code(message))
            return PaymentResult(success=False, error_kind="prepay_failed")
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return PaymentResult(success=False, error_kind="prepay_failed")
        return PaymentResult(success=True, code_url=data.get("code_url", ""))

    def query_payment(self, out_trade_no: str) -> QueryResult:
        try:
            code, message = self._client.query(out_trade_no=out_trade_no)
        except requests.exceptions.RequestException as e:
            logger.warning("event=wxpay.query error_kind=network error=%s", e)
            return QueryResult(status=PaymentStatus.UNKNOWN)
        except Exception:  # noqa: BLE001
            return QueryResult(status=PaymentStatus.UNKNOWN)
        if code != 200:
            # ORDER_NOT_EXIST / 系统错误等 → UNKNOWN（上层不据此发货）
            return QueryResult(status=PaymentStatus.UNKNOWN)
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return QueryResult(status=PaymentStatus.UNKNOWN)
        payer = data.get("payer") or {}
        return QueryResult(
            status=_PAY_STATUS_MAP.get(data.get("trade_state", ""), PaymentStatus.UNKNOWN),
            transaction_id=data.get("transaction_id", ""),
            payer_openid=payer.get("openid", ""),
        )

    def close_payment(self, out_trade_no: str) -> CloseResult:
        # 先查单确认未付再关单（官方建议）：已付（含已转退款）直接复活路径
        probe = self.query_payment(out_trade_no)
        if probe.status in (PaymentStatus.SUCCESS, PaymentStatus.REFUND):
            return CloseResult(success=False, already_paid=True)

        try:
            code, message = self._client.close(out_trade_no)
        except requests.exceptions.RequestException:
            return CloseResult(success=False)
        except Exception:  # noqa: BLE001
            return CloseResult(success=False)

        if code in (200, 204):
            return CloseResult(success=True)
        wx_code = _error_code(message)
        if wx_code == "ORDERPAID":
            # 官方：订单已支付无法关闭，「请当作已支付的正常交易」→ 复活发货
            return CloseResult(success=False, already_paid=True)
        if wx_code in _CLOSE_IDEMPOTENT_CODES:
            # 已关闭再关单 = 幂等成功，不告警不重试
            return CloseResult(success=True)
        logger.warning("event=wxpay.close rejected http=%s wx_code=%s order=%s",
                       code, wx_code, out_trade_no)
        return CloseResult(success=False)

    def create_refund(
        self, out_refund_no: str, out_trade_no: str,
        refund_fen: int, total_fen: int, reason: str, notify_url: str,
    ) -> RefundGatewayResult:
        # notify_url 必传：退款回调以申请时传入的 notify_url 开通，
        # 漏传则退款结果只剩 T3 查询兜底（官方文档明示的隐形开关）
        self._refund_limiter.wait()
        try:
            code, message = self._client.refund(
                out_refund_no=out_refund_no,
                out_trade_no=out_trade_no,
                amount={"refund": refund_fen, "total": total_fen, "currency": "CNY"},
                reason=reason or None,
                notify_url=notify_url or self._notify_url,
            )
        except requests.exceptions.RequestException:
            return RefundGatewayResult(status=RefundStatus.UNKNOWN, error_kind="network")
        except Exception:  # noqa: BLE001
            return RefundGatewayResult(status=RefundStatus.UNKNOWN, error_kind="network")

        if code != 200:
            wx_code = _error_code(message)
            if wx_code in _REFUND_RETRYABLE_CODES:
                kind = "retryable"   # 原退款单号间隔重试，勿换单号
            elif wx_code in _REFUND_MANUAL_CODES:
                kind = "manual"      # 余额不足/用户注销等不自愈，告警转人工
            else:
                kind = "unknown"
            logger.warning("event=wxpay.refund_rejected http=%s wx_code=%s kind=%s order=%s",
                           code, wx_code, kind, out_trade_no)
            return RefundGatewayResult(status=RefundStatus.UNKNOWN,
                                       error_kind=kind, error_code=wx_code)
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return RefundGatewayResult(status=RefundStatus.UNKNOWN, error_kind="unknown")
        return RefundGatewayResult(
            status=_REFUND_STATUS_MAP.get(data.get("status", ""), RefundStatus.UNKNOWN),
            wx_refund_id=data.get("refund_id", ""),
        )

    def query_refund(self, out_refund_no: str) -> RefundQueryResult:
        self._refund_limiter.wait()
        try:
            code, message = self._client.query_refund(out_refund_no)
        except requests.exceptions.RequestException:
            return RefundQueryResult(status=RefundStatus.UNKNOWN, error_kind="network")
        except Exception:  # noqa: BLE001
            return RefundQueryResult(status=RefundStatus.UNKNOWN, error_kind="network")
        if code == 404:
            # 受理丢失信号：refund_processing 订单在微信侧查无此退款单 → 告警勿干等
            logger.warning("event=wxpay.refund_query not_found refund_no=%s", out_refund_no)
            return RefundQueryResult(status=RefundStatus.UNKNOWN, error_kind="not_found")
        if code != 200:
            return RefundQueryResult(status=RefundStatus.UNKNOWN, error_kind="network")
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return RefundQueryResult(status=RefundStatus.UNKNOWN, error_kind="network")
        return RefundQueryResult(
            status=_REFUND_STATUS_MAP.get(data.get("status", ""), RefundStatus.UNKNOWN),
            wx_refund_id=data.get("refund_id", ""),
        )

    def download_bill(self, bill_date: str) -> list[BillLine]:
        """下载并解析昨日账单（ALL=支付流水 + REFUND=退款流水，两张分下）。

        允许抛错：T4 上层 _with_retry + error 报告兜底；静默空列表会把下载
        失败伪装成对账平衡。
        """
        lines: list[BillLine] = []
        for bill_type in ("ALL", "REFUND"):
            code, message = self._client.trade_bill(bill_date, bill_type=bill_type)
            if code != 200:
                raise RuntimeError(f"tradebill {bill_type} {bill_date} HTTP{code}: {_error_code(message)}")
            bill_meta = json.loads(message)
            download_url = bill_meta.get("download_url", "")
            expected_hash = (bill_meta.get("hash_value") or "").lower()
            if not download_url:
                raise RuntimeError(f"tradebill {bill_type} 缺 download_url")

            status, content = self._client.download_bill(download_url)
            if status != 200:
                raise RuntimeError(f"bill download {bill_type} HTTP{status}")
            # download_url 5 分钟有效即取即下；内容为 GZIP，解压后为 CSV
            csv_bytes = gzip.decompress(content) if content[:2] == b"\x1f\x8b" else content
            # 完整性校验：官方申请账单接口固定返回 hash_type=SHA1 + hash_value，
            # SHA1 是微信侧协议规定（完整性比对用途，非保密），不可自行换算法
            if expected_hash and hashlib.sha1(csv_bytes).hexdigest() != expected_hash:
                raise RuntimeError(f"bill {bill_type} sha1 mismatch（下载内容损坏）")
            lines.extend(_parse_bill_csv(csv_bytes.decode("UTF-8"), bill_type=bill_type))
        return lines

    # ── 回调验签+解密（notify.py 端点用）──

    def callback(self, headers, body) -> dict | None:
        """验签（微信支付公钥）+ AES-256-GCM 解密。失败返回 None。

        返回 dict 含 event_type（TRANSACTION.SUCCESS / REFUND.SUCCESS 等）与
        解密后的 resource。SIGNTEST 探测流量在端点层先行拦截。
        """
        return self._client.callback(headers=headers, body=body)


def Path_read(path: str) -> str:
    # 读取密钥文件内容（SDK 的 load_private_key/public_key 接受 PEM 内容，不接受路径）
    with open(path, encoding="UTF-8") as f:
        return f.read()


def _error_code(message) -> str:
    """SDK 失败响应体（JSON 字符串）里的微信业务错误码。"""
    try:
        data = json.loads(message)
        return (data.get("code") or "").upper() if isinstance(data, dict) else ""
    except (json.JSONDecodeError, TypeError):
        return ""


def _parse_bill_csv(csv_text: str, bill_type: str) -> list[BillLine]:
    """表头驱动的微信账单 CSV 解析（列序无关，剥反引号前缀）。

    首行为表头；遇「总交易单数」汇总行停止。金额列为元（2 位小数）→ 分。
    """
    lines_out: list[BillLine] = []
    reader = csv.reader(io.StringIO(csv_text))
    header: list[str] | None = None

    def _col(*keywords: str) -> int:
        for idx, name in enumerate(header or []):
            cleaned = name.lstrip("`").strip()
            if all(k in cleaned for k in keywords):
                return idx
        return -1

    for row in reader:
        if not row:
            continue
        cells = [c.lstrip("`").strip() for c in row]
        first = cells[0]
        # 汇总行截停：ALL 账单以「总交易单数」开头，REFUND 账单以「总退款单数」开头
        if first.startswith(("总交易单数", "总退款单数")):
            break
        if header is None:
            header = row  # 表头行（剥引号延后到 _col）
            continue
        if len(cells) < len(header):
            continue  # 脏行防御：列数不足表头的行跳过
        if bill_type == "ALL":
            tx_col, out_col = _col("微信订单号"), _col("商户订单号")
            status_col = _col("交易状态")
            amount_col = _col("订单金额") if _col("订单金额") >= 0 else _col("应结订单金额")
            time_col = _col("交易成功时间")
            amount_fen = _fen_from_yuan(cells[amount_col]) if amount_col >= 0 else 0
            if amount_fen <= 0:
                continue
            lines_out.append(BillLine(
                out_trade_no=cells[out_col] if out_col >= 0 else "",
                transaction_id=cells[tx_col] if tx_col >= 0 else "",
                amount_fen=amount_fen,
                status=cells[status_col] if status_col >= 0 else "UNKNOWN",
                success_time=cells[time_col] if time_col >= 0 else "",
            ))
        else:  # REFUND 账单
            tx_col, out_col = _col("微信订单号"), _col("商户订单号")
            refund_col = _col("退款金额")
            time_col = _col("退款成功时间")
            amount_fen = _fen_from_yuan(cells[refund_col]) if refund_col >= 0 else 0
            if amount_fen <= 0:
                continue
            lines_out.append(BillLine(
                out_trade_no=cells[out_col] if out_col >= 0 else "",
                transaction_id=cells[tx_col] if tx_col >= 0 else "",
                amount_fen=amount_fen,
                status="REFUND",
                success_time=cells[time_col] if time_col >= 0 else "",
            ))
    return lines_out
