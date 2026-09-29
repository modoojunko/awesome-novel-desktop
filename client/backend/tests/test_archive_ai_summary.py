"""归档 AI 链的开关与记账（c-chapter-dossier 受理制后的新矩阵）

新契约：模型就绪 → 受理返回 extracting，提取（一次四域）＋摘要在后台线程；
ai_summary=False 只关摘要（提取照跑）；提取不挂会员门（免费 BYOK 照跑）；
模型未就绪 → 同步放行归档（无章档、摘要降级）。

用法：
    cd client/backend
    python -m pytest tests/test_archive_ai_summary.py -v
"""

import asyncio
import json
import os
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

# ── Test environment (isolated temp DB) ───────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_archive_ai_summary.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_archive_ai_summary_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")


def _set_tier(tier: str, expires_at: str = ""):
    _service.CONFIG_FILE = _CFG_PATH
    _service.save_local_config({"tier": tier, "expires_at": expires_at, "api_key": ""})


def _future_iso(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


from auth_local.deps import require_novel_model, require_project_limit
from auth_local.middleware import get_current_user
from db import Base, async_session, engine, get_db
from main import app
from models.user import User


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _create_user(user_id: str) -> str:
    async with async_session() as session:
        session.add(
            User(
                id=user_id,
                email=f"{user_id}@test.com",
                password_hash="*",
                display_name=user_id,
            )
        )
        await session.commit()
    return user_id


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    _run_async(_create_tables())
    _run_async(_create_user("archai"))
    yield


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": "archai"}


async def _override_true():
    return True


@pytest.fixture(autouse=True)
def _setup_overrides():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = _override_true
    # 旧收尾提案（伏笔/lore）与本文件无关——钉住防后台线程加戏干扰记账断言
    import archive.dossier as _d

    _orig_reconcile = _d._maybe_start_reconcile
    _d._maybe_start_reconcile = lambda *a, **k: None
    yield
    _d._maybe_start_reconcile = _orig_reconcile
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_config_after():
    yield
    if os.path.exists(_CFG_PATH):
        os.remove(_CFG_PATH)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _create_sparse_project(client) -> str:
    name = f"archai-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), f"Create failed: {r.text}"
    return r.json()["id"]


def _create_volume_and_chapter(client, pid: str) -> str:
    r = client.post(
        f"/api/novels/{pid}/volumes", json={"vol_num": 1, "title": "Volume 1"}
    )
    assert r.status_code in (200, 201)
    r2 = client.post(
        f"/api/novels/{pid}/volumes/{r.json()['ref']}/chapters",
        json={"title": "第1章"},
    )
    assert r2.status_code in (200, 201)
    return r2.json()["chapter_ref"]


LONG_TEXT = "（归档正文）灯火在雨里摇晃，她合上日志，决定明日启程。行囊里只有半册旧书，与一枚磨亮的铜哨。" * 20

AI_SUMMARY = "（AI 摘要）她合上日志决定明日启程。"

EXTRACT_OK = json.dumps({
    "settings": [], "relations": [],
    "items": [{"name": "铜哨", "change_type": "obtain", "holder": "她",
               "detail": "行囊里的铜哨", "evidence": "一枚磨亮的铜哨"}],
    "knowledge": [],
}, ensure_ascii=False)


class _FakeAIClient:
    """按调用序返回预制应答（默认：提取 JSON → 摘要）。"""

    def __init__(self, calls: list, replies=None):
        self._calls = calls
        self.replies = list(replies or [EXTRACT_OK, AI_SUMMARY])

    async def chat(self, **kwargs):
        self._calls.append("chat")
        usage = kwargs.get("usage")
        if usage is not None:
            # 贴真客户端契约：成功调用回填 provider usage（记账数据源）
            usage["tokens_in"] = 30
            usage["tokens_out"] = 12
        reply = self.replies.pop(0) if self.replies else AI_SUMMARY
        if isinstance(reply, Exception):
            raise reply
        return reply


def _patch_model(monkeypatch, fake):
    import ai_client

    async def _fake_get(novel_id=None):
        return fake

    monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_get)


