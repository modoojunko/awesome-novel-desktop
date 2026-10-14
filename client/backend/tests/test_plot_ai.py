"""章内剧情 · AI 帮写剧情端点测试（c-plot-split tasks 3.1–3.4）。

矩阵：
- 3.1 三版出卡：响应形状 {ok, versions, grades, warnings}、三版共用首尾、
  生成预算上限（max_tokens=16384 进 client.chat kwargs，端点按上限打回时降 8192 重打一次）；
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


async def _seed(*, challenge: str = "船家临时改口要加钱", with_hook: bool = False,
               word_target: int | None = None) -> str:
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
            ladder_exit="假账册入箱，灯下换人值夜", word_target=word_target,
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

    def test_budget_caps_max_tokens_16384(self, monkeypatch):
        """3.1：生成预算上限——max_tokens 16384（c-scene-density：每版 4–12 条最坏
        ~8000 字 ≈8-9k token，8192 贴边会截断 JSON）＋素材四块齐。"""
        nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(_GOOD, captured))
        r = _post(nid, "plot/ai-draw")
        assert r.status_code == 200, r.text
        assert captured[-1]["max_tokens"] == 16384
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

    def test_overlong_item_passes_through_complete(self, monkeypatch):
        """c-field-truncation-alignment 终版：超长条目不截断——完整进版本（含提示词），
        也不再出「已截到最后一个句号」告警。"""
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
        assert not any("已截" in w for w in body["warnings"])
        assert body["versions"][0]["items"][1] == over  # 逐字完整

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

class TestSceneDensity:
    """c-scene-density：条数联动字数——素材恒带【本章字数】；中段上限 4→10。"""

    def test_band_and_hint_single_source(self):
        """c-shortfall-refill：hint 文案＝band 区间渲染（遥测与素材同源）。"""
        from chapters.ai_plot import plot_count_band, plot_count_hint

        for wt in (500, 1500, 2000, 2500, 2999, 3000, 3500, 4000, 6000):
            lo, hi = plot_count_band(wt)
            assert plot_count_hint(wt) == f"{lo}–{hi} 条场景"
        assert plot_count_band(500) == (4, 6)
        assert plot_count_band(2500) == (6, 8)
        assert plot_count_band(3000) == (8, 10)
        assert plot_count_band(6000) == (10, 12)

    def test_plot_blocks_carries_word_target(self):
        from types import SimpleNamespace

        from chapters.ai_plot import _plot_blocks

        row = SimpleNamespace(
            summary="她夜探库房调包账册",
            challenge="账房夜里有人值夜",
            ladder_exit="假账册压进箱底，灯灭了",
        )
        entry = {"text": "接上章结尾", "source": "上章结尾"}
        mat = {
            "fullstory": "全书主线文本",
            "ending": {},
            "world_brief": "",
            "cast_brief": "",
            "hooks_block": "",
            "closed_hooks": "",
            "genre_section": "",
        }
        block = _plot_blocks(mat, row, entry, "", 2500)
        assert "【本章字数】" in block
        assert "写满 2500 字" in block
        assert "建议拆 6–8 条场景" in block  # c-scene-density：建议条数直给

    def test_plot_blocks_without_word_target_omits_block(self):
        from types import SimpleNamespace

        from chapters.ai_plot import _plot_blocks

        row = SimpleNamespace(
            summary="概要", challenge="挑战", ladder_exit="落点"
        )
        entry = {"text": "接上章结尾", "source": "上章结尾"}
        mat = {
            "fullstory": "全书主线文本",
            "ending": {},
            "world_brief": "",
            "cast_brief": "",
            "hooks_block": "",
            "closed_hooks": "",
            "genre_section": "",
        }
        block = _plot_blocks(mat, row, entry, "")
        assert "【本章字数】" not in block

    def test_plot_count_hint_bands(self):
        """c-scene-density：字数→建议条数档位——≥2000 字档密度 330–500 字/条、单调爬升，
        上限钉 PLOT_MAX_ITEMS=12（档位饱和＝字数失去区分度，2026-10-13 用户否掉）。"""
        from chapters.ai_plot import plot_count_hint

        assert plot_count_hint(500) == "4–6 条场景"
        assert plot_count_hint(1500) == "4–6 条场景"
        assert plot_count_hint(2000) == "6–8 条场景"
        assert plot_count_hint(2999) == "6–8 条场景"
        assert plot_count_hint(3000) == "8–10 条场景"
        assert plot_count_hint(3999) == "8–10 条场景"
        assert plot_count_hint(4000) == "10–12 条场景"
        assert plot_count_hint(6000) == "10–12 条场景"

    def test_body_word_target_drives_hint(self, monkeypatch):
        """c-scene-density 联动：表单字数随请求体直发——素材【本章字数】与建议条数
        跟着走（页面显示什么，模型收到什么）；存值（此处空）让位。"""
        nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(_GOOD, captured))
        r = _post(nid, "plot/ai-draw", {"word_target": 4000})
        assert r.status_code == 200, r.text
        user = str(captured[-1]["messages"][0]["content"])
        assert "写满 4000 字" in user
        assert "建议拆 10–12 条场景" in user

    def test_no_body_falls_back_to_book_default(self, monkeypatch):
        """请求体不带 word_target → 本章存值（未填）→ 本书默认 2500：6–8 条。"""
        nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(_GOOD, captured))
        r = _post(nid, "plot/ai-draw")
        assert r.status_code == 200, r.text
        user = str(captured[-1]["messages"][0]["content"])
        assert "写满 2500 字" in user
        assert "建议拆 6–8 条场景" in user

    def test_sanitize_keeps_ten_middles(self):
        """每版 4–12 条（c-scene-density）：首尾共用占 2，中段最多留 10——
        12＝PLOT_MAX_ITEMS 存储单源。"""
        from chapters.ai_plot import _sanitize_versions

        parsed = {
            "entry": "首",
            "exit": "末",
            "middles": [[f"中{i}" for i in range(11)], ["乙一"], ["丙一"]],
            "ranks": [1, 2, 3],
        }
        versions, warn = _sanitize_versions(parsed)
        assert len(versions[0]["items"]) == 12  # 首 1 + 中段 10 + 末 1
        assert any("超发" in w for w in warn)  # 剪了要说（评审：警示区不能是空的）


class TestDrawChainBudget:
    """c-scene-density 评审批：取值链中间层、真无 body 兼容、预算被拒降级。"""

    def test_stored_word_target_used_without_body(self, monkeypatch):
        """取值链中间层：无 body → 本章存值优先于本书默认。"""
        nid = asyncio.run(_seed(word_target=4000))
        captured: list = []
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(_GOOD, captured))
        r = _post(nid, "plot/ai-draw")
        assert r.status_code == 200, r.text
        user = str(captured[-1]["messages"][0]["content"])
        assert "写满 4000 字" in user
        assert "建议拆 10–12 条场景" in user

    def test_body_wins_over_stored(self, monkeypatch):
        """表单现值优先于存值——页面显示什么模型收到什么（即使尚未保存）。"""
        nid = asyncio.run(_seed(word_target=4000))
        captured: list = []
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(_GOOD, captured))
        r = _post(nid, "plot/ai-draw", {"word_target": 1500})
        assert r.status_code == 200, r.text
        user = str(captured[-1]["messages"][0]["content"])
        assert "写满 1500 字" in user
        assert "建议拆 4–6 条场景" in user

    def test_request_without_body_at_all(self, monkeypatch):
        """真无 body 的 POST（旧客户端/curl）→ 200，走存值链（此处＝本书默认）。"""
        nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, "volumes.ai_plan", _FakeClient(_GOOD, captured))
        c = TestClient(app)
        c.__enter__()
        app.dependency_overrides[get_current_user] = lambda: {"id": _UIDS[nid]}
        app.dependency_overrides[_raa] = lambda: True
        app.dependency_overrides[_rnm] = lambda: True
        try:
            r = c.post(f"/api/novels/{nid}/chapters/{REF}/plot/ai-draw")
        finally:
            app.dependency_overrides.clear()
        assert r.status_code == 200, r.text
        assert "写满 2500 字" in captured[-1]["messages"][0]["content"]

    def test_budget_degrades_on_max_tokens_rejection(self, monkeypatch):
        """端点按输出上限打回（8k 模型面）→ 降 8192 重打一次成卡，不 502 全挂。"""
        nid = asyncio.run(_seed())
        captured: list = []
        base = _FakeClient(_GOOD, captured)

        async def flaky_chat(**kwargs):
            captured.append(kwargs)
            if len(captured) == 1:
                raise Exception(
                    "max_tokens: 16384 > 8192, which is the maximum number of "
                    "tokens that can be generated for this model"
                )
            return base._replies[0]

        base.chat = flaky_chat  # type: ignore[method-assign]
        _patch(monkeypatch, "volumes.ai_plan", base)
        r = _post(nid, "plot/ai-draw")
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        assert [c["max_tokens"] for c in captured] == [16384, 8192]

    def test_non_rejection_error_not_degraded(self, monkeypatch):
        """非 max_tokens 错误不降级：502 直穿、不重打（判不准宁可不降）。"""
        nid = asyncio.run(_seed())
        captured: list = []
        base = _FakeClient(_GOOD, captured)

        async def angry_chat(**kwargs):
            captured.append(kwargs)
            raise Exception("connection reset by peer")

        base.chat = angry_chat  # type: ignore[method-assign]
        _patch(monkeypatch, "volumes.ai_plan", base)
        r = _post(nid, "plot/ai-draw")
        assert r.status_code == 502
        assert len(captured) == 1
