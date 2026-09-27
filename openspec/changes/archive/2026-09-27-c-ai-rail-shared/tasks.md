## 1. 实现（补录：已随 PR #515 落地，squash=46be6357）

- [x] 1.1 book.css：ra-* 家族去 `.settings-v` 前缀全局化；写作域旧基线退役。完成证据＝design:lint 0 违规
- [x] 1.2 AiWriterAssistant 迁 components/novel/＋行级 testid＋children 插槽＋根节点 data-testid。完成证据＝SettingsView/测试导入同步更新后 tsc 通过
- [x] 1.3 AiAssistPanel 八页签重写为 ra-*（作用域行承载原统计卡口径）。完成证据＝AiAssistPanel.test 重写 7 用例绿
- [x] 1.4 Rail 瘦身＋VolumeAssistPanel 三态换装。完成证据＝volumePlan.test 绿＋实图目检
- [x] 1.5 e2e 五文件适配（ai-assist/reconcile/volume-plan/workbench-features/design-parity-book）。完成证据＝隔离栈 8 文件 e2e 全绿
- [x] 1.6 ADJUSTMENTS 登记。完成证据＝PR #515 内 diff
- [x] 1.7 本 change 归档（本 PR）：specs 同步 workbench 后移入 `archive/2026-09-27-c-ai-rail-shared`