def _wait_archived(pid: str, ref: str, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _run_async(_chapter_status(pid, ref))
        if status == "archived":
            return
        time.sleep(0.05)
    raise AssertionError(f"chapter 未归档: {status}")


def _wait_job_failed(pid: str, ref: str, timeout=15.0):
    deadline = time.time() + timeout
    state = None
    while time.time() < deadline:
        state = _run_async(_job_state(pid, ref))
        if state == "failed":
            return
        time.sleep(0.05)
    raise AssertionError(f"job 未失败: {state}")


async def _chapter_status(pid: str, ref: str):
    from models.chapter import Chapter

    async with async_session() as s:
        ch = (
            await s.scalars(
                select(Chapter).where(
                    Chapter.project_id == pid, Chapter.ref == ref
                )
            )
        ).first()
        return ch.status if ch else None


async def _job_state(pid: str, ref: str):
    from models.chapter import Chapter, ChapterDossierJob

    async with async_session() as s:
        job = (
            await s.scalars(
                select(ChapterDossierJob)
                .join(Chapter, Chapter.id == ChapterDossierJob.chapter_id)
                .where(Chapter.project_id == pid, Chapter.ref == ref)
            )
        ).first()
        return job.state if job else None


def _token_ops(pid: str):
    from models.token_log import TokenLog

    async def _ops():
        async with async_session() as session:
            rows = await session.execute(
                select(TokenLog).where(TokenLog.project_id == pid)
            )
            return {(row.operation, row.tokens_in, row.tokens_out)
                    for row in rows.scalars()}

    return _run_async(_ops())


class TestArchiveAiChain:
    def test_member_default_extracts_and_summarizes(self, client, monkeypatch):
        # 会员 + 默认 → 后台两段 AI：提取（四域）＋摘要
        _set_tier("monthly", _future_iso())
        calls: list = []
        _patch_model(monkeypatch, _FakeAIClient(calls))

        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive", json={"full_text": LONG_TEXT}
        )
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "extracting" and r.json()["model_ready"] is True
        _wait_archived(pid, ref)
        assert calls == ["chat", "chat"], "提取一次＋摘要一次"

    def test_member_opt_out_still_extracts_but_degrades_summary(self, client, monkeypatch):
        # ai_summary=False → 摘要降级前 200 字，提取照跑（解耦）
        _set_tier("monthly", _future_iso())
        calls: list = []
        _patch_model(monkeypatch, _FakeAIClient(calls, replies=[EXTRACT_OK]))

        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive",
            json={"full_text": LONG_TEXT, "ai_summary": False},
        )
        assert r.status_code == 200, r.text
        _wait_archived(pid, ref)
        assert calls == ["chat"], "只有提取一次，摘要零调用"

    def test_ai_calls_record_usage(self, client, monkeypatch):
        _set_tier("monthly", _future_iso())
        calls: list = []
        _patch_model(monkeypatch, _FakeAIClient(calls))

        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive", json={"full_text": LONG_TEXT}
        )
        assert r.status_code == 200, r.text
        _wait_archived(pid, ref)
        assert _token_ops(pid) == {
            ("archive_extract", 30, 12),
            ("archive_summary", 30, 12),
        }

    def test_extract_failure_records_fail_and_blocks_archive(self, client, monkeypatch):
        # 提取失败：归档被阻（新契约），记账落 fail 行（force 零 token）
        _set_tier("monthly", _future_iso())

        class _BoomClient:
            async def chat(self, **_kwargs):
                raise RuntimeError("供应商 5xx")

        import ai_client

        async def _fake_get(novel_id=None):
            return _BoomClient()

        monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_get)

        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive", json={"full_text": LONG_TEXT}
        )
        assert r.status_code == 200 and r.json()["state"] == "extracting"
        _wait_job_failed(pid, ref)
        assert _run_async(_chapter_status(pid, ref)) != "archived"
        assert _token_ops(pid) == {("archive_extract_fail", 0, 0)}

    def test_free_tier_with_model_still_extracts(self, client, monkeypatch):
        # 免费档 + 本书模型就绪 → 提取照跑（BYOK 全档，c-chapter-dossier 拍板 10）
        _set_tier("none")
        calls: list = []
        _patch_model(monkeypatch, _FakeAIClient(calls))

        pid = _create_sparse_project(client)
        ref = _create_volume_and_chapter(client, pid)
        r = client.post(
            f"/api/novels/{pid}/chapters/{ref}/archive", json={"full_text": LONG_TEXT}
        )
        assert r.status_code == 200, r.text
        assert r.json()["model_ready"] is True
        _wait_archived(pid, ref)
        _deadline = time.time() + 5
        while len(calls) < 2 and time.time() < _deadline:
            time.sleep(0.05)
        assert calls == ["chat", "chat"]
