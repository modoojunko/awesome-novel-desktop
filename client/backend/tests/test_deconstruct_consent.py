"""拆书承诺与原文 TTL（c-deconstruct-compliance-guard）——签署状态机与清理。

不跑 pipeline：只测 consent 模块的状态机、幂等、五种上报结果，以及
purge_expired_sources 的到期判定与目录清理。
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

_tmp_db = tempfile.NamedTemporaryFile(suffix="_dec_consent.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_dec_consent_")
os.environ["DECONSTRUCT_DISPATCHER_OFF"] = "1"

from db import Base, async_session, engine  # noqa: E402
from deconstruct import consent  # noqa: E402
from models.deconstruct import DeconstructConsent, DeconstructJob  # noqa: E402

_UID = "consent-user"


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _ensure_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="module", autouse=True)
def _db():
    _run(_ensure_tables())
    yield


@pytest.fixture(autouse=True)
def _clean_rows():
    async def _clear():
        from sqlalchemy import delete

        async with async_session() as s:
            await s.execute(delete(DeconstructConsent))
            await s.execute(delete(DeconstructJob))
            await s.commit()

    _run(_clear())
    yield


@pytest.fixture(autouse=True)
def _as_current_user(monkeypatch):
    import auth_local.service as svc

    monkeypatch.setattr(svc, "load_or_create_config", lambda: {"username": _UID})


@pytest.fixture(autouse=True)
def _no_background_sync(monkeypatch):
    """测试里显式调 sync；不额外起后台 task（避免跨事件循环的连接告警）。"""
    monkeypatch.setattr(consent, "_schedule_sync", lambda user_id: None)


def _patch_server(monkeypatch, response: dict):
    async def fake(endpoint, method="GET", params=None, json_body=None, with_token=False):
        assert endpoint == "deconstruct/consents"
        assert method == "POST"
        assert with_token is True
        assert set(json_body or {}) == {"agreement_version", "agreement_text_sha256"}
        return response

    import auth_local.service as svc

    monkeypatch.setattr(svc, "call_server_api", fake)


def _patch_get(monkeypatch, items: list[dict] | None):
    async def fake(endpoint, method="GET", params=None, json_body=None, with_token=False):
        assert endpoint == "deconstruct/consents"
        assert method == "GET"
        assert with_token is True
        return {"code": 0, "data": {"items": items or []}}

    import auth_local.service as svc

    monkeypatch.setattr(svc, "call_server_api", fake)


def test_unsigned_then_sign_is_idempotent(monkeypatch):
    _patch_server(monkeypatch, {"code": 0, "data": {"server_ts": "2026-11-11T10:00:00"}})

    async def _go():
        async with async_session() as s:
            assert (await consent.get_status(s, _UID))["signed"] is False
            first = await consent.sign(s, _UID)
            assert first["signed"] is True
            second = await consent.sign(s, _UID)
            assert second["signed_at"] == first["signed_at"]

    _run(_go())


def test_sync_success_and_can_build(monkeypatch):
    _patch_server(monkeypatch, {"code": 0, "data": {"server_ts": "2026-11-11T10:00:00.5"}})

    async def _go():
        async with async_session() as s:
            await consent.sign(s, _UID)
        view = await consent.sync(_UID)
        assert view["sync_state"] == "synced"
        assert view["can_build"] is True
        assert view["server_ts"].startswith("2026-11-11T10:00:00")

    _run(_go())


def test_sync_maps_401_404_400_and_network(monkeypatch):
    _patch_server(monkeypatch, {"code": 0, "data": {"server_ts": "2026-11-11T10:00:00"}})

    async def _go():
        async with async_session() as s:
            await consent.sign(s, _UID)
        await consent.sync(_UID)
        for response, expected in [
            ({"code": 401}, "login"),
            ({"code": 404}, "local"),
            ({"code": 400, "msg": "版本不支持"}, "failed"),
            ({"code": -1, "msg": "网络超时"}, "pending"),
        ]:
            _patch_server(monkeypatch, response)
            async with async_session() as s:
                row = (
                    await s.scalars(
                        select(DeconstructConsent).where(
                            DeconstructConsent.user_id == _UID
                        )
                    )
                ).first()
                row.sync_state = "pending"
                await s.commit()
            view = await consent.sync(_UID)
            assert view["sync_state"] == expected, response
            if expected in ("login", "pending", "failed"):
                assert view["can_build"] is False
            if expected == "local":
                assert view["can_build"] is True

    _run(_go())


def test_sync_pending_only_current_user(monkeypatch):
    """补偿只同步当前账号；本机残留的其他账号行保持 pending，不得冒名上报。"""
    _patch_server(monkeypatch, {"code": 0, "data": {"server_ts": "2026-11-11T10:00:00"}})

    async def _go():
        async with async_session() as s:
            await consent.sign(s, _UID)
            await consent.sign(s, "consent-user-2")
        assert await consent.sync_pending() == 1
        async with async_session() as s:
            other = await consent._current(s, "consent-user-2")
            assert other.sync_state == "pending" and other.attempts == 0

    _run(_go())


def _make_source(task_id: str) -> str:
    folder = tempfile.mkdtemp(prefix=f"task_{task_id}_")
    source = os.path.join(folder, "source.txt")
    with open(source, "w", encoding="utf-8") as f:
        f.write("第1章 试\n正文。\n")
    return source


def test_purge_expired_sources_deletes_only_old():
    from deconstruct.pipeline import purge_expired_sources

    now = datetime.now(UTC).replace(tzinfo=None)
    old_src = _make_source("old")
    new_src = _make_source("new")

    async def _seed():
        async with async_session() as s:
            s.add(DeconstructJob(
                id="old", user_id=_UID, status="completed", queue_seq=1,
                book_name="旧", source_path=old_src, encoding="utf-8",
                api_config_id="c", ai_model="m",
                selected_dims_json=json.dumps(["intro"]),
                finished_at=now - timedelta(days=8),
            ))
            s.add(DeconstructJob(
                id="new", user_id=_UID, status="completed", queue_seq=2,
                book_name="新", source_path=new_src, encoding="utf-8",
                api_config_id="c", ai_model="m",
                selected_dims_json=json.dumps(["intro"]),
                finished_at=now - timedelta(days=1),
            ))
            await s.commit()

    async def _go():
        await _seed()
        purged = await purge_expired_sources(now=now)
        assert purged == 1
        assert not os.path.exists(old_src)
        assert os.path.exists(new_src)
        async with async_session() as s:
            old = await s.get(DeconstructJob, "old")
            new = await s.get(DeconstructJob, "new")
            assert old.source_purged_at is not None
            assert new.source_purged_at is None

    _run(_go())

def test_consent_text_matches_legal_doc():
    """承诺文本单一事实源：代码常量与 docs/legal 附件逐字一致，哈希自洽。"""
    import hashlib
    from pathlib import Path

    doc = Path(__file__).resolve().parents[3] / "docs" / "legal" / "拆书使用承诺-v1.md"
    body = doc.read_text(encoding="utf-8").split("\n", 2)[2]
    body = body.split("\n本承诺构成《用户服务协议》的一部分。")[0].strip()
    assert body == consent.CONSENT_TEXT
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == consent.CONSENT_TEXT_SHA256

def test_get_status_restores_from_server(monkeypatch):
    """换设备/重装：本机无记录时从 S端 GET 取回（版本+哈希都匹配）。"""
    _patch_get(monkeypatch, [{
        "version": consent.CONSENT_VERSION,
        "agreement_text_sha256": consent.CONSENT_TEXT_SHA256,
        "server_ts": "2026-11-11T10:00:00",
    }])

    async def _go():
        async with async_session() as s:
            status = await consent.get_status(s, _UID, restore=True)
            assert status["signed"] is True
            assert status["sync_state"] == "synced"
            assert status["server_ts"] == "2026-11-11T10:00:00"
            row = await consent._current(s, _UID)
            assert row is not None and row.server_ts is not None

    _run(_go())


def test_get_status_does_not_restore_hash_mismatch(monkeypatch):
    """同版本但文本哈希不同（文本改了未升版本）：不回填，按未签署要求重签。"""
    _patch_get(monkeypatch, [{
        "version": consent.CONSENT_VERSION,
        "agreement_text_sha256": "b" * 64,
        "server_ts": "2026-11-11T10:00:00",
    }])

    async def _go():
        async with async_session() as s:
            status = await consent.get_status(s, _UID, restore=True)
            assert status["signed"] is False

    _run(_go())


def test_sync_skips_other_account(monkeypatch):
    """本机残留 A 账号的签署行时，不能用 B 账号的令牌替 A 上报。"""
    _patch_server(monkeypatch, {"code": 0, "data": {"server_ts": "2026-11-11T10:00:00"}})

    async def _seed():
        async with async_session() as s:
            await consent.sign(s, _UID)

    _run(_seed())
    import auth_local.service as svc

    monkeypatch.setattr(svc, "load_or_create_config", lambda: {"username": "other-user"})
    view = _run(consent.sync(_UID))
    assert view["sync_state"] == "pending"

    async def _check():
        async with async_session() as s:
            row = await consent._current(s, _UID)
            assert row.attempts == 0  # 未发请求
            assert row.sync_state == "pending"

    _run(_check())

def test_sync_pending_retries_local(monkeypatch):
    """S端 未上线降级（local）也要重试；上线后自动转 synced（spec 场景）。"""
    _patch_server(monkeypatch, {"code": 0, "data": {"server_ts": "2026-11-11T10:00:00"}})

    async def _go():
        async with async_session() as s:
            await consent.sign(s, _UID)
            row = await consent._current(s, _UID)
            row.sync_state = "local"
            await s.commit()
        assert await consent.sync_pending() == 1
        async with async_session() as s:
            row = await consent._current(s, _UID)
            assert row.sync_state == "synced"
            assert row.server_ts is not None

    _run(_go())


def test_restore_is_idempotent_on_unique_conflict(monkeypatch):
    """并发恢复撞唯一键：捕获后返回已存在行，不 500。"""
    _patch_get(monkeypatch, [{
        "version": consent.CONSENT_VERSION,
        "agreement_text_sha256": consent.CONSENT_TEXT_SHA256,
        "server_ts": "2026-11-11T10:00:00",
    }])

    async def _go():
        async with async_session() as s:
            await consent.sign(s, _UID)
            existing = await consent._current(s, _UID)
            row = await consent._restore_from_server(s, _UID)
            assert row is not None and row.id == existing.id
            assert (await consent._current(s, _UID)).id == existing.id

    _run(_go())
