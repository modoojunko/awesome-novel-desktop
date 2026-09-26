"""备份包格式契约头——FORMAT_VERSION 的唯一事实源。

演进规则（backup-restore spec）：加键=兼容不升版；删键/改布局=升版，读窗策略
按当次 change 裁定。character-settings-v2：角色段布局变化 → v2。
foreshadow-settings-v2：新增 hooks/hooks.yaml 伏笔段、settings 树摘除 hooks
键（删键+加段）→ v3。
卷纲换代（c-volume-view-storyline）：volumes 键集退役旧代字段 → v4；无用户
口径豁免 N-1 读窗——v0-v3 包可过版本门槛，但卷纲段旧键不承载（静默忽略）。
c-og-slim-v2：章档案删键（关键事件/地点/时间/叙事视角/视角指导/预期策略/
预期细节/可部分推进/段落规划/本章行动/场景卡/强度峰值·等级/情绪微弧线·钩子）
→ v5；同口径：v4 及更早包可过版本门槛，退役键按忽略处理（不落库、不报错）。
"""

FORMAT_VERSION = 5


# ── 产物归属单源（chapter-rewrite）─────────────────────────────────────────
# ref 语法双形制：主线 `vol-{N}-ch-{M}`；旧稿支线 `vol-{N}-ch-{M}-r{8hex}`。
# 一个产物文件名归属 ref R ⇔ 以 `{R}-` 开头，且**余段不构成旧稿后缀**
# （即余段不以 `r{8hex}-` 开头）——否则它属于更长的旧稿 ref。
import re as _re_refs

_GHOST_TAIL = _re_refs.compile(r"^r[0-9a-f]{8}-")


def belongs_to_ref(name: str, ref: str) -> bool:
    """产物归属判定（prompts/archives 共用）：边界感知，防主线吞旧稿产物。"""
    prefix = f"{ref}-"
    if not name.startswith(prefix):
        return False
    return not _GHOST_TAIL.match(name[len(prefix):])
