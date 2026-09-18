"""FastAPI 依赖注入。"""
from __future__ import annotations

from typing import NamedTuple

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.infrastructure.repositories.pg_http import get_pg_client
from app.infrastructure.repositories.pg_http.client import PgRestClient
from app.infrastructure.security.jwt import verify_jwt
from app.models.base import get_db as _get_sql_db

# DB handle 联合类型：sqlite 后端为 Session，pg_http 后端为 PgRestClient
Db = Session | PgRestClient


def get_db():
    """FastAPI Depends 用：按 DB_BACKEND 产出请求级 DB handle。"""
    if settings.DB_BACKEND == "pg_http":
        yield get_pg_client()
    else:
        yield from _get_sql_db()


class CurrentUser(NamedTuple):
    """双持身份（jwt-uid-claim）：业务表键是 user_id，token 携带后零翻译直查。

    uid 为权威身份（PK 不可变）；username 仅展示/身份域把手用途。
    """

    username: str
    uid: int


def _valid_uid(payload: dict) -> int | None:
    """uid claim 合法性：int 且非 bool（jose 解 JSON 后 True 是 int 子类）。"""
    uid = payload.get("uid")
    if isinstance(uid, int) and not isinstance(uid, bool):
        return uid
    return None


def get_current_user(authorization: str = Header(default="")) -> CurrentUser:
    """解析 JWT，返回双持身份。401 如果无效或缺合法 uid（jwt-uid-claim：
    严格口径，旧格式 token 一律作废走重登；无过渡兼容）。"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证信息")
    token = authorization.replace("Bearer ", "")
    payload = verify_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="无效的令牌")
    uid = _valid_uid(payload)
    if uid is None:
        raise HTTPException(status_code=401, detail="令牌格式过期，请重新登录")
    return CurrentUser(username=payload.get("sub", ""), uid=uid)


def token_revoked(payload: dict, uid: int) -> bool:
    """凭据版本比对（s-security-hardening R5）：无 ver 声明按 0（存量令牌不误伤）。

    版本查询带 60s 进程内缓存（撤销最迟 60s 生效，写侧即时失效）；
    查无此用户返回 False（交由后续业务判定）。
    """
    from app.infrastructure.security import token_version

    expected = token_version.get_version(uid)
    if expected is None:
        return False
    return payload.get("ver", 0) != expected


def get_current_user_or_none(authorization: str = Header(default="")):
    """解析 JWT，返回 username 或 None（不抛 401）。

    刻意宽松（不要求 uid claim）：C端桌面客户端存量 token（30 天窗口、无法强刷）
    走此依赖的设备端点必须不受签发格式变更影响。
    s-security-hardening R5：携带合法 uid 且版本不符（改密/改密保/注销后）→ 视同未登录。
    """
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "")
    payload = verify_jwt(token)
    if not payload:
        return None
    uid = _valid_uid(payload)
    if uid is not None and token_revoked(payload, uid):
        return None
    return payload.get("sub", "")
