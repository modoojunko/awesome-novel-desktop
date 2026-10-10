## Why

#766（c-rail-tier-badge，2179c6dd）给 AI 助手卡头加 `statusNote` 副行注记槽时，把这行写进了 `<AiWriterAssistant>` 开标签 `>` **之后**——落在了 children 里成裸文本。合法 JSX、不报编译错、无测试咬住：每个页签的卡面从此直接渲染字面量「statusNote=」（10-09 用户截图实锤），而 zhuque-workbench spec 既有 Requirement 要求的「朱雀检测已关闭 · 其余可用」功能性注记从未真正经 prop 上屏。

## What Changes

- 修复：`statusNote={tab === "prose" && !zqShow ? "朱雀检测已关闭 · 其余可用" : undefined}` 从 children 挪回 props 列表（注释随迁），字面量从卡面消失；副行走 `AiWriterAssistant` 既有优先级（功能性状态 > 调用方注记 > 不显示）。
- 防回归三钉（`AiAssistPanel.test.tsx`）：章纲页签卡面不得出现 statusNote 字面量；正文页签朱雀显示关→注记经 prop 上屏且无字面量；正文页签朱雀显示开→不出注记。修复前前两例必红（字面量命中 / 注记文本不存在）。
- 全仓仅此一处 `statusNote` 用法，无同类错位残留。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无——本变更是把实现对齐到 zhuque-workbench spec 既有 Requirement（正文页签检测行／功能性副行），不引入、不修改任何需求。`.openspec.yaml` 已声明 skip_specs。）

## Impact

- `client/frontend/src/components/novel/workbench/AiAssistPanel.tsx`：statusNote 一处归位（props 列表内、`data-od-id` 前）。
- `client/frontend/src/__tests__/AiAssistPanel.test.tsx`：新增回归 describe 三例。
- 验证：该测试文件 13/13 绿；`tsc --noEmit` 零错；e2e 无对字面量或该文案的引用。
- 交付：PR #809（squash＝b08eded1，2026-10-10 合 main，CI 绿）。
- 注意：字面量已随 #766 进入已发版本，修复随下一班发版带出。
