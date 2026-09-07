## 1. 双端影响判定

- [x] 1.1 判定结论：本 change 为纯 S端（server + S端 账户页），不触两端共享段；徽标复用既有 pill/info·warn 词汇与既有胶囊形态，无新增组件词汇、无裸色值（依据 proposal Design Impact；替代原型先行）

## 2. 后端冻结/解冻/到账接线

- [x] 2.1 code_repo 双实现（sql + pg_http）新增 `freeze_for_order` / `unfreeze_for_order`：CAS active→frozen / frozen→active，status 与 status_detail 同步，幂等可重入
- [x] 2.2 `request_refund`：orders CAS 赢后冻结该单 active 行（CAS 输不触碰码行）
- [x] 2.3 `cancel_refund`：orders CAS 赢后解冻该单 frozen 行
- [x] 2.4 `complete_refund`：`revoke_queued_for_order` 两支 CAS status 条件扩 `in.(active,frozen)`；新增已起算恢复路径（frozen→active，剩余权益继续有效）
- [x] 2.5 扫描 D（refund_status=succeeded 但 orders.status≠refunded 的半截重放）与 2.4 同口径

## 3. 自愈扫描

- [x] 3.1 R1 scan-orders 新增两路收敛（S-A：退款中订单 active 行补冻结；S-B：已取消回 fulfilled 且 refund_status=canceled 的 frozen 行补解冻），幂等、重跑 0 新增
- [x] 3.2 R3 扫描 E：refunded 订单残留 frozen 行按锚相位判定（排队中→revoked+:queued 事件；已起算→恢复 active）

## 4. 我的套餐冻结展示

- [x] 4.1 验证授权聚合与明细端点：frozen 行不计入 tier/到期/生效（License.merge 既有逻辑），行状态字段透出 frozen
- [x] 4.2 S端 我的套餐明细行：frozen 渲染「退款处理中·已冻结」徽标、不提供激活入口；未知状态按原文渲染防御性回退

## 5. 测试

- [x] 5.1 单测：确认退款即冻结／取消解冻还原（grant_start 不变）／到账两相位（排队 frozen→revoked、已起算 frozen→active）／队列与折算计算不排除 frozen 行
- [x] 5.2 契约：pg_http 与 sql 双实现 CAS 条件 parity（revoke 扩 frozen、restore、freeze/unfreeze）
- [x] 5.3 自愈：冻结半截、解冻半截、refunded 残留 frozen 三态扫描收敛且重跑 0 新增
- [x] 5.4 S端 前端：冻结徽标展示 + 取消后恢复（e2e 或组件测试，含未知状态回退）

## 6. 回归与交付

- [x] 6.1 全量 pytest 绿（362 passed）；vue-tsc --noEmit 零错误；design:lint 仅 1 项存量违规（site-beian.ts，与 origin/main 零差异，非本分支引入）；S端 e2e 全量 176 passed；ruff check app tests 零违规
- [x] 6.2 openspec validate 通过；spec 措辞对齐复核（「不提前收回」与「立即冻结」无冲突）
- [x] 6.3 提交 PR（base=main，分支 feat/refund-freeze），合并不自动部署（S端 发版走 tag/dispatch 线）
