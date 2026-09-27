"""章纲人物精盘 · 提案抽卡端点＋建卡扩参测试（c-character-intro tasks 2.1–2.3）。

矩阵：
- 2.1 模板快照：示例覆盖三轴三档、剔 why_not_old、system 零占位符、块界常驻、负锚；
- 2.2 抽卡端点：等级表驱动（3 维 2/3 项第一、并列不计、4 维回归 ≥3=S）＋组合对拍
  （同轴近似/称呼等值/异轴同词不丢/撞已知实体）＋axis 与退场档出界丢卡进重试＋
  clash 标志降温断言（exclude 撞车 0.7、结构性 0.3）＋降级阶梯（不足 2 张走重试、
  尽头回空批）＋why_not_old 服务端直抄不 clamp＋门控；
- 2.3 create_character 扩参：persona clamp 300＋prefill 白名单（非法键 400）＋
  background 拼句逐字形制（退场档值原文）＋409 撞名语义不变＋别名撞名名优先。
"""

import asyncio
import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_local.deps import require_ai_access as _raa
from auth_local.deps import require_novel_model as _rnm
from auth_local.middleware import get_current_user
from chapters.ai_cast import CAST_DIMS, CastExcludeItem
from chapters.ai_plan import DIMENSIONS, _grades
from db import async_session
from main import app
from models.chapter import Chapter
from models.character import Character
from models.project import Novel
from models.user import User
from models.volume import Volume

REF = "vol-1-ch-1"
_UIDS: dict[str, str] = {}

CARD_FIELDS = (
    "axis", "name", "duty", "persona", "entrance", "exit_kind", "exit_note",
    "ranks", "reasons", "why_not_old", "grade",
)


def _card(axis, name, persona, exit_kind="章内退场", ranks=None, **kw):
    c = {
        "axis": axis, "name": name,
        "duty": kw.get("duty", "替商号押送紧要货物"),
        "persona": persona,
        "entrance": kw.get("entrance", "码头拦船验货，当众报出货单"),
        "exit_kind": exit_kind,
        "exit_note": kw.get("exit_note", "验完货连夜离港"),
        "ranks": ranks or {"合不合适": 1, "差别在哪": 2, "好不好落地": 3},
        "reasons": {"合不合适": "正好卡在验货这环", "差别在哪": "身份老角色里没有", "好不好落地": "当场上场当场退"},
    }
    return c


GOOD_CARDS = {
    "cards": [
        _card("身份", "孟舟白", "行伍出身的押货头目，规矩重、话少，认单不认人", "章内退场",
              ranks={"合不合适": 1, "差别在哪": 1, "好不好落地": 3}),
        _card("关系", "温四娘", "跑单帮的女船东，笑面藏刀，欠她人情的人都睡不安稳", "本卷退场",
              ranks={"合不合适": 2, "差别在哪": 2, "好不好落地": 1}),
        _card("功能", "哑哨", "不会说话的信使，只认哨声办事，从不问信里写的什么", "申请常驻",
              ranks={"合不合适": 3, "差别在哪": 3, "好不好落地": 2}),
    ],
    "note": "三张分别走身份／关系／功能三条路",
}

# 重试第二轮的干净批（称呼全新，避开 exclude 撞名）
GOOD_CARDS_2 = {
    "cards": [
        _card("身份", "雷老三", "码头上验货的老把式，眼里不揉沙子"),
        _card("关系", "阿荔", "船家的外甥女，嘴快心热，专管递话"),
        _card("功能", "更夫哑锣", "打更报火的更夫，全城的巷子都熟"),
    ],
    "note": "",
}


# ── 种子与桩 ────────────────────────────────────────────────────────────────


