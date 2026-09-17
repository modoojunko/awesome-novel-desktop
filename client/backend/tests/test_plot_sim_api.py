"""剧情推演端点测试（plot-sim，storyline.html 四期尾）。

覆盖：AI 200 路径（回合结构/label/out 定形/提示词素材注入）、产物不合格回落
确定性推演（source=fallback）、client 缺失回落、双门控（PRO 403 / 模型 503）、
_parse_rounds 纯函数（杂讯容错/缺字段丢回合/上限 4）。
fake client 手法照 test_characters_ai：捕获 prompt、返回预置 payload。
"""

import asyncio
import json
import os
import tempfile

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_client import AITimeoutError
from auth_local.deps import require_ai_access as _require_ai_access
from auth_local.deps import require_novel_model as _require_novel_model
from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.chapter import (
    Chapter,
    ChapterCharacter,
    ChapterKeyPoint,
    ChapterPayoffItem,
    ChapterRequiredChange,
)
from models.project import Novel
from models.user import User
from models.volume import Volume
from write.plot_sim import _parse_rounds

REF = "vol-1-ch-2"

# 每份种子一个唯一用户（测试库跨用例复用：users.email/id 均唯一约束），
# nid → uid 供门控 override 与记账断言取用户
_UIDS: dict[str, str] = {}


def _uid_of(nid: str) -> str:
    return _UIDS[nid]


async def _seed() -> tuple[str, str]:
    """种一本书：第 1 章（有正文结尾）+ 第 2 章（章纲完整），返回 (root, novel_id)。
    User 行必须存在——token_log.user_id 有 users FK，缺行会让记账被静默拦下。"""
    root = tempfile.mkdtemp(prefix="test_plot_sim_")
    slug = f"sim-{os.path.basename(root)}"
    uid = f"sim-{os.path.basename(root)[-12:]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{slug}@test.local", password_hash="x",
            display_name="推演测试", api_key="", api_base_url="", api_model="",
        ))
        session.add(Novel(
            user_id=uid, name="推演书", slug=slug,
            root_path=root, source="manual", current_phase="write",
            ai_model="haiku",
        ))
        await session.flush()
        proj = (await session.scalars(
            select(Novel).where(Novel.root_path == root)
        )).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        ch1 = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref="vol-1-ch-1", title="第1章", status="archived",
        )
        session.add(ch1)
        await session.flush()
        from models.chapter import ChapterContent

        # 正文刻意超 300 字：素材「结尾摘录」截断方向错时会摘成中段——AI 路径
        # 的 "解开" in system 断言即该缺陷的回归探针
        session.add(ChapterContent(
            chapter_id=ch1.id,
            prose="前文推进。" * 90 + "她攥紧缆绳，解开了最后一根系泊。",
        ))
        ch2 = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=2,
            ref=REF, title="风起渡口", status="outline",
            summary="林晚在渡口等一班不存在的船。",
            location="临江渡口", story_time="清晨",
            current_task="查清匿名信的来路",
            expectation_strategy="先铺垫不安，再给一次喘息",
            primary_mood="悬疑",
        )
        session.add(ch2)
        await session.flush()
        session.add(ChapterKeyPoint(chapter_id=ch2.id, sort_order=1, func_tag="造悬念", content="匿名信被尾随"))
        session.add(ChapterKeyPoint(chapter_id=ch2.id, sort_order=2, func_tag="推进剧情", content="渡口对质"))
        session.add(ChapterCharacter(chapter_id=ch2.id, sort_order=1, character_name="林晚"))
        session.add(ChapterPayoffItem(chapter_id=ch2.id, sort_order=1, kind="must_hold", content="谁在暗中跟着她"))
        session.add(ChapterRequiredChange(chapter_id=ch2.id, sort_order=1, change_type="", content="她把信交给了陌生人"))
        await session.commit()
        _UIDS[proj.id] = uid
        return root, proj.id


class _FakeClient:
    def __init__(self, payload: str, capture: list):
        self._payload = payload
        self._capture = capture

    async def chat(self, **kwargs):
        self._capture.append(kwargs)
        return self._payload


def _with_client(monkeypatch, payload: str | None, capture: list):
    async def _fake(novel_id):
        return None if payload is None else _FakeClient(payload, capture)

    # plot_sim 顶层 from-import 绑定，须 patch 模块内名字（test_characters_ai 同款坑）
    monkeypatch.setattr("write.plot_sim.get_ai_client_for_novel", _fake)


def _post(nid: str, gating: bool = True):
    with TestClient(app) as c:
        app.dependency_overrides[get_current_user] = lambda: {"id": _uid_of(nid)}
        if gating:
            app.dependency_overrides[_require_ai_access] = lambda: True
            app.dependency_overrides[_require_novel_model] = lambda: True
        r = c.post(f"/api/novels/{nid}/chapters/{REF}/simulate")
        app.dependency_overrides.clear()
        return r


