# backend/db.py
"""SQLAlchemy async engine — 本地 SQLite"""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL

engine = create_async_engine(
    DATABASE_URL, echo=False, connect_args={"check_same_thread": False}
)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    # WAL：编辑器自动保存高频小事务下读写不互斥，崩溃恢复更稳
    cursor.execute("PRAGMA journal_mode=WAL")
    # 写写并发（两个 session 紧邻提交）时等锁而非立刻报 "database is locked"
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
