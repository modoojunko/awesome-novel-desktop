# Proposal: c-carry-receipt-ack（完成回执「收起」持久化——刷新不再复现）

## Why

真机报修（2026-10-14，升级迁移后书架截图）：完成提示条「已迁移上一版的作品和模型配置／旧文件
仍在原位置」点 × 之后，**刷新/重开页面又冒出来**——× 形同虚设。

根因：完成回执行的 × 只写组件内 state（`stripClosed`，代码注释原话「仅视觉收起」），
SPA 刷新即复位；而回执的呈现条件 `carried` 由 `migration.last` 决定，源旧文件按设计原位保留，
该条件在候选存续期内恒真——于是每次打开书架都复现一次，用户没有表达「我知道了」的持久出口。

## What Changes

- **× 语义改为「收起并记住」**：点击完成回执行的 × 除本会话收起外，SHALL 把「已阅」写回后端——
  新增免登端点 `POST /backup/db-migration/receipt-ack`，把候选身份指纹（stamp）写入当前版本库
  `app_meta` 键 `migration.receipt_acked`（与 `migration.snoozed` 同库同纪律）。
- **候选载荷增独立呈现字段 `receipt_acked`**：命中即前端不再渲染完成回执行。与「完成态／抑制态／
  部分迁移态」并列的第四态，SHALL NOT 混装进既有字段（沿用「呈现状态以独立字段表达」口径）。
- **重开条件**：已阅绑候选 stamp——源数据件变化（旧版又写过数据）＝新一次迁移，指纹对拍不命中，
  回执自然重开（不吞新数据）；下一版本建新库时键天然不存在＝自动重评估，不跨版本泄漏。
- **非目标**：完成回执的文案、版式、入口（账户 › 本机旧版本数据）一律不变；未迁移提醒行的
  「本版不再提醒」语义不变；不完整态「无静默出口」的规则不适用本条（回执只在完整迁移后出现）。

## Capabilities

### Modified Capabilities

- `db-generation`：「迁移告知卡（四步）与「稍后迁移」」Requirement 补完成回执收起口径——
  × SHALL 持久化已阅态（`app_meta`／绑 stamp／载荷独立字段 `receipt_acked`），刷新与重启
  SHALL NOT 复现；数据件变化自动重开。新增场景「完成回执收起即记住（刷新不复现）」。

## Impact

- **C端 后端**：`client/backend/migration/router.py`（`RECEIPT_ACK_KEY`＋`/receipt-ack` 端点＋
  candidates 载荷第四字段）；`tests/test_migration_receipt_ack.py`（新增 7 例）。
- **C端 前端**：`src/lib/carryStore.ts`（`ackCarryReceipt`）、`src/hooks/useLegacyDb.ts`
  （`receipt_acked` 字段类型）、`src/pages/NovelListPage.tsx`（呈现条件＋× 处理器）。
- **测试面**：`novelListPage.test.tsx` 旧钉「仅视觉收起」改钉为「收起＋写已阅态」并补
  「已阅态不渲染」一例；全量 vitest 与后端 pytest 复跑。
- 零视觉／原型改动：× 的收起语义为交互行为，静态原型未建模（原型 × 的形态不变），
  parity 屏不呈现该回执（parity 态即无迁移候选），无 design:check 基线影响。
