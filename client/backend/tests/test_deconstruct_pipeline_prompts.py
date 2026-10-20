"""拆书管线 × 真实模板集成（c-deconstruct-book 2.x）：

sibling 提示词仓在位时（PROMPT_PACK_DEV_DIR 指向 awesome-novel-prompts/prompts），
验证 12 份 deconstruct 模板可被 load_layers 加载、user 段 format 兼容（占位符齐备）、
渲染 md 的固定 H2 结构可反解。无模板源环境自动跳过（conftest 同口径）。
"""

import os
import tempfile

import pytest

_SIBLING = os.path.join(
    os.path.dirname(tempfile.gettempdir()),  # 占位：真实路径在下方按常量拼
)
SIBLING_CANDIDATES = [
    os.environ.get("PROMPT_PACK_DEV_DIR", ""),
    "/Users/modoojunko/Desktop/coding/awesome-novel-prompts/prompts",
    os.path.expanduser("~/Desktop/coding/awesome-novel-prompts/prompts"),
]

pytestmark = pytest.mark.needs_prompts


def _sibling_prompts_dir() -> str | None:
    for cand in SIBLING_CANDIDATES:
        if cand and os.path.isdir(cand) and any(f.startswith("deconstruct_") for f in os.listdir(cand)):
            return cand
    return None


@pytest.fixture
def _dev_dir(monkeypatch):
    d = _sibling_prompts_dir()
    if d is None:
        pytest.skip("sibling 提示词仓不在位")
    monkeypatch.setenv("PROMPT_PACK_DEV_DIR", d)


def test_all_prompts_load_and_format(_dev_dir):
    from models.deconstruct import DIMENSIONS
    from prompts import load_layers

    names = (["deconstruct_card", "deconstruct_place"]
             + [f"deconstruct_{k}" for k, _, _ in DIMENSIONS] + ["deconstruct_reduce"])
    for name in names:
        system, user_tpl = load_layers(name)
        assert system and user_tpl, f"{name} 分层缺段"
    # 占位符齐备性：按管线实传变量 format，KeyError 即模板漂移
    base = {
        "book_name": "书", "genre_or_unknown": "unknown", "full_synopsis": "梗概",
        "seg_range": "第1-40章", "excerpts": "【第1章】卡片碎片",
        "genre_vocab": "玄幻\n都市异能",
    }
    for key, _, _ in DIMENSIONS:
        _, user_tpl = load_layers(f"deconstruct_{key}")
        user_tpl.format(**base)  # 不抛 KeyError 即可
    _, user_tpl = load_layers("deconstruct_place")
    user_tpl.format(**base)  # 地点归并吃同一组五件套变量
    _, user_tpl = load_layers("deconstruct_card")
    user_tpl.format(book_name="书", chapter_no=1, chapter_title="第1章", chapter_text="正文")
    _, user_tpl = load_layers("deconstruct_reduce")
    user_tpl.format(dim_name="世界设定", dim_key="world", partials="【覆盖第1-40章】{}")


def test_render_md_fixed_h2_structure(_dev_dir):
    """渲染 md：键名翻中文标签、可信度翻高/中/低并进抬头、页脚为作家视角说明。"""
    from deconstruct.pipeline import _render_md

    md = _render_md(
        "世界设定",
        {"no_power": "无超凡", "confidence": "high",
         "factions": [{"name": "甲", "note": "证据 3章", "confidence": "mid"}]},
        "书名",
        "第1-40章",
    )
    assert "\n## 舞台类型\n" in md and "\n## 势力\n" in md
    assert "无超凡" in md and "甲" in md
    assert "可信度：高" in md and "可信度：中" in md
    assert "\n## 可信度\n" not in md, "单值可信度并入抬头，不单独成节"
    assert "· 可信度：高" in md
    assert "三铁律" not in md
    assert "高＝有直接依据" in md


def test_render_md_mainplot_shape(_dev_dir):
    """主线形状渲染：ending 对象逐字段展开（dict repr 修复）、标量节裸值不带
    自身标签、arcs 的 summary 翻「梗概」。"""
    from deconstruct.pipeline import _render_md

    md = _render_md(
        "主线剧情",
        {
            "fullstory": "李耀被强派夜班十三路末班车，卷入十年前水库旧案。",
            "arcs": [{"title": "接班车", "ch_start": 1, "ch_end": 40,
                      "summary": "上船，旧案浮出（第3章）", "confidence": "high"}],
            "ending": {"scene": "末班车驶向黎明", "hero": "李耀活着查明真相", "tone": "释然"},
        },
        "13路末班车",
        "第1-258章",
    )
    assert "{'scene'" not in md and "{'" not in md, "结局对象不给 dict repr"
    assert "结尾场景：末班车驶向黎明" in md
    assert "主角结局：李耀活着查明真相" in md
    assert "收束基调：释然" in md
    assert "梗概：上船，旧案浮出" in md
    # 标量节正文＝裸值，不重复节标题自身的标签
    assert "\n主线全景：李耀" not in md
    assert "李耀被强派夜班十三路末班车" in md


def test_render_md_scalar_sections_bare_value(_dev_dir):
    """标量节正文不带自身标签前缀（舞台类型标题下不再出现「舞台类型：」两连）。"""
    from deconstruct.pipeline import _render_md

    md = _render_md("世界设定", {"stage": "银河系边缘"}, "书名", "第1-40章")
    assert "\n## 地理与舞台\n\n银河系边缘\n" in md
