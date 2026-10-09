## 1. 引擎与路由（client/backend/migration）

- [x] 1.1 `engine.py`：存在性核对（逐表主键行值 IN → `rows_missing`；`book_count_present`）＋ `is_complete_report` 语义修订（在场书覆盖／通用行损失条款／FK 零行损降级）＋ 交集列 COALESCE 防 NULL 吞行 ＋ FK 孤儿 notes 实名留痕。
- [x] 1.2 `router.py`：`_record_completion` history 条目补记 `book_count_present`；`completeness_from_history` 透传（老数据无字段退回 migrated 保守口径）。
  - 回执：✅ 实现随 PR #797 第一笔（squash = 62470663，2026-10-09 合 main，CI 双绿）。

## 2. 前端（client/frontend/src）

- [x] 2.1 `CarryDialog.tsx`＋`carryStore.ts`：结果卡实名明细（`carryGaps`：跳过表名／缺几本书／缺行表名，泛化文案兜底）；成功卡书数取 present＋「· M 条模型配置」；notes 带出与死钥条件句去重；CarryReport 补 `book_count_present`/`tables`/`notes`。
- [x] 2.2 `LegacyMigrateModal.tsx`：`cleanupEligible` 书覆盖改按在场数（同病灶）；预览步补「模型配置 N 条（含 API Key）一并迁移」（PreviewReport 补 manifest）；「已迁移 N 本书」。
- [x] 2.3 `AcctMenu.tsx`＋`NovelListPage.tsx`：四条 toast／菜单 hint／常驻行两态／空态出口行话术对齐迁移口径。
  - 回执：✅ 实现随 PR #797 第二笔 copy-pass（同 squash）。

## 3. 话术「迁移」口径全量退役「带过来/带回」

- [x] 3.1 grep 扫「带过来|带回|稍后带」清零用户可见文案（源码＋测试断言＋e2e 钉死串；测试 it() 描述与注释里的内部用语保留）。
  - 回执：✅ 随 PR #797 第二笔；CarryDialog/LegacyMigrateModal/AcctMenu/NovelListPage/后端 note＋世代门禁消息共 11 文件。

## 4. 测试与门禁

- [x] 4.1 后端 `test_migration_engine.py`：重带仍完整／中断续带补齐／CHECK 拒收行显式化不完整／源孤儿 FK 降级＋note／NULL 行 COALESCE 不丢／判定单源单测（老报告与 history 保守口径）。
- [x] 4.2 前端：`carryDialog`（present 口径／notes 去重／实名明细四形态）＋其余四套文案断言随行。
- [x] 4.3 门禁：全量 pytest **1865 passed**＋ruff 0.16.3 绿；vitest **1387 passed**＋tsc 绿；rebase 到 #796/#799 之上后 CI 双绿。
  - 回执：✅ 复现实证另有三场景端到端（v0.30.2 models 造源库连跑两遍／中断续带／孤儿降级）。
