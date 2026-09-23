"""CloudBase PG HTTP 客户端需更新标记仓储（s-auth-outdated-signal）。"""
from __future__ import annotations

from datetime import UTC

from app.infrastructure.repositories.pg_http.client import PgRestClient, parse_dt

_TABLE = "device_outdated_marks"


class PgHttpOutdatedMarkRepo:
    def __init__(self, client: PgRestClient):
        self.client = client

    def mark(self, pc_hash: str) -> None:
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        existing = self.client.find_one(_TABLE, {"pc_hash": pc_hash})
        if existing:
            self.client.update(_TABLE, {"pc_hash": pc_hash}, {"rejected_at": now})
        else:
            self.client.insert(_TABLE, {"pc_hash": pc_hash, "rejected_at": now})

    def fresh(self, pc_hash: str) -> bool:
        from datetime import datetime, timedelta

        if not pc_hash:
            return False
        doc = self.client.find_one(_TABLE, {"pc_hash": pc_hash})
        if not doc or not doc.get("rejected_at"):
            return False
        rejected = parse_dt(doc["rejected_at"])
        if rejected is None:
            return False
        if rejected.tzinfo is None:
            rejected = rejected.replace(tzinfo=UTC)
        return datetime.now(UTC) - rejected <= timedelta(minutes=10)
