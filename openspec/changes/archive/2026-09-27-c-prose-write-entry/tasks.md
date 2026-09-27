## 1. 实现（补录：已随 PR #511 落地，squash=89965aba）

- [x] 1.1 `Rail.tsx`：撤「AI 生成正文」工具卡，`onAiWrite` 下传 AiAssistPanel。完成证据＝PR #511 diff
- [x] 1.2 `AiAssistPanel.tsx`：新增 `onAiWrite` prop，正文页签动作清单首位「生成正文」（testid=ai-write-btn 沿用）。完成证据＝NovelWorkspace PRO 用例通过
- [x] 1.3 modals-pr5 解锁链用例适配（补正文页签一步；trace 定位尾段旧前提失效，断言改新口径）；NovelWorkspace 流式用例切 PRO 会话＋先切正文页签。完成证据＝隔离栈 modals-pr5 4＋prompt-pipeline 1＋ai-write-route 1 全绿
- [x] 1.4 ADJUSTMENTS 登记原型偏差。完成证据＝PR #511 内 diff
- [x] 1.5 本 change 归档（本 PR）：specs 同步 workbench 后移入 `archive/2026-09-27-c-prose-write-entry`
