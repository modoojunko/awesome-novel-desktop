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


def test_sync_pending_processes_all(monkeypatch):
    _patch_server(monkeypatch, {"code": 0, "data": {"server_ts": "2026-11-11T10:00:00"}})

    async def _go():
        async with async_session() as s:
            await consent.sign(s, _UID)
            await consent.sign(s, "consent-user-2")
        assert await consent.sync_pending() == 2

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
