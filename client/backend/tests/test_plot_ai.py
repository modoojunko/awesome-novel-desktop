"""章内剧情 · AI 帮写剧情端点测试（c-plot-split tasks 3.1–3.4）。

矩阵：
- 3.1 三版出卡：响应形状 {ok, versions, grades, warnings}、三版共用首尾、
  生成预算上限（max_tokens=8192 进 client.chat kwargs）；
- 3.2 判读纪律：2 版→判失败（绝不将就、不重抽）、缺名次/并列名次→无角标卡照出、
  超长条目→句读截断且末句不腰斩；重试阶梯只认「0 可用版本」（temp 0.7→0.3）；
- 3.3 门槛与素材：三要素缺口 422 大白话、素材含进场不含伏笔台账、记账留痕
  （chapter_plot_fill，播种 User 防 FK 静默回滚）；
- 3.4 fill-gaps 不吃 plot_items：携带 plot_items 的缺口清单被丢弃、其余键照常补全。
fake client 手法照 test_ai_assist_checks；monkeypatch 目标＝volumes.ai_plan
（get_ai_client_for_novel 在该模块顶层绑定，_generate 走同一命名空间）。
"""

import asyncio
import os
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_local.deps import require_ai_access as _raa
from auth_local.deps import require_novel_model as _rnm
from auth_local.middleware import get_current_user
from chapters.ai_plot import clip_plot_item
from db import async_session
from main import app
from models.chapter import Chapter, ChapterContent
from models.hook import NovelHook
from models.project import Novel
from models.user import User
from models.volume import Volume


def _layered_prompt(kwargs) -> str:
    """分层协议下的全文（system＋user 合并读——内容断言不关心落在哪一段）。"""
    return str(kwargs.get("system") or "") + "\n" + str(kwargs["messages"][0]["content"])


REF = "vol-1-ch-2"  # 目标章＝第 2 章（第 1 章给进场：正文结尾）
PREV_PROSE_END = "船家把缆绳扔上岸，回头看了她一眼。"
_UIDS: dict[str, str] = {}

ENTRY = "接上：船家把缆绳扔上岸，回头看了她一眼。"
EXIT = "收束：她把假账册压进箱底，吹熄了灯。"
_GOOD = (
    '{"entry": "' + ENTRY + '",'
    ' "middles": [["甲一：她翻墙进了库房", "甲二：账册被调包"],'
    ' ["乙一：她在渡口截住船家"],'
    ' ["丙一：她放走了船家", "丙二：灯下的账册是假的"]],'
    ' "exit": "' + EXIT + '",'
    ' "ranks": [1, 2, 3]}'
)


async def _seed(*, challenge: str = "船家临时改口要加钱", with_hook: bool = False) -> str:
    """一书两章＋用户（记账 FK）；返回 novel_id。第 1 章带正文给进场。"""
    root = tempfile.mkdtemp(prefix="test_plot_ai_")
    slug = f"pa-{os.path.basename(root)}"
    uid = f"pa-{os.path.basename(root)[-12:]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{slug}@test.local", password_hash="x",
            display_name="剧情测试", api_key="", api_base_url="", api_model="",
        ))
        session.add(Novel(
            user_id=uid, name="剧情书", slug=slug, root_path=root,
            source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(select(Novel).where(Novel.root_path == root))).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        ch1 = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref="vol-1-ch-1", title="第1章", status="writing", has_prose=True,
        )
        session.add(ch1)
        await session.flush()
        session.add(ChapterContent(
            chapter_id=ch1.id, prose="夜里的渡口没有灯。\n" + PREV_PROSE_END,
        ))
        ch2 = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=2,
            ref=REF, title="第2章", status="outline",
            summary="她夜探库房调包账册", challenge=challenge,
            ladder_exit="假账册入箱，灯下换人值夜",
        )
        session.add(ch2)
        await session.flush()
        if with_hook:
            session.add(NovelHook(
                novel_id=proj.id, seq=1, description="乌鸦面具下的胎记",
                type="mystery", priority=2, status="active",
            ))
        await session.commit()
        _UIDS[proj.id] = uid
        return proj.id


class _FakeClient:
    def __init__(self, replies, capture: list | None = None):
        self._replies = list(replies) if isinstance(replies, list) else [replies]
        self._capture = capture if capture is not None else []

    async def chat(self, **kwargs):
        self._capture.append(kwargs)
        usage = kwargs.get("usage")
        if usage is not None:
            usage["tokens_in"] = 30
            usage["tokens_out"] = 12
        return self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]


