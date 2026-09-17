"""本章文风影子 API 测试（write/style_shadow.py 收尾验收）。

覆盖三块验收缺口：
- PUT 形状清洗：非 dict rows/非 dict 行/值与理由全空行丢弃、维度字符串化、
  值不脱空格原样落库（清洗只判空不改编）、GET baseline 回读一致；
- suggest 门控：PRO 403 先于本书模型 503（依赖注入顺序=挂载顺序），
  PUT/GET 不受 AI 门控（免费可写影子——门禁属待拍板项，此处锁现状）；
- AI 解析：行名白名单（六行外丢弃）、空值丢弃、理由 200 截断、
  裸 JSON 前后杂讯容错、非法 JSON/非列表 → []。
fake client 手法照 test_characters_ai：捕获 prompt、返回预置 payload。
"""

import asyncio
import json
import os
import tempfile

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_local.deps import require_ai_access as _require_ai_access
from auth_local.deps import require_novel_model as _require_novel_model
from auth_local.middleware import get_current_user
from db import async_session
from filesystem.storage import get_storage
from main import app
from models.chapter import Chapter, ChapterKeyPoint
from models.project import Novel
from models.volume import Volume
from settings.style_quant_model import BASELINE_KEYS
from write.style_shadow import _parse_suggestions

QUANT_PATH = "settings/style-quant.yaml"


async def _seed_book_with_chapter(summary: str = "") -> tuple[str, str, str]:
    """种一本书（root_path 指临时目录）+ 一卷一章，返回 (root, novel_id, ch_ref)。"""
    root = tempfile.mkdtemp(prefix="test_style_shadow_")
    slug = f"shd-{os.path.basename(root)}"
    async with async_session() as session:
        session.add(Novel(
            user_id="shd_user", name="文风影子书", slug=slug,
            root_path=root, source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(
            select(Novel).where(Novel.root_path == root)
        )).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        ch = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref="vol-1-ch-1", title="第1章", status="outline", summary=summary,
        )
        session.add(ch)
        await session.flush()
        session.add(ChapterKeyPoint(
            chapter_id=ch.id, sort_order=1, func_tag="造悬念", content="荒庙接头",
        ))
        await session.commit()
        return root, proj.id, "vol-1-ch-1"


async def _seed_quant(root: str, *, distilled: bool) -> None:
    """蒸馏完成的量化基线（confidence>0 且至少一行有值）；否则空基线。"""
    doc = {
        "confidence": 88 if distilled else 0,
        "baseline": {
            "syntax": {"value": "中长句为主", "tolerance": 10, "locked": False},
            "narrative": {"value": "第三人称限知" if distilled else "", "tolerance": 10},
        },
    }
    await get_storage().write_yaml(root, QUANT_PATH, doc)


class _FakeClient:
    def __init__(self, payload: str, capture: list):
        self._payload = payload
        self._capture = capture

    async def chat(self, **kwargs):
        self._capture.append(kwargs)
        return self._payload


