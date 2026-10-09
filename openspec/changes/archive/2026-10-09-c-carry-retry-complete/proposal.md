## Why

v0.30.x 真机（内测同学，2026-10-09 截图）：无损升级带回后再点「重新带一次」，结果卡恒报「有内容没有完整迁入，可以重新带一次」——重带多少遍都一样，无法收尾，且下次启动还会再弹。

根因（本地复现实锤，v0.30.2 models 造源库连跑两遍：run1 complete / run2 mig=0 判不完整）＝完整达成判据拿 `book_count_migrated`（**本次真正 INSERT** 的书数）对拍 `book_count_source`；OR IGNORE 幂等让重带时已带回的行全部忽略 → migrated 恒 0 < source N → 永远不完整。四步卡文案明示「已带回的部分不会重复，可以重新带一次」，实现却让重带永远无法转完整——任何中断过的首带都掉进死循环。

同批用户拍板（2026-10-09）：① 结果卡「不完整」须**实名明细**（此前只给一句泛化文案，无法定位缺了什么）；② 话术专业化——「带过来/带回」太土，用户是作家，动词统一「迁移」，且作品与模型配置并列表达（标题/成功卡/toast 不再只提书）。

## What Changes

- **存在性核对**：核对步逐表按主键（含复合主键行值 IN）统计「源行在目标在场数」`rows_missing`；`novels` 同源产出 `book_count_present`（源书在目标在场数）。
- **完整性判定语义修订（单源 is_complete_report）**：书覆盖改按在场数（`book_count_present == book_count_source`，老报告缺 present 退回 migrated 保守口径）；新增通用行损失条款（任一表 `rows_missing>0` 即不完整）；FK 违规在「每表零行损可证」时降级为 notes 实名留痕（旧库自带孤儿行，一行没丢），缺证保守不放松；cleanup 白名单与 history 条目（补记 `book_count_present`）走同一判定。
- **COALESCE 防 NULL 吞行**：源实有列按目标 NOT NULL 约束包中性字面量——旧世代无约束的 NULL 存量直插不再被 OR IGNORE 静默吞整行。
- **结果卡实名明细**：不完整卡列出整表跳过表名／缺几本书／哪些表缺几行，对不上时才退回泛化文案；成功卡书数取在场数；引擎 notes（孤儿留痕）带出并与死钥条件句去重。
- **话术「迁移」口径（翻案原「带回」口径）**：标题「迁移上一版的作品与模型配置」、主按钮「立即迁移」、「稍后带→稍后迁移」、「重新带一次→重新迁移」、成功卡「迁移完成／已迁移 N 本书 · M 条模型配置」；LegacyMigrateModal 预览步补「模型配置 N 条（含 API Key）一并迁移」；AcctMenu 四条 toast／NovelListPage 常驻行与空态出口行／后端 FK 留痕 note 与世代门禁消息全部对齐。

## Impact

- **Specs**：`db-generation` RENAMED「带回告知卡（四步）与「稍后带」」→「迁移告知卡（四步）与「稍后迁移」」＋ MODIFIED 五条——「旧库迁入引擎（六步＋预检）」（存在性核对＋完整性判定语义＋COALESCE＋4 个新场景）、「迁入候选与只读清单」（迁移口径文案条款）、「清理候选必须通过完整性校验」（history 补 present＋孤儿降级放行）、「迁移告知卡（四步）与「稍后迁移」」（按钮/出口/文案条款翻案）、「搬运不完整必须提示用户」（在场判据＋实名明细）。
- **Code**：`client/backend/migration/{engine,router}.py`；前端 `components/CarryDialog.tsx`、`components/LegacyMigrateModal.tsx`、`components/AcctMenu.tsx`、`pages/NovelListPage.tsx`、`lib/carryStore.ts`。
- **Tests**：`tests/test_migration_engine.py`（重带回归 6 组＋判定单源单测）；前端 `carryDialog`／`novelListPage`／`legacyMigrateModal`／`AcctMenu`／`dialogQueue` 文案钉死断言＋e2e `db-version-upgrade.spec.ts`。
- **实现**：PR #797（双提交 squash = 62470663，2026-10-09 合 main，CI 双绿；全量 pytest 1865 passed＋ruff 绿、vitest 1387 passed＋tsc 绿）。
