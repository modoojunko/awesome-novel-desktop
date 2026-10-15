"""脱敏层钉子（模型输入中性替换，绕开内容审核 1301）：

- 基础替换与计数留痕；长短语优先（「血流成河」不被「流血」截胡成乱码）；
- 空文本／无命中恒等返回；常用词不误伤（词表不收单字，「鬼才」「杀价」原样）；
- 替换不改叙事事实：中性词语义等价，喂模型副本专用。
"""

from deconstruct.sanitize import sanitize_for_model


def test_basic_replacement_with_hits():
    out, hits = sanitize_for_model("她看见了尸体，鲜血淋漓。")
    assert "尸体" not in out and "鲜血" not in out
    assert "遗体" in out and "血液" in out
    assert len(hits) == 2
    assert any(h.startswith("尸体→遗体") and "（1处）" in h for h in hits)
    assert any(h.startswith("鲜血→血液") and "（1处）" in h for h in hits)


def test_long_phrase_before_substring():
    out, hits = sanitize_for_model("门外血流成河")
    assert out == "门外大面积出血"
    assert hits == ["血流成河→大面积出血（1处）"]


def test_count_reported():
    out, hits = sanitize_for_model("一具尸体。又一具尸体。")
    assert out == "一具遗体。又一具遗体。"
    assert hits == ["尸体→遗体（2处）"]


def test_empty_and_no_hit_identity():
    assert sanitize_for_model("") == ("", [])
    text = "林晚在渡口救人，阿蓟归来报恩。"
    assert sanitize_for_model(text) == (text, [])


def test_common_words_not_collateral():
    """词表刻意不收单字：常用词误替换会毁喂料语义。"""
    text = "他真是鬼才，杀价杀得店主直跺脚。"
    out, hits = sanitize_for_model(text)
    assert out == text and hits == []


def test_no_sensitive_left_after_replacement():
    """替换后文本不再含任何词表原词（避免替换输出又撞上其它键的子串漏网）。"""
    from deconstruct.sanitize import _SORTED_MAP

    sample = "。".join(k for k, _ in _SORTED_MAP)
    out, _ = sanitize_for_model(sample)
    for original, _ in _SORTED_MAP:
        assert original not in out, f"替换后仍残留：{original}"
