"""章纲人物精盘 · 盘点端点与提示词测试（c-character-intro tasks 1.1–1.4）。

矩阵：
- 1.1 模板快照：单文件标记式分层、system 零占位符、示例层位（system 内、行前钉句）、
  负锚（改法/剧情建议/评分/grade 不出现）、空块渲染「（本次无）」、suggest 三值各一次；
- 1.2 端点：免费可用（只读例外）/未配模型引导 503/空章 422/只读不落库/快照同源/
  计量 operation=cast_review 且不落生成类口径＋负向锚（免费直调 ai-draw→403、
  ai-review 响应无提案卡字段）；
- 1.3 契约与校验：闭集漂移表驱动（含否定式判反即红）、缺键 suggest 缺省＋defaulted、
  滤空「老角色能演」保留＋warning 不重抽、idx 位置对位/idx 对齐双路径、空串条目跳过
  不重排、MAX_ATTEMPTS=3 只认 0 可用行、退化整章行、零新增、丢行呈现；
- 1.4 软提示与配额：两章同名触发、同章双名不触发、配额计数与档位。
"""

import asyncio
import json
import os
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_local.deps import require_ai_access as _raa
from auth_local.deps import require_novel_model as _rnm
from auth_local.middleware import get_current_user
from chapters.ai_cast import (
    AXES,
    EXIT_KINDS,
    ROW_UNJUDGED,
    SUGGESTS,
    VERDICTS,
    _quota_line,
    normalize_closed,
)
from db import async_session
from main import app
from models.chapter import Chapter, ChapterCharacter
from models.character import Character
from models.project import Novel
from models.user import User
from models.volume import Volume

REF = "vol-1-ch-1"
_UIDS: dict[str, str] = {}

GOOD_ROWS = {
    "rows": [
        {"idx": 0, "echo": "她夜探库房调包账册", "verdict": "老角色能演", "who": ["林拾"],
         "as": "", "why": "查账是她的老本行", "gap": None},
        {"idx": 1, "echo": "账房伙计把钥匙落在柜台", "verdict": "不起名也行", "who": [],
         "as": "店伙计", "why": "递一句话就退场", "gap": None},
        {"idx": 2, "echo": "码头有人拦住船家", "verdict": "缺一个新角色", "who": [], "as": "",
         "why": "缺一张押货的生面孔",
         "gap": {"need": "拦船验货的押货头目", "why_not_old": "老角色都对不上押货身份", "suggest": "延后"}},
    ]
}


# ── 种子与桩 ────────────────────────────────────────────────────────────────


