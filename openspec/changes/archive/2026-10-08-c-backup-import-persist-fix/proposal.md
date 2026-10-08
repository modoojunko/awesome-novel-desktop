## Why

备份「恢复落库」对最常见的用户形态（恰好 1 个 active 模型配置＋包里有书）自上线起必炸：`backup/importer.py:938` 在 `unique_active` 智能挂回分支读了不存在的属性 `novel.api_config_id`（模型字段实为 `ai_config_id`），首本书即 `AttributeError` → persist 500，重试恒复现（2026-10-08 用户真机 app.log 实录，5 连 500）。该笔误由 9643b2bc（2026-09-05，#324 恢复导入接线）首日引入。

排查中实锤第二处更深的缺陷：整个 `backup/` 模块没有一处 `db.commit()`。逐书 SAVEPOINT 能落库纯靠 SQLite「外层无真 BEGIN 时 RELEASE 即提交」的方言巧合（且仅当本次请求内书之前没有其他写入先开真事务）；而**挂回（reattach）的 `ai_config_id` 赋值发生在所有 SAVEPOINT 之后、无 flush 无 commit，会话关闭即回滚——修掉笔误后挂回依然永远不生效**，与自家 spec「persist 落库＋智能挂回」直接矛盾。已用与 `db.py` 同款引擎配置实证两种命运（书落/挂回丢；带配置块时全回滚）。

## What Changes

- 修正 `_reattach_configs` 幂等守卫的属性笔误：`novel.api_config_id` → `novel.ai_config_id`（一行）。
- `persist_package` 补**显式提交边界**：每书成功即 `await db.commit()`（逐书原子不依赖方言巧合），reattach 后收尾提交兜住 config-only 包；挂回异常时已落书保持、挂回不生效（置空待选）。
- 补回归测试钉子：走 `persist_package` 全链用例（单 active 配置＋含书包），复刻 `get_db` 会话生命周期并用**新开 session** 验证书落库且 `ai_config_id` 已挂，辅以挂回异常的「书保持」钉——变异检查证明两条钉双向咬合。
- 不改 export 侧、不改挂回策略本身（unique_active/by_model 语义照旧）、不改前端。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `backup-restore`: 「恢复导入（双槽位+逐书原子）」Requirement 补 durability 语义——persist 成功返回前书与挂回结果 SHALL 已持久化（新会话可见），挂回幂等守卫 SHALL 读 `Novel.ai_config_id`；新增「智能挂回持久生效」与「单配置恢复全链」场景钉住本次两处缺陷。

## Impact

- 代码：`client/backend/backup/importer.py`（`_reattach_configs` 一行＋`persist_package` 提交边界）；`client/backend/tests/test_backup_import.py`（新增回归用例）。
- 行为影响：修复后单配置用户恢复导入从「恒 500」变为可用；挂回结果跨请求真实生效。此前因 500 整体回滚（带配置块路径），已重试多次的用户无脏数据；纯书包路径下书可能已落库（多次重试会积累《书名（备份）》重复本），本次修复不追溯清理。
- 测试：现有 `test_backup_import.py` 只直测 `_restore_config`/`_import_single_book`，未覆盖 persist 全链——新钉子补齐；其余套件不受影响。
- 无 UI 改动，免原型与设计门禁。
