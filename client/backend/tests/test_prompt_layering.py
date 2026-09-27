"""分层协议闸门（用户 2026-09-27 定：**每个提示词模板都要区分 system / user**）。

协议见 `prompts/__init__.py`：模板用 `<<system>>` / `<<user>>` 两行切段——
system＝角色＋优先级＋禁止项＋输出契约（同一功能恒定，吃供应商 prompt 缓存）；
user＝设定素材/前文/本次任务（每次替换）。**逐模板独立，不做跨模板共享层**
（每个页面的 AI 功能独立演进）。

本测试把"全部模板都要分层"变成可跟踪的仓库不变量：
- 名单外的模板必须已分层；
- 名单内的模板必须**尚未**分层（迁完就要从名单删掉，名单只减不增——防止清单变成摆设）。
每迁一批（按页面/功能族），从名单里删掉对应名字。
"""

from __future__ import annotations

import os

from prompts import _PROMPTS_DIR, is_layered

# 待迁移名单：尚未分层的模板（按页面/功能族分组，迁一族删一族）。
MIGRATION_PENDING: frozenset[str] = frozenset(
    {
        # —— 拆书/卷/章（结构类 AI）：拆卷出卡/展开/卷体检、拆章出卡/位置片、章纲起草/补缺、章内剧情抽卡、章级自检
        "volume_options", "volume_expand", "volume_check", "volume_pos_first", "volume_rules",
        "chapter_split", "chapter_plot_draw", "pos_ch1", "pos_golden3", "pos_vol_start",
        "outline_draft", "outline_fill_gaps", "chapter_selfcheck",
        # —— 写正文与辅助写作：整章组装、提示词工坊/精修、续写/润色/扩写/压缩、推演、自检
        "prompt_crafting", "prompt_refine", "continue_writing", "polish_text", "expand_text",
        "compress_text", "plot_sim", "ai_check", "story_stage", "story_character",
        # —— 设定页其余 AI：题材四行、简介三能力、世界起草/体检/lore、文风三区与蒸馏、伏笔四能力
        "settings_genre_core_promise", "settings_genre_forbidden_list", "settings_genre_cost_ratio",
        "settings_genre_battlefield",
        "settings_intro_fill", "settings_intro_introspect", "settings_intro_polish",
        "world_draft_topic", "world_check", "world_lore_suggest",
        "settings_style", "style_check", "style_fewshot_mine",
        "style_distill_step1", "style_distill_step2", "style_distill_step3",
        "hooks_draft", "hooks_payoff", "hooks_check", "hooks_audit",
        # —— 角色页五能力
        "settings_characters_bootstrap", "settings_characters_dossier", "settings_characters_persona",
        "settings_characters_cog", "settings_characters_check",
        # —— 归档/反推/建书：归档摘要、收尾五段（当前硬编码在代码里）、旧稿反推、建书建议
        "archive_summary", "backfill_synopsis_world", "backfill_style", "backfill_characters",
        "backfill_outlines", "backfill_step1_system", "backfill_step2_system", "suggest_meta",
        # —— 非模板资产：专名口径片段（供引用，本身不是一次调用的模板）
        "name_canon",
    }
)


def _all_prompt_names() -> set[str]:
    return {
        f[:-len(".prompt")]
        for f in os.listdir(_PROMPTS_DIR)
        if f.endswith(".prompt")
    }


def test_layering_progress():
    names = _all_prompt_names()

    # 名单里的模板必须存在且尚未分层（迁完就删名单项，名单只减不增）
    stale = sorted(n for n in MIGRATION_PENDING if n not in names)
    assert not stale, f"待迁移名单里有已不存在的模板：{stale}"
    done_but_listed = sorted(n for n in MIGRATION_PENDING if is_layered(n))
    assert not done_but_listed, f"这些模板已分层，请从 MIGRATION_PENDING 删除：{done_but_listed}"

    # 名单外的模板必须已分层（新加未分层的模板会在这里红）
    not_layered = sorted(n for n in names if n not in MIGRATION_PENDING and not is_layered(n))
    assert not not_layered, f"以下模板未分层（须按协议拆 system/user）：{not_layered}"
