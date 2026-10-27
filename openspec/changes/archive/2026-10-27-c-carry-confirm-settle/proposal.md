# Proposal: c-carry-confirm-settle

## Why

用户口径（2026-10-27，附书架截图）：迁移完成后书架顶部挂着两条要人动手的提示——绿色「还没配置 API Key，AI 功能不可用」（模型配置明明已随迁带回 Key）与黄色「已迁移上一版的作品和模型配置」（要点 × 才走）。要求：迁移完成后页面自净，不给人留要点的框。

两条横幅的病灶：

1. **绿框（缺 Key 提示）**：`NovelListPage` 只在挂载时查一次 `/auth/config` 的 `has_api_key`——迁移是在同一页面会话内完成的，Key 带回来后该结果从不重查，提示僵在屏上。
2. **黄框（完成回执行）**：spec 既有口径（c-carry-receipt-ack）钉了「点完成确认后……顶部留完成回执行」，用户必须点 × 才收起。但用户刚刚才在结果卡上亲眼确认过「迁移完成」，这条常驻回执是同一信息的重复出场。

## What Changes

心智模型：**确认即已阅＋按需重查**——用户在结果卡上点过完成确认，就不再在书架重复告知；页面状态由查询缓存失效驱动自净，不依赖整页刷新（整页 reload 救不了黄框——已阅态没写，刷新照旧在；还多一次白屏闪烁）。

- **确认即已阅**：四步卡「好，开始写作」与向导完整结果的「去书架看看」就地持久化 `receipt_acked`（同键同纪律，绑 stamp），书架不再渲染完成回执行；乐观收起免闪条。× 出口保留给**带外完成**（后台守望完成、重启后发现已完成——用户没亲眼看到结果卡，回执行仍是唯一持久告知面）。
- **缺 Key 提示重查**：`/auth/config` 的 `has_api_key`／`portal_url` 升入查询缓存（`queryKeys.authConfig`），迁移完成确认（四步卡与向导两路）及后台守望完成时失效重查——模型配置随迁到位则绿框当场消失；确实无 Key（含 dead_keys）时提示照常保留。
- 不改后端：`receipt-ack` 端点与候选载荷字段全部复用。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `db-generation`：「迁移告知卡（四步）与「稍后迁移」」——完成回执收起条款增补「确认即已阅」（c-carry-confirm-settle），× 退居带外完成；「有登录态升级首启」「完成回执收起即记住」两场景随改，新增「完成确认即已阅（页面自净）」场景；「搬运不完整必须提示用户」——「重迁完整后收口」场景随改（完整确认后持续提醒行消失且不再出回执行）。

## Impact

- 前端：`client/frontend/src/lib/queryKeys.ts`（增 `authConfig`）、`pages/NovelListPage.tsx`（auth/config 升查询缓存＋onConfirmed 乐观收条）、`components/CarryDialog.tsx`（confirmDone 写已阅＋失效 authConfig）、`components/LegacyMigrateModal.tsx`（去书架看看写已阅）、`components/AcctMenu.tsx`（onDone／守望完成失效 authConfig）。
- 测试：`carryDialog.test.tsx`、`novelListPage.test.tsx`、`legacyMigrateModal.test.tsx`、`AcctMenu.test.tsx`。
- 不动：后端端点、候选载荷形状、部分迁移提醒行（其 spec 义务「搬运不完整必须提示」原样保留）、带外完成的回执行与 ×。

## Design Impact

- 受影响端：仅 C端 前端。无新组件、无布局变化；两条横幅的显隐逻辑变化，非原型 parity 场景项（提示条显隐属实现层），免原型先行（本判定即登记）。
- 文案零变化：不新增任何用户可见文案。

## 非目标

- 不做整页 `window.location.reload()`（见 What Changes 心智模型；若验收后仍要硬刷新另行立项）。
- 不动部分迁移（carried_partial）的持续提醒行——那是 spec 既有义务，不是「要人点的框」。
- 不改带外完成的回执呈现与 × 收起。