class TestPutShapeCleaning:
    def test_put_cleans_rows_and_roundtrips(self):
        """合法行保留（值/理由原样），脏行丢弃；GET baseline 回读一致。"""
        async def _run():
            root, nid, ref = await _seed_book_with_chapter()
            return root, nid, ref

        _root, nid, ref = asyncio.run(_run())
        with TestClient(app) as c:
            app.dependency_overrides[get_current_user] = lambda: {"id": "shd_user"}
            body_rows = {
                "syntax": {"value": " 短句 ", "reason": " 打斗章节奏 "},
                "lexicon": {"value": "", "reason": "只改理由也算覆盖"},
                "rhythm": {"value": "   ", "reason": ""},  # 全空 → 丢
                "emotion": "短句",  # 非 dict 行 → 丢
                123: {"value": "x"},  # 维度不设白名单（前端只发六行）：字符串化保留
            }
            r = c.put(f"/api/novels/{nid}/chapters/{ref}/style-shadow",
                      json={"rows": body_rows})
            assert r.status_code == 200, r.text
            shadow = r.json()["shadow"]
            # 清洗只判空不改编：值/理由原样落库（不脱空格）
            assert shadow == {
                "syntax": {"value": " 短句 ", "reason": " 打斗章节奏 "},
                "lexicon": {"value": "", "reason": "只改理由也算覆盖"},
                "123": {"value": "x", "reason": ""},
            }
            g = c.get(f"/api/novels/{nid}/chapters/{ref}/style-shadow/baseline")
            assert g.status_code == 200, g.text
            assert g.json()["shadow"] == shadow
            app.dependency_overrides.clear()

    def test_put_non_dict_rows_and_blank_body(self):
        async def _run():
            return await _seed_book_with_chapter()

        _root, nid, ref = asyncio.run(_run())
        with TestClient(app) as c:
            app.dependency_overrides[get_current_user] = lambda: {"id": "shd_user"}
            for body in ({"rows": "junk"}, {}, {"rows": {"syntax": 5}}):
                r = c.put(f"/api/novels/{nid}/chapters/{ref}/style-shadow", json=body)
                assert r.status_code == 200, r.text
                assert r.json()["shadow"] == {}
            app.dependency_overrides.clear()

    def test_put_not_ai_gated(self):
        """PUT/GET 不挂 AI 门控：require_ai_access 抛 403 也放行（免费可写，
        门禁属待拍板项——若日后收 PRO，此处与前端 locked 态要同批改）。"""
        async def _run():
            return await _seed_book_with_chapter()

        _root, nid, ref = asyncio.run(_run())

        def _forbidden():
            raise HTTPException(403, detail={"reason": "member_required"})

        with TestClient(app) as c:
            app.dependency_overrides[get_current_user] = lambda: {"id": "shd_user"}
            app.dependency_overrides[_require_ai_access] = _forbidden
            r = c.put(f"/api/novels/{nid}/chapters/{ref}/style-shadow",
                      json={"rows": {"syntax": {"value": "短句", "reason": "r"}}})
            assert r.status_code == 200, r.text
            assert r.json()["shadow"]["syntax"]["value"] == "短句"
            app.dependency_overrides.clear()


class TestSuggestGating:
    def test_free_user_403_before_model_check(self):
        """PRO 门控在前：403 且未发生任何模型调用。"""
        async def _run():
            root, nid, ref = await _seed_book_with_chapter()
            await _seed_quant(root, distilled=True)
            return nid, ref

        nid, ref = asyncio.run(_run())
        captured: list = []

        def _forbidden():
            raise HTTPException(403, detail={"reason": "member_required"})

        with TestClient(app) as c:
            app.dependency_overrides[get_current_user] = lambda: {"id": "shd_user"}
            app.dependency_overrides[_require_ai_access] = _forbidden
            r = c.post(f"/api/novels/{nid}/chapters/{ref}/style-shadow/suggest")
            assert r.status_code == 403, r.text
            assert captured == []
            app.dependency_overrides.clear()

    def test_model_not_ready_503(self):
        """会员通过但本书模型未就绪 → 503（require_novel_model 判定层口径）。"""
        async def _run():
            root, nid, ref = await _seed_book_with_chapter()
            await _seed_quant(root, distilled=True)
            return nid, ref

        nid, ref = asyncio.run(_run())
        captured: list = []

        def _no_model(project_id: str):
            raise HTTPException(503, detail={"reason": "missing_model"})

        with TestClient(app) as c:
            app.dependency_overrides[get_current_user] = lambda: {"id": "shd_user"}
            app.dependency_overrides[_require_ai_access] = lambda: True
            app.dependency_overrides[_require_novel_model] = _no_model
            r = c.post(f"/api/novels/{nid}/chapters/{ref}/style-shadow/suggest")
            assert r.status_code == 503, r.text
            assert captured == []
            app.dependency_overrides.clear()

    def test_no_baseline_409(self):
        """未蒸馏（confidence=0/基线全空）→ 409，调用未发生不记账。"""
        async def _run():
            root, nid, ref = await _seed_book_with_chapter()
            await _seed_quant(root, distilled=False)
            return nid, ref

        nid, ref = asyncio.run(_run())
        captured: list = []

        with TestClient(app) as c:
            app.dependency_overrides[get_current_user] = lambda: {"id": "shd_user"}
            app.dependency_overrides[_require_ai_access] = lambda: True
            app.dependency_overrides[_require_novel_model] = lambda: True
            r = c.post(f"/api/novels/{nid}/chapters/{ref}/style-shadow/suggest")
            assert r.status_code == 409, r.text
            assert "蒸馏" in r.json()["detail"]
            assert captured == []
            app.dependency_overrides.clear()

    def test_client_none_409(self, monkeypatch):
        """判定层放行但 client 拿不到（get_ai_client_for_novel → None）→ 409
        （调用未发生不记账）。"""
        async def _run():
            root, nid, ref = await _seed_book_with_chapter()
            await _seed_quant(root, distilled=True)
            return nid, ref

        nid, ref = asyncio.run(_run())
        captured: list = []

        async def _none(novel_id):
            return None

        monkeypatch.setattr("ai_client.get_ai_client_for_novel", _none)

        with TestClient(app) as c:
            app.dependency_overrides[get_current_user] = lambda: {"id": "shd_user"}
            app.dependency_overrides[_require_ai_access] = lambda: True
            app.dependency_overrides[_require_novel_model] = lambda: True
            r = c.post(f"/api/novels/{nid}/chapters/{ref}/style-shadow/suggest")
            assert r.status_code == 409, r.text
            assert "未就绪" in r.json()["detail"]
            assert captured == []
            app.dependency_overrides.clear()


