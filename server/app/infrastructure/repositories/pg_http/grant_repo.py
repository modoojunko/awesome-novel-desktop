"""CloudBase PG HTTP API 设备授权凭证仓储（user_id 代理键，s-pay-foundation）。

域对象 DeviceGrant 仍以 username 字符串做身份；仓储内部完成 username ↔ user_id 解析。
"""
from __future__ import annotations

from app.domain.devices import DeviceGrant
from app.infrastructure.repositories.pg_http.client import PgRestClient

_TABLE = "device_grants"
_USERS = "users"


class PgHttpGrantRepo:
    def __init__(self, client: PgRestClient):
        self.client = client

    def _resolve_user_id(self, username: str) -> int | None:
        # username 路径走共享 TTL 缓存解析（license-userid-cache），免每请求一趟 users 往返
        from app.infrastructure.repositories.pg_http.user_repo import resolve_user_id
        return resolve_user_id(self.client, username)

    def _resolve_username(self, user_id) -> str:
        if user_id is None:
            return ""
        doc = self.client.find_one(_USERS, {"id": int(user_id)})
        return doc.get("username", "") if doc else ""

    def _to_domain(self, doc: dict) -> DeviceGrant:
        return DeviceGrant(
            pc_hash=doc["pc_hash"],
            username=self._resolve_username(doc.get("user_id")),
            token=doc["token"],
            enrolled=bool(doc.get("enrolled", False)),
            fingerprint=doc.get("fingerprint", "") or "",
            challenge=doc.get("challenge", "") or "",
        )

    def get(self, pc_hash: str) -> DeviceGrant | None:
        doc = self.client.find_one(_TABLE, {"pc_hash": pc_hash})
        return self._to_domain(doc) if doc else None

    def upsert(
        self, pc_hash: str, username: str, token: str, enrolled: bool, fingerprint: str,
        *, challenge: str | None = None,
    ) -> None:
        user_id = self._resolve_user_id(username)
        if user_id is None:
            return  # 用户不存在，不写 grant

        existing = self.client.find_one(_TABLE, {"pc_hash": pc_hash})
        payload = {
            "user_id": user_id,
            "token": token,
            "enrolled": 1 if enrolled else 0,
            "fingerprint": fingerprint,
            "challenge": challenge or None,
        }
        if existing:
            self.client.update(_TABLE, {"pc_hash": pc_hash}, payload)
        else:
            # 省略 created_at：数据库 DEFAULT now()
            self.client.insert(_TABLE, {"pc_hash": pc_hash, **payload})

    def set_enrolled(self, pc_hash: str, username: str, enrolled: bool) -> None:
        user_id = self._resolve_user_id(username)
        if user_id is None:
            return
        self.client.update(
            _TABLE,
            {"pc_hash": pc_hash, "user_id": user_id},
            {"enrolled": 1 if enrolled else 0},
        )

    def delete_all_for_user(self, username: str) -> int:
        """注销执行：清空该用户全部设备授权。返回行数。"""
        user_id = self._resolve_user_id(username)
        if user_id is None:
            return 0
        return self.client.delete(_TABLE, {"user_id": user_id})

    def delete_by_fingerprint(self, username: str, fingerprint: str) -> int:
        """移除设备时同步清除该设备授权凭证（s-security-hardening R5）。

        指纹为空不清（无 device_profile 的授权彼此不可区分，且真实 C端 恒携带档案）。
        """
        user_id = self._resolve_user_id(username)
        if user_id is None or not fingerprint:
            return 0
        return self.client.delete(
            _TABLE, {"user_id": user_id, "fingerprint": fingerprint},
        )
