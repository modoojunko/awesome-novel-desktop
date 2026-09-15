"""备份包格式契约头——FORMAT_VERSION 的唯一事实源。

演进规则（backup-restore spec）：加键=兼容不升版；删键/改布局=升版且导入端
保留 N-1 读窗。character-settings-v2：角色段布局变化 → v2。
foreshadow-settings-v2：新增 hooks/hooks.yaml 伏笔段、settings 树摘除 hooks
键（删键+加段）→ v3；导入端保留 ≤3 读窗（v1 KV 三数组→真表行的读窗见
importer._hooks_v1_to_entries）。
"""

FORMAT_VERSION = 3
