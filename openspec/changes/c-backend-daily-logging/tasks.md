## 1. 影响判定与基建

- [x] 1.1 无 UI 影响判定：本 change 纯后端＋壳层，不触任何 prototype／ADJUSTMENTS.md／design tokens／共享段（依据＝proposal 无 Design Impact 段）；设计门禁（design:lint/design:check/design-cross）不适用。产出此判定记录即可。
- [x] 1.2 新建 `client/backend/logging_setup.py`：`setup_logging()` 按 design D1/D2/D4/D5/D9 落地——`TimedRotatingFileHandler`（midnight、backupCount=5、utf-8、delay=True）挂 root＋`uvicorn` logger；`uvicorn.access` 压到 WARNING；root/uvicorn 显式 INFO；`AINOVEL_LOG_DIR` > `DATA_ROOT/logs` 解析；**显式 `log_dir.mkdir(parents=True, exist_ok=True)`**；`AINOVEL_LOG_OFF=1` 跳过；`_ainovel_daily` handler 标记幂等；`sys.stdout` 判空再挂控制台 handler；`httpx`/`httpcore`/`openai`/`sqlalchemy` 显式压回 WARNING（design D2 静音名单）；同文限速 Filter 挂文件 handler（design D4 护栏）。验证：单元测试见 2.1。
- [x] 1.3 `main.py` 模块顶部（早于业务 import）调用 `setup_logging()`（design D3）。验证：单测断言导入 main 后 root 已带标记 handler（AINOVEL_LOG_OFF 关闭时）。

## 2. 后端测试先行判据

- [x] 2.1 `tests/test_logging_setup.py`：①幂等——重复调用不重复挂 handler、单条消息单行；②轮转参数钉死（midnight/backupCount=5/utf-8，可通过预置 6 份带日期旧文件＋强制 rollover 断言最老被删）；③uvicorn 桥接——`getLogger("uvicorn.error").info(...)` 落文件且**单行**（无 dictConfig 环境下断言，钉 uvicorn 0.52.1 的 configure_logging 时序＋propagate 语义双写面，升级变行为时此处先红）；④业务 `getLogger(__name__)` 落文件；⑤`AINOVEL_LOG_OFF=1` 不产生文件；⑥uvicorn.access 的 INFO 行被压掉；⑦体积护栏——同型消息风暴（循环 logger.error 同模板）限速去重（首条＋计数），文件行数有界；⑧日志目录不存在（含父目录）时初始化后首条消息仍落盘。验证：`cd client/backend && .venv/bin/python -m pytest tests/test_logging_setup.py -q` 全绿。
- [x] 2.2 conftest 全局设 `AINOVEL_LOG_OFF=1`（防既有套件导入 main 时刷文件）。验证：全量 pytest 后 `client/backend/data/logs`（或 DATA_ROOT/logs）不存在当日新文件。
- [x] 2.3 请求中间件 `client/backend/request_logging.py`（纯 ASGI，design D6）：status 捕获、perf_counter 耗时、`/api/health` 豁免、异常 finally 记 500；在 main.py 全部 add_middleware **之后**注册（最外层）。测试：一次 POST 返回 200/4xx 各落一行「method path status 耗时」；health 连打 N 次零行；**被 loginless guard 403 短路的请求仍落一行**（外层次序判据）；流式路由响应体逐块到达不被缓冲（合成流式路由断言分块时序）。验证：`pytest tests/test_request_logging.py -q` 全绿。
- [x] 2.4 `ai_client.py` 调用留痕（design D7）：成功 INFO 行（operation/model/host/耗时/tokens/ok）；失败 WARNING 行带归一化分类＋attempt 序号；断言日志不含 api_key、不含正文全文（只长度/截断）。验证：`pytest tests/test_ai_client_logging.py -q` 全绿（monkeypatch 供应商调用造超时与成功两路，caplog＋文件双断言）。

## 3. 壳层退役与失败页

