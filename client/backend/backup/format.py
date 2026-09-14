"""备份包格式契约头——FORMAT_VERSION 的唯一事实源。

演进规则（backup-restore spec）：加键=兼容不升版；删键/改布局=升版且导入端
保留 N-1 读窗。character-settings-v2：角色段布局变化 → v2。
"""

FORMAT_VERSION = 2
