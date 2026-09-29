# c-ops-tab-progress-only — 操作页签只留进度：提案各归各的页签＋归档可多次

## Why

用户真机反馈「操作tab下还是这么乱的」：操作页签同时承载生命周期卡（归档/重写/回退）
与收尾结果区（待确认/失败/已处理行全部铺开、失败行红字长 JSON 全文不省略），与 #569
拍板的「各归各的 tab」IA 相悖。用户拍板（2026-09-28）：

1. 操作 tab 下**可以多次归档**；
2. 操作 tab **只显示进度**；
3. 结果要**提示去其他 tab 查看**。

后端语义已齐备无需动：已归档章 `POST /dossier/extract` 即 rows_only 重提（覆盖章档行＋
清 dossier_stale，不重跑收尾提案）；收尾提案有右栏「登记新伏笔」独立触发。

## What Changes

- **收尾提案区撤出操作页签**：伏笔登记提案→「伏笔」页签（HooksPane 上方）、世界要素
  提案→「设定」页签（本章变化区下方）——与采纳写回目标同位。ReconcilePane 加 `kinds`
  过滤，两处各挂一份；「操作」页签不再渲染任何提案行。
- **免费档收尾占位退役**：免费档不渲染收尾区（PRO 能力信号由归档弹窗「归档收尾（PRO）」
  计划区承载），操作/伏笔/设定页签对免费档同样干净。
- **归档卡可多次归档**：已归档且已提取的章显示「重新归档」入口 → ArchiveModal 重归档
  变体（警示清空并重提 N 条含已采纳 M 条）→ 确认走既有 rows_only 重提。
- **降噪**：已决（已采纳/已驳回）行默认折叠只显计数；失败行错误单行省略（悬停看全文）。
- **去向提示**：已归档态归档卡文案改为「变化与提案在『设定 / 角色关系 / 伏笔』页签确认」。

## Impact

- specs：chapter-dossier（变化分区归属 MODIFIED——提案各归各位＋重新归档入口）、
  archive-reconcile（ADD 提案展示各归各的页签；MODIFIED 三处「操作页签」措辞）。
- 前端：ReconcilePane / ChapterWorkspace / modals / book.css；后端零改动。
- 测试：ReconcilePane vitest 重写断言；e2e reconcile / chapter-dossier 改页签目标。