async def _seed(*, cards: list[str] | None = None) -> str:
    root = tempfile.mkdtemp(prefix="test_cast_draw_")
    slug = f"cd-{os.path.basename(root)}"
    uid = f"cd-{os.path.basename(root)[-12:]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{slug}@test.local", password_hash="x",
            display_name="抽卡测试", api_key="", api_base_url="", api_model="",
        ))
        session.add(Novel(
            user_id=uid, name="抽卡书", slug=slug, root_path=root,
            source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(select(Novel).where(Novel.root_path == root))).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        session.add(Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref=REF, title="第1章", status="outline",
            summary="她夜探库房调包账册", challenge="船家临时改口要加钱",
            ladder_exit="假账册入箱，灯下换人值夜",
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


def _draw_body(**kw) -> dict:
    b = {
        "gap": {"idx": 2, "need": "拦船验货的押货头目", "why_not_old": "老角色都对不上押货的身份"},
        "characters": ["林拾"],
        "exclude": [],
    }
    b.update(kw)
    return b


# ── 2.1 模板快照 ────────────────────────────────────────────────────────────


class TestDrawPromptTemplate:
    def test_example_covers_axes_exit_kinds_and_dims(self):
        from prompts import load_layers

        system, _user = load_layers("cast_draw")
        example = system[system.index("【输出示例】"):]
        for axis in ("身份", "关系", "功能"):
            assert f'"axis":"{axis}"' in example.replace(" ", "")
        for kind in ("章内退场", "本卷退场", "申请常驻"):
            assert f'"exit_kind":"{kind}"' in example.replace(" ", "")
        for d in CAST_DIMS:
            assert f'"{d}"' in example
        assert "以下为格式示例，不是本次输入" in example

    def test_example_omits_why_not_old(self):
        from prompts import load_layers

        system, _ = load_layers("cast_draw")
        assert "why_not_old" not in system  # 模型不输出该字段（服务端直抄缺人行）
        assert "老角色为什么不行" in system  # 但规则句要交代清楚

    def test_block_headers_constant(self):
        from prompts import load_layers

        _, user = load_layers("cast_draw")
        assert user.count("=====【缺的人】=====") == 1
        assert user.count("=====【素材】=====") == 1
        assert user.count("=====【这几条路走过了（作者换一批，避开已出的人物路数）】=====") == 1
        assert user.count("=====【临时要求】=====") == 1

    def test_exclude_block_body_pinned(self):
        """禁令块正文（decision 10 钉词源）：轴必须再用、禁同路人、仍贴缺的人；「换结构上不同」退役。"""
        from chapters.ai_cast import _EXCLUDE_RULE, _exclude_block

        assert "轴照旧三张各出一张（身份／关系／功能）" in _EXCLUDE_RULE
        assert "轴可以再用、必须再用" in _EXCLUDE_RULE
        assert "禁的是同一条人物路子" in _EXCLUDE_RULE
        assert "仍要贴合【缺的人】" in _EXCLUDE_RULE
        assert "换结构上不同" not in _EXCLUDE_RULE
        block = _exclude_block([CastExcludeItem(axis="身份", name="孟舟白", persona="押货头目")])
        assert block.startswith("- 身份｜孟舟白｜押货头目")
        assert _exclude_block([]) == "（本次无）"


# ── 2.2 等级表驱动（服务端算；唯一第一才计分）────────────────────────────────


class TestGradesTable:
    def test_three_dims_two_firsts_is_s(self):
        ranks = {"合不合适": [1, 2, 3], "差别在哪": [1, 2, 3], "好不好落地": [2, 1, 3]}
        assert _grades({"ranks": ranks}, 3, [0, 1, 2], dims=CAST_DIMS, s_min=2) == ["S", "A", "B"]

    def test_two_cards_threshold_two(self):
        """3 维 2 卡：2 项第一＝S（阈值按维数＝2，不共拆章的 3）；并列维不计分。"""
        ranks = {"合不合适": [1, 2], "差别在哪": [1, 2], "好不好落地": [2, 1]}
        assert _grades({"ranks": ranks}, 2, [0, 1], dims=CAST_DIMS, s_min=2) == ["S", "A"]
        # 好不好落地并列第一 → 该维不计分，两张各得 1 项第一 → 双 A（不出两张 S）
        tied = {"合不合适": [1, 2], "差别在哪": [2, 1], "好不好落地": [1, 1]}
        assert _grades({"ranks": tied}, 2, [0, 1], dims=CAST_DIMS, s_min=2) == ["A", "A"]
        swept = {"合不合适": [1, 2], "差别在哪": [1, 2], "好不好落地": [1, 2]}
        assert _grades({"ranks": swept}, 2, [0, 1], dims=CAST_DIMS, s_min=2) == ["S", "B"]

    def test_three_dims_one_first_each(self):
        ranks = {"合不合适": [1, 2, 3], "差别在哪": [2, 1, 3], "好不好落地": [2, 3, 1]}
        assert _grades({"ranks": ranks}, 3, [0, 1, 2], dims=CAST_DIMS, s_min=2) == ["A", "A", "A"]

    def test_three_dims_zero_firsts_is_b(self):
        ranks = {"合不合适": [2, 1, 3], "差别在哪": [2, 1, 3], "好不好落地": [2, 1, 3]}
        assert _grades({"ranks": ranks}, 3, [0, 1, 2], dims=CAST_DIMS, s_min=2) == ["B", "S", "B"]

    def test_tied_first_does_not_count(self):
        """并列第一不计该维（源头禁并列，服务端「唯一第一才计分」降为兜底）。"""
        ranks = {"合不合适": [1, 1, 2], "差别在哪": [1, 1, 2], "好不好落地": [1, 1, 2]}
        assert _grades({"ranks": ranks}, 3, [0, 1, 2], dims=CAST_DIMS, s_min=2) == ["B", "B", "B"]

    def test_pigeonhole_at_most_one_s(self):
        for r1, r2, r3 in (([1, 2, 3], [1, 2, 3], [1, 2, 3]),
                           ([1, 2, 3], [2, 1, 3], [1, 3, 2]),
                           ([1, 1, 2], [1, 2, 3], [2, 1, 3])):
            g = _grades({"ranks": {"合不合适": r1, "差别在哪": r2, "好不好落地": r3}},
                        3, [0, 1, 2], dims=CAST_DIMS, s_min=2)
            assert g.count("S") <= 1, g

    def test_keep_map_after_drop(self):
        ranks = {"合不合适": [1, 2, 3], "差别在哪": [1, 2, 3], "好不好落地": [2, 1, 3]}
        # 第 2 张被丢弃：第一落在被丢卡上的维不计分
        assert _grades({"ranks": ranks}, 3, [0, 2], dims=CAST_DIMS, s_min=2) == ["S", "B"]

    def test_four_dims_regression_threshold_three(self):
        """4 维回归（拆章）：≥3 项第一＝S 行为不变；2 项第一＝A（不得出两张 S）。"""
        ranks = {
            "反转": [1, 2, 3], "递增": [1, 2, 3], "推进": [1, 2, 3], "拉力": [2, 1, 3],
        }
        assert _grades({"ranks": ranks}, 3, [0, 1, 2], dims=DIMENSIONS, s_min=3) == ["S", "A", "B"]
        ranks2 = {
            "反转": [1, 2, 3], "递增": [1, 2, 3], "推进": [2, 1, 3], "拉力": [2, 1, 3],
        }
        g = _grades({"ranks": ranks2}, 3, [0, 1, 2], dims=DIMENSIONS, s_min=3)
        assert g == ["A", "A", "B"] and g.count("S") == 0


# ── 2.2 端点 ───────────────────────────────────────────────────────────────


class TestDrawEndpoint:
    def test_shape_grade_and_why_not_old_verbatim(self, monkeypatch):
        nid = asyncio.run(_seed())
        long_why = "老角色都对不上押货的身份，而且这一段的坎只认货单不认人，谁来都不好使"
        _patch(monkeypatch, _FakeClient(json.dumps(GOOD_CARDS, ensure_ascii=False)))
        r = _post(nid, "cast/ai-draw", _draw_body(gap={"idx": 2, "need": "押货头目", "why_not_old": long_why}))
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body.keys()) == {"cards", "note"}
        assert len(body["cards"]) == 3
        for card in body["cards"]:
            assert set(card.keys()) == set(CARD_FIELDS)
            assert card["grade"] in ("S", "A", "B")
            assert set(card["ranks"].keys()) == set(CAST_DIMS)
            assert set(card["reasons"].keys()) == set(CAST_DIMS)
            assert card["why_not_old"] == long_why  # 服务端直抄缺人行：不 clamp、逐字
        # 卡 1 在合不合适/差别在哪两个维唯一第一 → S；其余 A/B
        assert [c["grade"] for c in body["cards"]] == ["S", "A", "B"]
        assert body["note"].startswith("三张分别走")

    def test_model_side_has_no_grade_letters(self, monkeypatch):
        """模型侧零等级字母：模板/请求不给 grade，card.grade 是服务端算出的加键。"""
        from prompts import load_layers

        nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, _FakeClient(json.dumps(GOOD_CARDS, ensure_ascii=False), captured))
        body = _post(nid, "cast/ai-draw", _draw_body()).json()
        system, _ = load_layers("cast_draw")
        assert "grade" not in system  # 全文无等级字母分数
        user_msg = captured[-1]["messages"][0]["content"]
        assert "grade" not in user_msg and '"S"' not in user_msg
        assert body["cards"][0]["grade"] == "S"  # 等级由服务端按名次算

    def test_material_blocks_and_name_ban(self, monkeypatch):
        nid = asyncio.run(_seed(cards=["林拾"]))
        captured: list = []
        _patch(monkeypatch, _FakeClient(json.dumps(GOOD_CARDS, ensure_ascii=False), captured))
        _post(nid, "cast/ai-draw", _draw_body(
            characters=["阿七"],
            exclude=[{"axis": "身份", "name": "孟舟白", "persona": "行伍出身的押货头目，规矩重话少"}],
        ))
        user_msg = captured[-1]["messages"][0]["content"]
        assert "=====【缺的人】=====" in user_msg
        assert "这段戏缺的是：拦船验货的押货头目" in user_msg
        assert "【不要用这些名字】" in user_msg
        for name in ("林拾", "阿七", "孟舟白"):
            assert f"- {name}" in user_msg
        assert "- 身份｜孟舟白｜行伍出身的押货头目，规矩重话少" in user_msg
        assert "轴照旧三张各出一张（身份／关系／功能）" in user_msg
        assert "配额只影响建议分寸。" in user_msg
        assert captured[-1]["max_tokens"] == 8192 and captured[-1]["temperature"] == 0.7

    def test_empty_exclude_block_is_none_text(self, monkeypatch):
        nid = asyncio.run(_seed())
        captured: list = []
        _patch(monkeypatch, _FakeClient(json.dumps(GOOD_CARDS, ensure_ascii=False), captured))
        _post(nid, "cast/ai-draw", _draw_body())
        assert "=====【这几条路走过了（作者换一批，避开已出的人物路数）】=====\n（本次无）" in (
            captured[-1]["messages"][0]["content"]
        )

    def test_clash_by_name_cools_never(self, monkeypatch):
        """exclude 撞车（称呼等值）丢卡 → 重抽不降温（0.7）、计入 clash。"""
        nid = asyncio.run(_seed())
        captured: list = []
        first = {
            "cards": [
                _card("身份", "孟舟白", "行伍出身的押货头目，规矩重话少"),
                _card("关系", "温四娘", "跑单帮的女船东，笑面藏刀"),
                _card("功能", "哑哨", "不会说话的信使，只认哨声办事"),
            ],
            "note": "",
        }
        _patch(monkeypatch, _FakeClient([json.dumps(first, ensure_ascii=False),
                                         json.dumps(GOOD_CARDS_2, ensure_ascii=False)], captured))
        r = _post(nid, "cast/ai-draw", _draw_body(exclude=[
            {"axis": "身份", "name": "孟舟白", "persona": "完全不同的人设句"},
            {"axis": "关系", "name": "温四娘", "persona": "另一个完全不同的人设句"},
        ]))
        assert r.status_code == 200, r.text
        assert len(captured) == 2  # 只剩 1 张 → 走重试阶梯
        assert captured[1]["temperature"] == 0.7  # exclude 撞车重抽不降温
        assert "=====【上次失败原因】=====" in captured[1]["messages"][0]["content"]
        ops = [o for o in _ops(nid)]
        assert "cast_draw" in ops and "cast_draw_retry" in ops

    def test_structural_failure_cools_to_0_3(self, monkeypatch):
        """结构性失败（axis 出闭集丢到不足 2 张）→ 重试降温 0.3。"""
        nid = asyncio.run(_seed())
        captured: list = []
        bad = {"cards": [
            _card("神秘", "孟舟白", "行伍出身的押货头目"),
            _card("玄学", "温四娘", "跑单帮的女船东"),
            _card("功能", "哑哨", "不会说话的信使"),
        ], "note": ""}
        _patch(monkeypatch, _FakeClient([json.dumps(bad, ensure_ascii=False),
                                         json.dumps(GOOD_CARDS, ensure_ascii=False)], captured))
        r = _post(nid, "cast/ai-draw", _draw_body())
        assert r.status_code == 200, r.text
        assert len(captured) == 2
        assert captured[1]["temperature"] == 0.3  # 非 exclude 触发 → 照阶梯降温

    def test_pairing_same_axis_similar_dropped(self, monkeypatch):
        """对拍：同轴且人设句 difflib≥0.6 丢卡（称呼不同也算同路人）。"""
        nid = asyncio.run(_seed())
        reply = {"cards": [
            _card("身份", "孟舟白", "行伍出身的押货头目，规矩重、话少，认单不认人"),
            _card("关系", "温四娘", "跑单帮的女船东，笑面藏刀，欠她人情的人都睡不安稳"),
            _card("功能", "哑哨", "不会说话的信使，只认哨声办事，从不问信里写的什么"),
        ], "note": ""}
        _patch(monkeypatch, _FakeClient(json.dumps(reply, ensure_ascii=False)))
        r = _post(nid, "cast/ai-draw", _draw_body(exclude=[
            {"axis": "身份", "name": "雷老三", "persona": "行伍出身的押货头目，规矩重话少，认单不认人"},
        ]))
        cards = r.json()["cards"]
        assert [c["axis"] for c in cards] == ["关系", "功能"]  # 身份那张是同路人 → 丢

    def test_pairing_different_axis_same_persona_kept(self, monkeypatch):
        """边界：异轴同词不丢（禁令单位＝轴＋人设句组合，不单禁人设句）。"""
        nid = asyncio.run(_seed())
        _patch(monkeypatch, _FakeClient(json.dumps(GOOD_CARDS, ensure_ascii=False)))
        r = _post(nid, "cast/ai-draw", _draw_body(exclude=[
            {"axis": "关系", "name": "雷老三", "persona": "行伍出身的押货头目，规矩重、话少，认单不认人"},
        ]))
        cards = r.json()["cards"]
        assert [c["axis"] for c in cards] == ["身份", "关系", "功能"]  # 全留

    def test_known_name_collision_dropped(self, monkeypatch):
        """称呼撞已知实体（角色表名字）→ 丢卡计入重试。"""
        nid = asyncio.run(_seed(cards=["孟舟白"]))
        captured: list = []
        _patch(monkeypatch, _FakeClient(json.dumps(GOOD_CARDS, ensure_ascii=False), captured))
        r = _post(nid, "cast/ai-draw", _draw_body())
        cards = r.json()["cards"]
        assert "孟舟白" not in [c["name"] for c in cards]
        assert [c["axis"] for c in cards] == ["关系", "功能"]

    def test_exit_kind_out_of_set_dropped_then_retry(self, monkeypatch):
        """axis 与退场档出闭集都丢卡进重试；批内同轴重复也丢。"""
        nid = asyncio.run(_seed())
        captured: list = []
        bad = {"cards": [
            _card("身份", "孟舟白", "行伍出身的押货头目", exit_kind="退场"),        # 档出界
            _card("关系", "温四娘", "跑单帮的女船东", exit_kind="本卷退场"),
            _card("关系", "哑哨", "不会说话的信使", exit_kind="申请常驻"),          # 同轴重复
        ], "note": ""}
        _patch(monkeypatch, _FakeClient([json.dumps(bad, ensure_ascii=False),
                                         json.dumps(GOOD_CARDS, ensure_ascii=False)], captured))
        r = _post(nid, "cast/ai-draw", _draw_body())
        assert r.status_code == 200, r.text
        assert len(captured) == 2  # 只剩 1 张 → 重试
        assert [c["axis"] for c in r.json()["cards"]] == ["身份", "关系", "功能"]

    def test_retry_ladder_exhausts_to_empty_batch(self, monkeypatch):
        """降级阶梯尽头：不返回残批，回空批（前端呈失败态三出口）。"""
        nid = asyncio.run(_seed())
        captured: list = []
        one = {"cards": [_card("身份", "孟舟白", "行伍出身的押货头目")], "note": ""}
        _patch(monkeypatch, _FakeClient(json.dumps(one, ensure_ascii=False), captured))
        r = _post(nid, "cast/ai-draw", _draw_body())
        assert r.status_code == 200, r.text
        assert r.json() == {"cards": [], "note": ""}
        assert len(captured) == 3  # MAX_ATTEMPTS=3

    def test_no_model_gives_503(self):
        nid = asyncio.run(_seed())
        r = _post(nid, "cast/ai-draw", _draw_body(), model=False)
        assert r.status_code == 503, r.text
        assert r.json()["detail"]["reason"] in ("no_key", "missing_model")


