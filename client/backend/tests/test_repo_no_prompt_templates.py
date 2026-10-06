"""主库零模板门禁（c-prompt-source-flip 4.4/5.1）。

提示词唯一源在 awesome-novel-prompts 仓；本仓 SHALL NOT 跟踪任何 .prompt 模板
（loader 与同步器代码不在此列）。组4 阶段以允许清单过渡（存量 58 文件），组5
`git rm` 后收紧为全禁——清单为空集即终态；新增任何 .prompt 都在这里红。
"""

from __future__ import annotations

from pathlib import Path

# 组5（git rm）完成后应清空此清单；存在即说明翻转未完成。
ALLOWED: frozenset[str] = frozenset(
    f"prompts/{name}.prompt"
    for name in (
        # —— 组4 过渡期允许清单：现有 58 个模板（组5 收紧时整段删除）——
        "ai_check", "arc_calibrate", "arc_check", "arc_draft", "arc_tone", "archive_summary",
        "backfill_characters", "backfill_outlines", "backfill_style", "backfill_synopsis_world",
        "cast_draw", "cast_review", "chapter_archive_extract", "chapter_plot_draw",
        "chapter_selfcheck", "chapter_split", "hooks_audit", "hooks_check", "hooks_draft",
        "hooks_payoff", "name_canon", "outline_fill_gaps", "plot_sim", "polish_text",
        "pos_ch1", "pos_golden3", "pos_vol_start", "prompt_crafting",
        "settings_characters_bootstrap", "settings_characters_check", "settings_characters_cog",
        "settings_characters_dossier", "settings_characters_persona",
        "settings_genre_battlefield", "settings_genre_core_promise", "settings_genre_cost_ratio",
        "settings_genre_forbidden_list", "settings_intro_fill", "settings_intro_introspect",
        "settings_intro_polish", "settings_style", "story_character", "story_stage",
        "style_check", "style_distill_step1", "style_distill_step2", "style_distill_step3",
        "style_fewshot_mine", "suggest_meta", "volume_check", "volume_expand",
        "volume_options", "volume_pos_first", "volume_rules", "world_check",
        "world_draft_topic", "world_lore_suggest", "write_chapter",
    )
)

_BACKEND = Path(__file__).resolve().parents[1]


def test_repo_tracks_no_prompt_templates():
    found = sorted(
        str(p.relative_to(_BACKEND)) for p in _BACKEND.rglob("*.prompt")
        if "__pycache__" not in p.parts and ".venv" not in p.parts
    )
    strays = [f for f in found if f not in ALLOWED]
    assert not strays, (
        "主库出现未登记的 .prompt 模板——提示词唯一源在 awesome-novel-prompts 仓，"
        f"不得回植（c-prompt-source-flip）：{strays}"
    )
