## Why

c-db-per-version 上线后，库版本治理链路上留了三个数据安全缺口，本轮复审实勘确认：

1. **打戳失败全静默**：启动期写 schema 指纹/版本快照失败时 `except SQLAlchemyError: pass`（`main.py:128-143`）——零日志。下次启动该库因无 `schema_id` 被判 `mismatch` 改名、按新库启动（书架空），而日志里没有任何线索指向打戳失败。
2. **清理门只在 UI 层**：规格要求「仅本次成功带回的源可删、部分失败不得出现清理入口」，实现却按整个 `migration.history` 出待删清单，且 history 条目不含 `tables_skipped`/`fk_violations`——上一次半途搬运（整表跳过或 FK 违规）的源库，会在下一次干净搬完后进清单被不可逆删除。
3. **备份白名单漏字段**：`planned_volume_no`（计划收束卷）已进模型/API/写入路径，但导出 `_dump_hooks` payload 与导入 `_hook_row_fields` 白名单都没有它——备份→恢复静默丢该字段，且 roundtrip 测试用「键集完全相等」断言把旧白名单冻死，补字段反而被判回归。

另外：db-per-version 的验收门（UP-11 活体 e2e、version-chain 演练）规格写明「每个版本 PR SHALL 以本演练全绿为验收门」，但 CI 未承载（`UP11_DATA_DIR` 未设即整组 skip）；`VolumeCastMember` 成为零读写死表；C端 5 处裸 `datetime.now()` 违反 CLAUDE.md 时间口径红线。

## What Changes

- 打戳失败可见化：error 级日志（含库路径与异常摘要），不再静默；补测试钉住。
- 清理门下沉后端：待删清单只认 `migration.last.source_stamp`（对齐规格）；history 条目补记 `book_count_source`/`tables_skipped`/`fk_violations`，含未搬表或 FK 违规的源不进待删清单。
- 备份契约补 `planned_volume_no`：导出 payload 与导入白名单同批补键（加键兼容不升版）；roundtrip 断言由「键集相等」改「必含键」。
- db-per-version 验收门进 CI：nightly 补 `UP11_DATA_DIR` 使 UP-11 活体 e2e 真跑；`upgrade_drill version-chain` 接入 nightly 或打包流水线。
- 清理 `VolumeCastMember` 死表（模型 + relationship + 建表），`cast_members` 读侧键名登记保留理由。
- 时间口径清理：C端 裸 `datetime.now()` ×5（`db_lifecycle.py` / `migration/engine.py` / `backup/export.py`）改 `datetime.now(UTC).replace(tzinfo=None)`。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `db-generation`: 新增「打戳失败必须可见」「清理候选必须通过完整性校验」两条要求（均为新关注点，不改既有条款行为）。
- `backup-restore`: `双包格式契约 v1` 要求补 `hooks/hooks.yaml` 携带 `planned_volume_no` 的字段归属与跨机恢复场景。

## Impact

- `client/backend/main.py`（打戳日志）、`client/backend/db_lifecycle.py`（清理候选、时间口径）、`client/backend/migration/router.py`（history 条目）、`client/backend/backup/export.py`＋`importer.py`（伏笔白名单、时间口径）、`client/backend/models/volume.py`（死表）。
- 测试：`client/backend/tests/test_backup_roundtrip.py`（冻结断言改必含）、`client/backend/tests/test_version_upgrade_acceptance.py`（清理门）、新增打戳失败测试。
- CI：`.github/workflows/e2e-scheduled.yml`（UP11_DATA_DIR）、打包/nightly（version-chain 演练）。
- 无用户可见界面改动：清理清单与备份恢复均为既有界面，仅数据口径收紧；不触共享段，Design Impact 不适用。