class TestOkPath:
    def test_ai_rounds_structured_and_material_injected(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        captured: list = []
        payload = json.dumps({"rounds": [
            {"beat": "匿名信被尾随", "who": "林晚", "place": "渡口", "time": "清晨",
             "at": "承上：她解开了缆绳", "shift": "她决定不再等船",
             "ok": "顺线落地", "warn": "被船夫叫住"},
            {"beat": "渡口对质", "who": "林晚", "place": "渡口", "time": "清晨",
             "at": "推向本章结尾", "shift": "信到了陌生人手里",
             "ok": "对质完成", "warn": "对质被人打断"},
        ]}, ensure_ascii=False)
        _with_client(monkeypatch, payload, captured)
        r = _post(nid)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["source"] == "ai"
        assert d["prev_label"] == "第 1 章"
        # entry = 上一章正文末 60 字（种子正文 >300 字，尾段即最终句）
        assert d["entry"].endswith("她攥紧缆绳，解开了最后一根系泊。")
        assert d["exit"] == "她把信交给了陌生人"
        assert d["cast"] == ["林晚"]
        assert [x["n"] for x in d["rounds"]] == [1, 2]
        r1 = d["rounds"][0]
        assert r1["beat"] == "匿名信被尾随"
        assert [m["k"] for m in r1["moves"]] == ["顺", "拗"]
        assert r1["moves"][0]["label"] == "林晚顺着当前节奏动手"
        assert r1["moves"][1]["tone"] == "warn"
        assert r1["moves"][0]["out"] == "顺线落地"
        # 素材注入：章纲关键事件 + 任务 + 悬念 + 上一章正文结尾
        system = captured[-1]["system"]
        assert "匿名信被尾随" in system
        assert "查清匿名信的来路" in system
        assert "谁在暗中跟着她" in system
        assert "解开" in system  # 上一章正文结尾摘录进素材

    def test_invalid_payload_falls_back_deterministic(self, monkeypatch):
        """产物非 JSON → 原型同款确定性推演（关键事件环 + 模板走法）。"""
        _root, nid = asyncio.run(_seed())
        captured: list = []
        _with_client(monkeypatch, "抱歉，我无法输出 JSON。", captured)
        r = _post(nid)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["source"] == "fallback"
        assert [x["beat"] for x in d["rounds"]] == ["[造悬念]匿名信被尾随", "[推进剧情]渡口对质"]
        assert d["rounds"][0]["at"] == "承上：" + d["entry"]
        assert d["rounds"][-1]["shift"] == "她把信交给了陌生人"
        assert "主情绪停在「悬疑」" in d["rounds"][0]["moves"][0]["out"]
        assert "谁在暗中跟着她" in d["rounds"][0]["moves"][1]["out"]

    def test_client_none_falls_back(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        captured: list = []
        _with_client(monkeypatch, None, captured)
        r = _post(nid)
        assert r.status_code == 200, r.text
        assert r.json()["source"] == "fallback"
        assert captured == []

    def test_timeout_falls_back_and_records_fail_once(self, monkeypatch):
        """AI 超时：记一次 plot_sim_fail（调用已发生）后回落，不向用户报错；
        成功记账与调用 try 解耦——超时路径不得同时落 plot_sim 成功账。"""
        _root, nid = asyncio.run(_seed())

        class _TimeoutClient:
            async def chat(self, **kwargs):
                raise AITimeoutError("timeout")

        async def _fake(novel_id):
            return _TimeoutClient()

        monkeypatch.setattr("write.plot_sim.get_ai_client_for_novel", _fake)
        r = _post(nid)
        assert r.status_code == 200, r.text
        assert r.json()["source"] == "fallback"

        async def _ops():
            from models.token_log import TokenLog

            async with async_session() as session:
                rows = (
                    await session.scalars(
                        select(TokenLog).where(TokenLog.project_id == nid)
                    )
                ).all()
                return [x.operation for x in rows]

        ops = asyncio.run(_ops())
        assert ops.count("plot_sim_fail") == 1
        assert "plot_sim" not in ops


class TestGating:
    def test_free_user_403_no_call(self, monkeypatch):
        _root, nid = asyncio.run(_seed())
        captured: list = []
        _with_client(monkeypatch, "{}", captured)

        def _forbidden():
            raise HTTPException(403, detail={"reason": "member_required"})

        with TestClient(app) as c:
            app.dependency_overrides[get_current_user] = lambda: {"id": _uid_of(nid)}
            app.dependency_overrides[_require_ai_access] = _forbidden
            r = c.post(f"/api/novels/{nid}/chapters/{REF}/simulate")
            app.dependency_overrides.clear()
        assert r.status_code == 403
        assert captured == []

    def test_model_not_ready_503(self):
        _root, nid = asyncio.run(_seed())

        def _no_model(project_id: str):
            raise HTTPException(503, detail={"reason": "missing_model"})

        with TestClient(app) as c:
            app.dependency_overrides[get_current_user] = lambda: {"id": _uid_of(nid)}
            app.dependency_overrides[_require_ai_access] = lambda: True
            app.dependency_overrides[_require_novel_model] = _no_model
            r = c.post(f"/api/novels/{nid}/chapters/{REF}/simulate")
            app.dependency_overrides.clear()
        assert r.status_code == 503


class TestParseRounds:
    def test_noise_tolerated_and_cap(self):
        payload = "杂讯 {\"rounds\": [" + ",".join(
            json.dumps({"beat": f"b{i}", "ok": "o", "warn": "w"}) for i in range(6)
        ) + "]} 杂讯"
        out = _parse_rounds(payload)
        assert len(out) == 4  # 上限
        assert out[0]["beat"] == "b0"

    def test_missing_fields_drop_round(self):
        payload = json.dumps({"rounds": [
            {"beat": "缺走法", "ok": "o"},
            {"beat": "", "ok": "o", "warn": "w"},
            {"beat": "完整", "ok": "o", "warn": "w"},
        ]})
        out = _parse_rounds(payload)
        assert [x["beat"] for x in out] == ["完整"]

    def test_invalid_shapes_empty(self):
        assert _parse_rounds("") == []
        assert _parse_rounds("不是 JSON") == []
        assert _parse_rounds('{"rounds": "x"}') == []
        assert _parse_rounds('{"other": 1}') == []
