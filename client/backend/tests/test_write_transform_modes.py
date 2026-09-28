"""选区变换端点（transform 族）行为测试：/write/compress、/write/polish。

覆盖：200 路径（提示词含对应要求段、返回产物字段、记账 operation）、
缺 selected_text 400、超时 502 留败账。
（/expand 为同族存量端点；c-prose-deai 起 /polish 口径＝去AI味。）
"""

import asyncio
import os
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_client import AITimeoutError
from auth_local.deps import require_ai_access as _raa
from auth_local.deps import require_novel_model as _rnm
from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.chapter import Chapter, ChapterContent
from models.project import Novel
from models.user import User
from models.volume import Volume

REF = "vol-1-ch-1"
_UIDS: dict[str, str] = {}


async def _seed() -> tuple[str, str]:
    root = tempfile.mkdtemp(prefix="test_transform_")
    slug = f"tf-{os.path.basename(root)}"
    uid = f"tf-{os.path.basename(root)[-12:]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{slug}@test.local", password_hash="x",
            display_name="变换测试", api_key="", api_base_url="", api_model="",
        ))
        session.add(Novel(
            user_id=uid, name="变换书", slug=slug, root_path=root,
            source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(select(Novel).where(Novel.root_path == root))).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        ch = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref=REF, title="第1章", status="writing", word_count=10, has_prose=True,
        )
        session.add(ch)
        await session.flush()
        session.add(ChapterContent(chapter_id=ch.id, prose="她握紧船桨，风声很大。"))
        await session.commit()
        _UIDS[proj.id] = uid
        return root, proj.id


class _FakeClient:
    def __init__(self, capture: list):
        self._capture = capture

    async def chat(self, **kwargs):
        self._capture.append(kwargs)
        usage = kwargs.get("usage")
        if usage is not None:
            usage["tokens_in"] = 30
            usage["tokens_out"] = 12
        return "她握桨听风。"


def _client(nid: str):
    c = TestClient(app)
    c.__enter__()
    app.dependency_overrides[get_current_user] = lambda: {"id": _UIDS[nid]}
    app.dependency_overrides[_raa] = lambda: True
    app.dependency_overrides[_rnm] = lambda: True
    return c


def _post(nid: str, path: str, body: dict):
    c = _client(nid)
    try:
        return c.post(f"/api/novels/{nid}/chapters/{REF}/write{path}", json=body)
    finally:
        app.dependency_overrides.clear()


class TestCompress:
    def test_compress_200_prompt_and_usage(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        captured: list = []
        monkeypatch.setattr(
            "write.auxiliary.get_ai_client_for_novel",
            lambda *a, **k: _async_return(_FakeClient(captured)),
        )
        r = _post(nid, "/compress", {
            "selected_text": "她握紧船桨，风声很大，衣裳被吹得猎猎作响，头发也乱了。",
            "context_before": "临江渡口。",
            "context_after": "船家解缆。",
        })
        assert r.status_code == 200, r.text
        assert r.json()["compressed_text"] == "她握桨听风。"
        prompt = captured[-1]["messages"][0]["content"]
        assert "压缩要求" in prompt
        assert "她握紧船桨" in prompt

        # 记账：operation=compress
        from models.token_log import TokenLog

        async def _ops():
            async with async_session() as s:
                rows = (await s.scalars(
                    select(TokenLog).where(TokenLog.project_id == nid)
                )).all()
                return [x.operation for x in rows]

        assert "compress" in asyncio.run(_ops())

    def test_compress_missing_selection_400(self):
        _root, nid = asyncio.run(_seed())
        r = _post(nid, "/compress", {"selected_text": ""})
        assert r.status_code == 400

    def test_compress_timeout_502_with_fail_row(self, monkeypatch):
        _root, nid = asyncio.run(_seed())

        class _Timeout:
            async def chat(self, **kwargs):
                raise AITimeoutError("timeout")

        async def _fake(novel_id):
            return _Timeout()

        monkeypatch.setattr("write.auxiliary.get_ai_client_for_novel", _fake)
        r = _post(nid, "/compress", {"selected_text": "一段啰嗦的话。"})
        assert r.status_code == 502, r.text

        from models.token_log import TokenLog

        async def _ops():
            async with async_session() as s:
                rows = (await s.scalars(
                    select(TokenLog).where(TokenLog.project_id == nid)
                )).all()
                return [x.operation for x in rows]

        assert "compress_fail" in asyncio.run(_ops())


class TestPolish:
    """c-prose-deai：段落润色改「去AI味」——提示词锚定新口径＋禁用词句单源注入。"""

    def test_polish_200_prompt_and_usage(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        captured: list = []
        monkeypatch.setattr(
            "write.auxiliary.get_ai_client_for_novel",
            lambda *a, **k: _async_return(_FakeClient(captured)),
        )
        r = _post(nid, "/polish", {
            "selected_text": "她握紧船桨，风声很大，衣裳被吹得猎猎作响，头发也乱了。",
            "context_before": "临江渡口。",
            "context_after": "船家解缆。",
        })
        assert r.status_code == 200, r.text
        assert r.json()["polished_text"] == "她握桨听风。"
        prompt = captured[-1]["messages"][0]["content"]
        # 新口径锚：要求段标题＋选区原文＋禁止规则单源（未配置文风 → 「（无）」兜底）
        assert "去AI味要求" in prompt
        assert "她握紧船桨" in prompt
        assert "禁止规则" in prompt and "（无）" in prompt
        system = captured[-1]["system"]
        assert "AI 腔" in system

        # 记账：operation=polish（口径不变）
        from models.token_log import TokenLog

        async def _ops():
            async with async_session() as s:
                rows = (await s.scalars(
                    select(TokenLog).where(TokenLog.project_id == nid)
                )).all()
                return [x.operation for x in rows]

        assert "polish" in asyncio.run(_ops())

    def test_polish_missing_selection_400(self):
        _root, nid = asyncio.run(_seed())
        r = _post(nid, "/polish", {"selected_text": ""})
        assert r.status_code == 400


async def _async_return(v):
    return v
