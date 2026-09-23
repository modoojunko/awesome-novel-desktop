"""c-chapter-plan-ai T2：出卡校验、四维名次→字母、互斥与降级（tasks 3.3/3.4/3.5）。

不调模型：直接喂 parsed 结构进 sanitize/grades/reasons 校验。
"""

from chapters.ai_plan import (
    DIMENSIONS,
    _grades,
    _reasons_verifiable,
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
    cards, warn = _sanitize_directions(parsed)
    assert len(cards) == 2
    assert all(c["axis"] in ("线索", "关系") for c in cards)  # 未知轴丢卡，不改写
    assert any("闭集" in w or "不一致" in w for w in warn)


def test_sanitize_drops_stage_out_of_set_and_overlong():
    parsed = {"diff": {"axes": ["线索", "关系"]},
              "directions": [_card(), _card(axis="关系", stage="高潮", title="越界阶段")]}
    cards, warn = _sanitize_directions(parsed)
    assert len(cards) == 1 and cards[0]["stage"] == "矛盾升级"
    assert warn


def test_dedupe_similar_cards():
    same_plot = "她调出那份记录，最后一页被撕掉了"
    parsed = {"diff": {"axes": ["线索", "关系"]},
              "directions": [_card(), _card(axis="关系", title="第二张", plot=same_plot, ending="她把残角收进怀里，决定去旧档堆")]}
    cards, warn = _sanitize_directions(parsed)
    assert len(cards) == 1
    assert any("太像" in w for w in warn)


def test_grades_pigeonhole_and_tie():
    parsed = {"ranks": {"反转": [1, 2, 3], "递增": [1, 2, 3], "推进": [1, 3, 2], "拉力": [1, 2, 3]}}
    g = _grades(parsed, 3)
    assert g[0] == "S" and g[1] == "B" and g[2] == "B"   # 4 个第一名 → S
    # 并列第一不计：1/1/2 → 该维无唯一第一名 → 无人得分
    tie = {"ranks": {"反转": [1, 1, 2], "递增": [1, 1, 2], "推进": [1, 1, 2], "拉力": [1, 1, 2]}}
    assert _grades(tie, 3) == ["B", "B", "B"]
    # 至多一张 S：随机合法名次下不出现两张 S
    import itertools
    for r1, r2 in itertools.product(itertools.permutations([1, 2, 3]), repeat=2):
        gg = _grades({"ranks": {"反转": list(r1), "递增": list(r2), "推进": [1, 2, 3], "拉力": [1, 2, 3]}}, 3)
        assert gg.count("S") <= 1


def test_reasons_must_be_verbatim():
    cards = [_card(), _card(axis="关系", title="船队的条件", plot="船队长开价换航线", ending="她换来留在船上的许可")]
    good = {"ranks": {d: [1, 2] for d in DIMENSIONS},
            "reasons": {"反转": "最后一页被撕掉了", "递增": "旧档堆不对活人开放", "推进": "决定去旧档堆", "拉力": "决定去旧档堆"}}
    assert _reasons_verifiable(good, cards) is True
    bad = {"ranks": {d: [1, 2] for d in DIMENSIONS},
           "reasons": {"反转": "这是一个非常精彩的反转", "递增": "旧档堆不对活人开放", "推进": "决定去旧档堆", "拉力": "决定去旧档堆"}}
    assert _reasons_verifiable(bad, cards) is False


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
    s = paths["/api/novels/{project_id}/chapters/{chapter_ref}/ai-selfcheck"]["post"]
    a = paths["/api/novels/{project_id}/volumes/{vol_ref}/next-chapter-anchor"]["get"]
    assert d and s and a
    # 出卡/自检/进场 三端点均已注册（路由可达性——防 #255 的 404 先例）
    assert d["responses"] and s["responses"]
