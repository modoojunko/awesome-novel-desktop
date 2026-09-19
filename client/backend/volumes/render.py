"""卷纲文本装配单源（settings/render 同型先例；新增依赖边 write/* → volumes.render）。

行标签与格式逐字对齐原型 volOutlineText（storyline.html 1609-1620）：
- 本卷主旨：…／- 核心矛盾：…／- 整体目标：…／- 预期结局：…
- 关键节点：1. 〈阶段〉：〈内容〉 ｜ 2. …（单行 ｜ 连接）
- 本卷待埋伏笔：a ｜ b／- 本卷待揭信息：x ｜ y
空段整行略过；**有意偏差（ADJUSTMENTS ③）**：全空返回空串而非原型占位符，
以维持 prompt-sources「未填＝chars 0/empty=true」断言。只做剧情规划，不含角色言行。
"""

from models.volume import Volume
from volumes.schemas import normalize_line_list

_SEPARATOR = " ｜ "


def volume_outline_text(vol: Volume) -> str:
    """卷纲六段纯文本；写章提示词「大纲 · 卷纲」、写章背景、卷纲冲突检测共用。"""
    lines: list[str] = []
    if vol.summary:
        lines.append(f"- 本卷主旨：{vol.summary}")
    if vol.core_conflict:
        lines.append(f"- 核心矛盾：{vol.core_conflict}")
    if vol.goal:
        lines.append(f"- 整体目标：{vol.goal}")
    if vol.ending:
        lines.append(f"- 预期结局：{vol.ending}")
    nodes = list(vol.plot_nodes or [])
    if nodes:
        joined = _SEPARATOR.join(
            f"{i + 1}. {n.stage}：{n.text}" for i, n in enumerate(nodes)
        )
        lines.append(f"- 关键节点：{joined}")
    plants = normalize_line_list([vol.plants or ""])
    if plants:
        lines.append("- 本卷待埋伏笔：" + _SEPARATOR.join(plants))
    reveals = normalize_line_list([vol.reveals or ""])
    if reveals:
        lines.append("- 本卷待揭信息：" + _SEPARATOR.join(reveals))
    return "\n".join(lines)
