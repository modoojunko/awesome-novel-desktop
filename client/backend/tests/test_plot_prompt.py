"""章内剧情条目 → 提示词层接线测试（c-plot-split tasks 4.1/4.2）。

- 4.1 两路同源：`_plot_block` 单源渲染，material_markdown 与 to_user_material 都含同一块
  且逐字一致；单条内换行折叠为空格；空剧情两路产物逐字不变（golden fixture 对拍，
  fixture 抓自注入前的产物）。
- 4.2 润色条件锚（随 c-retire-prompt-polish 退役）：原用例只覆盖润色产物校验，
  校验函数已删；剧情块本身的两路同源钉由 4.1 继续看住。
"""

import os

from write.chapter_writer import (
    ChapterContext,
    _plot_block,
)

_GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")


def _rich_ctx() -> ChapterContext:
    """确定性素材齐全的 ctx（golden 与 parity 共用；除 plot_items 外全字段填满）。"""
    ctx = ChapterContext()
    ctx.novel_title = "渡口"
    ctx.premise = "她要替父还清赌债。"
    ctx.story_arc = "从渔村到皇城。"
    ctx.world_setting = {"constraints": "银钱不过夜"}
    ctx.style_setting = {"role": "一位小说家"}
    ctx.style_quant = {}
    ctx.genre_section = "题材：古风悬疑"
    ctx.volume_outline = "本卷主旨：翻身"
    ctx.chapter_outline = {"summary": "她夜探库房调包账册", "characters": ["林晚"]}
    ctx.micro_payoffs = [{"kind": "reveal", "description": "守夜人认错人"}]
    ctx.ladder_exit = "假账册入箱"
    ctx.challenge = "船家改口要加钱"
    ctx.plot_stage = "卷中转折"
    ctx.required_changes = ["账册被调包"]
    ctx.prohibitions = ["不许杀人"]
    ctx.characters = [{"name": "林晚", "state": "戒备", "speech": "短句"}]
    ctx.hooks = [{"description": "乌鸦面具", "code": "H-0001", "priority_label": "高"}]
    ctx.previous_context = "上章写的是：她在码头截住船家"
    ctx.word_target = 2000
    ctx.volume_no = 1
    ctx.chapter_no = 2
    return ctx


def _golden(name: str) -> str:
    with open(os.path.join(_GOLDEN_DIR, name), encoding="utf-8") as f:
        return f.read()


class TestPlotBlockTwoPaths:
    def test_block_shared_verbatim_between_paths(self):
        """4.1：同一渲染 helper 两路同调——块在两路产物中逐字一致、3 条各占一行。"""
        ctx = _rich_ctx()
        ctx.plot_items = [
            "甲一：她翻墙进了库房",
            "乙一：她在渡口截住船家\n暗线：有人尾随",
            "丙一：灯下的账册是假的",
        ]
        block = _plot_block(ctx.plot_items)
        assert block
        material = ctx.material_markdown()
        prompt = ctx.to_user_material()
        assert material.count(block) == 1
        assert prompt.count(block) == 1
        # 3 条各占一行；单条内换行折叠为空格（不切条）
        assert "- 甲一：她翻墙进了库房" in block.split("\n")
        assert "- 乙一：她在渡口截住船家 暗线：有人尾随" in block.split("\n")
        assert "- 丙一：灯下的账册是假的" in block.split("\n")
        assert len(block.split("\n")) == 5  # 标题＋定位句＋3 条：换行条目没切条
        # 块名＋定位句（c-og-slim-v2：场景原材料与「必须发生的动作」随退役字段出局）
        assert block.startswith("【本章剧情走向（分条）】\n定位：首尾以章卡")
        assert "章末落点/要撞的墙" in block
        assert "【场景原材料】" not in block

    def test_empty_plots_golden_unchanged(self):
        """4.1：空/缺剧情时两路产物与注入前逐字不变（golden 对拍）。"""
        ctx = _rich_ctx()
        assert _plot_block([]) == ""
        assert _plot_block(None) == ""
        material = ctx.material_markdown()
        prompt = ctx.to_user_material()
        assert material == _golden("plot_empty_material.txt")
        assert prompt == _golden("plot_empty_prompt.txt")
        assert "剧情走向" not in material
        assert "剧情走向" not in prompt
