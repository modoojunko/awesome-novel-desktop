"""mdrender 单源（c-deconstruct-evidence-report）：作家 md 去证据＋证据报告视图。

- 证据类字段（EVIDENCE_KEYS）不入作家 md；列表值「；」join；新契约键翻中文标签。
- render_evidence/evidence_report：证据账按维度执行序、只收有证据的条目与维度。
- md_map_from_products：读取侧一律由 data 现渲染（存量任务存储 md 不再被读），
  缺 data 回退存量 md 兜底（test_deconstruct_api 旧形状夹具顺带覆盖该臂）。
"""

from deconstruct.mdrender import (
    EVIDENCE_KEYS,
    evidence_report,
    md_map_from_products,
    render_evidence,
    render_md,
)

_TECHNIQUES = {
    "confidence": "high",
    "reader_needs": [
        {"need": "日常撞鬼的代入式惊吓", "how": "把夜班公交写成异入口",
         "evidence_ch": [1, 7, 12], "transferable": "适用于任何都市背景", "note": "两说并立"},
    ],
    "techniques": [
        {"name": "章末炸点收束", "emotion_chain": ["平稳推进", "最后一句抛出反转"],
         "repro_steps": ["把关键信息压到全书最后一句", "不解释、不展开，直接断章"],
         "swappable": "反转可换成身份揭露", "no_copy": "不能每章都用",
         "example": "末班车驶向黎明", "evidence_ch": "第3、8、118章",
         "confidence": "high", "note": ""},
    ],
}


def test_evidence_keys_contract():
    """证据键单源：五键只承担「证明结论」职责，全部维度一视同仁剥除。"""
    assert EVIDENCE_KEYS == frozenset({"evidence_ch", "confidence", "note", "quote", "raw"})


def test_render_md_strips_evidence_and_humanizes_lists():
    md = render_md("写作技法", _TECHNIQUES, "13路末班车", "第1-258章")
    assert "## 读者需求" in md and "## 可复现模块卡" in md
    assert "日常撞鬼的代入式惊吓" in md and "适用于任何都市背景" in md
    assert "章末炸点收束" in md and "例：末班车驶向黎明" in md
    # 列表值说人话：「；」连接，SHALL NOT 出现 Python 列表 repr
    assert "平稳推进；最后一句抛出反转" in md
    assert "把关键信息压到全书最后一句；不解释、不展开，直接断章" in md
    assert "['" not in md
    # 证据五键全剥（含页脚口径说明退役）
    for token in ("证据章节", "可信度", "说明：", "原文佐证", "原文措辞",
                  "第3、8、118章", "1、7、12", "高＝有直接依据", "---"):
        assert token not in md, token
    # 新契约键翻中文标签（不再裸出英文键）
    assert "可迁移：适用于任何都市背景" in md and "复现步骤：把关键信息" in md
    assert "情绪链：平稳推进" in md and "可替换：反转可换成身份揭露" in md
    assert "勿照搬：不能每章都用" in md
    for key in ("need", "transferable", "repro_steps", "emotion_chain", "swappable", "no_copy"):
        assert key not in md, key


def test_render_md_skips_evidence_shell_items_and_sections():
    """条目剥证据后无内容字段→整条不出；节内全是证据壳→整节不出。"""
    md = render_md(
        "世界设定",
        {"history": [{"evidence_ch": "第2章", "note": "只有证据"},
                     {"name": "大迁徙", "note": "文明迁移"}],
         "factions": [{"evidence_ch": "第3章"}]},
        "书",
        "第1-9章",
    )
    assert "\n## 势力\n" not in md, "全证据壳条目的节不渲染"
    assert "只有证据" not in md and "文明迁移" not in md
    assert "大迁徙" in md, "有内容的条目照常（其证据已剥）"


def test_render_md_scalar_list_and_non_dict_data():
    """标量列表逐条出弹点（空串不出）；非 dict 数据兜底进 result 节。"""
    md = render_md("题材", {"tags": ["星际", "", "末世"]}, "书", "第1-9章")
    assert "- 星际\n- 末世" in md and "- \n" not in md
    md2 = render_md("题材", "科幻末世", "书", "第1-9章")
    assert "## 结果\n\n科幻末世" in md2


