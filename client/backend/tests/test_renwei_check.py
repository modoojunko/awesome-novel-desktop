"""人味检测引擎（c-renwei-check）：19 项指纹／人味率／定位 findings 单元测试。

纯函数为主（check_prose）；方向钉是本文件的核心——省略号/虚词是下限型（少=差）、
句号/抽象名词是上限型（多=差），写反了分数会反向（演示阶段实际发生过）。

对拍：`docs/design-c/drafts/check-renwei-demo.py` 是原型阶段与用户共同确认过的参考
实现，本文件用同一输入对拍关键指标（容差内一致），确保生产引擎不漂移。
"""

import importlib.util
import os

import pytest

from write.renwei_baseline import METRICS, MIN_RATE_CHARS
from write.renwei_check import (
    check_prose,
    gap_stats,
    hanzi,
    mtld,
    narration,
    split_paragraphs,
)

DEMO = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "docs", "design-c", "drafts", "check-renwei-demo.py"
)


def _demo():
    spec = importlib.util.spec_from_file_location("renwei_demo_ref", DEMO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _values(report):
    return {m["k"]: m["v"] for m in report["metrics"]}


# ── 基础工具 ────────────────────────────────────────────────────────────


def test_split_paragraphs_trims_and_drops_empty():
    assert split_paragraphs("  第一段 \n\n 第二段\n") == ["第一段", "第二段"]


def test_narration_strips_quoted_spans():
    txt = narration(["他说：“今天不去。”然后转身。"])
    assert "今天不去" not in txt
    assert "然后转身" in txt


def test_mtld_higher_for_varied_text():
    varied = hanzi("甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥" * 3)
    repeated = hanzi("灯" * 20 + "船" * 20 + "水" * 20)
    assert mtld(varied) > mtld(repeated)


def test_gap_stats_skew_zero_for_uniform():
    mean, skew = gap_stats("他走。她笑。你说。")
    assert mean == pytest.approx(2.0)
    assert abs(skew) < 1e-9


# ── 方向钉：每项指标「变差」方向必须让它更差 ─────────────────────────

HUMAN_LIKE = (
    "巡灯是亥时来的，光贴着水面一寸一寸扫过来的时候，阿槎正把最后半碗咸鱼粥推给陆沉……"
    "粥凉了，结了层薄油皮，腥气呛得嗓子发紧。\n"
    "「吃。」阿槎把碗往他手边又推了推，「查完这趟，天就该亮了。」\n"
    "陆沉没接话，几口把粥扒完，把碗扣在膝上，指甲一下一下刮着碗沿……"
    "巡灯的光从船头量到船尾，停了停，很快又退回去……船上只剩灯芯偶尔爆的一声轻响。\n"
    "「没查我们？还是查了没说！」\n"
    "「查的是灯。」阿槎朝桅顶努了努嘴，那盏旧灯照旧挂着，晃晃悠悠，"
    "把两个人的影子投在舱板上，一会儿长，一会儿短。\n"
    "陆沉盯着那点灯火看了半晌，忽然把袖子里的图按了按……还在。"
)


def _repeat_to_rate(text: str) -> str:
    """补足到 1500 字以上（短章不出人味率），保持文本特征。"""
    out = text
    while len(hanzi(out)) < MIN_RATE_CHARS + 100:
        out += "\n" + text
    return out


def test_more_periods_lowers_rate():
    base = _repeat_to_rate(HUMAN_LIKE)
    chopped = base.replace("，", "。")
    assert check_prose(chopped)["score"]["rate"] < check_prose(base)["score"]["rate"]


def test_fewer_function_words_lowers_rate():
    base = _repeat_to_rate(HUMAN_LIKE)
    stiff = base.replace("了", "").replace("的", "").replace("着", "")
    assert check_prose(stiff)["score"]["rate"] < check_prose(base)["score"]["rate"]


def test_more_abstract_nouns_lowers_rate():
    base = _repeat_to_rate(HUMAN_LIKE)
    abstract = base + "\n意义有价值，状态是过程的结果，情绪与感觉构成节奏。"
    assert check_prose(abstract)["score"]["rate"] <= check_prose(base)["score"]["rate"]


def test_ellipsis_floor_judged():
    base = _repeat_to_rate(HUMAN_LIKE)
    r = check_prose(base)
    ellipsis = next(m for m in r["metrics"] if m["k"] == "省略号 / 千字")
    assert ellipsis["ok"] is True  # 人类腔样本省略号充足
    bare = check_prose(_repeat_to_rate(HUMAN_LIKE.replace("……", "。")))
    ell2 = next(m for m in bare["metrics"] if m["k"] == "省略号 / 千字")
    assert ell2["ok"] is False


# ── 定位 findings ────────────────────────────────────────────────────


def test_dash_and_not_a_but_b_located_to_para():
    text = "第一段干净。\n他按住她的手——掌心一片凉。\n这不是勇气的问题，而是信任的问题。"
    r = check_prose(text)
    rules = {f["rule_id"]: f for f in r["findings"]}
    assert rules["dash"]["para"] == 1
    assert rules["dash"]["sev"] == "err"
    assert rules["not_a_but_b"]["para"] == 2
    assert "不是勇气" in rules["not_a_but_b"]["hit"]


def test_trailing_tag_located():
    r = check_prose("「三更了。」陆沉说。")
    assert any(f["rule_id"] == "trailing_tag" and f["para"] == 0 for f in r["findings"])


def test_halfwidth_and_nested_quote_are_err():
    r = check_prose("他走,她笑。“外层“内层”外层”。")
    ids = {f["rule_id"] for f in r["findings"]}
    assert "halfwidth_punct" in ids
    assert "nested_quotes" in ids


def test_para_head_repeat_exempts_dialogue():
    # 两段都以对白起手＝豁免；正文起手同词才报
    dialogue = "「走。」他说。\n「走。」她说。"
    assert not any(f["rule_id"] == "para_head_repeat" for f in check_prose(dialogue)["findings"])
    narr = "陆沉抬头看灯。\n陆沉低头看图。"
    assert any(f["rule_id"] == "para_head_repeat" for f in check_prose(narr)["findings"])


def test_long_sentence_located():
    long_sent = "他" + "走" * 70 + "。"
    r = check_prose(long_sent)
    f = next(f for f in r["findings"] if f["rule_id"] == "long_sent")
    assert "71" in f["hit"]


def test_findings_use_zero_based_para_order():
    text = "干净段。\n他按住她的手——掌心一片凉。"
    r = check_prose(text)
    assert all(0 <= f["para"] < r["paras"] for f in r["findings"])


# ── 门槛与短章语义 ───────────────────────────────────────────────────


def test_short_chapter_has_no_rate_but_keeps_findings():
    r = check_prose("他按住她的手——掌心一片凉。")
    assert r["short_chapter"] is True
    assert r["score"] is None
    assert r["priorities"] == []
    assert any(f["rule_id"] == "dash" for f in r["findings"])


def test_mtld_unconverged_marks_sample_insufficient():
    r = check_prose(HUMAN_LIKE)
    assert r["mtld_unconverged"] is True
    mtld_metric = next(m for m in r["metrics"] if m["k"] == "MTLD 词汇丰富度")
    assert mtld_metric["v"] == "—"
    assert mtld_metric["ok"] is None


def test_empty_prose_is_safe():
    r = check_prose("")
    assert r["chars"] == 0
    assert r["paras"] == 0
    assert r["score"] is None
    assert r["findings"] == []


# ── 基线与确定性 ─────────────────────────────────────────────────────


def test_all_19_metrics_present():
    r = check_prose(HUMAN_LIKE)
    assert len(r["metrics"]) == 19
    assert len(METRICS) == 19
    keys = {m["k"] for m in r["metrics"]}
    for expect in ("句号 / 千字", "句长趋同连串", "虚词 / 千字", "感官覆盖类数"):
        assert expect in keys


def test_deterministic_repeat_runs():
    a = check_prose(HUMAN_LIKE)
    b = check_prose(HUMAN_LIKE)
    assert a == b


def test_priorities_sorted_by_weight_times_z():
    r = check_prose(_repeat_to_rate(HUMAN_LIKE.replace("，", "。")))
    if r["priorities"]:
        scores = [p["w"] * abs(p["z"]) for p in r["priorities"]]
        assert scores == sorted(scores, reverse=True)
        assert len(r["priorities"]) <= 3


# ── 对拍：生产引擎 vs 原型参考实现 ──────────────────────────────────


@pytest.mark.skipif(not os.path.exists(DEMO), reason="原型参考实现不在本检出")
def test_matches_reference_implementation():
    """同一演示文本：生产引擎与原型参考实现的关键指标一致（容差 0.1）。

    参考实现是用户逐屏确认过的原型数字来源；漂移即意味着原型与实现不再同源。
    """
    demo = _demo()
    chapters = demo.extract_chapters(demo.read(demo.SRC))
    for key, expect_rate in (("ch14", 53.9), ("ch13", 81.6)):
        text = "\n".join(chapters[key])
        r = check_prose(text)
        assert r["chars"] == len(hanzi(text))
        assert r["score"]["rate"] == pytest.approx(expect_rate, abs=0.2)
        vals = _values(r)
        # 关键密度项与参考实现同口径（参考值来自同一演示文本的实算）
        for label, expected in (
            ("句号 / 千字", 67.3 if key == "ch14" else 23.8),
            ("省略号 / 千字", 0.0 if key == "ch14" else 18.8),
            ("虚词 / 千字", 218.1 if key == "ch14" else 199.5),
            ("抽象名词 / 千字", 5.2 if key == "ch14" else 2.7),
            ("具体名词 / 千字", 29.9 if key == "ch14" else 24.5),
        ):
            assert float(vals[label].rstrip("%")) == pytest.approx(expected, abs=0.1), label
