"""凭据版本（s-security-hardening R5）：会话撤销的查询与失效。

- 版本写入点（+1 或哨兵）：改密码 / 改密保 / 注销执行；写入方 MUST 调 invalidate_all()
  （撤销即时生效，不等 60s TTL）。
- 查询侧带 60s 进程内缓存：devices/pay 面每请求免一趟查库；撤销最迟 60 秒生效。
- 缺失用户（uid 查无行）返回 None——调用方自行决定语义（当前一律放行给后续业务判）。
"""
from __future__ import annotations

import time

TTL = 60.0
DELETION_SENTINEL = 1  # 注销执行：PostgREST 无 col=col+1，终态行不可复活，写固定哨兵等价

_CACHE: dict[int, tuple[float, int]] = {}


def _fetch(uid: int) -> int | None:
    import logging

    from app.config import settings

    try:
        if settings.DB_BACKEND == "pg_http":
            from app.infrastructure.repositories.pg_http import get_pg_client

            rows = get_pg_client().find(
                "users", {"id": int(uid)}, select="token_version", limit=1)
            if not rows or rows[0].get("token_version") is None:
                return None
            return int(rows[0]["token_version"])
        from app.models.base import SessionLocal
        from app.models.user import UserORM

        with SessionLocal() as s:
            row = s.query(UserORM.token_version).filter(UserORM.id == int(uid)).first()
            return int(row[0]) if row else None
    except Exception as e:  # noqa: BLE001 — 版本查询失败按"无法判定"处理（fail-open）
        # 撤销比对是增强防线：网关抖动/DDL 漂移不得放大队谢绝为全站 500；
        # 其他防线（口令/grant 生命周期/注销门禁）不受影响。记 warning 供观察。
        logging.getLogger("app.security").warning(
            "event=token_version_fetch_failed uid=%s err=%s", uid, e)
        return None


def get_version(uid: int) -> int | None:
    now = time.monotonic()
    hit = _CACHE.get(uid)
    if hit is not None and now - hit[0] < TTL:
        return hit[1]
    version = _fetch(uid)
    if version is not None:
        _CACHE[uid] = (now, version)
    return version


def invalidate_all() -> None:
    """版本写入后全量失效（改密/改密保/注销属低频事件，全清代价可忽略）。"""
    _CACHE.clear()


def clear() -> None:
    """测试用：清缓存（与 invalidate_all 同义，命名区分语义）。"""
    _CACHE.clear()
