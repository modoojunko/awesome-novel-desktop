"""仓储工厂：按 DB_BACKEND 选择 SQL（SQLite）或 PG HTTP（CloudBase）实现，服务层无感知。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.infrastructure.repositories.pg_http import get_pg_client
from app.infrastructure.repositories.pg_http.code_repo import PgHttpCodeRepo
from app.infrastructure.repositories.pg_http.config_repo import PgHttpConfigRepo
from app.infrastructure.repositories.pg_http.device_repo import PgHttpDeviceRepo
from app.infrastructure.repositories.pg_http.grant_repo import PgHttpGrantRepo
from app.infrastructure.repositories.pg_http.outdated_repo import PgHttpOutdatedMarkRepo
from app.infrastructure.repositories.pg_http.user_repo import PgHttpUserRepo
from app.infrastructure.repositories.sql.code_repo import SqlCodeRepo
from app.infrastructure.repositories.sql.config_repo import SqlConfigRepo
from app.infrastructure.repositories.sql.device_repo import SqlDeviceRepo
from app.infrastructure.repositories.sql.grant_repo import SqlGrantRepo
from app.infrastructure.repositories.sql.outdated_repo import SqlOutdatedMarkRepo
from app.infrastructure.repositories.sql.user_repo import SqlUserRepo

Db = Session | object  # Session（sqlite）/ PgRestClient（pg_http），具体类型见 get_db()


def _use_pg_http() -> bool:
    return settings.DB_BACKEND == "pg_http"


def user_repo(db: Db):
    return PgHttpUserRepo(get_pg_client()) if _use_pg_http() else SqlUserRepo(db)


def code_repo(db: Db):
    return PgHttpCodeRepo(get_pg_client()) if _use_pg_http() else SqlCodeRepo(db)


def device_repo(db: Db):
    return PgHttpDeviceRepo(get_pg_client()) if _use_pg_http() else SqlDeviceRepo(db)


def grant_repo(db: Db):
    return PgHttpGrantRepo(get_pg_client()) if _use_pg_http() else SqlGrantRepo(db)


def outdated_mark_repo(db: Db):
    return PgHttpOutdatedMarkRepo(get_pg_client()) if _use_pg_http() else SqlOutdatedMarkRepo(db)


def config_repo(db: Db):
    return PgHttpConfigRepo(get_pg_client()) if _use_pg_http() else SqlConfigRepo(db)
