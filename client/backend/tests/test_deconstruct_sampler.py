"""智能拆书选章器测试（c-deconstruct-knowledge 批A A4）：打标判例/选章约束/节奏口径。"""


from deconstruct.rhythm import _peak_intervals, _scene_switches, compute_rhythm
from deconstruct.sampler import (
    ChapterInput,
    select_chapters,
    tag_chapter,
    tag_emotions,
)


def _chapter(ref: str, chapter_no: int, text: str, vol_no: int = 1, title: str = "") -> ChapterInput:
    return ChapterInput(ref=ref, vol_no=vol_no, chapter_no=chapter_no, title=title, text=text)


# ── 打标判例 ──────────────────────────────────────────────────


def test_打标_各类正例():
    cases = {
        "打斗": "狭路相逢，两人交手，刀光剑影厮杀半宿，出手狠辣，激战正酣！" * 8,
        "对峙": "两帮人马隔街僵持，谁都不肯先动，谈判桌上寸步不让，气氛凝重。" * 8,
        "文戏": "两人在茶楼谈心聊天，说了许多往事，交流彼此的想法。" * 8,
        "开篇": "新书第一章，主角登场亮相，故事从这里开场起手。" * 8,
        "转折": "密信揭底，真相揭穿，局势急转直下，一夜翻盘。" * 8,
        "收尾": "这一卷落幕，恩怨了结收场，尾声将近，故事终结。" * 8,
        "日常": "市井烟火的一天，柴米油盐的平凡生活。" * 8,
    }
    for want, text in cases.items():
        tag = tag_chapter(text)
        assert tag.label == want, f"{want} 判成了 {tag.label}"


def test_打标_未分类不硬猜():
    tag = tag_chapter("去邮局取包裹，排队半天。")
    assert tag.label == "" and tag.strength == 0.0


def test_打标_每千字强度_防长章刷分():
    short_dense = tag_chapter("交手厮杀对决！" * 30)     # 120 字高密度
    long_sparse = tag_chapter("交手厮杀对决！" * 8 + "平淡叙述。" * 500)  # 长章低密度
    assert short_dense.strength > long_sparse.strength


def test_标题加权():
    body = "两人在渡口重逢，说了些旧事。" * 10
    with_title = tag_chapter(body, title="第三十章 火拼码头")
    without_title = tag_chapter(body)
    assert with_title.label == "打斗"  # 标题「火拼」命中（3 倍权重）
    assert with_title.strength != without_title.strength or with_title.label != without_title.label


def test_情绪词命中():
    counts = tag_emotions("他热血沸腾，怒火中烧，燃到了极点。")
    assert counts["燃"] >= 2


# ── 选章约束 ──────────────────────────────────────────────────


def _fixture_book(n_chapters: int = 40, volumes: int = 4) -> list[ChapterInput]:
    """合成一本 n 章书：循环七类场面文本，字数 1200-2600，卷按章数均分。"""
    import itertools

    pools = {
        "打斗": "正面交锋，两人交手厮杀，刀光剑影，激战！" * 12,
        "文戏": "茶楼谈心聊天，交流心事。" * 12,
        "开篇": "主角登场亮相，故事开场。" * 12,
        "转折": "密信揭底，真相揭穿，局势急转。" * 12,
        "收尾": "落幕了结，尾声收场。" * 12,
        "对峙": "僵持不下，谈判博弈，冷战对视。" * 12,
        "日常": "市井烟火，柴米油盐的平淡生活。" * 12,
    }
    cycle = itertools.cycle(pools.items())
    per_vol = n_chapters // volumes
    out = []
    for i in range(1, n_chapters + 1):
        scene, text = next(cycle)
        out.append(_chapter(
            f"g-{i}", i, text,
            vol_no=(i - 1) // per_vol + 1,
            title=f"第{i}章 {scene}示范",
        ))
    return out


def test_选章_前3固定_封顶_类型覆盖():
    book = _fixture_book(40)
    sel = select_chapters(book)
    assert sel.fixed_refs == ["g-1", "g-2", "g-3"]
    assert all(r in sel.selected_refs for r in sel.fixed_refs)
    assert len(sel.selected_refs) <= 31
    # 七类都有代表（合成书每类都有连续段落）
    labels = {sel.tags[r].label for r in sel.selected_refs}
    assert "打斗" in labels and "文戏" in labels


