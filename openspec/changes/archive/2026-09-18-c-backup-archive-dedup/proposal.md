## Why

`backup/export.py::dump_book_into` 的归档查询（书级 join `Chapter.project_id`）与 zip 写入位于 `for vol in volumes:` 卷循环体内（卷循环内归档块，定位以结构为准，不按行号）：**N 卷书的每条归档会被写 N 遍**——zip 内同名条目重复 N 份、每次重复写入触发 `UserWarning: Duplicate name`、`manifest_archives` 追加 N 遍（N×A 条），且书级全量 `select(Archive)`（含 `content` 大 TEXT 列）被每卷重拉一次（N×A 次最大字段读）。主要损害 = **包体膨胀与全文字段读放大**；manifest 失真属契约/工具面（实查全仓无 `archives/manifest.yaml` 运行时消费方：`importer.py` 只按文件名匹配且 `set(namelist())` 去重、前端零 zip 解析）。现有导出用例的种子书或零卷（`test_backup_export.py`）或单卷（`test_backup_roundtrip.py` 1 卷 1 归档，只断 `manifest["archives"][0]`），单卷不触发重复 → 缺陷静默。

来源：PR #409 后端架构评审定位（[评审结论](https://github.com/modoojunko/awesome-novel-desktop/pull/409#issuecomment-5724119655)「记录不修（预存在）：归档逐卷重复写包……建议后续单开」），本 change 即该跟进单开。

## What Changes

- **归档段提升到书级**：卷循环内的归档查询与写入整块移到循环之后，每条归档恰写一次 zip 条目；`manifest_archives` 回到 1×A；查询补显式排序（`Volume.volume_no, Chapter.chapter_no`）——manifest 升为契约后顺序须确定性。
- **产物形状收紧（契约化）**：zip 内 `archives/` 无重复条目；`archives/manifest.yaml` 条数恰等于归档行数（Archive 表行数，每章至多一行）且 `filename` 无重复。
- **读取端兼容性（非改动）**：此前 python zipfile 同名重复条目的 `read()` 取最后一条、且重复条目内容等值——导入结果与修复前逐字节一致；本修复只消除包体膨胀与 manifest 失真。不改任何字段与布局，`format_version` 不变；多卷包内 `archives/*` 条目顺序由「逐卷交错」变为「收拢于卷循环之后」，实查无消费方依赖顺序（导入按集合、测试按 sorted、前端不解析 zip）。
- 无用户可见界面改动；**前端零改动**（依据：`/backup/parse` 响应与备份/恢复入口文案均不含归档段信息，前端全仓无 zip 解析与 manifest 读取）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `backup-restore`: 新增「归档段唯一性与完整性」需求——多卷书导出时 zip 内每归档恰一条目、manifest 条数恰等于归档行数且 `filename` 无重复（锁定本缺陷的回归口径）。

## Impact

- 代码：`client/backend/backup/export.py`（`dump_book_into` 单函数内代码块平移＋归档查询补排序，零签名变化）；`kind=backup`（整库双包）与 `kind=single`（单书交付导出）同函数、同受益。`GET /novels/{id}/export` 走并行旧端点 `_dump_project_snapshot`（本就无此缺陷、不写 manifest），**不在本 change 覆盖面**。
- 测试：`test_backup_export.py` 补多卷书＋逐卷归档种子（断言形态见 tasks 1.2——必须用 list 计数）与 1 卷 1 归档用例；既有双包/单书与 roundtrip 用例回归。
- 导入端（`backup/importer.py`）与 `format_version`：零改动（形状回归契约本义）。

## Non-Goals（显式排除，防归档后误读）

- `_dump_characters` 缺 per-book prefix 缺陷（多书资产包角色段互相覆盖，`todo.md` 已登记挂起专项）不在本 change 范围。
- `_archive_filename` 已知缺口：章标题含 `/` 时归档条目名可产生 `../` 路径段 → 导入端 `validate_paths` 422、整包不可导入（评审实测复现）。本 change 只契约化「条目唯一性」，该命名缺口另行跟进。
