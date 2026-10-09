# c-upgrade-log — 无损升级链独立落 upgrade.log，升级报错可直查

## Why

2026-10-09 用户反馈：无损升级（旧库迁入）报错后无法定位原因。现状三层失守：

1. **无专项档**：迁移链（`migration/engine.py`、`db_lifecycle.py`）日志全部走
   `uvicorn.error` 落 `app.log`，与请求行、业务行、启动行混在一起；5 天滚动下
   人工翻查成本高，升级问题没有「直查一个文件」的入口。
2. **六步零留痕**：迁入引擎除兜底 `logger.exception` 外全程不落一行——预检为什么拒、
   每张表搬了多少行、FK 违规几何、书数对拍结果，全部只存在于内存 report dict 里，
   失败现场无从复盘。
3. **线程异常静默**：迁移任务线程体（router `_body`）若在完成记录等环节抛异常，
   `job_runner.run_thread` 只把 `str(e)` 吞进 status、**一行日志都不落**——
   堆栈彻底丢失，正是「报错无法定位」的直接形态。

## What Changes

- **第三专项档 `upgrade.log`**（完全复制 c-llm-call-log 的 llm.log 模式）：
  `logging_setup` 增加同参第三 handler，挂 `migration` 具名 logger；propagate 保持
  True——行双写 app.log（求诊主档不缺行）＋ upgrade.log（升级问题直查）。轮转、
  保留 5 天、独立体积护栏（独立 FoldRepeatFilter 实例）、`AINOVEL_LOG_OFF` 关闭
  语义全部与按天日志单源。
- **迁移链留痕补全**：
  - 引擎六步逐事件落行（`event=migration_start` / `migration_precheck_failed` /
    `migration_plan` / 逐表 `migration_table` 行数 / `migration_verify` /
    终局 `migration_report`＝整份 report JSON 单行）；异常升级为 ERROR 级完整堆栈。
  - router 补预检拒绝原因码、单飞 409、preview 计划失败、完成记录、旧库清理结果；
    线程体 try/except 记日志后重抛（job_runner 兜底 state=error 语义不变）。
- **logger 归位**：engine 与 db_lifecycle 的 logger 从 `uvicorn.error` 切到
  `migration`——app.log 行为不变（propagate 到 root），upgrade.log 增量收获；
  db_lifecycle 既有告警行（隔离、checkpoint 失败、staging 清理）随之进专项档。

## Capabilities

### Modified Capabilities

- `backend-logging`: 新增「无损升级链独立落 upgrade.log」Requirement（双写、
  留痕覆盖面、终局报告行、同参轮转与关闭语义、隐私红线）。

## Impact

- **受影响端**：C端 backend（`logging_setup.py`、`migration/engine.py`、
  `migration/router.py`、`db_lifecycle.py`）；前端/壳层/S端 零改动。
- **落位**：upgrade.log 自动落在 `AINOVEL_LOG_DIR` 注入的既有日志目录
  （打包态＝运行目录 logs/，开发态＝数据目录 logs/），求诊仍只收集一个目录。
- **无行为变更**：迁移语义、端点契约、返回面全部不动；纯观测面增量。
- 风险点＝双写带来的 app.log 行为不变性（切 logger 后 uvicorn.error 专属行
  不再经过该 logger，但 propagate 到 root 的落盘路径等价）与测试夹具的
  handler 还原（daily_file_log 夹具须同批接管 migration logger）。
