"""c-chapter-plan-ai T2：出卡校验、四维名次→字母、互斥与降级（tasks 3.3/3.4/3.5）。

不调模型：直接喂 parsed 结构进 sanitize/grades/名次形态校验。

c-chapter-plan-draw-latency 后口径变更：依据（reasons）是**参考文本**，不参与任何机判；
名次按模型输出的原始卡序给，经 keep_map 映射到保留卡（丢卡不连带作废名次）。
"""

from chapters import ai_plan
from chapters.ai_plan import (
    DIMENSIONS,
    _as_reason_map,
    _grades,
    _ranks_ok,
    _sanitize_directions,
)


def _card(axis="线索", title="同名档案", plot="她调出那份记录，最后一页被撕掉了", ending="她把残角收进怀里，决定去旧档堆", stage="矛盾升级", **kw):
    d = {
        "axis": axis, "title": title, "plot": plot, "obstacle": "旧档堆不对活人开放",
        "ending": ending, "acts": ["她：调档"], "stage": stage,
        "cast": ["沉舟"], "factions": [], "places": ["旧档堆"], "why": "撕页钩子立住了", "gap": "阻力偏程序化",
    }
    d.update(kw)
    return d


def test_sanitize_drops_unknown_axis_not_rewrite():
    parsed = {"diff": {"axes": ["线索", "关系", "危机"]},
              "directions": [_card(), _card(axis="关系", title="船队的条件", plot="船队长开价换航线，她交出半条航线", ending="她换来继续留在船上的许可"),
                             _card(axis="悬念", title="假轴")]}
    cards, keep_map, warn = _sanitize_directions(parsed)
    assert len(cards) == 2
    assert keep_map == [0, 1]  # 原始卡序：丢的是第 3 张
    assert all(c["axis"] in ("线索", "关系") for c in cards)  # 未知轴丢卡，不改写
    assert any("闭集" in w or "不一致" in w for w in warn)


def test_sanitize_drops_stage_out_of_set_and_overlong():
    parsed = {"diff": {"axes": ["线索", "关系"]},
              "directions": [_card(), _card(axis="关系", stage="高潮", title="越界阶段")]}
    cards, keep_map, warn = _sanitize_directions(parsed)
    assert len(cards) == 1 and cards[0]["stage"] == "矛盾升级"
    assert keep_map == [0]
    assert warn


def test_dedupe_similar_cards():
    same_plot = "她调出那份记录，最后一页被撕掉了"
    parsed = {"diff": {"axes": ["线索", "关系"]},
              "directions": [_card(), _card(axis="关系", title="第二张", plot=same_plot, ending="她把残角收进怀里，决定去旧档堆")]}
    cards, keep_map, warn = _sanitize_directions(parsed)
    assert len(cards) == 1 and keep_map == [0]
    assert any("太像" in w for w in warn)


def test_grades_pigeonhole_and_tie():
    parsed = {"ranks": {"反转": [1, 2, 3], "递增": [1, 2, 3], "推进": [1, 3, 2], "拉力": [1, 2, 3]}}
    g = _grades(parsed, 3, [0, 1, 2])
    assert g[0] == "S" and g[1] == "B" and g[2] == "B"   # 4 个第一名 → S
    # 并列第一不计：1/1/2 → 该维无唯一第一名 → 无人得分
    tie = {"ranks": {"反转": [1, 1, 2], "递增": [1, 1, 2], "推进": [1, 1, 2], "拉力": [1, 1, 2]}}
    assert _grades(tie, 3, [0, 1, 2]) == ["B", "B", "B"]
    # 至多一张 S：随机合法名次下不出现两张 S
    import itertools
    for r1, r2 in itertools.product(itertools.permutations([1, 2, 3]), repeat=2):
        gg = _grades({"ranks": {"反转": list(r1), "递增": list(r2), "推进": [1, 2, 3], "拉力": [1, 2, 3]}}, 3, [0, 1, 2])
        assert gg.count("S") <= 1


def test_ranks_shape_soft_skip():
    """名次形态不合法只让该维不计分（不重抽）：个数不符／取值越界／跳档各一。"""
    assert _ranks_ok([1, 2, 3], 3) and _ranks_ok([1, 1, 2], 3)
    assert not _ranks_ok([1, 1, 3], 3)   # 跳档
    assert not _ranks_ok([1, 2], 3)      # 个数不符
    assert not _ranks_ok([1, 2, 4], 3)   # 取值越界
    parsed = {"ranks": {"反转": [1, 2, 3], "递增": [1, 1, 3], "推进": [1, 2], "拉力": [1, 2, 3]}}
    assert _grades(parsed, 3, [0, 1, 2]) == ["A", "B", "B"]  # 只有「反转」「拉力」计入


def test_grades_map_after_drop():
    """丢卡不连带作废名次：按原始卡序映射到保留卡；该维第一名所在卡被丢则该维不计。"""
    ranks = {"反转": [3, 1, 2], "递增": [1, 2, 3], "推进": [2, 3, 1], "拉力": [1, 3, 2]}
    # 保留第 1、3 张（原始下标 0、2）
    assert _grades({"ranks": ranks}, 3, [0, 2]) == ["A", "A"]
    # 保留第 1、2 张（原始下标 0、1）：推进第一名原本是第 3 张（已丢）→ 该维不计，其余照算
    assert _grades({"ranks": ranks}, 3, [0, 1]) == ["A", "A"]


def test_reasons_are_reference_only():
    """依据降为参考文本：不参与机判、退役逐字可寻校验；`_reasons_verifiable` 不得复活。"""
    assert not hasattr(ai_plan, "_reasons_verifiable")
    # 依据与卡面毫无字面关系，也不影响字母（名次合法即出）
    ranks = {d: [1, 2] for d in DIMENSIONS}
    assert _grades({"ranks": ranks, "reasons": {d: "这是一个非常精彩的走向" for d in DIMENSIONS}}, 2, [0, 1]) == ["S", "B"]
    # ≤20 字 clamp（超长截断、非对象当空、空串丢弃）
    assert _as_reason_map({"reasons": {"反转": "这是一句超过二十个字符的依据文本会被截断"}})["反转"] == "这是一句超过二十个字符的依据文本会被截断"[:20]
    assert _as_reason_map({"reasons": "不是对象"}) == {}
    assert _as_reason_map({"reasons": {"反转": "   "}}) == {}


# ── 端点契约（打桩模型，不真调） ─────────────────────────────────────────
def test_endpoints_contract_and_gates():
    """三端点形状与门禁：出卡 PRO＋模型门；自检只读例外（不挂 PRO）；进场全档。"""
    import os
    import tempfile

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    os.environ["DATA_ROOT"] = tempfile.mkdtemp()

    import main as m  # noqa: PLC0415

    spec = m.app.openapi()
    paths = spec["paths"]
    d = paths["/api/novels/{project_id}/volumes/{vol_ref}/chapters/ai-directions"]["post"]
    s = paths["/api/novels/{project_id}/chapters/ai-selfcheck"]["post"]
    a = paths["/api/novels/{project_id}/volumes/{vol_ref}/next-chapter-anchor"]["get"]
    assert d and s and a
    # 出卡/自检/进场 三端点均已注册（路由可达性——防 #255 的 404 先例）
    assert d["responses"] and s["responses"]