async def _seed(*, chapter_cast: dict[int, list[str]] | None = None, target: int | None = None,
                cards: list[str] | None = None) -> str:
    """一书一卷 N 章（默认只第 1 章）＋出场名单行＋可选角色卡；返回 novel_id。"""
    chapter_cast = chapter_cast if chapter_cast is not None else {1: []}
    root = tempfile.mkdtemp(prefix="test_cast_ai_")
    slug = f"cr-{os.path.basename(root)}"
    uid = f"cr-{os.path.basename(root)[-12:]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{slug}@test.local", password_hash="x",
            display_name="盘点测试", api_key="", api_base_url="", api_model="",
        ))
        session.add(Novel(
            user_id=uid, name="盘点书", slug=slug, root_path=root,
            source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(select(Novel).where(Novel.root_path == root))).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷", chapter_target=target)
        session.add(vol)
        await session.flush()
        for no, names in sorted(chapter_cast.items()):
            ch = Chapter(
                project_id=proj.id, volume_id=vol.id, chapter_no=no,
                ref=f"vol-1-ch-{no}", title=f"第{no}章", status="outline",
            )
            session.add(ch)
            await session.flush()
            for i, nm in enumerate(names):
                session.add(ChapterCharacter(
                    chapter_id=ch.id, sort_order=i, character_name=nm,
                ))
        for seq, nm in enumerate(cards or [], 1):
            session.add(Character(novel_id=proj.id, seq=seq, name=nm, role="配角"))
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


def _patch(monkeypatch, client):
    async def _fake(novel_id):
        return client

    monkeypatch.setattr("volumes.ai_plan.get_ai_client_for_novel", _fake)


def _free_tier(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr("auth_local.deps.ensure_entitlement_snapshot", _noop)
    monkeypatch.setattr(
        "auth_local.deps.check_permission",
        lambda: {"is_member": False, "expired": False, "project_limit": 1},
    )


def _post(nid: str, path: str, body: dict | None = None, *, model: bool = True, access: bool = True):
    c = TestClient(app)
    c.__enter__()
    app.dependency_overrides[get_current_user] = lambda: {"id": _UIDS[nid]}
    if access:
        app.dependency_overrides[_raa] = lambda: True
    if model:
        app.dependency_overrides[_rnm] = lambda: True
    try:
        return c.post(f"/api/novels/{nid}/chapters/{REF}/{path}", json=body or {})
    finally:
        app.dependency_overrides.clear()


def _body(**kw) -> dict:
    b = {
        "summary": "她夜探库房调包账册", "challenge": "船家临时改口要加钱",
        "plot_stage": "矛盾升级", "ladder_exit": "假账册入箱，灯下换人值夜",
        "plot_items": ["她夜探库房调包账册", "账房伙计把钥匙落在柜台", "码头有人拦住船家"],
        "characters": ["林拾"],
    }
    b.update(kw)
    return b


def _ops(nid: str) -> list[str]:
    from models.token_log import TokenLog

    async def _q():
        async with async_session() as s:
            rows = (await s.scalars(select(TokenLog).where(TokenLog.project_id == nid))).all()
            return [x.operation for x in rows]

    return asyncio.run(_q())


# ── 1.1 模板快照：已迁提示词仓（c-prompt-source-flip tests/test_templates_extra.py）；
# user 块头/示例覆盖断言同批；配额行（服务端代码单源）保留在本文件。


    def test_quota_line_tails_pinned(self):
        assert _quota_line("open", draw=False).endswith("配额只影响建议的分寸，不得改变三分类判定。")
        assert _quota_line("tight", draw=False).endswith("配额只影响建议的分寸，不得改变三分类判定。")
        assert _quota_line("open", draw=True).endswith("配额只影响建议分寸。")
        assert _quota_line("tight", draw=True).endswith("配额只影响建议分寸。")
        assert "1–3" in _quota_line("tight", draw=True)


# ── 1.3 归一化表驱动（闭集漂移；否定式判反即红）────────────────────────────


class TestNormalizeClosed:
    def test_verdict_variants(self):
        cases = [
            ("缺一个新角色", "缺一个新角色"),          # 精确
            ("「缺一个新角色」", "缺一个新角色"),      # 剥引号括注
            ("缺一个新角色。", "缺一个新角色"),        # 剥句读
            ("这段戏缺一个新角色", "缺一个新角色"),    # 唯一子串
            ("缺两个新角色", None),                    # 量词漂移→出界
            ("老角色能演，缺一个新角色", None),        # 双命中→出界
            ("缺一个新角色，缺一个新角色", None),      # 同值多次→出界
            ("不缺一个新角色", None),                  # 否定（单字窗）判反即红
            ("这不是缺一个新角色", None),              # 否定（双字窗「不是」）判反即红
            ("未必缺一个新角色", None),                # 否定（「未必」）判反即红
        ]
        for raw, want in cases:
            assert normalize_closed(raw, VERDICTS, allow_substring=True) == want, raw

    def test_suggest_two_char_exact_only(self):
        cases = [
            ("加人", "加人"),
            ("「改段」", "改段"),
            ("延后。", "延后"),
            ("加人或改段", None),      # 短值混入句不子串兜底→走缺省
            ("不加人", None),          # 否定（单字）判反即红
            ("不是加人", None),        # 否定（双字「不是」）判反即红
            ("还没加人", None),        # 命中位前窗含「没」
        ]
        for raw, want in cases:
            assert normalize_closed(raw, SUGGESTS, allow_substring=False) == want, raw

    def test_axis_two_char_exact_only(self):
        assert normalize_closed("身份", AXES, allow_substring=False) == "身份"
        assert normalize_closed("身份。", AXES, allow_substring=False) == "身份"
        assert normalize_closed("身份或关系", AXES, allow_substring=False) is None

    def test_exit_kind_substring_with_guard(self):
        cases = [
            ("章内退场", "章内退场"),
            ("「本卷退场」", "本卷退场"),
            ("那就本卷退场吧", "本卷退场"),
            ("本卷退场/申请常驻", None),     # 双命中→出界
            ("别申请常驻", None),            # 否定（单字「别」）
            ("不是申请常驻", None),          # 否定（双字「不是」）
        ]
        for raw, want in cases:
            assert normalize_closed(raw, EXIT_KINDS, allow_substring=True) == want, raw


# ── 1.2/1.3/1.4 端点 ───────────────────────────────────────────────────────


class TestReviewEndpoint:
    def test_free_direct_review_is_403(self, monkeypatch):
        """负向锚：免费直调 ai-review→403 member_required（只读盘点归 ai-plan 标准档，
        c-tier-gating-completion 收门——原「免费只读例外」退役）。"""
        nid = asyncio.run(_seed())
        _free_tier(monkeypatch)
        _patch(monkeypatch, _FakeClient(json.dumps(GOOD_ROWS, ensure_ascii=False)))
        r = _post(nid, "cast/ai-review", _body(), access=False)
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["reason"] == "member_required"

    def test_review_ok_without_card_fields(self, monkeypatch):
        """负向锚：盘点响应无提案卡字段（rows/quota/hints/warnings 四键）。"""
        nid = asyncio.run(_seed())
        _patch(monkeypatch, _FakeClient(json.dumps(GOOD_ROWS, ensure_ascii=False)))
        # access=True 覆盖门依赖——本钉只管响应形状，档位语义由上一钉与 HTTP 钉管
        r = _post(nid, "cast/ai-review", _body(), access=True)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body.keys()) == {"rows", "quota", "hints", "warnings"}
        assert "cards" not in body and "note" not in body  # 无提案卡字段

    def test_free_direct_draw_is_403(self, monkeypatch):
        """负向锚：免费直调 ai-draw→403 member_required（生成类归 PRO）。"""
        nid = asyncio.run(_seed())
        _free_tier(monkeypatch)
        _patch(monkeypatch, _FakeClient('{"cards": []}'))
        r = _post(
            nid, "cast/ai-draw",
            {"gap": {"idx": 0, "need": "人", "why_not_old": ""}},
            model=False, access=False,
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["reason"] == "member_required"

    def test_no_model_gives_guidance_not_500(self):
        nid = asyncio.run(_seed())
        r = _post(nid, "cast/ai-review", _body(), model=False)
        assert r.status_code == 503, r.text
        assert r.json()["detail"]["reason"] in ("no_key", "missing_model")

    def test_empty_chapter_422_without_model_call(self, monkeypatch):
        nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, _FakeClient(json.dumps(GOOD_ROWS, ensure_ascii=False), captured))
        r = _post(nid, "cast/ai-review", {
            "summary": "", "challenge": "", "plot_stage": "冲突初现",
            "ladder_exit": "", "plot_items": [], "characters": [],
        })
        assert r.status_code == 422, r.text
        assert "先写剧情再盘点" in r.json()["detail"]
        assert captured == []

    def test_empty_items_but_form_filled_degenerates(self, monkeypatch):
        """条目零条＋留存格有字 → 退化整章一行（idx=null），不 422。"""
        nid = asyncio.run(_seed())
        reply = {"rows": [{"idx": None, "echo": "", "verdict": "老角色能演", "who": ["林拾"],
                           "as": "", "why": "整章一个老角色够用", "gap": None}]}
        _patch(monkeypatch, _FakeClient(json.dumps(reply, ensure_ascii=False)))
        r = _post(nid, "cast/ai-review", _body(plot_items=[]))
        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert len(rows) == 1 and rows[0]["idx"] is None
        assert rows[0]["echo"].startswith("她夜探库房")  # echo＝梗概＋挑战＋落点前 60 字

    def test_readonly_and_metering_operation(self, monkeypatch):
        """只读不落库＋计量 operation=cast_review（不落生成类口径）。"""
        nid = asyncio.run(_seed())
        _patch(monkeypatch, _FakeClient(json.dumps(GOOD_ROWS, ensure_ascii=False)))
        r = _post(nid, "cast/ai-review", _body())
        assert r.status_code == 200, r.text

        async def _q():
            async with async_session() as s:
                chars = (
                    await s.scalars(select(Character).where(Character.novel_id == nid))
                ).all()
                ch = (
                    await s.scalars(select(Chapter).where(Chapter.project_id == nid))
                ).first()
                return len(chars), ch.plot_stage, ch.summary

        n_chars, stage, summary = asyncio.run(_q())
        assert n_chars == 0  # 角色表零变化
        assert stage in ("", None) and summary in ("", None)  # 章纲零变化（快照不落库）
        ops = _ops(nid)
        assert "cast_review" in ops, ops
        assert not any(o.startswith(("chapter_plot", "chapter_directions", "volume_", "chapter_selfcheck")) for o in ops), ops

    def test_snapshot_source_and_known_filter(self, monkeypatch):
        """快照同源：请求体 characters 并入已知集合（3s 未存名不漏）；who 逐名过滤。"""
        nid = asyncio.run(_seed(cards=["林拾"]))
        reply = {"rows": [
            {"idx": 0, "echo": "", "verdict": "老角色能演", "who": ["林拾", "只在快照里的人"],
             "as": "", "why": "都在名单里", "gap": None},
            {"idx": 1, "echo": "", "verdict": "老角色能演", "who": ["凭空冒出来的人"],
             "as": "", "why": "名字查无此人", "gap": None},
        ]}
        captured: list = []
        _patch(monkeypatch, _FakeClient(json.dumps(reply, ensure_ascii=False), captured))
        r = _post(nid, "cast/ai-review", _body(characters=["林拾", "只在快照里的人"]))
        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert rows[0]["who"] == ["林拾", "只在快照里的人"]  # 快照名字在已知集合内
        assert rows[1]["who"] == [] and rows[1]["verdict"] == "老角色能演"  # 滤空保留
        assert any("核对" in w for w in r.json()["warnings"])
        assert len(captured) == 1  # 判读类不重抽
        assert "只在快照里的人" in captured[-1]["messages"][0]["content"]

    def test_who_filter_drops_faction_and_place_names(self, monkeypatch):
        """who 过滤域＝角色名∪别名∪出场名单∪无卡名——known_entities 的势力/地点
        不进 who（spec R2 名字来源域；终审 P3，素材禁令行同词）。"""
        nid = asyncio.run(_seed(cards=["林拾"]))

        async def fake_material(db, project, with_hooks=False):
            return {
                "fullstory": "主线截取素材。",
                "card_names": {"林拾"},
                "known_entities": {"林拾", "铁衣卫", "母港旧址"},
            }

        monkeypatch.setattr("chapters.ai_cast._book_material", fake_material)
        reply = {"rows": [
            {"idx": 0, "echo": "", "verdict": "老角色能演",
             "who": ["林拾", "铁衣卫", "母港旧址"], "as": "",
             "why": "都在已知集合里", "gap": None},
        ]}
        _patch(monkeypatch, _FakeClient(json.dumps(reply, ensure_ascii=False)))
        r = _post(nid, "cast/ai-review", _body(characters=["林拾"]))
        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert rows[0]["who"] == ["林拾"]  # 势力/地点被 who 过滤域收掉

    def test_idx_positional_alignment_and_echo(self, monkeypatch):
        """等长按位置对位：模型 idx/echo 都被服务端覆盖成快照原文。"""
        nid = asyncio.run(_seed())
        reply = {"rows": [
            {"idx": 9, "echo": "模型自己编的回显", "verdict": "老角色能演", "who": ["林拾"], "as": "", "why": "a", "gap": None},
            {"idx": 9, "echo": "x", "verdict": "不起名也行", "who": [], "as": "店伙计", "why": "b", "gap": None},
            {"idx": 9, "echo": "x", "verdict": "缺一个新角色", "who": [], "as": "",
             "why": "c", "gap": {"need": "押货头目", "why_not_old": "老角色不对路", "suggest": "加人"}},
        ]}
        _patch(monkeypatch, _FakeClient(json.dumps(reply, ensure_ascii=False)))
        r = _post(nid, "cast/ai-review", _body())
        rows = r.json()["rows"]
        assert [x["idx"] for x in rows] == [0, 1, 2]
        assert rows[0]["echo"] == "她夜探库房调包账册"[:60]
        assert rows[0]["why"] == "a" and rows[2]["gap"]["suggest"] == "加人"

    def test_idx_alignment_path_and_invalid_idx(self, monkeypatch):
        """不等长按 idx 对齐：无效 idx 丢行、缺行段给「这一段没判出来」行。"""
        nid = asyncio.run(_seed())
        reply = {"rows": [
            {"idx": 2, "echo": "", "verdict": "不起名也行", "who": [], "as": "路人", "why": "b", "gap": None},
            {"idx": 7, "echo": "", "verdict": "老角色能演", "who": ["林拾"], "as": "", "why": "x", "gap": None},
        ]}
        _patch(monkeypatch, _FakeClient(json.dumps(reply, ensure_ascii=False)))
        r = _post(nid, "cast/ai-review", _body())
        rows = r.json()["rows"]
        assert [x["idx"] for x in rows] == [0, 1, 2]
        assert rows[2]["verdict"] == "不起名也行"
        assert rows[0]["verdict"] == ROW_UNJUDGED and rows[1]["verdict"] == ROW_UNJUDGED
        assert any("没判出来" in w for w in r.json()["warnings"])

    def test_blank_items_skipped_without_reindex(self, monkeypatch):
        """空串条目跳过不重排：只剩 idx=1 的目标段。"""
        nid = asyncio.run(_seed())
        reply = {"rows": [
            {"idx": 0, "echo": "", "verdict": "老角色能演", "who": ["林拾"], "as": "", "why": "a", "gap": None},
        ]}
        _patch(monkeypatch, _FakeClient(json.dumps(reply, ensure_ascii=False)))
        r = _post(nid, "cast/ai-review", _body(plot_items=["", "账房伙计把钥匙落在柜台", "  "]))
        rows = r.json()["rows"]
        assert len(rows) == 1 and rows[0]["idx"] == 1
        assert rows[0]["echo"] == "账房伙计把钥匙落在柜台"

    def test_out_of_closed_set_becomes_unjudged_row(self, monkeypatch):
        """verdict 出闭集：该段换「这一段没判出来」行（不静默少行），其余段照出、不重抽。"""
        nid = asyncio.run(_seed())
        reply = {"rows": [
            {"idx": 0, "echo": "", "verdict": "缺一个新帮手", "who": [], "as": "", "why": "", "gap": None},
            {"idx": 1, "echo": "", "verdict": "老角色能演", "who": ["林拾"], "as": "", "why": "a", "gap": None},
            {"idx": 2, "echo": "", "verdict": "老角色能演", "who": ["林拾"], "as": "", "why": "b", "gap": None},
        ]}
        captured: list = []
        _patch(monkeypatch, _FakeClient(json.dumps(reply, ensure_ascii=False), captured))
        r = _post(nid, "cast/ai-review", _body())
        rows = r.json()["rows"]
        assert rows[0]["verdict"] == ROW_UNJUDGED
        assert rows[0]["gap"] is None and rows[0]["why"] == ""
        assert len(captured) == 1  # 有可用行就不重抽

    def test_zero_new_is_normal_output(self, monkeypatch):
        nid = asyncio.run(_seed())
        reply = {"rows": [
            {"idx": i, "echo": "", "verdict": "老角色能演", "who": ["林拾"], "as": "", "why": "a", "gap": None}
            for i in range(3)
        ]}
        _patch(monkeypatch, _FakeClient(json.dumps(reply, ensure_ascii=False)))
        r = _post(nid, "cast/ai-review", _body())
        rows = r.json()["rows"]
        assert all(x["gap"] is None for x in rows) and len(rows) == 3

    def test_suggest_default_and_defaulted_flag(self, monkeypatch):
        """缺键/出界 suggest → 缺省「加人」＋defaulted=true（前端不打「AI 建议」标）。"""
        nid = asyncio.run(_seed())
        reply = {"rows": [
            {"idx": 0, "echo": "", "verdict": "缺一个新角色", "who": [], "as": "", "why": "a",
             "gap": {"need": "押货头目", "why_not_old": "老角色不对路"}},          # 缺键
            {"idx": 1, "echo": "", "verdict": "缺一个新角色", "who": [], "as": "", "why": "b",
             "gap": {"need": "更夫", "why_not_old": "分身乏术", "suggest": "加人或改段"}},  # 混入句
            {"idx": 2, "echo": "", "verdict": "缺一个新角色", "who": [], "as": "", "why": "c",
             "gap": {"need": "见证人", "why_not_old": "不在场", "suggest": "延后"}},        # 正常
        ]}
        _patch(monkeypatch, _FakeClient(json.dumps(reply, ensure_ascii=False)))
        rows = _post(nid, "cast/ai-review", _body()).json()["rows"]
        assert rows[0]["gap"]["suggest"] == "加人" and rows[0]["defaulted"] is True
        assert rows[1]["gap"]["suggest"] == "加人" and rows[1]["defaulted"] is True
        assert rows[2]["gap"]["suggest"] == "延后" and rows[2]["defaulted"] is False

    def test_retry_only_on_zero_usable_rows(self, monkeypatch):
        """整批重试只认「0 可用行/JSON 不可解析」：喂失败摘要走 user 尾块、system 各轮恒定。"""
        nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, _FakeClient(["这不是 JSON", json.dumps(GOOD_ROWS, ensure_ascii=False)], captured))
        r = _post(nid, "cast/ai-review", _body())
        assert r.status_code == 200, r.text
        assert len(captured) == 2
        assert captured[1]["system"] == captured[0]["system"]  # system 各轮恒定
        assert "=====【上次失败原因】=====" in captured[1]["messages"][0]["content"]
        assert captured[1]["temperature"] == 0.1
        assert captured[0]["temperature"] == 0.2
        assert captured[0]["max_tokens"] == 4096
        ops = _ops(nid)
        assert "cast_review" in ops and "cast_review_retry" in ops

    def test_max_attempts_three_then_502(self, monkeypatch):
        nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, _FakeClient("这不是 JSON", captured))
        r = _post(nid, "cast/ai-review", _body())
        assert r.status_code == 502, r.text
        assert len(captured) == 3  # MAX_ATTEMPTS=3

    def test_soft_hint_two_chapters_and_same_chapter_dedupe(self, monkeypatch):
        """软提示：同名出现在 ≥2 章触发；同章双行只算一章不触发。"""
        nid = asyncio.run(_seed(chapter_cast={1: ["阿七", "阿七", "孙八"], 2: ["阿七", "赵九"]}))
        reply = {"rows": [{"idx": 0, "echo": "", "verdict": "老角色能演", "who": ["阿七"],
                           "as": "", "why": "a", "gap": None}]}
        _patch(monkeypatch, _FakeClient(json.dumps(reply, ensure_ascii=False)))
        r = _post(nid, "cast/ai-review", _body(characters=["阿七"]))
        hints = r.json()["hints"]
        names = {h["name"] for h in hints}
        assert "阿七" in names  # 第 1、2 章都出现 → 建议建卡
        assert all("建议建卡" in h["text"] for h in hints)
        assert "孙八" not in names  # 同章两行只算一章，不误触发
        assert "赵九" not in names  # 只在第 2 章出现（快照不含）→ 不触发

    def test_quota_count_and_regime(self, monkeypatch):
        """配额计数＝本卷出场名单去重名字数（含无卡名，快照并入）；档位按已排章数派生。"""
        nid = asyncio.run(_seed(chapter_cast={1: ["阿七"], 2: ["赵九"]}, cards=["林拾"]))
        reply = {"rows": [{"idx": 0, "echo": "", "verdict": "老角色能演", "who": ["林拾"],
                           "as": "", "why": "a", "gap": None}]}
        _patch(monkeypatch, _FakeClient(json.dumps(reply, ensure_ascii=False)))
        q = _post(nid, "cast/ai-review", _body(characters=["林拾", "钱十"])).json()["quota"]
        assert q == {"named_count": 4, "regime": "open"}  # 阿七/赵九/林拾/钱十

        # 4 章已排、未设目标 → 收紧期
        nid2 = asyncio.run(_seed(chapter_cast={1: [], 2: [], 3: [], 4: []}))
        _patch(monkeypatch, _FakeClient(json.dumps(reply, ensure_ascii=False)))
        q2 = _post(nid2, "cast/ai-review", _body()).json()["quota"]
        assert q2["regime"] == "tight"

    def test_system_carries_material_blocks(self, monkeypatch):
        """素材＝裁剪子集：主线截取＋三个人名单块＋配额行；不裸 dump 集合清单。"""
        nid = asyncio.run(_seed(cards=["林拾"]))
        captured: list = []
        _patch(monkeypatch, _FakeClient(json.dumps(GOOD_ROWS, ensure_ascii=False), captured))
        _post(nid, "cast/ai-review", _body(characters=["林拾", "阿七"]))
        user_msg = captured[-1]["messages"][0]["content"]
        for mark in ("【主线（截取）】", "【人物全名单（含别名）】", "【出场名单（本章）】",
                     "【无卡出场名单（本卷出现、未建卡）】", "【本卷配额】"):
            assert mark in user_msg, mark
        assert "配额只影响建议的分寸，不得改变三分类判定。" in user_msg
        assert "（本次无）" in user_msg  # 临时要求为空 → 块头恒存＋「（本次无）」
        assert "她夜探库房调包账册" in user_msg  # 条目原文照抄
        system = captured[-1]["system"]
        assert "演这段戏的角色只写有名有姓的人，不写势力、地点、泛称" in system  # 禁令上移 system
        assert "配额只影响建议的分寸，不得改变三分类判定" in system  # 静态钉句上移 system
