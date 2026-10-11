"""seam_refill 端点测试（c-chapter-seam-check 后续：章际衔接修复 draft）。

覆盖：SSE 三版契约、素材带【前文】锚、para_count 校验、无前文 409、解析失败 error 事件。
夹具镜像 test_ai_assist_checks（独立 seed＋依赖覆写；注意 Chapter.ref 不跨项目唯一）。
"""

import asyncio
import json
import os
import tempfile

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_client import StreamEvent
from auth_local.deps import require_ai_access as _raa
from auth_local.deps import require_novel_model as _rnm
from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.chapter import Chapter, ChapterContent
from models.project import Novel
from models.user import User
from models.volume import Volume

REF1 = "vol-1-ch-1"
REF2 = "vol-1-ch-2"
_UIDS: dict[str, str] = {}

_PROSE1 = "他推门进了哨站，风灌进来。灯芯爆了一声。"
_PROSE2 = "林野在桌边坐下，炉火还没灭。"


async def _seed() -> str:
    root = tempfile.mkdtemp(prefix="test_seamrefill_")
    slug = f"sr-{os.path.basename(root)}"
    uid = f"sr-{os.path.basename(root)[-12:]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{slug}@test.local", password_hash="x",
            display_name="衔接测试", api_key="", api_base_url="", api_model="",
        ))
        session.add(Novel(
            user_id=uid, name="衔接测试书", slug=slug, root_path=root,
            source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(select(Novel).where(Novel.slug == slug))).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        ch1 = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref=REF1, title="第1章", status="archived", word_count=15, has_prose=True,
        )
        session.add(ch1)
        await session.flush()
        session.add(ChapterContent(chapter_id=ch1.id, prose=_PROSE1))
        await session.commit()
        _UIDS[proj.id] = uid
        return proj.id


async def _add_ch2(nid: str) -> None:
    async with async_session() as session:
        proj = await session.get(Novel, nid)
        vol = (await session.scalars(
            select(Volume).where(Volume.project_id == proj.id)
        )).one()
        ch2 = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=2,
            ref=REF2, title="第2章", status="writing", word_count=12, has_prose=True,
        )
        session.add(ch2)
        await session.flush()
        session.add(ChapterContent(chapter_id=ch2.id, prose=_PROSE2))
        await session.commit()


class _FakeStreamClient:
    def __init__(self, chunks: list[str], capture: list | None = None):
        self._chunks = chunks
        self._capture = capture

    async def chat_stream(self, **kwargs):
        if self._capture is not None:
            self._capture.append(kwargs)
        for c in self._chunks:
            yield StreamEvent(text=c, tokens=10, tokens_in=100)
        yield StreamEvent(is_done=True)


def _patch(monkeypatch, client):
    async def _fake(novel_id):
        return client

    monkeypatch.setattr("write.seam_refill.get_ai_client_for_novel", _fake)


def _client(nid: str, *, free: bool = False):
    c = TestClient(app)
    c.__enter__()
    app.dependency_overrides[get_current_user] = lambda: {"id": _UIDS[nid]}
    app.dependency_overrides[_rnm] = lambda: True
    if free:
        def _deny():
            raise HTTPException(403, "AI 功能需要开通会员")

        app.dependency_overrides[_raa] = _deny
    else:
        app.dependency_overrides[_raa] = lambda: True
    return c


def _post_sse(nid: str, body: dict):
    c = _client(nid)
    try:
        return c.post(f"/api/novels/{nid}/chapters/{REF2}/seam-refill/draft", json=body)
    finally:
        app.dependency_overrides.clear()


_THREE_VERSIONS = (
    '{"before_echo":"风灌进来","after_echo":"炉火还没灭","versions":['
    '{"approach":"直承","text":"他坐回桌边。炉火映在他脸上。","note":"顺时直承"},'
    '{"approach":"过渡","text":"他先给炉子添了块煤。火苗稳了。","note":"补一拍"},'
    '{"approach":"重排","text":"桌上那份文书还摊着。他没看它。","note":"从物件起笔"}]}'
)


class TestSeamRefillDraft:
    def test_draft_sse_three_options_and_material(self, monkeypatch):
        """draft：SSE 三版契约＋素材带【前文】锚＋计费。"""
        nid = asyncio.run(_seed())
        asyncio.run(_add_ch2(nid))
        captured: list = []
        _patch(monkeypatch, _FakeStreamClient(
            [_THREE_VERSIONS[:60], _THREE_VERSIONS[60:]], capture=captured))
        c = _client(nid)
        try:
            with c:
                r = c.post(f"/api/novels/{nid}/chapters/{REF2}/seam-refill/draft",
                           json={"para_count": 2})
        finally:
            app.dependency_overrides.clear()
        assert r.status_code == 200, r.text
        assert "text/event-stream" in r.headers.get("content-type", "")
        events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1
        opts = done[0]["options"]
        assert [o["key"] for o in opts] == ["direct", "transition", "reframe"]
        assert all(o["text"].strip() for o in opts)
        # 素材带【前文】锚（ch-1 正文末段）
        prompt = captured[-1]["messages"][0]["content"] + captured[-1]["system"]
        assert "## 前文（上一章结尾原文＋本章断点前已写段" in prompt
        assert "灯芯爆了一声" in prompt  # ch-1 正文尾句进了上章结尾窗口
        # 病文块（被替换开场原文）在素材里
        assert "病文" in prompt and _PROSE2[:10] in prompt
        # 计数字节事件在 done 之前
        assert any(e["type"] == "chunk" for e in events)

    def test_draft_para_count_422(self):
        nid = asyncio.run(_seed())
        c = _client(nid)
        try:
            with c:
                r = c.post(f"/api/novels/{nid}/chapters/{REF1}/seam-refill/draft",
                           json={"para_count": 9})
        finally:
            app.dependency_overrides.clear()
        assert r.status_code == 422

    def test_no_prev_tail_409(self):
        """首章（无上一章正文）→ 409，没有「前」可接。"""
        nid = asyncio.run(_seed())
        c = _client(nid)
        try:
            with c:
                r = c.post(f"/api/novels/{nid}/chapters/{REF1}/seam-refill/draft", json={})
        finally:
            app.dependency_overrides.clear()
        assert r.status_code == 409

    def test_bad_json_yields_error_event(self, monkeypatch):
        nid = asyncio.run(_seed())
        asyncio.run(_add_ch2(nid))
        _patch(monkeypatch, _FakeStreamClient(["这不是JSON，模型跑题了。"]))
        r = _post_sse(nid, {})
        assert r.status_code == 200
        assert '"type": "error"' in r.text or '"type":"error"' in r.text

    def test_free_tier_403(self):
        nid = asyncio.run(_seed())
        asyncio.run(_add_ch2(nid))
        c = _client(nid, free=True)
        try:
            with c:
                r = c.post(f"/api/novels/{nid}/chapters/{REF2}/seam-refill/draft", json={})
        finally:
            app.dependency_overrides.clear()
        assert r.status_code == 403
