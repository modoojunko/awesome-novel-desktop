## MODIFIED Requirements

### Requirement: 完结状态落库与 finish/reopen 端点

- `novels` 表 SHALL 增加可空列 `finished_at`（TIMESTAMP）：完本动作写入服务端当前时间，撤完本清空；此外 SHALL NOT 有任何路径写该列。迁移 SHALL 走 `main.py` lifespan 既有「列存在检查→ALTER TABLE ADD COLUMN」守卫模式，无回填、无兼容层。
- `POST /api/novels/{project_id}/finish` SHALL 在满足全部守卫时写入 `finished_at` 并在响应中返回更新后的书摘要（含 `finished_at`）；守卫任一不满足 SHALL 返回 409：**未完结**、**作者章数 > 0**、**作者章已归档数 == 作者章总数**（作者章＝`origin!=import`；主线口径与书架统计同源：`chapters.ghost_of` 为空才算主线）。
- `POST /api/novels/{project_id}/reopen` SHALL 仅在**已完结**时清空 `finished_at` 并返回更新后的书摘要，否则 SHALL 返回 409。
- `GET /api/novels`（list）与书详情端点 SHALL 下发 `finished_at`（ISO 字符串或 null）、`authored_total`、`authored_archived`。
- 完结与撤完本 SHALL 触发 `updated_at` 常规更新（书架排序口径不变）。

#### Scenario: 主线全归档后完本成功

- **WHEN** 对一本作者章 3 章且 3 章全部归档、未完结的书调用 finish
- **THEN** `finished_at` 写入当前时间，响应含该时间戳；list 下发同一值
- **AND** 再调 finish SHALL 返回 409（已完结）

#### Scenario: 有未归档主线章时拒绝完本

- **WHEN** 对一本作者章 5 章仅归档 3 章的书调用 finish（旧稿支线章与导入章不计入作者章分母）
- **THEN** 返回 409，`finished_at` 保持为空

#### Scenario: 只有导入章不能完本

- **WHEN** 一本 42 章全部为 origin=import、没有作者章的书调用 finish
- **THEN** 返回 409（还没有作者章），`finished_at` 保持为空

#### Scenario: 导入章归档不满足完本

- **WHEN** 一本 42 章导入书把 42 章全部归档后调用 finish
- **THEN** 返回 409，因为 authored_total=0；书仍为写作中

#### Scenario: 导入书有了作者章后可完本

- **WHEN** 一本导入书写了第 43、44 章并全部归档，调用 finish
- **THEN** 完本成功；导入章是否归档不影响作者章分母

#### Scenario: 撤完本回待完本

- **WHEN** 对一本已完结的书调用 reopen
- **THEN** `finished_at` 清空，list 中该书 `finished_at` 为 null
- **AND** 对未完结的书调用 reopen SHALL 返回 409
