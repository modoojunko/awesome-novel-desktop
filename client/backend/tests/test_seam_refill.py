"""seam_refill 端点测试（c-chapter-seam-check 后续：章际衔接修复 draft）。

覆盖：SSE 三版契约、素材带【前文】锚、para_count 校验、无前文 409、解析失败 error 事件。
夹具镜像 test_ai_assist_checks（独立 seed＋依赖覆写；注意 Chapter.ref 不跨项目唯一）。
"""

import asyncio
import json
import logging
import os
import tempfile

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

import pytest

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

pytestmark = [pytest.mark.needs_prompts]
from write import seam_refill

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


async def _add_ch2(nid: str, prose: str = _PROSE2) -> None:
    async with async_session() as session:
        proj = await session.get(Novel, nid)
        vol = (await session.scalars(
            select(Volume).where(Volume.project_id == proj.id)
        )).one()
        ch2 = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=2,
            ref=REF2, title="第2章", status="writing",
            word_count=len(prose), has_prose=True,
        )
        session.add(ch2)
        await session.flush()
        session.add(ChapterContent(chapter_id=ch2.id, prose=prose))
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


class _FakeSeqStreamClient:
    """按轮换稿的流式桩：第 n 次 chat_stream 返回 responses[n]（耗尽后重复末条）。"""

    def __init__(self, responses: list[str], capture: list | None = None):
        self._responses = responses
        self._capture = capture
        self.calls = 0

    async def chat_stream(self, **kwargs):
        self.calls += 1
        if self._capture is not None:
            self._capture.append(kwargs)
        idx = min(self.calls - 1, len(self._responses) - 1)
        yield StreamEvent(text=self._responses[idx], tokens=10, tokens_in=100)
        yield StreamEvent(is_done=True)


def _draft_payload(before_echo: str, after_echo: str, versions: list[tuple[str, str]]) -> str:
    """构造方案 JSON：versions=[(approach, text), ...]（note 占位）。"""
    return json.dumps(
        {
            "before_echo": before_echo,
            "after_echo": after_echo,
            "versions": [
                {"approach": a, "text": t, "note": "占位"} for a, t in versions
            ],
        },
        ensure_ascii=False,
    )


def _events(r) -> list[dict]:
    return [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]


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


_CLEAN_VERSIONS = [
    ("直承", "他坐回桌边。炉火映在他脸上。"),
    ("过渡", "他先给炉子添了块煤。火苗稳了。"),
    ("重排", "桌上那份文书还摊着。他没看它。"),
]


