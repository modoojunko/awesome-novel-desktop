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

# 片段资产：被其他模板以占位符吸纳的文本片段，不是一次独立的模型调用，SHALL NOT 分层
# （name_canon 现为文档副本——c-prompt-dead-refs-cleanup 后无模板吸纳它，仍 SHALL NOT 分层）
ASSETS: frozenset[str] = frozenset(
    {"name_canon", "volume_rules", "volume_pos_first", "pos_ch1", "pos_golden3", "pos_vol_start"}
)

# 待迁移名单：尚未分层的模板（按页面/功能族分组，迁一族删一族）。
MIGRATION_PENDING: frozenset[str] = frozenset(
    {
        # —— 拆书/卷/章：八个调用模板已完成分层（2026-09-27）；volume_rules/pos_* 为注入片段资产，见 ASSETS
        # —— 写正文与辅助写作＋推演 10 个已完成分层（2026-09-27）
        # —— 设定页全部 AI（题材四行/简介三/世界三/文风六/伏笔四/角色页五）已完成分层（2026-09-27）
        # —— 归档/反推/建书 6 个已完成分层（2026-09-27）；backfill_step1/2_system 两个死模板已删除
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
    not_layered = sorted(n for n in names if n not in MIGRATION_PENDING and n not in ASSETS and not is_layered(n))
    assert not not_layered, f"以下模板未分层（须按协议拆 system/user）：{not_layered}"