- [x] 3.1 `pywebview_app.py`：`log_config` 字典退役改 `log_config=None`（注释指向 backend-logging 单源）；起 uvicorn 前 `os.environ.setdefault("AINOVEL_LOG_DIR", str(appdata/"logs"))`；在 `uvicorn.Config` 构造前预调 `setup_logging()`（backend_dir 已在 sys.path，见 pywebview_app.py:720-722；幂等标记与 main 内调用合一，design D3 预挂）；`startup.log`／`pywebview.log` 写入目标迁入 `logs/` 子目录（`log_line`／`attach_pywebview_log` 同批，`log_line` 确保目录存在、创建失败回退运行目录根——design D8③）。验证：grep 全仓确认壳层无文件 log_config 残留、startup.log/pywebview.log 落位 logs/＋单测断言（3.3 同批）。
- [x] 3.2 失败页日志尾段收集改读 `logs/`（`startup.log`＋最新一份后端按天日志，含 `app.log` 与带日期轮转件）→ 回退遗留的运行目录根 `uvicorn.log`，遗留文件不删（design D8④）。相关提示文案（如「明细见同目录 uvicorn.log」）同批改口径。验证：`test_packaging_shell_startup.py` 更新后全绿。
- [x] 3.3 壳层测试更新：①错误页含最新按天日志尾段（预置 logs/app.log.2026-10-01＋app.log 断言取后者）；②仅有遗留 uvicorn.log 的老现场断言回退生效；③uvicorn.Config 收到 log_config=None；④startup.log／pywebview.log 落位 `logs/` 子目录；⑤logs/ 目录创建失败时 log_line 回退运行目录根不丢行。验证：`cd client/backend && .venv/bin/python -m pytest tests/test_packaging_shell_startup.py -q` 全绿。
- [x] 3.4 求诊口径落点：启动失败页文案（或 docs/manual 支持页）注明日志位置（运行目录 `logs/`）与「求诊时附最新两份日志文件」口径，与 3.2 的失败页改动同批落。验证：文案评审过目＋文档存在（引用路径贴任务下）。
- [x] 3.5 打包工具链日志消费方同批迁移：`build_release.ps1` smoke 失败诊断（build_release.ps1:146）改读 `logs/`（startup.log＋最新 `app*.log`）；`install_portable.bat:57` 提示文案、`verify_pack_hardening.ps1:76` 回报口径改为 `logs/` 新文件名。验证：本地 dry-run 人为判负一次 smoke，确认诊断段能读出新路径日志（输出贴任务下）。

## 4. 回归与发版前置

- [x] 4.1 后端全量回归：`cd client/backend && .venv/bin/python -m pytest -q`，零新增红（存量红按惯例逐条归因）。产出：结果摘要贴任务下。
  - 4.1 实测（worktree @独立分支，venv 0.16.3 解释器）：2007 passed / 1 skipped / 0 failed（162s）；测试后核验 DATA_ROOT/logs 与 backend/logs 均未产生（AINOVEL_LOG_OFF 生效）。
- [x] 4.2 ruff 门禁：`pip install ruff==0.16.3` 后对 app/tests/scripts 复核零新增告警（BLE001 判例化写法按仓内先例）。产出：输出结论贴任务下。
  - 4.2 实测：ruff 0.16.3 `check .` 全绿（初跑 5 条 F401/I001 已 --fix，复跑 All checks passed；E902 为误传不存在目录非代码问题）。
- [x] 4.3 打包 dispatch 演练：打包链改动（pywebview_app.py＋build_release.ps1 工具链）按惯例先演练一次（Windows cp1252 判例在案），产物核对特征串＝本分支构建；演练中顺带确认 3.5 的 smoke 诊断路径生效。产出：dispatch run 链接＋产物特征串核对记录。
  - 4.3 实测：dispatch run [37567505008](https://github.com/modoojunko/awesome-novel-desktop/actions/runs/37567505008)（ref=c-backend-daily-logging）Windows＋macOS 双平台构建全绿（release job 跳过＝非 tag 正常）；macOS DMG 挂载后抽壳层入口（PyInstaller CArchive 自解，签名包 overlay 末端＝cookie 末），marshalled 常量区实锤 `AINOVEL_LOG_DIR`＋`_backend_log_candidates`，PYZ 目录含 `logging_setup`/`request_logging` 模块名——容器里跑的确实是本分支构建。3.5 的 smoke 诊断段（logs/ 读取）随 build_release.ps1 同批入包，真机判负场景随 4.4 一并人工核。
- [ ] 4.4 真机冒烟判据（打包产物）：运行目录 `logs/` 下同时出现 `app.log`、`startup.log`、`pywebview.log`，运行目录根无新增 `uvicorn.log`；制造一次 AI 失败与一次 4xx 请求后，日志可见请求行＋WARNING 失败行；失败页在人为断后端场景下能展示按天日志尾段。产出：现场记录（可后补）。