class TestSuggestOk:
    def test_suggest_prompt_and_parse(self, monkeypatch):
        """200 路径：提示词带基线行＋章纲；解析按白名单清洗脏建议。"""
        async def _run():
            root, nid, ref = await _seed_book_with_chapter(
                summary="林晚在荒庙接头时被尾随。")
            await _seed_quant(root, distilled=True)
            return nid, ref

        nid, ref = asyncio.run(_run())
        captured: list = []
        payload = json.dumps({"suggestions": [
            {"row": "syntax", "value": "短句", "reason": "打斗章节奏需要"},
            {"row": "nope", "value": "x", "reason": "六行外丢弃"},
            {"row": "narrative", "value": "  ", "reason": "空值丢弃"},
            "junk",
        ]}, ensure_ascii=False)

        async def _fake(nid_):
            return _FakeClient(payload, captured)

        monkeypatch.setattr("ai_client.get_ai_client_for_novel", _fake)

        with TestClient(app) as c:
            app.dependency_overrides[get_current_user] = lambda: {"id": "shd_user"}
            app.dependency_overrides[_require_ai_access] = lambda: True
            app.dependency_overrides[_require_novel_model] = lambda: True
            r = c.post(f"/api/novels/{nid}/chapters/{ref}/style-shadow/suggest")
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["ok"] is True
            assert data["suggestions"] == [
                {"row": "syntax", "value": "短句", "reason": "打斗章节奏需要"},
            ]
            prompt = captured[-1]["messages"][0]["content"]
            assert "中长句为主" in prompt  # 基线当前值注入
            assert "林晚在荒庙接头" in prompt  # 章纲概要注入
            assert "[造悬念]荒庙接头" in prompt  # 关键事件注入
            app.dependency_overrides.clear()


class TestParseSuggestions:
    def test_wrapped_json_and_noise_tolerated(self):
        text = '前置杂讯 {"suggestions": [{"row": "syntax", "value": "短句", "reason": "r"}]} 后置杂讯'
        assert _parse_suggestions(text) == [
            {"row": "syntax", "value": "短句", "reason": "r"},
        ]

    def test_invalid_shapes_return_empty(self):
        assert _parse_suggestions("") == []
        assert _parse_suggestions("不是 JSON") == []
        assert _parse_suggestions('{"suggestions": "nope"}') == []
        assert _parse_suggestions('{"other": 1}') == []

    def test_row_whitelist_blank_value_and_reason_truncation(self):
        long_reason = "长" * 260
        long_value = "值" * 260
        text = json.dumps({"suggestions": [
            {"row": BASELINE_KEYS[0], "value": long_value, "reason": long_reason},
            {"row": "unknown_row", "value": "v", "reason": "r"},
            {"row": "rhythm", "value": "", "reason": "r"},
            {"row": "rhythm", "value": 42},  # 值非 str → str() 收编；缺理由 → ""
            [1, 2],
        ]}, ensure_ascii=False)
        out = _parse_suggestions(text)
        assert len(out) == 2
        assert out[0]["reason"] == "长" * 200  # 截断到 200
        assert out[0]["value"] == "值" * 200  # 值同截断（防超长值灌进影子行/提示词）
        assert out[1] == {"row": "rhythm", "value": "42", "reason": ""}
