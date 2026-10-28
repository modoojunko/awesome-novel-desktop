# Proposal: c-tree-batch-confirm-retire

## Why

用户实测反馈（2026-10-28）：写作页左栏树底常驻一枚「确认全部已填章节」，在最常见的写作态（前章已归档、当前章在写）里没有任何可确认对象，点了也只弹「没有可确认的章节」——是个死按钮。它来自 book.html 原型树列复刻（#183，ADJUSTMENTS #4「批量确认」），而章纲确认的正规入口早已收敛到章纲页签的「确认章纲」（显式、逐章、缺项反馈、可撤回，见 c-og-draft-no-autconfirm 立下的口径）。批量入口的「失败静默跳过」（必填未齐的章不留任何反馈）与该口径相悖——确认＝显式、逐章、有缺项反馈的动作，不该有一条绕过校验反馈的钝器旁路。

## What Changes

- **树底批量确认退役**：`OutlineTree` 删除「确认全部已填章节」按钮与 `handleBatchConfirm`，非空书态左栏树底不再渲染任何常驻按钮（空书态「＋ 新增一章／＋ 新增一卷」两入口不动）。
- **随删孤儿样式**：`.tree-foot .batch` 两条规则删除；`.col-tree.ai-lock` 选择器组里的 `.tree-foot` 成员随能力退场移除（`.tree-foot` 本身保留——设定页左栏口径注仍在用）。
- **不动**：章纲页签「确认章纲／撤回确认」链路（含后端 confirm/unconfirm 端点）原样保留；树上三态 dot 与已归档标签不动。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `workbench`：「EmptyState without settings gating (N4)」左栏条目改写——「确认全部已填章节」由「空书态不呈现、非空书态结构不变」改为**全态退役**。

## Impact

- 前端：`client/frontend/src/components/novel/workbench/OutlineTree.tsx`（删按钮＋处理函数）、`client/frontend/src/design/book.css`（删孤儿样式两处成员）。
- 测试：零覆盖（无单测/e2e 点击该按钮；e2e 仅一行注释提及），无需改钉；vitest 定向＋tsc 回归。
- 后端：零改动——`POST /chapters/{ref}/confirm` 端点仍由章纲页签「确认章纲」消费。
