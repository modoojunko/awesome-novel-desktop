# Tasks: c-carry-receipt-ack

## 1. 后端：已阅态持久化

- [x] 1.1 `migration/router.py` 增 `RECEIPT_ACK_KEY = "migration.receipt_acked"`（与 `SNOOZE_KEY` 同纪律：绑 stamp、存当前库 app_meta）
- [x] 1.2 免登端点 `POST /backup/db-migration/receipt-ack`（白名单校验＋哨兵放行＋写指纹；不存在/越界 → code 1 不落笔）
- [x] 1.3 `candidates()` 增第四呈现字段 `receipt_acked`（双形态指纹对拍，与 carried/suppressed 单源同规则）
- [x] 1.4 新增 `tests/test_migration_receipt_ack.py`：命中/未收起/绑 stamp/数据漂移重开/旧形态对拍/端点写键/非法文件名拒写（7 例）

## 2. 前端：收起即记忆

- [x] 2.1 `carryStore.ts` 增 `ackCarryReceipt(filename)`（quiet POST → refreshCarry）
- [x] 2.2 `useLegacyDb.ts` 的 `LegacyCandidate` 增 `receipt_acked?: boolean`
- [x] 2.3 `NovelListPage.tsx`：完成回执行呈现条件加 `!carryRec.receipt_acked`；× 处理器＝乐观收起＋`ackCarryReceipt`；注释口径同步（原「仅视觉收起」退役）

## 3. 测试

- [x] 3.1 旧钉改钉（novelListPage.test）：× 收起 → 断言 POST `/receipt-ack` 且带 filename
- [x] 3.2 新增钉子：`receipt_acked: true` 时完成回执行不渲染
- [x] 3.3 全量 vitest 绿（1520/1520；契约文件覆盖率四项 100 保持）
- [x] 3.4 后端 pytest 全量复跑

## 4. 规格与验证

- [x] 4.1 openspec change 同名（proposal／spec delta／tasks）
- [x] 4.2 `openspec validate` 通过
- [ ] 4.3 真机复验：升级迁移 → 书架点 × → 刷新/重启不复现（待发包后由用户侧确认）
