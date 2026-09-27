# c-prose-write-entry — 「AI 生成正文」常驻卡退役：入口收编正文页签面板

## Why

用户 2026-09-27 拍板（右栏纯 AI 化第三刀）：撤掉右栏全页签常驻的「AI 生成正文」工具卡——在章纲
页签等非正文语境下它是不相干入口。按 2026-09-20 确立的「动作在对应页签面板」架构收编。

## What Changes

- 右栏常驻「AI 生成正文」工具卡（标题＋PRO 标＋描述＋按钮）退役。
- 生成正文入口收编 `AiAssistPanel`「AI 辅助 · 正文」动作清单**首位**：label「生成正文」、
  `testid=ai-write-btn` 沿用；点击走页面级解锁链（归档章先弹「解除只读」）→ AiModal，链路零变化。
- 免费态按面板既有 locked 口径置灰禁点（与原卡 `pointer-events:none` 的真实行为等价）；
  PRO 流式期间禁用（同原卡）。
- 测试适配：modals-pr5 解锁链用例补「点正文页签」一步，尾段「真 bug #2」断言改新口径
  （章纲页签断言无入口＋正文页签确认生成编辑器可见）；NovelWorkspace「AI 流式中点写作」用例
  切 PRO 会话＋先切正文页签。

**非目标**：正文页签右栏工具卡（续写/润色/扩写）的再收敛；原型同步（ADJUSTMENTS 已登记）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`: 「右栏「AI 辅助」面板」补正文页签「生成正文」首动作口径＋全页签常驻工具卡退役。

## Impact

- 前端 `Rail.tsx`（撤卡＋下传 `onAiWrite`）、`AiAssistPanel.tsx`（新 prop＋动作）。
- 门禁：tsc、vitest 875、build、隔离栈 modals-pr5 4＋prompt-pipeline 1＋ai-write-route 1 全绿
  （PR #511，squash=89965aba）。
- 零数据面改动；解锁链/AiModal 链路不变。
