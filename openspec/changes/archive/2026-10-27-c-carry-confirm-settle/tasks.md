# Tasks: c-carry-confirm-settle

## 1. 影响判定

- [x] 1.1 用户可见面＝书架两条既有横幅的显隐（绿框重查后消失／黄框确认后不再出现），零新组件零新文案；提示条显隐非原型 parity 场景项，免原型先行（proposal Design Impact 已登记）。验证：本任务即判定记录。

## 2. 前端

- [x] 2.1 `queryKeys.ts` 增 `authConfig`；`NovelListPage.tsx` 的 `/auth/config` 挂载期一次性拉取升为 `useQuery(queryKeys.authConfig)`（`has_api_key`→缺 Key 提示、`portal_url`→升级出口，派生值不再落 state）。验证：既有「缺 API Key 提示」用例绿。
- [x] 2.2 `CarryDialog.confirmDone`：完整达成分支（`status==ok && complete!==false`）追加 `ackCarryReceipt`（写已阅）＋失效 `authConfig`；不完整／失败确认不写已阅。验证：`carryDialog.test.tsx` 新例两臂。
- [x] 2.3 `NovelListPage.onConfirmed`：完整确认分支乐观 `setStripClosed(true)`——确认到 `receipt-ack` 往返之间不闪回执行。验证：`novelListPage.test.tsx` 全流程新例。
- [x] 2.4 `LegacyMigrateModal`「去书架看看」：完整结果就地 `ackCarryReceipt(picked)`。验证：`legacyMigrateModal.test.tsx` 新例＋不完整结果不写已阅。
- [x] 2.5 `AcctMenu`：`onDone` 与后台守望完成（ok 分支）失效 `authConfig`；守望完成**不**写已阅（带外完成回执行保留）。验证：`AcctMenu.test.tsx` 两例接线断言。

## 3. openspec

- [x] 3.1 delta：`db-generation` 两 Requirement MODIFIED（四步卡／搬运不完整），场景随改＋新增「完成确认即已阅」。验证：`openspec validate c-carry-confirm-settle` 0 红。
- [x] 3.2 sync＋archive 随本 PR（openspec-archive-in-implementation-pr 规矩）。验证：主 spec 落档、changes 无本户。

## 4. 收尾

- [x] 4.1 门禁：前端 vitest 全量＋`tsc --noEmit`。验证：0 红。
- [x] 4.2 PR；合入后真机验收＝升级首启走完四步迁移→书架无黄框、绿框随 Key 到位消失；后台守望完成路径回执行仍在、× 照常收起。验证：用户侧验收记录。
