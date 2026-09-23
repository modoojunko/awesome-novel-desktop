## ADDED Requirements

### Requirement: 打戳失败必须可见

启动期把 schema 指纹与版本/组件快照写入当前库 `app_meta` 失败时，系统 MUST 输出 error 级日志，含库路径与异常摘要，MUST NOT 静默吞掉；日志 MUST NOT 包含凭据或行数据。打戳失败 MUST NOT 阻断本次启动。

#### Scenario: 打戳失败有线索

- **WHEN** 当前库所在目录只读或库被独占导致打戳写入失败
- **THEN** 启动日志出现 error 级记录（含库路径与异常摘要），服务照常启动
- **THEN** 此后该库被判 `mismatch` 时，日志中可回溯到打戳失败这一前因

#### Scenario: 打戳成功不新增噪声

- **WHEN** 打戳正常完成
- **THEN** 不出现 error 级记录，启动行为与现状一致

### Requirement: 清理候选必须通过完整性校验

待删清单 SHALL 只包含**本次成功带回**的源（`stamp == migration.last.source_stamp`）。搬运记录（`migration.history`）SHALL 记入 `book_count_source`、`tables_skipped`、`fk_violations`；含整表跳过或 FK 违规的搬运源 MUST NOT 进入待删清单。清理判定 MUST 在后端完成，前端只做展示。

#### Scenario: 半途搬运的源不进清单

- **WHEN** 某次搬运有整表被跳过（NOT NULL 无默认列），其后又有一次干净搬运完成
- **THEN** 待删清单不含半途那次的源库；只含本次成功带回的源

#### Scenario: 非本次源不可删

- **WHEN** 用户在清理清单展开前，盘中存在更早成功搬运的源库
- **THEN** 待删清单不含该更早源库（`stamp != migration.last.source_stamp`）
