## Why

C端 打包态的日志现状（`uvicorn.log` 按大小轮转 2MB×3）最多保留几小时，用户「昨天遇到的问题」现场已不可考；且 AI 调用链（`ai_client.py`）零日志——失败被归一化成前端弹窗后，后端文件里无迹可寻，远程定位全靠猜。需要按天轮转、保留 5 天、单源化的日志管道，把「操作了什么 / 运行了什么 / 报错了什么」三者落进文件。

## What Changes

- 新建 `client/backend/logging_setup.py`：root logger 挂 `TimedRotatingFileHandler`（每日 0 点轮转、保留 5 天、UTF-8、单文件体积护栏/同文限速），并桥接 `uvicorn` / `uvicorn.error` / `uvicorn.access` 消息进同一份按天文件；幂等挂载（handler 标记防 reload/测试双挂）、日志目录显式创建。
- 壳层（`pywebview_app.py`）`log_config` 字典退役：改为 `log_config=None`（stdout 在打包态已是 devnull），文件落盘职责整体移交 backend，并在起 uvicorn 前预挂 `setup_logging()`（幂等合一，覆盖 main.py 导入期之前的死法）；`uvicorn.log` 不再产生。
- 启动失败页日志尾段读取从 `uvicorn.log` 扩展为 `logs/` 目录最新一份按天文件（遗留 `uvicorn.log` 作回退兜底，老现场不丢）。
- `main.py` 新增请求日志中间件：`method path status 耗时ms` 一行一条（替代 access 日志消除双份），`/api/health` 豁免降噪。
- `ai_client.py` 补调用日志：每次调用一行 INFO（operation / model / base_url 主机 / 耗时 / tokens / 结果），失败升 WARNING 带归一化错误分类。
- 全部诊断日志收拢单一目录：壳层 `startup.log`／`pywebview.log` 连同后端按天日志一并落在 `<运行目录>/logs/`（打包态；开发态默认 `DATA_ROOT/logs`），运行目录根不再产生新日志文件（遗留文件不清理），`port.json` 等非日志运行时文件维持原位，控制台输出保持。
- 隐私红线钉进实现：API Key 永不打；AI 请求/响应正文只打长度＋截断，不落全文。

非目标：业务域关键写操作的 event 级埋点（保存章纲/归档等）不在本次铺开，请求中间件＋AI 调用行已覆盖「操作了什么」的支持排障面；后续按报障高频度另行立项。

## Capabilities

### New Capabilities
- `backend-logging`: C端 诊断日志管道——单一日志目录（后端按天日志＋壳层 startup.log/pywebview.log 同落 logs/）、按天轮转与 5 天保留＋单文件体积护栏、单源挂载（backend 接管，壳层退役 uvicorn log_config）、请求耗时日志、AI 调用留痕、隐私红线与测试隔离。

### Modified Capabilities

（无——主 spec 无日志相关 capability；未归档 change `c-shell-render-resilience` 的 `client-shell-startup` delta 与本 change 在「uvicorn.log 措辞」上有交叠，见 Impact 的归档顺序注记。）

## Impact

- **代码**：`client/backend/logging_setup.py`（新）、`main.py`（中间件＋setup 调用）、`ai_client.py`（调用日志）、`client/packaging/build/pywebview_app.py`（log_config 退役＋壳层日志迁 logs/＋失败页读 logs 目录）、打包工具链三件（`build_release.ps1` smoke 日志收集、`install_portable.bat`/`verify_pack_hardening.ps1` 求诊文案）、`client/backend/tests/`（新增与改判）。
- **行为变化**：打包态运行目录不再新增 `uvicorn.log`（既有文件保留为历史现场）；壳层 `startup.log`／`pywebview.log` 迁入 `logs/`；用户求诊口径＝提供 `logs/` 目录最新两份文件。
- **测试**：`test_packaging_shell_startup.py` 中 uvicorn.log 相关判据随失败页逻辑同批更新；conftest 需设 `AINOVEL_LOG_OFF`（或等价开关）防测试刷文件。
- **打包链**：壳层改动一行＋失败页函数，按惯例发版前须 dispatch 打包演练（Windows cp1252 判例在案）。
- **归档顺序注记**：`c-shell-render-resilience`（已合码未归档）的 client-shell-startup delta 钉了「uvicorn 日志级别 INFO 含 access、MUST NOT 无限增长、失败页带 uvicorn.log 尾段、pywebview.log 旁路 `<运行目录>`」等措辞。本 change 落地后这些措辞与实现出现偏差（uvicorn.log → logs/ 按天文件，access 行由请求中间件承载，startup.log/pywebview.log 迁入 logs/）。处置：本 change **先归档**；c-shell-render-resilience 归档 sync 时同批把主 spec 措辞对齐（或引用本 change 的 backend-logging capability），避免归档竞态把旧路径钉死进主 spec。
