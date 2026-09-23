"""c-ai-usage-correctness — 记账/埋点 SAVEPOINT 化

- record_usage / log_event_async 写入失败只回滚自身 SAVEPOINT，
  同会话主流程已暂存的写入 MUST NOT 被连带回滚；失败留 warning 日志。
"""

import logging

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from db import async_session
from models.app_meta import AppMeta
from models.user import User

USER_ID = "usg_user"


def _run_async(coro):
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module", autouse=True)
def _seed_user():
    async def _run():
        async with async_session() as session:
            if await session.get(User, USER_ID) is None:
                session.add(
                    User(id=USER_ID, email=f"{USER_ID}@test.com",
                         password_hash="*", display_name=USER_ID)
                )
                await session.commit()

    _run_async(_run())
    yield


def test_record_usage_fk_failure_keeps_pending_main_write(caplog):
    from api_configs.usage import record_usage

    caplog.set_level(logging.WARNING)

    async def _run():
        async with async_session() as db:
            db.add(AppMeta(key="probe-main-write", value="1"))  # 主流程暂存写入
            # 记账指向不存在的用户 → FK 失败：不得抛出、不得连带回滚主写入
            await record_usage(db, user_id="ghost-user", operation="write_chapter",
                               model="haiku", tokens_in=5, tokens_out=7)
            await db.commit()
            saved = await db.get(AppMeta, "probe-main-write")
            return saved is not None

    assert _run_async(_run()) is True
    assert any("usage.write_failed" in r.message for r in caplog.records)


def test_record_usage_success_writes_row():
    from api_configs.usage import record_usage
    from models.token_log import TokenLog

    async def _run():
        async with async_session() as db:
            await record_usage(db, user_id=USER_ID, operation="write_chapter_probe",
                               model="haiku", tokens_in=11, tokens_out=13)
            return (
                await db.scalars(
                    select(TokenLog).where(
                        TokenLog.user_id == USER_ID,
                        TokenLog.operation == "write_chapter_probe",
                    )
                )
            ).first()

    row = _run_async(_run())
    assert row is not None and row.tokens_in == 11 and row.tokens_out == 13


def test_log_event_async_failure_keeps_pending_main_write(monkeypatch, caplog):
    """埋点会话 commit 失败：只回滚埋点自身，调用方会话的主写入存活。"""
    import novels.events as events_mod

    class _BoomSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def add(self, obj):
            pass

        async def commit(self):
            raise OperationalError("events", {}, "boom")

        async def rollback(self):
            pass

    monkeypatch.setattr(events_mod, "events_enabled", lambda: True)
    import db as db_mod

    monkeypatch.setattr(db_mod, "async_session", lambda: _BoomSession())
    caplog.set_level(logging.WARNING)

    async def _run():
        async with async_session() as db:
            db.add(AppMeta(key="probe-event-main-write", value="1"))
            await events_mod.log_event_async(db, user_id=USER_ID,
                                             event_type="probe_event", payload={"k": "v"})
            await db.commit()
            return await db.get(AppMeta, "probe-event-main-write")

    assert _run_async(_run()) is not None
    assert any("metrics.write_failed" in r.message for r in caplog.records)