def _ops(nid: str) -> list[str]:
    from models.token_log import TokenLog

    async def _q():
        async with async_session() as s:
            rows = (await s.scalars(select(TokenLog).where(TokenLog.project_id == nid))).all()
            return [x.operation for x in rows]

    return asyncio.run(_q())


# ── 2.3 create_character 向后兼容扩参 ───────────────────────────────────────


class TestCreateCharacterExt:
    @pytest.fixture(autouse=True)
    def _cleanup_overrides(self):
        yield
        app.dependency_overrides.clear()

    def _client(self, nid: str):
        c = TestClient(app)
        c.__enter__()
        app.dependency_overrides[get_current_user] = lambda: {"id": _UIDS[nid]}
        return c

    def test_persona_and_prefill_landed(self):
        nid = asyncio.run(_seed())
        c = self._client(nid)
        bg = "怎么出场：巷口拦人；怎么退场（本卷退场）：卖错主顾，卷末随商队离港"
        r = c.post(f"/api/novels/{nid}/characters", json={
            "name": "孟舟白", "role": "配角",
            "persona": "行伍出身的押货头目，规矩重、话少",
            "prefill": {"plot": "替商号押送紧要货物", "background": bg},
        })
        assert r.status_code == 200, r.text
        card = r.json()["data"]
        assert card["persona"] == "行伍出身的押货头目，规矩重、话少"
        assert card["dossier"]["plot"] == "替商号押送紧要货物"
        # background 拼句逐字形制：怎么出场＋怎么退场（退场档值原文，勿缩写）
        assert card["dossier"]["background"] == bg
        assert "怎么出场：" in card["dossier"]["background"]
        assert "怎么退场（本卷退场）：" in card["dossier"]["background"]

    def test_persona_clamped_300(self):
        nid = asyncio.run(_seed())
        c = self._client(nid)
        r = c.post(f"/api/novels/{nid}/characters", json={"name": "长人设", "persona": "人" * 400})
        assert r.status_code == 200, r.text
        assert len(r.json()["data"]["persona"]) == 300

    def test_prefill_illegal_keys_400_and_no_half_card(self):
        nid = asyncio.run(_seed())
        c = self._client(nid)
        for prefill in ({"look": "短打"}, {"plot": "x", "cog": "y"}, "不是对象", {"plot": 5}):
            r = c.post(f"/api/novels/{nid}/characters", json={"name": "违规卡", "prefill": prefill})
            assert r.status_code == 400, (prefill, r.text)
            assert r.json()["detail"]["code"] == "invalid_prefill"
        items = c.get(f"/api/novels/{nid}/characters").json()["data"]["items"]
        assert items == []  # 非法键 400 且不留半张卡

    def test_default_behavior_unchanged(self):
        nid = asyncio.run(_seed())
        c = self._client(nid)
        r = c.post(f"/api/novels/{nid}/characters", json={"name": "只带名字"})
        assert r.status_code == 200, r.text
        card = r.json()["data"]
        assert card["role"] == "配角" and card["persona"] == "" and card["dossier"] == {}
        # 空名占位与409撞名语义不变
        r2 = c.post(f"/api/novels/{nid}/characters", json={"name": "只带名字"})
        assert r2.status_code == 409
        assert r2.json()["detail"]["code"] == "name_taken"

    def test_alias_collision_name_wins(self):
        """别名撞名：称呼命中某卡别名时建卡成功（UNIQUE 只锁 name）；_resolve_names 名优先。"""
        nid = asyncio.run(_seed())
        c = self._client(nid)
        a = c.post(f"/api/novels/{nid}/characters", json={"name": "林拾"}).json()["data"]
        c.patch(f"/api/novels/{nid}/characters/{a['id']}", json={
            "path": "aliases", "value": ["乙"], "base_rev": a["rev"],
        })
        b = c.post(f"/api/novels/{nid}/characters", json={"name": "乙"})
        assert b.status_code == 200, b.text

        async def _resolve():
            from chapters.store import _resolve_names

            async with async_session() as s:
                return await _resolve_names(s, nid, ["乙", "林拾"])

        m = asyncio.run(_resolve())
        assert m["乙"] == b.json()["data"]["id"]  # 名优先于别名
        assert m["林拾"] == a["id"]