class TestSeamValidationChain:
    """输出校验链（W3/W1/W2）：echo 对拍＋重试、污染判负、预览对拍、句界剪尾。"""

    def test_echo_valid_but_overlong_passes_without_retry(self, monkeypatch, caplog):
        """W1：echo 归一化子串成立即过；超 20 字只 warning，不重试。"""
        nid = asyncio.run(_seed())
        long_after = "天黑透的时候他终于回来了，带着一身寒气和半句没说完的话。炉子早灭了。"
        asyncio.run(_add_ch2(nid, prose="旧开场占位一行。\n" + long_after))
        payload = _draft_payload("风灌进来", long_after[:24], _CLEAN_VERSIONS)
        client = _FakeSeqStreamClient([payload])
        _patch(monkeypatch, client)
        with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
            r = _post_sse(nid, {"para_count": 1})
        assert r.status_code == 200, r.text
        events = _events(r)
        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1 and len(done[0]["options"]) == 3
        assert not any(e["type"] == "error" for e in events)
        assert client.calls == 1  # 超长仅告警，不烧重试
        assert "seam_refill_echo_overlong" in caplog.text

    def test_echo_mismatch_retries_once_then_done(self, monkeypatch):
        """W3：echo 对拍不符→带错误信息重试一次；重试素材回注失败原因＋上一轮各版前120字。"""
        nid = asyncio.run(_seed())
        asyncio.run(_add_ch2(nid))
        bad = _draft_payload("这句话哪里都不在", "炉火还没灭", [
            ("直承", "第一轮的开头写天气。第二句继续铺垫。"),
            ("过渡", "第一轮补一拍过场。再接后文。"),
            ("重排", "第一轮从物件起笔。收在动作。"),
        ])
        good = _draft_payload("风灌进来", "炉火还没灭", _CLEAN_VERSIONS)
        captured: list = []
        client = _FakeSeqStreamClient([bad, good], capture=captured)
        _patch(monkeypatch, client)
        c = _client(nid)
        try:
            with c:
                r = c.post(f"/api/novels/{nid}/chapters/{REF2}/seam-refill/draft",
                           json={"para_count": 2})
        finally:
            app.dependency_overrides.clear()
        assert r.status_code == 200
        events = _events(r)
        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1 and len(done[0]["options"]) == 3
        assert not any(e["type"] == "error" for e in events)
        assert client.calls == 2
        retry_user = captured[1]["messages"][0]["content"]
        assert "上一轮方案已作废" in retry_user
        assert "before_echo与前文原文对不上" in retry_user
        assert "第一轮的开头写天气" in retry_user  # 上一轮直承版前 120 字回注

    def test_echo_wrong_twice_yields_error_event(self, monkeypatch):
        """W3：echo 两次不符→error 事件收尾（终态必达，无 done）。"""
        nid = asyncio.run(_seed())
        asyncio.run(_add_ch2(nid))
        bad = _draft_payload("这句话哪里都不在", "炉火还没灭", _CLEAN_VERSIONS)
        client = _FakeSeqStreamClient([bad, bad])
        _patch(monkeypatch, client)
        r = _post_sse(nid, {"para_count": 2})
        assert r.status_code == 200
        events = _events(r)
        errors = [e for e in events if e["type"] == "error"]
        assert len(errors) == 1 and "可重试" in errors[0]["error"]
        assert not any(e["type"] == "done" for e in events)
        assert client.calls == 2

    def test_contaminated_version_dropped_others_kept(self, monkeypatch):
        """W3：与前文公共子串 ≥15 字判负；存活版照常 done（三选一变二选一），不重试。"""
        nid = asyncio.run(_seed())
        asyncio.run(_add_ch2(nid))
        polluted = _PROSE1 + "他数着当天的变化。"  # 整段复述前文（20 字 ≥15）
        payload = _draft_payload("风灌进来", "炉火还没灭", [
            ("直承", polluted),
            *_CLEAN_VERSIONS[1:],
        ])
        client = _FakeSeqStreamClient([payload])
        _patch(monkeypatch, client)
        r = _post_sse(nid, {"para_count": 2})
        assert r.status_code == 200
        events = _events(r)
        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1
        keys = [o["key"] for o in done[0]["options"]]
        assert keys == ["transition", "reframe"]  # 污染的直承版被丢，其余保留
        assert client.calls == 1

    def test_rejected_preview_overlap_dropped(self, monkeypatch):
        """W2：判负对拍范围＝注入模板的同一段 120 字预览；新版复用其中 ≥30 字判负。"""
        nid = asyncio.run(_seed())
        asyncio.run(_add_ch2(nid))
        run = "夜里哨站的灯忽明忽暗，他数着墙上的刻痕等天亮，谁也没有说话。风雪夜。"  # 34 字
        filler = "他记得那晚炉膛的余温，记得门轴的响动，记得巡更表上停住的时刻。"
        rejected_text = (run + filler) * 2  # >120 字，run 位于前 120 字预览内
        payload = _draft_payload("风灌进来", "炉火还没灭", [
            ("直承", "他记得那个晚上。" + run + "一切都过去了。"),
            *_CLEAN_VERSIONS[1:],
        ])
        captured: list = []
        client = _FakeSeqStreamClient([payload], capture=captured)
        _patch(monkeypatch, client)
        r = _post_sse(nid, {"para_count": 2,
                            "rejected": [{"approach": "直承", "text": rejected_text}]})
        assert r.status_code == 200
        events = _events(r)
        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1
        keys = [o["key"] for o in done[0]["options"]]
        assert keys == ["transition", "reframe"]  # 复用预览的直承版判负
        assert client.calls == 1
        # 注入口径：模板收到的是前 120 字预览（W2 对拍与注入同源）
        assert rejected_text[:20] in captured[0]["messages"][0]["content"]

    def test_tail_overlap_with_after_clipped_and_kept(self, monkeypatch):
        """W3：版末与后文首句重叠 ≥6 字剪尾；剪后非空保留，不重试。"""
        nid = asyncio.run(_seed())
        asyncio.run(_add_ch2(
            nid, prose="旧开场占位一行。\n他抬头看门。林晓推开门走进来，屋里一片狼藉。"))
        payload = _draft_payload("风灌进来", "他抬头看门", [
            ("直承", "他数着刻痕。他抬头看门。"),  # 末尾＝后文首句前 6 字
            *_CLEAN_VERSIONS[1:],
        ])
        client = _FakeSeqStreamClient([payload])
        _patch(monkeypatch, client)
        r = _post_sse(nid, {"para_count": 1})
        assert r.status_code == 200
        events = _events(r)
        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1 and len(done[0]["options"]) == 3
        assert done[0]["options"][0]["text"] == "他数着刻痕。"  # 重叠尾被剪且非空
        assert client.calls == 1


class TestSeamValidators:
    """纯函数钉子：归一化、公共子串、污染标记判负。"""

    def test_norm_unifies_whitespace_and_quotes(self):
        assert seam_refill._norm("  “他 说”\n") == '"他说"'
        assert seam_refill._norm("") == ""

    def test_lcs_len_basics(self):
        assert seam_refill._longest_common_substring_len("abcdxyz", "xyzabcd") == 4
        assert seam_refill._longest_common_substring_len("abc", "xyz") == 0
        assert seam_refill._longest_common_substring_len("", "abc") == 0

    def test_validate_options_pollution_marker_rejects(self):
        opts = [{"key": "direct", "label": "直承", "how": "", "text": "```json\n{}"}]
        kept, warns = seam_refill._validate_options(opts, "前文素材", "后文素材", [])
        assert kept == [] and warns and "直承" in warns[0]

    def test_validate_options_empty_rejected_previews_pass(self):
        opts = [{"key": "direct", "label": "直承", "how": "", "text": "他坐回桌边。"}]
        kept, warns = seam_refill._validate_options(opts, "", "", [])
        assert len(kept) == 1 and warns == []
