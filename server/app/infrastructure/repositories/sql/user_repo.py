"""SQL（SQLAlchemy/SQLite）用户仓储。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.identity import User
from app.infrastructure.security.token_version import DELETION_SENTINEL
from app.models.user import UserORM


class SqlUserRepo:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _to_domain(row: UserORM) -> User:
        return User(
            username=row.username,
            password_hash=row.password_hash,
            status=row.status,
            security_question=row.security_question or "",
            security_answer_hash=row.security_answer_hash or "",
            created_at=row.created_at,
            theme=row.theme or "",
            deletion_status=row.deletion_status or "正常",
            deletion_requested_at=row.deletion_requested_at,
            deletion_deadline=row.deletion_deadline,
            deletion_waive_assets=bool(row.deletion_waive_assets),
            token_version=row.token_version or 0,
        )

    def get_id(self, username: str) -> int | None:
        """username → user_id（代理键解析 helper，2026-08-30 新增）。"""
        row = self.db.query(UserORM.id).filter(UserORM.username == username).first()
        return row[0] if row else None

    def get(self, username: str) -> User | None:
        row = self.db.query(UserORM).filter(UserORM.username == username).first()
        return self._to_domain(row) if row else None

    def exists(self, username: str) -> bool:
        return self.db.query(UserORM).filter(UserORM.username == username).first() is not None

    def create(self, user: User) -> User:
        row = UserORM(
            username=user.username,
            password_hash=user.password_hash,
            security_question=user.security_question,
            security_answer_hash=user.security_answer_hash,
            status=user.status,
        )
        self.db.add(row)
        return user

    def update_password(self, username: str, new_password_hash: str,
                        *, token_version: int | None = None) -> None:
        changes = {"password_hash": new_password_hash}
        if token_version is not None:
            changes["token_version"] = token_version  # 会话撤销（R5）
        self.db.query(UserORM).filter(UserORM.username == username).update(changes)
        if token_version is not None:
            from app.infrastructure.security.token_version import invalidate_all
            invalidate_all()

    def update_security(self, username: str, question: str, answer_hash: str,
                        *, token_version: int | None = None) -> None:
        changes = {"security_question": question, "security_answer_hash": answer_hash}
        if token_version is not None:
            changes["token_version"] = token_version
        self.db.query(UserORM).filter(UserORM.username == username).update(changes)
        if token_version is not None:
            from app.infrastructure.security.token_version import invalidate_all
            invalidate_all()

    def update_theme(self, username: str, theme: str) -> None:
        self.db.query(UserORM).filter(UserORM.username == username).update(
            {"theme": theme}
        )

    def flush(self) -> None:
        """确保用户已持久化，后续试用码 FK 不失败。"""
        self.db.flush()

    # ── 账号自助注销（account-deletion）：单语句 CAS，rowcount 即语义 ──
    def request_deletion(self, username: str, requested_at, deadline, waive: bool) -> int:
        result = self.db.query(UserORM).filter(
            UserORM.username == username,
            UserORM.deletion_status.in_(["正常", ""]),
        ).update(
            {
                "deletion_status": "注销撤销期",
                "deletion_requested_at": requested_at,
                "deletion_deadline": deadline,
                "deletion_waive_assets": bool(waive),
            },
            synchronize_session=False,
        )
        self.db.commit()
        return result

    def revoke_deletion(self, username: str, now) -> int:
        result = self.db.query(UserORM).filter(
            UserORM.username == username,
            UserORM.deletion_status == "注销撤销期",
            UserORM.deletion_deadline > now,
        ).update(
            {"deletion_status": "正常", "deletion_requested_at": None, "deletion_deadline": None,
             "deletion_waive_assets": False},
            synchronize_session=False,
        )
        self.db.commit()
        return result

    def mark_deleted(self, username: str, now) -> int:
        """到期执行标记：CAS 到位后立刻清空凭据（去标识化第一步，防过期账号继续持有有效密码）。"""
        result = self.db.query(UserORM).filter(
            UserORM.username == username,
            UserORM.deletion_status == "注销撤销期",
            UserORM.deletion_deadline <= now,
        ).update(
            {"deletion_status": "已注销", "password_hash": "",
             "token_version": DELETION_SENTINEL},
            synchronize_session=False,
        )
        self.db.commit()
        return result

    def find_due_deletion_usernames(self, now) -> list[str]:
        rows = self.db.query(UserORM.username).filter(
            UserORM.deletion_status == "注销撤销期",
            UserORM.deletion_deadline <= now,
        ).all()
        return [r[0] for r in rows]
