"""卷纲文本装配单源（volumes/render）— 六段行序／空段略过／全空空串。"""

from models.volume import Volume
from volumes.render import volume_outline_text


def _vol(**kw) -> Volume:
    vol = Volume(project_id="p", volume_no=1, title="第一卷")
    for k, v in kw.items():
        setattr(vol, k, v)
    return vol


def test_full_six_sections_in_order():
    """c-volume-antagonist 终版行序：主旨→对抗物→矛盾→结局→节点（目标/伏笔行退役）。"""
    vol = _vol(summary="开局卷", core_conflict="A vs B",
               ending="同伴远走",
               antagonist_type="人物", antagonist_line="副队长——销毁证据")
    vol.plants = "徽章"  # 退役字段存在也不渲染
    text = volume_outline_text(vol)
    lines = text.split("\n")
    assert lines[0] == "- 本卷主旨：开局卷"
    assert lines[1] == "- 本卷对抗物：人物 · 副队长——销毁证据"
    assert lines[2] == "- 核心矛盾：A vs B"
    assert lines[3] == "- 预期结局：同伴远走"
    # 整体目标与伏笔两行退役（伏笔只走台账注入）
    assert "整体目标" not in text and "待埋伏笔" not in text and "待揭信息" not in text


def test_empty_sections_skipped_and_all_empty_is_blank():
    vol = _vol(summary="", core_conflict=None, goal="", ending=None)
    # 有意偏差（ADJUSTMENTS ③）：全空返回空串，而非原型占位符「（卷纲未填）」
    assert volume_outline_text(vol) == ""
    vol.summary = "只有主旨"
    assert volume_outline_text(vol) == "- 本卷主旨：只有主旨"
