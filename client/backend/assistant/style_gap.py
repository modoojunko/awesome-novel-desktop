"""本书文风三区就绪判断（c-agent-prose-kb-picks 单源）。

只读 `project_settings.style`（JSON 文本）：`role/rules/craft/few_shot_examples`
全空＝未配置。读取失败按未配置处理（fail-visible：让编排提示「先去填」，
不阻断检索）。
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def style_three_zones_empty(db: AsyncSession, root_path: str) -> bool:
    """本书文风三区是否全空；行缺失/坏 JSON/非字典一律视为未配置。"""
    from models.project_setting import ProjectSetting

    row = (
        await db.execute(
            select(ProjectSetting).where(
                ProjectSetting.root_path == root_path,
                ProjectSetting.key == "style",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return True
    try:
        style = json.loads(row.content or "{}")
    except ValueError:
        return True
    if not isinstance(style, dict):
        return True
    return not (
        str(style.get("role") or "").strip()
        or style.get("rules")
        or style.get("craft")
        or style.get("few_shot_examples")
    )