def test_选章_同卷上限_章长过滤_确定性():
    book = _fixture_book(40)
    sel = select_chapters(book)
    # 同卷 ≤2（类型代表层面：逐类型逐卷计数）

    vol_of = {c.ref: c.vol_no for c in book}
    per_type_vol: dict[str, dict[int, int]] = {}
    for r in sel.selected_refs:
        t = sel.tags[r].label
        v = vol_of[r]
        per_type_vol.setdefault(t, {})
        per_type_vol[t][v] = per_type_vol[t].get(v, 0) + 1
    for t, vols in per_type_vol.items():
        assert all(n <= 2 for n in vols.values()), f"{t} 同卷超限：{vols}"
    # 确定性：同输入两次同输出
    sel2 = select_chapters(book)
    assert sel2.selected_refs == sel.selected_refs


def test_选章_兜底补足确定性():
    # 冷门书：只有两类有信号 → 类型代表少，兜底补到 floor
    book = [
        _chapter("x-1", 1, "正面交锋厮杀不停。" * 20),
        _chapter("x-2", 2, "正面交锋厮杀不停。" * 20),
        _chapter("x-3", 3, "正面交锋厮杀不停。" * 20),
        _chapter("x-4", 4, "无关内容，平平无奇的一章，写些过渡。" * 60),
        _chapter("x-5", 5, "无关内容，平平无奇的一章，写些过渡。" * 60),
        _chapter("x-6", 6, "无关内容，平平无奇的一章，写些过渡。" * 60),
        _chapter("x-7", 7, "无关内容，平平无奇的一章，写些过渡。" * 60),
        _chapter("x-8", 8, "无关内容，平平无奇的一章，写些过渡。" * 60),
        _chapter("x-9", 9, "无关内容，平平无奇的一章，写些过渡。" * 60),
        _chapter("x-10", 10, "无关内容，平平无奇的一章，写些过渡。" * 60),
        _chapter("x-11", 11, "无关内容，平平无奇的一章，写些过渡。" * 60),
        _chapter("x-12", 12, "无关内容，平平无奇的一章，写些过渡。" * 60),
        _chapter("x-13", 13, "无关内容，平平无奇的一章，写些过渡。" * 60),
    ]
    sel = select_chapters(book)
    assert len(sel.selected_refs) >= 12  # floor 兜底
    assert "x-1" in sel.selected_refs    # 前 3 章固定


def test_选章_章长过滤():
    book = [
        _chapter("s-1", 1, "开场。" * 40),
        _chapter("s-2", 2, "过渡。" * 40),
        _chapter("s-3", 3, "开场。" * 40),
        _chapter("s-short", 4, "太短。"),
        _chapter("s-long", 5, "超长章。" * 4000),
        _chapter("s-6", 6, "正面交锋厮杀不停，激战！" * 20),
    ]
    sel = select_chapters(book)
    refs = set(sel.selected_refs)
    assert "s-short" not in refs and "s-long" not in refs
    assert sel.skipped.get("s-short", "").startswith("过短")
    assert sel.skipped.get("s-long", "").startswith("超长")
    # 兜底不绕过质量过滤：跳过章即使总数不足 floor 也不回流
    assert all(r not in refs for r in sel.skipped)


# ── 节奏统计器 ────────────────────────────────────────────────


def test_节奏四指标口径():
    book = _fixture_book(28, volumes=2)
    r = compute_rhythm(book)
    assert set(r) >= {"chapter_len", "scenes_per_chapter", "climax_interval", "volume_chapters"}
    assert r["chapter_len"]["min"] > 0  # fixture 每章非空
    assert r["volume_chapters"] == {"1": 14, "2": 14}


def test_峰间章距():
    series = [0, 1, 0, 5, 0, 1, 0, 8, 0, 1, 0, 7, 0, 1]  # 峰在 3/7/11 → 间距 4,4
    assert _peak_intervals(series) == [4, 4]
    assert _peak_intervals([1, 2]) == []


def test_场景切换估计():
    assert _scene_switches("叙述。\n「对话。」\n叙述。\n「对话。」") == 3
    assert _scene_switches("纯叙述没有对话。") == 0
