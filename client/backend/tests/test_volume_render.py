"""卷纲文本装配单源（volumes/render）— 六段行序／空段略过／全空空串。"""

from models.volume import Volume, VolumePlotNode
from volumes.render import volume_outline_text


def _vol(**kw) -> Volume:
    vol = Volume(project_id="p", volume_no=1, title="第一卷")
    for k, v in kw.items():
        setattr(vol, k, v)
    return vol


def test_full_six_sections_in_order():
    vol = _vol(summary="开局卷", core_conflict="A vs B", goal="拿到证据",
               ending="同伴远走", plants="徽章\n 航线图 \n", reveals="内鬼是他")
    vol.plot_nodes = [VolumePlotNode(stage="开局铺垫", text="雨夜接头"),
                      VolumePlotNode(stage="重要转折", text="暗号指向内部")]
    lines = volume_outline_text(vol).split("\n")
    assert lines[0] == "- 本卷主旨：开局卷"
    assert lines[1] == "- 核心矛盾：A vs B"
    assert lines[2] == "- 整体目标：拿到证据"
    assert lines[3] == "- 预期结局：同伴远走"
    assert lines[4] == "- 关键节点：1. 开局铺垫：雨夜接头 ｜ 2. 重要转折：暗号指向内部"
    assert lines[5] == "- 本卷待埋伏笔：徽章 ｜ 航线图"
    assert lines[6] == "- 本卷待揭信息：内鬼是他"


def test_empty_sections_skipped_and_all_empty_is_blank():
    vol = _vol(summary="", core_conflict=None, goal="", ending=None)
    vol.plot_nodes = []
    # 有意偏差（ADJUSTMENTS ③）：全空返回空串，而非原型占位符「（卷纲未填）」
    assert volume_outline_text(vol) == ""
    vol.summary = "只有主旨"
    assert volume_outline_text(vol) == "- 本卷主旨：只有主旨"
