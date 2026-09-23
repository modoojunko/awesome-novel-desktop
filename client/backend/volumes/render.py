"""卷纲文本装配单源（settings/render 同型先例；新增依赖边 write/* → volumes.render）。

行标签与格式逐字对齐原型 volOutlineText（storyline.html 1609-1620）：
- 本卷主旨：…／- 本卷对抗物：〈类型〉·〈一句话〉／- 核心矛盾：…／- 预期结局：…
- 关键节点：1. 〈阶段〉：〈内容〉 ｜ 2. …（单行 ｜ 连接）
（c-volume-antagonist：整体目标与两条伏笔行退役——goal 并入 ending，伏笔只走台账注入）
空段整行略过；**有意偏差（ADJUSTMENTS ③）**：全空返回空串而非原型占位符，
以维持 prompt-sources「未填＝chars 0/empty=true」断言。只做剧情规划，不含角色言行。
"""

from models.volume import Volume

_SEPARATOR = " ｜ "


def volume_outline_text(vol: Volume) -> str:
    """卷纲六段纯文本；写章提示词「大纲 · 卷纲」、写章背景、卷纲冲突检测共用。"""
    lines: list[str] = []
    if vol.summary:
        lines.append(f"- 本卷主旨：{vol.summary}")
    if vol.antagonist_line:
        ant = ((vol.antagonist_type + " · ") if vol.antagonist_type else "") + vol.antagonist_line
        lines.append(f"- 本卷对抗物：{ant}")
    if vol.core_conflict:
        lines.append(f"- 核心矛盾：{vol.core_conflict}")
    if vol.ending:
        lines.append(f"- 预期结局：{vol.ending}")
    # c-chapter-plan-ai：关键节点行随剧情节点退役移除（拆章素材包改取已排章的阶段序列）
    # c-volume-antagonist：整体目标与伏笔两行退役（goal 并入 ending；伏笔只走台账注入）
    return "\n".join(lines)