def _patch(monkeypatch, module: str, client):
    async def _fake(novel_id):
        return client

    monkeypatch.setattr(f"{module}.get_ai_client_for_novel", _fake)


def _post(nid: str, path: str, body: dict | None = None):
    c = TestClient(app)
    c.__enter__()
    app.dependency_overrides[get_current_user] = lambda: {"id": _UIDS[nid]}
    app.dependency_overrides[_raa] = lambda: True
    app.dependency_overrides[_rnm] = lambda: True
    try:
        return c.post(f"/api/novels/{nid}/chapters/{REF}/{path}", json=body or {})
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


class TestDrawShape:
    def test_shape_shared_head_tail_grades(self, monkeypatch):
        """3.1：形状四键、三版共用首尾（进场/结尾单源）、名次→字母 S/A/B。"""
        nid = asyncio.run(_seed())
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(_GOOD))
        r = _post(nid, "plot/ai-draw")
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body.keys()) == {"ok", "versions", "grades", "warnings"}
        assert body["ok"] is True
        versions = body["versions"]
        assert len(versions) == 3
        for v in versions:
            assert v["items"][0] == ENTRY
            assert v["items"][-1] == EXIT
            assert all(len(x) <= 200 for x in v["items"])
        # 中段互斥：三版中段各不相同
        assert versions[0]["items"][1:-1] == ["甲一：她翻墙进了库房", "甲二：账册被调包"]
        assert versions[1]["items"][1:-1] == ["乙一：她在渡口截住船家"]
        assert body["grades"] == ["S", "A", "B"]

    def test_budget_caps_max_tokens_8192(self, monkeypatch):
        """3.1：生成预算上限——max_tokens 8192（默认 4096 不动）＋素材四块齐。"""
        nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(_GOOD, captured))
        r = _post(nid, "plot/ai-draw")
        assert r.status_code == 200, r.text
        assert captured[-1]["max_tokens"] == 8192
        assert captured[-1]["temperature"] == 0.7
        system = str(captured[-1].get("system") or "") + "\n" + str(captured[-1]["messages"][0]["content"])  # 分层：system＋user 合并读
        for mark in ("【进场（本章从哪接）】", "【本章概要】", "碰到的挑战", "【本章结尾（收束到这）】"):
            assert mark in system, mark


class TestJudgementDiscipline:
    def test_two_versions_fails_without_retry(self, monkeypatch):
        """3.2（拍板⑤）：凑不满 3 版＝失败，绝不 2 版将就；非 0 可用不重抽。"""
        nid = asyncio.run(_seed())
        captured: list = []
        reply = (
            '{"entry": "' + ENTRY + '", "exit": "' + EXIT + '",'
            ' "middles": [["甲一"], ["乙一"]], "ranks": [1, 2]}'
        )
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(reply, captured))
        r = _post(nid, "plot/ai-draw")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is False
        assert body["versions"] == []
        assert body["grades"] == []
        assert len(captured) == 1  # 有可用版本就不走重试阶梯

    def test_missing_ranks_no_corner(self, monkeypatch):
        """3.2（拍板⑧）：缺名次→三版都无角标，卡照出。"""
        nid = asyncio.run(_seed())
        reply = (
            '{"entry": "' + ENTRY + '",'
            ' "middles": [["甲一"], ["乙一"], ["丙一"]],'
            ' "exit": "' + EXIT + '"}'
        )
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(reply))
        r = _post(nid, "plot/ai-draw")
        body = r.json()
        assert body["ok"] is True
        assert len(body["versions"]) == 3
        assert body["grades"] == ["", "", ""]

    def test_duplicate_ranks_no_corner(self, monkeypatch):
        """3.2（拍板⑧）：并列名次不映射字母；唯一名次照常出角标。"""
        nid = asyncio.run(_seed())
        reply = (
            '{"entry": "' + ENTRY + '",'
            ' "middles": [["甲一"], ["乙一"], ["丙一"]],'
            ' "exit": "' + EXIT + '", "ranks": [1, 1, 3]}'
        )
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(reply))
        r = _post(nid, "plot/ai-draw")
        body = r.json()
        assert body["ok"] is True
        assert body["grades"] == ["", "", "B"]

    def test_clip_keeps_last_sentence(self):
        """3.2：超长条目截到最后一个句读点（末句不腰斩）；无句读才硬截。"""
        sent = "他推门进了院子。"
        over = sent + "吵" * 199  # 207 字：首句收在第 8 字
        assert clip_plot_item(over) == sent
        assert clip_plot_item("吵" * 250) == "吵" * 200  # 全条无句读→硬截 200
        assert clip_plot_item("短句。") == "短句。"  # 预算内不改编

    def test_overlong_item_clipped_with_warning(self, monkeypatch):
        """3.2：端点层超长条目句读截断＋进 warnings；条目全部 ≤200。"""
        nid = asyncio.run(_seed())
        over = "他推门进了院子。" + "吵" * 199
        reply = (
            '{"entry": "' + ENTRY + '",'
            ' "middles": [["' + over + '", "甲二"], ["乙一"], ["丙一"]],'
            ' "exit": "' + EXIT + '", "ranks": [1, 2, 3]}'
        )
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(reply))
        r = _post(nid, "plot/ai-draw")
        body = r.json()
        assert body["ok"] is True
        assert any("已截到最后一个句号" in w for w in body["warnings"])
        for v in body["versions"]:
            assert all(len(x) <= 200 for x in v["items"])
        assert body["versions"][0]["items"][1] == "他推门进了院子。"

    def test_retry_only_on_zero_versions(self, monkeypatch):
        """3.2：0 可用版本才重试（temp 0.3、把失败原因喂回、记 _retry 账）。"""
        nid = asyncio.run(_seed())
        captured: list = []
        client = _FakeClient(["这不是 JSON", _GOOD], captured)
        _patch(monkeypatch, "volumes.ai_plan", client)
        r = _post(nid, "plot/ai-draw")
        body = r.json()
        assert body["ok"] is True
        assert len(body["versions"]) == 3
        assert len(captured) == 2
        assert captured[1]["temperature"] == 0.3
        assert "（上一次" in captured[1]["system"]
        ops = _ops(nid)
        assert ops.count("chapter_plot_fill") == 1
        assert "chapter_plot_fill_retry" in ops


