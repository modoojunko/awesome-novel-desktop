"""CloudBase PG HTTP API 激活码仓储。

2026-08-30 代理键迁移：FK 从 username(String) 改为 user_id(BigInteger)。
仓储层接受 username 字符串或 user_id(int)，内部经 users 表解析。
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from app.domain.licensing import ActivationCode
from app.infrastructure.repositories.pg_http.client import (
    PgRestClient,
    parse_dt,
    to_iso,
)

_TABLE = "codes"


class PgHttpCodeRepo:
    def __init__(self, client: PgRestClient):
        self.client = client

    @staticmethod
    def _created_at(now=None) -> str:
        """台账行 created_at 显式 naive UTC（s-payments 写入口径）——
        列默认 now() 在上海时区会话求值会落成上海本地时间裸值被按 UTC 读，禁用。"""
        if now is None:
            now = datetime.now(UTC)
        dt = now.astimezone(UTC).replace(tzinfo=None) if now.tzinfo else now
        return dt.isoformat()

    def _resolve_user_id(self, username_or_id) -> int | None:
        """接受 username(str) 或 user_id(int)，返回 user_id(int)。

        username 路径走共享 TTL 缓存解析（license-userid-cache）：
        /pay/license 等每请求都解析，直查 users 表会多一趟往返。
        """
        if isinstance(username_or_id, int):
            return username_or_id
        if not username_or_id:
            return None
        from app.infrastructure.repositories.pg_http.user_repo import resolve_user_id
        return resolve_user_id(self.client, username_or_id)

    @staticmethod
    def _to_domain(doc: dict) -> ActivationCode:
        return ActivationCode(
            code_id=doc["code_id"],
            tier=doc["tier"],
            duration_days=doc["duration_days"],
            status=doc["status"],
            user_id=doc.get("user_id"),
            expires_at=parse_dt(doc.get("expires_at")),
            activated_at=parse_dt(doc.get("activated_at")),
            created_at=parse_dt(doc.get("created_at")),
            created_by=doc.get("created_by", "") or "",
            refund_requested_at=parse_dt(doc.get("refund_requested_at")),
            grant_start=parse_dt(doc.get("grant_start")),
            order_id=doc.get("order_id"),
            source=doc.get("source", "admin") or "admin",
        )

    def get(self, code_id: str) -> ActivationCode | None:
        doc = self.client.find_one(_TABLE, {"code_id": code_id})
        return self._to_domain(doc) if doc else None

    def find_all_by_username(self, username: str) -> list[ActivationCode]:
        uid = self._resolve_user_id(username)
        if uid is None:
            return []
        docs = self.client.find(_TABLE, {"user_id": uid}, sort=[("activated_at", "desc")])
        return [self._to_domain(d) for d in docs]

    def find_active_by_username(self, username: str) -> list[ActivationCode]:
        uid = self._resolve_user_id(username)
        if uid is None:
            return []
        docs = self.client.find(
            _TABLE,
            {"user_id": uid, "status": "active"},
            sort=[("activated_at", "desc")],
        )
        return [self._to_domain(d) for d in docs]

    def find_all(self, limit: int = 200) -> list[ActivationCode]:
        docs = self.client.find(_TABLE, sort=[("created_at", "desc")], limit=limit)
        return [self._to_domain(d) for d in docs]

    def create(self, code: ActivationCode) -> None:
        uid = self._resolve_user_id(code.user_id)
        self.client.insert(_TABLE, {
            "code_id": code.code_id,
            "tier": code.tier,
            "duration_days": code.duration_days,
            "status": code.status,
            "user_id": uid,
            "created_by": code.created_by,
            "created_at": self._created_at(),
        })

    def activate(self, code_id: str, username_or_id, expires_at: date) -> None:
        uid = self._resolve_user_id(username_or_id)
        self.client.update(_TABLE, {"code_id": code_id}, {
            "status": "active",
            "user_id": uid,
            "activated_at": to_iso(datetime.now(UTC).replace(tzinfo=None)),
            "expires_at": to_iso(datetime.combine(expires_at, datetime.min.time())),
        })

    def revoke_unconsumed_for_user(self, username: str) -> int:
        """注销执行：unused（待激活）+ active（排队中/消耗中）全部置 revoked。返回行数。"""
        uid = self._resolve_user_id(username)
        if uid is None:
            return 0
        return self.client.update_cas(
            _TABLE,
            {"user_id": f"eq.{uid}", "status": "in.(unused,active)"},
            {"status": "revoked"},
        )

    def revoke_unconsumed_for_order(self, order_no: str) -> int:
        """退款收回：该订单未激活台账行置 revoked；已激活行不动（部分退款
        按秒折算，用户保留剩余权益）。发货幂等键 code_id=O-{order_no}。"""
        return self.client.update_cas(
            _TABLE,
            {"code_id": f"eq.O-{order_no}", "status": "in.(unused,pending_activation)"},
            {"status": "revoked", "status_detail": "revoked"},
        )

    def revoke_queued_for_order(self, order_no: str, anchor) -> int:
        """退款收回（排队相位）：active/frozen 且 grant_start 空或 > anchor 置 revoked；
        已起算行不动。anchor=refund_requested_at（与折算金额锁定同锚）。
        frozen 一并覆盖：确认退款即冻结，到账时排队行从冻结态直接收回。

        PostgREST 单 filter 无法表达跨列 OR（`or` 参数值以 `(` 开头会被客户端
        误加 eq. 前缀）——两支无条件 CAS（is.null 一支 + gt.anchor 一支）取并集，
        各自单列条件天然幂等；TOCTOU 安全：active/frozen 行 grant_start 不可变
        （冻结只翻 status，不碰 grant_start）。"""
        if isinstance(anchor, datetime):
            a = anchor
        else:
            a = datetime.fromisoformat(str(anchor).replace("Z", "+00:00"))
        if a.tzinfo is not None:
            a = a.astimezone(UTC).replace(tzinfo=None)
        anchor_iso = a.isoformat()
        total = 0
        for grant_filter in ("is.null", f"gt.{anchor_iso}"):
            total += self.client.update_cas(
                _TABLE,
                {
                    "code_id": f"eq.O-{order_no}",
                    "status": "in.(active,frozen)",
                    "grant_start": grant_filter,
                },
                {"status": "revoked", "status_detail": "revoked"},
            )
        return total

    def freeze_for_order(self, order_no: str) -> int:
        """退款冻结（s-pay-refund-freeze）：该订单 active 行置 frozen——可用性暂停，
        不计 tier/到期/生效展示；grant_start/expires_at 不动（排队位与取消还原不受
        影响）。幂等：已 frozen 重放返回 0。"""
        return self.client.update_cas(
            _TABLE,
            {"code_id": f"eq.O-{order_no}", "status": "eq.active"},
            {"status": "frozen", "status_detail": "frozen"},
        )

    def unfreeze_for_order(self, order_no: str) -> int:
        """退款解冻（冷静期取消/到账已起算恢复共用）：frozen → active。
        冻结不触碰起算信息，还原即精确（active↔frozen 对偶）。幂等。"""
        return self.client.update_cas(
            _TABLE,
            {"code_id": f"eq.O-{order_no}", "status": "eq.frozen"},
            {"status": "active", "status_detail": "active"},
        )

    def find_frozen(self, limit: int = 200) -> list[ActivationCode]:
        """扫描 F（冻结完整性）取数：全部冻结行（在途退款单量级，天然有界）。"""
        docs = self.client.find(_TABLE, filter={"status": "eq.frozen"}, limit=limit)
        return [self._to_domain(d) for d in docs]

    def find_unconsumed_by_username(self, username: str) -> list[ActivationCode]:
        uid = self._resolve_user_id(username)
        if uid is None:
            return []
        docs = self.client.find(
            _TABLE,
            {"user_id": f"eq.{uid}", "status": "in.(unused,active)"},
            sort=[("activated_at", "desc")],
        )
        return [self._to_domain(d) for d in docs]

    def request_refund_for_user(self, code_id: str, username: str, now) -> int:
        """权益级退款申请：CAS 标记 refund_requested_at（幂等，重复申请 0 行）。"""
        uid = self._resolve_user_id(username)
        if uid is None:
            return 0
        return self.client.update_cas(
            _TABLE,
            {
                "code_id": f"eq.{code_id}",
                "user_id": f"eq.{uid}",
                "status": "in.(unused,active)",
                "refund_requested_at": "is.null",
            },
            {"refund_requested_at": now.isoformat()},
        )

    # ── 支付台账（s-pay-foundation：到货-激活两段式）──

    def create_from_order(self, code_id: str, tier: str, duration_days: int,
                          user_id: int, order_id: int, now) -> bool:
        """发货插台账行（pending_activation）；撞 code_id 唯一键返回 False。"""
        return self.client.insert_or_conflict(_TABLE, {
            "code_id": code_id,
            "tier": tier,
            "duration_days": duration_days,
            "status": "pending_activation",
            "status_detail": "pending_activation",
            "user_id": user_id,
            "source": "order",
            "order_id": order_id,
            "created_by": "payment",
            "created_at": self._created_at(now),
        })

    def find_by_order(self, order_id: int) -> list[ActivationCode]:
        docs = self.client.find(
            _TABLE,
            {"order_id": f"eq.{order_id}"},
            sort=[("created_at", "asc")],
        )
        return [self._to_domain(d) for d in docs]

    def find_active_by_user_id(self, user_id: int) -> list[ActivationCode]:
        docs = self.client.find(
            _TABLE,
            {"user_id": f"eq.{user_id}", "status": "eq.active"},
            sort=[("expires_at", "desc")],
        )
        return [self._to_domain(d) for d in docs]

    def activate_pending(self, code_id: str, grant_start, expires_at, activated_at) -> bool:
        """CAS pending_activation→active；False=已被并发方改走。"""
        rows = self.client.update_cas(
            _TABLE,
            {"code_id": f"eq.{code_id}", "status": "eq.pending_activation"},
            {
                "status": "active",
                "status_detail": "active",
                "grant_start": grant_start.isoformat() if grant_start else None,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "activated_at": activated_at.isoformat() if activated_at else None,
            },
        )
        return rows > 0

    def find_order_codes_page(self, user_id: int, statuses: list[str] | None = None,
                               limit: int = 20, offset: int = 0) -> tuple[list[ActivationCode], int]:
        """订单来源明细分页单往返（count 与取行合并，同 OrderRepo.find_by_user_page；
        网关不回 Content-Range 时降级单独计数）。source=eq.order 天然排除 NULL 来源行。"""
        filt: dict = {"user_id": f"eq.{user_id}", "source": "eq.order"}
        if statuses:
            filt["status"] = f"in.({','.join(statuses)})"
        docs, total = self.client.find(
            _TABLE,
            filter=filt,
            sort=[("created_at", "desc")],
            limit=limit,
            offset=offset,
            want_count=True,
        )
        if total is None:
            total = self.client.count(_TABLE, filter=filt)
        return [self._to_domain(d) for d in docs], total
