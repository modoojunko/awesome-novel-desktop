"""情绪条件的匹配口径（c-kb-emotion-free-text）：自由文本两侧归一再比，不可归一不算条件。"""

from types import SimpleNamespace

from kb.match import _emotion_conds, _emotion_hit


def _sig(emotion: str):
    return SimpleNamespace(emotion=emotion, scene="", chapter_pos="")


def test_free_text_emotion_matches_by_normalized_family():
    # 归一取首个命中族：「压抑—不安」→ 冷；与信号的归一族相等才算命中
    assert _emotion_hit({"emotion": "压抑—不安"}, _sig("冷")) is True
    assert _emotion_hit({"emotion": "压抑"}, _sig("冷")) is True
    assert _emotion_hit({"emotion": "热血"}, _sig("甜暖")) is False


def test_unmappable_emotion_is_not_a_condition():
    # 「复杂」归一不了：不能算条件，否则条目永远 0 分、被 select_block 丢掉
    assert _emotion_conds({"emotion": "复杂"}, _sig("")) == set()
    assert _emotion_conds({"emotion": "压抑—不安"}, _sig("")) == {"压抑—不安"}
    assert _emotion_conds({}, _sig("")) == set()