class TestGateMaterialUsage:
    def test_three_element_gate_422(self, monkeypatch):
        """3.3（拍板⑦）：三要素缺口 422 大白话，不发生模型调用。"""
        nid = asyncio.run(_seed(challenge=""))
        captured: list = []
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(_GOOD, captured))
        r = _post(nid, "plot/ai-draw")
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        assert "这一章还没填全" in detail
        assert "碰到的挑战" in detail
        assert captured == []

    def test_material_entry_without_hooks_ledger(self, monkeypatch):
        """3.3：素材带进场（正文结尾单源）＋三要素；伏笔台账不进素材（防提前揭底）。"""
        nid = asyncio.run(_seed(with_hook=True))
        captured: list = []
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(_GOOD, captured))
        r = _post(nid, "plot/ai-draw")
        assert r.status_code == 200, r.text
        system = str(captured[-1].get("system") or "") + "\n" + str(captured[-1]["messages"][0]["content"])  # 分层：system＋user 合并读
        assert "【进场（本章从哪接）】" in system
        assert PREV_PROSE_END in system
        assert "取自正文结尾" in system
        assert "她夜探库房调包账册" in system  # 本章概要
        assert "假账册入箱" in system  # 章末落点
        assert "乌鸦面具下的胎记" not in system
        assert "伏笔台账" not in system

    def test_usage_recorded(self, monkeypatch):
        """3.3：成功出卡记 chapter_plot_fill（独立会话记账，User 已播种）。"""
        nid = asyncio.run(_seed())
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(_GOOD))
        r = _post(nid, "plot/ai-draw")
        assert r.status_code == 200, r.text
        assert "chapter_plot_fill" in _ops(nid)


class TestFillGapsExclusion:
    def test_plot_items_dropped_others_filled(self, monkeypatch):
        """3.4：缺口清单带 plot_items 被丢弃（不吃整卡补缺），其余键照常补全。"""
        nid = asyncio.run(_seed())
        captured: list = []
        reply = '{"fills": {"plot_items": ["甲一"], "summary": "渡口夜谈"}}'
        _patch(monkeypatch, "chapters.ai_draft", _FakeClient(reply, captured))
        r = _post(nid, "outline/fill-gaps", {"missing": ["plot_items", "summary"]})
        assert r.status_code == 200, r.text
        assert r.json()["fills"] == {"summary": "渡口夜谈"}
        assert "plot_items" not in captured[-1]["system"]

    def test_plot_items_only_missing_is_out_of_scope(self, monkeypatch):
        """3.4：plot_items 与越界键同待遇——全越界直接 400（当没看见）。"""
        nid = asyncio.run(_seed())
        _patch(monkeypatch, "chapters.ai_draft", _FakeClient('{"fills": {}}'))
        r = _post(nid, "outline/fill-gaps", {"missing": ["plot_items"]})
        assert r.status_code == 400