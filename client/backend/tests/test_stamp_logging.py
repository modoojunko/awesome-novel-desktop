"""c-db-version-hardening — 打戳失败必须可见（不静默吞）

打戳（schema 指纹/版本快照写入 app_meta）失败时 MUST 记 error 日志且不阻断启动；
成功路径不产生 error 噪声。
"""

import logging

import pytest
from sqlalchemy.exc import OperationalError

import main as main_mod


class _ExplodingSession:
    """async_session() 替身：进入即抛（只读挂载/库被独占的模拟）。"""

    async def __aenter__(self):
        raise OperationalError("PRAGMA", {}, "database is locked")

    async def __aexit__(self, *args):
        return False

    def __call__(self):
        return self


@pytest.fixture
def caplog_stamp(caplog):
    caplog.set_level(logging.ERROR, logger="uvicorn.error")
    return caplog


@pytest.mark.anyio
async def test_stamp_failure_logs_error_and_does_not_raise(caplog_stamp, monkeypatch):
    monkeypatch.setattr(main_mod, "async_session", _ExplodingSession)
    await main_mod.stamp_current_library("fp-x")  # MUST NOT raise
    msgs = [r for r in caplog_stamp.records if r.message.startswith("event=app.stamp result=fail")]
    assert msgs, "打戳失败必须留 error 日志（下次启动 mismatch 的前因）"
    assert "db=" in msgs[0].getMessage() and "hint=" in msgs[0].getMessage()


@pytest.mark.anyio
async def test_stamp_success_no_error_noise(caplog_stamp, monkeypatch):
    monkeypatch.setattr(main_mod, "async_session", main_mod.async_session)  # 真 session（测试库）
    await main_mod.stamp_current_library("fp-ok")
    errs = [r for r in caplog_stamp.records if r.message.startswith("event=app.stamp result=fail")]
    assert not errs
