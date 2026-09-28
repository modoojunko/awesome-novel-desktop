"""AI 辅助三件套后端行为测试：ai-check（六类案头检查）／章纲缺项补全／提示词精修。

矩阵：
- ai-check：六类各自材料与返回解析、未知类别 400、非 JSON 回空 findings、
  关系类素材取自真表、超时 502 留败账、免费档门控 403
- fill-gaps：白名单过滤（越界键丢弃/空值丢弃）、缺 missing 400、全不合法 400、
  返回非法 JSON 502、超时 502
- refine：两模式提示词含各自指令与现有提示词、未传 current 时以服务端组装稿为基底、
  未知模式 400、超时 502 留败账、产物不落库（提示词存储保持原样）
"""

import asyncio
import os
import tempfile

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_client import AITimeoutError
from auth_local.deps import require_ai_access as _raa
from auth_local.deps import require_novel_model as _rnm
from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.chapter import Chapter, ChapterCharacter, ChapterContent
from models.character import Character, CharacterRelation
from models.project import Novel
from models.user import User
from models.volume import Volume


def _layered_prompt(kwargs) -> str:
    """分层协议下的全文（system＋user 合并读）。"""
    return str(kwargs.get("system") or "") + "\n" + str(kwargs["messages"][0]["content"])


REF = "vol-1-ch-1"
_UIDS: dict[str, str] = {}


async def _seed() -> tuple[str, str]:
    root = tempfile.mkdtemp(prefix="test_aiassist_")
    slug = f"aa-{os.path.basename(root)}"
    uid = f"aa-{os.path.basename(root)[-12:]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{slug}@test.local", password_hash="x",
            display_name="辅助测试", api_key="", api_base_url="", api_model="",
        ))
        session.add(Novel(
            user_id=uid, name="辅助书", slug=slug, root_path=root,
            source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(select(Novel).where(Novel.root_path == root))).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        ch = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref=REF, title="第1章", status="writing", word_count=20, has_prose=True,
        )
        session.add(ch)
        await session.flush()
        session.add(ChapterContent(
            chapter_id=ch.id, prose="她握紧船桨，风声很大。船家说渡口明早封江。"
        ))
        session.add(ChapterCharacter(chapter_id=ch.id, sort_order=1, character_name="林晚"))
        c1 = Character(novel_id=proj.id, seq=1, name="林晚")
        c2 = Character(novel_id=proj.id, seq=2, name="老聋")
        session.add(c1)
        session.add(c2)
        await session.flush()
        session.add(CharacterRelation(
            novel_id=proj.id, owner_id=c1.id, other_id=c2.id,
            rel_type="师徒", stance="信任",
        ))
        await session.commit()
        _UIDS[proj.id] = uid
        return root, proj.id


class _FakeClient:
    def __init__(self, reply: str, capture: list | None = None, error: Exception | None = None):
        self._reply = reply
        self._capture = capture
        self._error = error

    async def chat(self, **kwargs):
        if self._capture is not None:
            self._capture.append(kwargs)
        if self._error is not None:
            raise self._error
        usage = kwargs.get("usage")
        if usage is not None:
            usage["tokens_in"] = 30
            usage["tokens_out"] = 12
        return self._reply


def _patch(monkeypatch, module: str, client):
    async def _fake(novel_id):
        return client

    monkeypatch.setattr(f"{module}.get_ai_client_for_novel", _fake)


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


def _post(nid: str, path: str, body: dict, *, free: bool = False):
    c = _client(nid, free=free)
    try:
        return c.post(f"/api/novels/{nid}/chapters/{REF}/{path}", json=body)
    finally:
        app.dependency_overrides.clear()


def _ops(nid: str) -> list[str]:
    from models.token_log import TokenLog

    async def _q():
        async with async_session() as s:
            rows = (await s.scalars(
                select(TokenLog).where(TokenLog.project_id == nid)
            )).all()
            return [x.operation for x in rows]

    return asyncio.run(_q())


FINDINGS_JSON = (
    '{"findings": [{"title": "第3段", "detail": "人称从第三人称滑到第一人称"},'
    ' {"title": "", "detail": "标题缺失被丢弃"},'
    ' {"title": "渡口时间", "detail": "与卷纲的封江时间冲突"}]}'
)


