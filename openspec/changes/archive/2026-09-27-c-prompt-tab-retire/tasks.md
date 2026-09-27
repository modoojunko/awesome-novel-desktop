## 1. 实现（补录：已随 PR #518 落地，squash=88efc995）

- [x] 1.1 modals.tsx：AiModal「存为本章提示词」＋onPromptSaved（润色成功同回调）。完成证据＝AiModal.twoStage 新增用例绿
- [x] 1.2 ChapterWorkspace：撤页签/探测/徽标/降级 effect/PromptPane 渲染；promptSavedSignal 透传（onRailData 依赖同步）。完成证据＝e2e 存稿用例状态行刷新通过
- [x] 1.3 AiAssistPanel：正文页签收编提示词状态/组装来源＋精修两行；撤 prompt 分支。完成证据＝AiAssistPanel.test 更新用例绿
- [x] 1.4 退役件删除（PromptPane/PromptManagementPage/死 CSS/singleCard 测试）。完成证据＝tsc/vitest 绿＋bundle 残留 grep 0
- [x] 1.5 e2e 适配（workbench-features ④/④b/⑤/⑥、ai-assist、plot-sim、免费态锁定口径）。完成证据＝隔离栈 9 文件 48 条全绿（rebase #516 后）
- [x] 1.6 ADJUSTMENTS 登记。完成证据＝PR #518 内 diff
- [x] 1.7 本 change 归档（本 PR）：specs 同步 workbench 后移入 `archive/2026-09-27-c-prompt-tab-retire`
