"""SQL（SQLAlchemy/SQLite）激活码仓储。

2026-08-30 代理键迁移：codes 表 FK 从 username(String) 改为 user_id(BigInteger)。
仓储层接受 username 字符串，内部经 UserORM 解析为 user_id。
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.domain.licensing import ActivationCode
from app.models.code import ActivationCodeORM
from app.models.user import UserORM


class SqlCodeRepo:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _created_at(now=None):
        """台账行 created_at 显式 naive UTC（与 pg_http 同口径，禁用列默认的时区漂移）。"""
        if now is None:
            now = datetime.now(UTC)
        return now.astimezone(UTC).replace(tzinfo=None) if now.tzinfo else now

    def _resolve_user_id(self, username_or_id) -> int | None:
        """接受 username(str) 或 user_id(int)（与 pg_http 侧契约对齐：
        jwt-uid-claim 后 web 端点直传 token uid，int 零开销直通）。"""
        if isinstance(username_or_id, int) and not isinstance(username_or_id, bool):
            return username_or_id
        row = self.db.query(UserORM.id).filter(UserORM.username == username_or_id).first()
        return row[0] if row else None

    @staticmethod
    def _to_domain(row: ActivationCodeORM) -> ActivationCode:
        return ActivationCode(
            code_id=row.code_id,
            tier=row.tier,
            duration_days=row.duration_days,
            status=row.status,
            user_id=row.user_id,
            expires_at=row.expires_at,
            activated_at=row.activated_at,
            created_at=row.created_at,
            created_by=row.created_by or "",
            refund_requested_at=row.refund_requested_at,
            grant_start=row.grant_start,
            order_id=row.order_id,
            source=row.source or "admin",
        )

    def get(self, code_id: str) -> ActivationCode | None:
        row = self.db.query(ActivationCodeORM).filter(ActivationCodeORM.code_id == code_id).first()
        return self._to_domain(row) if row else None

    def find_all_by_username(self, username: str) -> list[ActivationCode]:
        uid = self._resolve_user_id(username)
        if uid is None:
            return []
        rows = (
            self.db.query(ActivationCodeORM)
            .filter(ActivationCodeORM.user_id == uid)
            .order_by(ActivationCodeORM.activated_at.desc())
            .all()
        )
        return [self._to_domain(r) for r in rows]

    def find_active_by_username(self, username: str) -> list[ActivationCode]:
        uid = self._resolve_user_id(username)
        if uid is None:
            return []
        rows = (
            self.db.query(ActivationCodeORM)
            .filter(
                ActivationCodeORM.user_id == uid,
                ActivationCodeORM.status == "active",
            )
            .order_by(ActivationCodeORM.activated_at.desc())
            .all()
        )
        return [self._to_domain(r) for r in rows]

    def find_all(self, limit: int = 200) -> list[ActivationCode]:
        rows = (
            self.db.query(ActivationCodeORM)
            .order_by(ActivationCodeORM.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_domain(r) for r in rows]

    def create(self, code: ActivationCode) -> None:
        # user_id 可以是 int（代理键）或 str（username，需解析）
        uid = code.user_id
        if isinstance(uid, str):
            uid = self._resolve_user_id(uid)

        row = ActivationCodeORM(
            code_id=code.code_id,
            tier=code.tier,
            duration_days=code.duration_days,
            status=code.status,
            user_id=uid,  # int 或 None（未绑定码）
            created_by=code.created_by,
            created_at=self._created_at(),
        )
        self.db.add(row)

    def activate(self, code_id: str, username: str, expires_at: date) -> None:
        uid = self._resolve_user_id(username)
        self.db.query(ActivationCodeORM).filter(ActivationCodeORM.code_id == code_id).update({
            "status": "active",
            "user_id": uid,
            "activated_at": datetime.now(UTC).replace(tzinfo=None),
            "expires_at": datetime.combine(expires_at, datetime.min.time()),
        })

    def revoke_unconsumed_for_user(self, username: str) -> int:
        """注销执行：unused（待激活）+ active（排队中/消耗中）全部置 revoked。返回行数。"""
        uid = self._resolve_user_id(username)
        if uid is None:
            return 0
        result = self.db.query(ActivationCodeORM).filter(
            ActivationCodeORM.user_id == uid,
            ActivationCodeORM.status.in_(["unused", "active"]),
        ).update({"status": "revoked"}, synchronize_session=False)
        self.db.commit()
        return result

    def revoke_unconsumed_for_order(self, order_no: str) -> int:
        """退款收回：该订单未激活台账行置 revoked；已激活行不动（部分退款
        按秒折算，用户保留剩余权益）。发货幂等键 code_id=O-{order_no}。"""
        result = self.db.query(ActivationCodeORM).filter(
            ActivationCodeORM.code_id == f"O-{order_no}",
            ActivationCodeORM.status.in_(["unused", "pending_activation"]),
        ).update({"status": "revoked", "status_detail": "revoked"}, synchronize_session=False)
        self.db.commit()
        return result

    def revoke_queued_for_order(self, order_no: str, anchor) -> int:
        """退款收回（排队相位）：active/frozen 且 grant_start 空或 > anchor 置 revoked；
        已起算行（grant_start <= anchor）不动。anchor=refund_requested_at（naive UTC）。
        frozen 一并覆盖：确认退款即冻结，到账时排队行从冻结态直接收回。"""
        if isinstance(anchor, str):
            anchor = datetime.fromisoformat(anchor.replace("Z", "+00:00"))
        if anchor is not None and anchor.tzinfo is not None:
            anchor = anchor.astimezone(UTC).replace(tzinfo=None)
        result = self.db.query(ActivationCodeORM).filter(
            ActivationCodeORM.code_id == f"O-{order_no}",
            ActivationCodeORM.status.in_(["active", "frozen"]),
            or_(ActivationCodeORM.grant_start.is_(None),
                ActivationCodeORM.grant_start > anchor),
        ).update({"status": "revoked", "status_detail": "revoked"}, synchronize_session=False)
        self.db.commit()
        return result

    def freeze_for_order(self, order_no: str) -> int:
        """退款冻结（s-pay-refund-freeze）：该订单 active 行置 frozen——可用性暂停，
        不计 tier/到期/生效展示；grant_start/expires_at 不动（排队位与取消还原不受影响）。
        幂等：已 frozen 重放返回 0。"""
        result = self.db.query(ActivationCodeORM).filter(
            ActivationCodeORM.code_id == f"O-{order_no}",
            ActivationCodeORM.status == "active",
        ).update({"status": "frozen", "status_detail": "frozen"}, synchronize_session=False)
        self.db.commit()
        return result

    def unfreeze_for_order(self, order_no: str) -> int:
        """退款解冻（冷静期取消/到账已起算恢复共用）：frozen → active。
        冻结不触碰起算信息，还原即精确（active↔frozen 对偶）。幂等。"""
        result = self.db.query(ActivationCodeORM).filter(
            ActivationCodeORM.code_id == f"O-{order_no}",
            ActivationCodeORM.status == "frozen",
        ).update({"status": "active", "status_detail": "active"}, synchronize_session=False)
        self.db.commit()
        return result

    def find_frozen(self, limit: int = 200) -> list[ActivationCode]:
        """扫描 F（冻结完整性）取数：全部冻结行（在途退款单量级，天然有界）。"""
        rows = (
            self.db.query(ActivationCodeORM)
            .filter(ActivationCodeORM.status == "frozen")
            .limit(limit)
            .all()
        )
        return [self._to_domain(r) for r in rows]

    def find_unconsumed_by_username(self, username: str) -> list[ActivationCode]:
        uid = self._resolve_user_id(username)
        if uid is None:
            return []
        rows = (
            self.db.query(ActivationCodeORM)
            .filter(
                ActivationCodeORM.user_id == uid,
                ActivationCodeORM.status.in_(["unused", "active"]),
            )
            .order_by(ActivationCodeORM.activated_at.desc())
            .all()
        )
        return [self._to_domain(r) for r in rows]

    def request_refund_for_user(self, code_id: str, username: str, now) -> int:
        """权益级退款申请：CAS 标记 refund_requested_at（幂等，重复申请 0 行）。"""
        uid = self._resolve_user_id(username)
        if uid is None:
            return 0
        result = self.db.query(ActivationCodeORM).filter(
            ActivationCodeORM.code_id == code_id,
            ActivationCodeORM.user_id == uid,
            ActivationCodeORM.status.in_(["unused", "active"]),
            ActivationCodeORM.refund_requested_at.is_(None),
        ).update({"refund_requested_at": now}, synchronize_session=False)
        self.db.commit()
        return result

    # ── 支付台账（s-pay-foundation：到货-激活两段式）──

    def create_from_order(self, code_id: str, tier: str, duration_days: int,
                          user_id: int, order_id: int, now) -> bool:
        """发货插台账行（pending_activation）；撞 code_id 唯一键返回 False。"""
        if self.db.query(ActivationCodeORM).filter(
                ActivationCodeORM.code_id == code_id).first() is not None:
            return False
        self.db.add(ActivationCodeORM(
            code_id=code_id,
            tier=tier,
            duration_days=duration_days,
            status="pending_activation",
            status_detail="pending_activation",
            user_id=user_id,
            source="order",
            order_id=order_id,
            created_by="payment",
            created_at=self._created_at(now),
        ))
        self.db.commit()
        return True

    def find_by_order(self, order_id: int) -> list[ActivationCode]:
        rows = (
            self.db.query(ActivationCodeORM)
            .filter(ActivationCodeORM.order_id == order_id)
            .order_by(ActivationCodeORM.created_at)
            .all()
        )
        return [self._to_domain(r) for r in rows]

    def find_active_by_user_id(self, user_id: int) -> list[ActivationCode]:
        rows = (
            self.db.query(ActivationCodeORM)
            .filter(
                ActivationCodeORM.user_id == user_id,
                ActivationCodeORM.status == "active",
            )
            .order_by(ActivationCodeORM.expires_at.desc())
            .all()
        )
        return [self._to_domain(r) for r in rows]

    def activate_pending(self, code_id: str, grant_start, expires_at, activated_at) -> bool:
        """CAS pending_activation→active；False=已被并发方改走。"""
        result = self.db.query(ActivationCodeORM).filter(
            ActivationCodeORM.code_id == code_id,
            ActivationCodeORM.status == "pending_activation",
        ).update({
            "status": "active",
            "status_detail": "active",
            "grant_start": grant_start,
            "expires_at": expires_at,
            "activated_at": activated_at,
        }, synchronize_session=False)
        self.db.commit()
        return result > 0

    def find_order_codes_page(self, user_id: int, statuses: list[str] | None = None,
                               limit: int = 20, offset: int = 0) -> tuple[list[ActivationCode], int]:
        """订单来源明细分页：filtered 全量装载后 len()+切片（个人量级，同 OrderRepo 假设）。"""
        q = self.db.query(ActivationCodeORM).filter(
            ActivationCodeORM.user_id == user_id,
            ActivationCodeORM.source == "order",
        )
        if statuses:
            q = q.filter(ActivationCodeORM.status.in_(statuses))
        rows = q.order_by(ActivationCodeORM.created_at.desc()).all()
        return [self._to_domain(r) for r in rows[offset:offset + limit]], len(rows)