class TestAiCheck:
    def test_six_kinds_200_and_prompt(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        cases = {
            "volume_conflict": "本卷卷纲",
            "relations_conflict": "全书角色关系",
            "hooks_conflict": "活跃伏笔台账",
            "style_consistency": "全书文风基线",
            "style_deviations": "逐条引用原文片段",
            "relation_suggest": "建议「全书角色关系」",
        }
        for kind, anchor in cases.items():
            captured: list = []
            _patch(monkeypatch, "write.ai_check", _FakeClient(FINDINGS_JSON, captured))
            r = _post(nid, "ai-check", {"kind": kind})
            assert r.status_code == 200, f"{kind}: {r.text}"
            body = r.json()
            assert body["kind"] == kind
            # 空标题条目被丢弃，其余两条保留
            assert len(body["findings"]) == 2
            assert body["findings"][0]["title"] == "第3段"
            prompt = captured[-1]["messages"][0]["content"] + captured[-1]["system"]  # 分层后指令在 system
            assert anchor in prompt, f"{kind} 素材缺失：{anchor}"

    def test_relations_material_from_real_tables(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, "write.ai_check", _FakeClient(FINDINGS_JSON, captured))
        r = _post(nid, "ai-check", {"kind": "relations_conflict"})
        assert r.status_code == 200, r.text
        prompt = _layered_prompt(captured[-1])
        assert "林晚 → 老聋" in prompt and "师徒" in prompt

    def test_unknown_kind_400(self):
        _root, nid = asyncio.run(_seed())
        r = _post(nid, "ai-check", {"kind": "nope"})
        assert r.status_code == 400

    def test_unparseable_reply_returns_empty_findings(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        _patch(monkeypatch, "write.ai_check", _FakeClient("没有问题，一切正常。"))
        r = _post(nid, "ai-check", {"kind": "style_consistency"})
        assert r.status_code == 200, r.text
        assert r.json()["findings"] == []

    def test_findings_capped_at_8(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        items = ",".join(
            f'{{"title":"t{i}","detail":"d{i}"}}' for i in range(12)
        )
        _patch(monkeypatch, "write.ai_check", _FakeClient(f'{{"findings":[{items}]}}'))
        r = _post(nid, "ai-check", {"kind": "style_consistency"})
        assert r.status_code == 200, r.text
        assert len(r.json()["findings"]) == 8

    def test_free_tier_403_ai_not_touched(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, "write.ai_check", _FakeClient(FINDINGS_JSON, captured))
        r = _post(nid, "ai-check", {"kind": "hooks_conflict"}, free=True)
        assert r.status_code == 403
        assert captured == []

    def test_timeout_502_with_fail_row(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        _patch(
            monkeypatch, "write.ai_check",
            _FakeClient("", error=AITimeoutError("timeout")),
        )
        r = _post(nid, "ai-check", {"kind": "volume_conflict"})
        assert r.status_code == 502, r.text
        assert "ai_check_volume_conflict_fail" in _ops(nid)


class TestFillGaps:
    def test_200_whitelist_and_usage(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        captured: list = []
        reply = (
            '{"fills": {"summary": "渡口夜谈", "characters": ["林晚", " "],'
            ' "bogus_key": "不该收", "mood": "紧张",'
            ' "key_points": ["上船"], "location": "   "}}'
        )
        _patch(monkeypatch, "chapters.ai_draft", _FakeClient(reply, captured))
        r = _post(nid, "outline/fill-gaps", {"missing": ["summary", "characters", "bogus_key"]})
        assert r.status_code == 200, r.text
        fills = r.json()["fills"]
        # 白名单＝留存可写格；退役键（key_points/location）即便返回也被丢弃
        assert fills == {"summary": "渡口夜谈", "characters": ["林晚"], "mood": "紧张"}
        # 越界键不进提示词：missing 白名单过滤
        assert "bogus_key" not in _layered_prompt(captured[-1])
        # 记账：outline_fill_gaps（与 AI 起草同族留痕）
        assert "outline_fill_gaps" in _ops(nid)

    def test_retired_keys_dropped(self, monkeypatch):
        """c-og-slim-v2：段落规划/预期策略/关键事件等退役键即便被模型返回也一律丢弃。"""
        _root, nid = asyncio.run(_seed())
        reply = (
            '{"fills": {"mood": "紧张",'
            ' "segments": [{"summary": "上船", "target_words": "900"}],'
            ' "strategy": "顺推", "key_points": ["上船"],'
            ' "changes": ["拿到货单"]}}'
        )
        _patch(monkeypatch, "chapters.ai_draft", _FakeClient(reply))
        r = _post(nid, "outline/fill-gaps", {"missing": ["mood", "changes"]})
        assert r.status_code == 200, r.text
        fills = r.json()["fills"]
        assert "segments" not in fills and "strategy" not in fills
        assert "key_points" not in fills
        assert fills == {"mood": "紧张", "changes": ["拿到货单"]}

    def test_missing_list_400(self):
        _root, nid = asyncio.run(_seed())
        r = _post(nid, "outline/fill-gaps", {"missing": []})
        assert r.status_code == 400

    def test_all_keys_out_of_whitelist_400(self):
        _root, nid = asyncio.run(_seed())
        r = _post(nid, "outline/fill-gaps", {"missing": ["bogus", "whatever"]})
        assert r.status_code == 400

    def test_empty_or_broken_reply_502(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        _patch(monkeypatch, "chapters.ai_draft", _FakeClient("抱歉，我无法补全。"))
        r = _post(nid, "outline/fill-gaps", {"missing": ["summary"]})
        assert r.status_code == 502

    def test_timeout_502(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        _patch(
            monkeypatch, "chapters.ai_draft",
            _FakeClient("", error=AITimeoutError("timeout")),
        )
        r = _post(nid, "outline/fill-gaps", {"missing": ["summary"]})
        assert r.status_code == 502
        assert "outline_fill_gaps_fail" in _ops(nid)


class TestPromptRefine:
    def test_negative_mode_200_and_prompt(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, "ai_client", _FakeClient("```\n## 任务指示\n新提示词\n```", captured))
        r = _post(nid, "write/prompt/refine", {
            "mode": "negative", "current_prompt": "## 任务指示\n旧提示词",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mode"] == "negative"
        # strip_code_fences 生效：围栏被剥掉
        assert body["prompt"] == "## 任务指示\n新提示词"
        system = _layered_prompt(captured[-1])
        assert "补全「负向约束」" in system
        assert "旧提示词" in system

    def test_concise_mode_uses_stored_prompt_as_base(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, "ai_client", _FakeClient("精简后的提示词", captured))
        r = _post(nid, "write/prompt/refine", {"mode": "concise"})
        assert r.status_code == 200, r.text
        system = _layered_prompt(captured[-1])
        assert "精简提示词" in system
        # 未传 current_prompt：以服务端组装稿为基底（章级动态分节，c-write-prompt-layering）
        assert "## 当前章节" in system

    def test_unknown_mode_400(self):
        _root, nid = asyncio.run(_seed())
        r = _post(nid, "write/prompt/refine", {"mode": "shout"})
        assert r.status_code == 400

    def test_timeout_502_with_fail_row(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        _patch(monkeypatch, "ai_client", _FakeClient("", error=AITimeoutError("timeout")))
        r = _post(nid, "write/prompt/refine", {"mode": "concise", "current_prompt": "x"})
        assert r.status_code == 502, r.text
        assert "prompt_refine_concise_fail" in _ops(nid)

    def test_result_not_persisted(self, monkeypatch):
        """提案制口径：精修产物不落库，提示词存储保持原样。"""
        _root, nid = asyncio.run(_seed())
        _patch(monkeypatch, "ai_client", _FakeClient("AI 改过的稿"))
        r = _post(nid, "write/prompt/refine", {"mode": "concise", "current_prompt": "原稿"})
        assert r.status_code == 200, r.text

        async def _read():
            async with async_session() as s:
                novel = (await s.scalars(
                    select(Novel).where(Novel.id == nid)
                )).one()
                return novel.root_path

        root = asyncio.run(_read())
        import prompt.store as prompt_store

        async def _stored():
            return await prompt_store.load_prompt(root, REF, "write-prompt")

        assert asyncio.run(_stored()) in (None, "")