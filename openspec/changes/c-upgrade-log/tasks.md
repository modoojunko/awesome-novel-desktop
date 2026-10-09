# c-upgrade-log — tasks

## 1. 专项档挂载（logging_setup）

- [x] 1.1 `_UPGRADE_LOGGERS = ("migration",)`；第三个 TimedRotatingFileHandler（`upgrade.log`，与 app.log/llm.log 同参：midnight、backupCount=5、UTF-8、delay=True），标记 `_ainovel_upgrade`，独立 FoldRepeatFilter 实例，挂 `migration` logger（propagate 不动＝双写 app.log）
- [x] 1.2 模块 docstring 补 upgrade.log 专项档一段（来源、双写口径、与 llm.log 同构）

## 2. 迁移链留痕（migration/engine + db_lifecycle + router）

- [x] 2.1 engine/db_lifecycle logger 切 `logging.getLogger("migration")`；engine 补六步事件行＋终局 `event=migration_report` 整份 report JSON 单行；异常行改 `event=migration_error`（保留 exc_info）
- [x] 2.2 router：logger 挂 `migration`；preview/start 预检拒绝带 reason 码、单飞 409、preview 计划失败、完成记录、cleanup 结果落行；线程体 `_body` try/except 记 ERROR 堆栈后重抛

## 3. 测试

- [x] 3.1 conftest `daily_file_log` 夹具同批快照/还原 migration logger handlers；`test_missing_dirs_created`／`test_unwritable_log_dir_falls_back_to_next_candidate` 的 finally 清理同批摘 upgrade handler
- [x] 3.2 `test_logging_setup.py` 增 ⑪ 节：挂载与轮转参数、幂等不重挂、双写 app.log、非 migration 行不进、关闭态不挂
- [x] 3.3 `test_migration_engine.py` 增留痕用例（caplog）：成功路径含 start/逐表/终局 report 行；预检拒绝带原因码；失败路径含 ERROR 堆栈行

## 4. 验证

- [x] 4.1 `pytest tests/test_logging_setup.py tests/test_migration_engine.py tests/test_db_lifecycle.py` 全绿；全量后端套件零新增红（1864 passed / 6 skipped / 242 skip）
- [x] 4.2 `ruff check` 零新增；`openspec validate` 通过；真文件冒烟＝引擎实跑一次迁移，upgrade.log 全事件链＋终局 report JSON、app.log 双写齐

