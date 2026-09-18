"""CloudBase PG HTTP API 用户仓储。"""
from __future__ import annotations

from app.domain.identity import User
from app.domain.identity.deletion import (
    DELETION_STATUS_DELETED,
    DELETION_STATUS_NORMAL,
    DELETION_STATUS_PENDING,
)
from app.infrastructure.repositories.pg_http.client import (
    PgRestClient,
    RawFilter,
    parse_dt,
)

_TABLE = "users"


def resolve_user_id(client: PgRestClient, username: str) -> int | None:
    """username → user_id（普通直查）。

    jwt-uid-claim 后 web 业务端点凭 token uid 直查业务表，本函数仅服务
    身份域（登录/注册/注销）与 C端激活链等以 username 为输入的低频路径；
    曾经的 TTL 缓存替身已随 token 携带 uid 一并拆除。
    """
    doc = client.find_one(_TABLE, {"username": username})
    return int(doc["id"]) if doc and doc.get("id") is not None else None


class PgHttpUserRepo:
    def __init__(self, client: PgRestClient):
        self.client = client

    @staticmethod
    def _to_domain(doc: dict) -> User:
        return User(
            username=doc["username"],
            password_hash=doc["password_hash"],
            status=doc.get("status", "active"),
            security_question=doc.get("security_question", "") or "",
            security_answer_hash=doc.get("security_answer_hash", "") or "",
            created_at=parse_dt(doc.get("created_at")),
            theme=doc.get("theme", "") or "",
            deletion_status=doc.get("deletion_status", "") or "正常",
            deletion_requested_at=parse_dt(doc.get("deletion_requested_at")),
            deletion_deadline=parse_dt(doc.get("deletion_deadline")),
            deletion_waive_assets=bool(doc.get("deletion_waive_assets", False)),
            token_version=int(doc.get("token_version") or 0),
        )

    def get(self, username: str) -> User | None:
        doc = self.client.find_one(_TABLE, {"username": username})
        return self._to_domain(doc) if doc else None

    def get_id(self, username: str) -> int | None:
        """username → user_id（代理键解析，与 SqlUserRepo.get_id 对齐）。"""
        return resolve_user_id(self.client, username)

    def exists(self, username: str) -> bool:
        return self.client.find_one(_TABLE, {"username": username}) is not None

    def create(self, user: User) -> User:
        # 省略 created_at：数据库 DEFAULT now()
        self.client.insert(_TABLE, {
            "username": user.username,
            "password_hash": user.password_hash,
            "security_question": user.security_question,
            "security_answer_hash": user.security_answer_hash,
            "status": user.status,
        })
        return user

    def update_password(self, username: str, new_password_hash: str,
                        *, token_version: int | None = None) -> None:
        changes: dict = {"password_hash": new_password_hash}
        if token_version is not None:
            changes["token_version"] = token_version  # 会话撤销（R5）
        self.client.update(_TABLE, {"username": username}, changes)
        if token_version is not None:
            from app.infrastructure.security.token_version import invalidate_all
            invalidate_all()

    def update_security(self, username: str, question: str, answer_hash: str,
                        *, token_version: int | None = None) -> None:
        changes: dict = {"security_question": question, "security_answer_hash": answer_hash}
        if token_version is not None:
            changes["token_version"] = token_version
        self.client.update(_TABLE, {"username": username}, changes)
        if token_version is not None:
            from app.infrastructure.security.token_version import invalidate_all
            invalidate_all()

    def update_theme(self, username: str, theme: str) -> None:
        self.client.update(_TABLE, {"username": username}, {"theme": theme})

    def flush(self) -> None:
        """无 FK 顺序问题，no-op。"""
        return

    # ── 账号自助注销（account-deletion）：单语句 CAS，受影响行数即语义 ──
    def request_deletion(self, username: str, requested_at, deadline, waive: bool) -> int:
        """WHERE deletion_status='正常'（迁移已给存量行回填默认值，无 NULL）；0 行=已在流程中。"""
        return self.client.update_cas(
            _TABLE,
            {"username": username, "deletion_status": DELETION_STATUS_NORMAL},
            {
                "deletion_status": DELETION_STATUS_PENDING,
                "deletion_requested_at": requested_at.isoformat(),
                "deletion_deadline": deadline.isoformat(),
                "deletion_waive_assets": bool(waive),
            },
        )

    def revoke_deletion(self, username: str, now) -> int:
        """WHERE status='注销撤销期' AND deadline>now（gt.{iso}）；0 行=已到期或无申请。"""
        return self.client.update_cas(
            _TABLE,
            {
                "username": username,
                "deletion_status": DELETION_STATUS_PENDING,
                "deletion_deadline": RawFilter(f"gt.{now.isoformat()}"),
            },
            {"deletion_status": DELETION_STATUS_NORMAL,
             "deletion_requested_at": None, "deletion_deadline": None,
             "deletion_waive_assets": False},
        )

    def mark_deleted(self, username: str, now) -> int:
        """到期执行标记：CAS 到位即置空凭据（去标识化第一步）。"""
        return self.client.update_cas(
            _TABLE,
            {
                "username": username,
                "deletion_status": DELETION_STATUS_PENDING,
                "deletion_deadline": RawFilter(f"lte.{now.isoformat()}"),
            },
            {"deletion_status": DELETION_STATUS_DELETED, "password_hash": "",
             "token_version": 1},
        )

    def find_due_deletion_usernames(self, now) -> list[str]:
        rows = self.client.find(
            _TABLE,
            {"deletion_status": DELETION_STATUS_PENDING, "deletion_deadline": RawFilter(f"lte.{now.isoformat()}")},
            select="username",
        )
        return [r["username"] for r in rows]