def test_render_evidence_view_shape():
    view = render_evidence("techniques", _TECHNIQUES)
    assert view["dim"] == "techniques" and view["name"] == "写作技法"
    assert view["confidence"] == "高"
    sections = {s["title"]: s for s in view["sections"]}
    tech = sections["可复现模块卡"]["items"][0]
    assert tech["head"] == "章末炸点收束"
    cells = {c["label"]: c["value"] for c in tech["cells"]}
    assert cells == {"证据章节": "第3、8、118章", "可信度": "高"}
    reader = sections["读者需求"]["items"][0]
    assert reader["head"] == "日常撞鬼的代入式惊吓"
    rcells = {c["label"]: c["value"] for c in reader["cells"]}
    assert rcells == {"证据章节": "1、7、12", "说明": "两说并立"}  # reader_needs 契约无条目级 confidence


def test_render_evidence_heads_and_confidence_only():
    """head 候选序与关系边/兜底臂；仅顶层可信度无条目节的维度照样下发。"""
    data = {
        "confidence": "mid",
        "edges": [{"from": "李耀", "to": "老吴", "rel_type": "相互猜疑",
                   "evidence_ch": "第75章", "note": "立场反复"}],
        "characters": [{"plot": "关" * 45, "quote": "原文引用"}],
        "volumes": [{"title": "第一卷", "ch_range": "第1-40章", "raw": "原文措辞"}],
    }
    view = render_evidence("relations", data)
    assert view["confidence"] == "中"
    sections = {s["title"]: s for s in view["sections"]}
    edge = sections["关系边"]["items"][0]
    assert edge["head"] == "李耀 → 老吴"
    char = sections["人物卡"]["items"][0]
    assert char["head"] == "关" * 40, "兜底 head 截 40 字"
    vol = sections["分卷"]["items"][0]
    vcells = {c["label"]: c["value"] for c in vol["cells"]}
    assert vcells == {"原文措辞": "原文措辞"}
    only_conf = render_evidence("intro", {"intro": "梗概", "confidence": "超高"})
    assert only_conf["sections"] == [] and only_conf["confidence"] == "超高"  # 未知档原样回显
    assert render_evidence("intro", "非 dict 数据")["confidence"] == ""


def test_evidence_report_orders_by_dim_and_filters_empty():
    products = {
        "techniques": {"file": "写作技法.md", "data": _TECHNIQUES},
        "intro": {"file": "简介.md", "data": {"intro": "无证据维度不下发"}},
        "broken": "旧形状字符串",
        "style": {"file": "写作文风.md",
                  "data": {"role": "", "rules": [{"name": "短句对话", "how": "对峙用短句",
                                                  "confidence": "high", "evidence_ch": "第17章",
                                                  "note": ""}]}},
    }
    report = evidence_report(products)
    assert [d["dim"] for d in report] == ["style", "techniques"]  # DIMENSIONS 执行序
    style = report[0]
    assert style["file"] == "写作文风.md"
    item = style["sections"][0]["items"][0]
    assert item["head"] == "短句对话"
    assert {c["label"]: c["value"] for c in item["cells"]} == {"证据章节": "第17章", "可信度": "高"}
    assert evidence_report(None) == []
    assert evidence_report({"intro": {"file": "简介.md", "data": {}}}) == []  # 无 data 维度不出


def test_md_map_renders_from_data_and_falls_back_to_stored_md():
    products = {
        "intro": {"file": "简介.md", "data": {"intro": "新渲染。"}, "md": "# 旧存储内嵌证据章节"},
        "legacy": {"file": "旧.md", "md": "只有存量 md"},
        "baddim": "旧形状字符串",
        "nofile": {"data": {"intro": "缺文件名不出"}},
    }
    mds = md_map_from_products(products, "书名", "第1-9章")
    assert mds["简介.md"] == render_md("简介", {"intro": "新渲染。"}, "书名", "第1-9章")
    assert "证据章节" not in mds["简介.md"], "现渲染口径，存储 md 不被读"
    assert mds["旧.md"] == "只有存量 md", "缺 data 回退存量 md 兜底"
    assert set(mds) == {"简介.md", "旧.md"}
