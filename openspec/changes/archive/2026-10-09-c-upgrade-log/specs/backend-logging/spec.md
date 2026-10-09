# backend-logging（delta）

## ADDED Requirements

### Requirement: 无损升级链独立落 upgrade.log

C端 无损升级（旧库迁入）全链——迁入引擎六步、预检、完成记录、旧库清理——SHALL 经具名 logger `migration` 留痕，且这些行 SHALL 同时落当日按天日志（`app.log`）与专项档 `upgrade.log`（双写：求诊主档不缺行，专项档供升级问题直查）。留痕 SHALL 覆盖：每次迁入的开始行（含源文件名）；预检拒绝与任务启动拒绝行（带机器可读原因码）；搬运计划摘要行（计划表数与跳过表数）；逐表搬运行（表名、源行数、迁入行数）；核对行（FK 违规数、源/迁入/合并后书数）；终局行 SHALL 整份单行落迁移报告 JSON（状态、逐表明细、跳过表、密钥转接死钥数、书数对拍、完整性判定）。任何异常 SHALL 升级为 ERROR 级并带完整堆栈落双档；任务线程体异常（完成记录等环节）SHALL 在重抛给任务骨架兜底前先行落日志——堆栈 MUST NOT 静默丢失。专项档 SHALL 与按天日志同轮转同保留参数（按本地自然日、保留 5 天）、有独立体积护栏（同型消息限速），其初始化与关闭（`AINOVEL_LOG_OFF`）语义 SHALL 与按天日志单源。隐私红线：日志 MUST NOT 包含 API Key（密文或明文）与用户正文内容；计数与元数据不受限。

#### Scenario: 迁入失败可直查专项档

- **WHEN** 一次迁入在搬运或完成记录环节抛异常失败
- **THEN** `upgrade.log` 存在该次迁入的开始行、异常前的逐表行、ERROR 级完整堆栈行与终局报告行；同一行同步出现在当日 `app.log`（双写）

#### Scenario: 预检拒绝带原因码可定诊

- **WHEN** 迁入因磁盘不足、源占用或世代门禁被拒绝（start/preview 任一入口）
- **THEN** `upgrade.log` 存在带 `reason` 原因码与源文件名的拒绝行，无需用户复现即可定位拒绝原因

#### Scenario: 成功迁入终局报告完整可复盘

- **WHEN** 一次迁入成功完成
- **THEN** `upgrade.log` 含逐表搬运行（表名与行数）与终局单行报告 JSON（含逐表明细、跳过表、书数对拍、完整性判定），app.log 同步可见

#### Scenario: 专项档轮转与保留同口径

- **WHEN** `upgrade.log` 跨过本地 0 点或历史文件超过保留窗口
- **THEN** 与 `app.log` 同参轮转（每天一个文件）并只保留最近 5 天

#### Scenario: 日志整体关闭

- **WHEN** 环境设 `AINOVEL_LOG_OFF=1`
- **THEN** 专项档 handler 同样不挂载，测试与脚本零文件副作用
