# c-rail-ai-only — 右栏收敛为纯 AI 助手：本章进度卡退役并入头部徽章行

## Why

用户 2026-09-27 看实图后拍板：右栏「本章进度」块与中栏头部 meta 行大量重复（本章字数/计划字数
两边都有），右侧应当只有 AI 助手相关的功能。

## What Changes

- **BREAKING（UI）** 右栏「本章进度」块整体退役：大百分数/进度条/目标字数就地编辑/进度提示语/
  「本章已归档 · 只读查看」卡/mini 统计（本书总字数/本章草稿/目标达成）。
- 非重复两项收编中栏头部 meta 行：**完成度 N%**（wordCount/planWords，与正文页签统计卡同口径；
  计划字数未定不渲染）＋**本书总字数 N**；与头部重复的项不再二次展示。
- 目标字数就地编辑退役：改值走章纲「本章目标字数」格（同一 `word_target`，500-6000 校验照常）。
- `RailChapterData` 数据通道全量保留（仅 Rail 不再渲染进度块），Rail 死代码清除。
- e2e 适配：workbench-features 进度卡断言改头部徽章；free-writing-flow/settings-forms/modals-pr5
  三处「本章已归档 · 只读」断言（原命中右栏归档卡文案）改头部「已归档」徽章。

**非目标**：其余页签右栏统计卡；卷视图右栏；原型 `book.html` 同步（ADJUSTMENTS 登记，待同批更新）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`: 「卷/章页签结构同位」头部徽章行六枚→八枚（＋完成度、本书总字数）；新增「右栏纯 AI
  助手（本章进度卡退役）」requirement。

## Impact

- 前端 `Rail.tsx`（撤进度块＋死代码）、`ChapterWorkspace.tsx`（e-meta 两枚新徽章）；e2e 四文件。
- 门禁：tsc、vitest 875、build、隔离栈 e2e 47 条、实图目检——全绿（PR #510，squash=d93fcdd7）。
- 零数据面改动。
