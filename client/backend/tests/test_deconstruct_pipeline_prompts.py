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
    "/Users/modoojunko/Desktop/coding/awesome-novel-prompts/prompts",
    os.path.expanduser("~/Desktop/coding/awesome-novel-prompts/prompts"),
]

pytestmark = pytest.mark.needs_prompts


def _sibling_prompts_dir() -> str | None:
    for cand in SIBLING_CANDIDATES:
        if os.path.isdir(cand) and any(f.startswith("deconstruct_") for f in os.listdir(cand)):
            return cand
    return None


@pytest.fixture
def _dev_dir(monkeypatch):
    d = _sibling_prompts_dir()
    if d is None:
        pytest.skip("sibling 提示词仓不在位")
    monkeypatch.setenv("PROMPT_PACK_DEV_DIR", d)


def test_all_12_templates_load_and_format(_dev_dir):
    from models.deconstruct import DIMENSIONS
    from prompts import load_layers

    names = ["deconstruct_prescan"] + [f"deconstruct_{k}" for k, _, _ in DIMENSIONS] + ["deconstruct_reduce"]
    for name in names:
        system, user_tpl = load_layers(name)
        assert system and user_tpl, f"{name} 分层缺段"
    # 占位符齐备性：按管线实传变量 format，KeyError 即模板漂移
    base = {
        "book_name": "书", "genre_or_unknown": "unknown", "full_synopsis": "梗概",
        "seg_range": "第1-40章", "excerpts": "【第1章】摘录",
    }
    for key, _, _ in DIMENSIONS:
        _, user_tpl = load_layers(f"deconstruct_{key}")
        user_tpl.format(**base)  # 不抛 KeyError 即可
    _, user_tpl = load_layers("deconstruct_prescan")
    user_tpl.format(chapter_no=1, chapter_title="第1章", chapter_text="正文")
    _, user_tpl = load_layers("deconstruct_reduce")
    user_tpl.format(dim_name="world", partials="【覆盖第1-40章】{}")


def test_render_md_fixed_h2_structure(_dev_dir):
    """渲染 md 的固定 H2 键序（展示用；建书消费模型 JSON 不做 md 反解——评审 P0-1）。"""
    from deconstruct.pipeline import _render_md

    md = _render_md(
        "世界设定",
        {"no_power": "无超凡", "factions": [{"name": "甲", "note": "证据 3章"}]},
        "书名",
        "第1-40章",
    )
    assert "\n## no_power\n" in md and "\n## factions\n" in md
    assert "无超凡" in md and "甲" in md
