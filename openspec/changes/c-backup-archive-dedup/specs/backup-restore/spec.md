## ADDED Requirements

### Requirement: 归档段唯一性与完整性

备份包（整库资产包 `kind=backup` 与单书交付导出 `kind=single`）的归档段 SHALL 满足：zip 内 `archives/` 每条归档**恰一个条目**（多卷书不得因卷循环产生同名重复条目）；`archives/manifest.yaml` 的 `archives` 列表条数 SHALL 恰等于**归档行数**（Archive 表行数；一章至多一行），且 `filename` 字段无重复。

- 归档查询 SHALL 保持书级口径（按 `Chapter.project_id` 全量），与卷遍历解耦，并带显式排序（卷序 + 章序）保证 manifest 顺序确定。
- 本条款为既有意图的契约化，不改任何字段与布局，`format_version` 不变；多卷包内条目顺序由「逐卷交错」变为「收拢于卷循环之后」（无消费方依赖顺序）。
- `GET /novels/{id}/export`（并行旧端点）不在本条款覆盖面。

#### Scenario: 多卷书归档条目唯一

- **WHEN** 一本 2 卷、每卷各含 1 条归档（共 2 条归档行）的书执行整库备份导出
- **THEN** 包内 `projects/{slug}/archives/` 下恰有 2 个归档条目（`namelist` 计数为 2，无同名重复——断言必须用 list 计数，集合会掩盖重复），manifest 的 `archives` 列表恰 2 条且 `filename` 互不相同

#### Scenario: 单卷书行为不变

- **WHEN** 单卷书的常规导出执行
- **THEN** 归档段产物与修复前逐字段一致（条目名、条目内容字节、manifest 字段集不变；条目相对顺序仅在多卷时变化）
