## Context

打包态壳层（`pywebview_app.py`）现以自定义 `log_config` 把 uvicorn 三 logger 写进运行目录 `uvicorn.log`（RotatingFileHandler 2MB×3）；业务代码 19 处 getLogger 几乎全钉 `logging.getLogger("uvicorn.error")` 才能进文件，标准 `getLogger(__name__)` 在打包态丢失（root 无 handler）；`ai_client.py`（604 行）零日志。约束：

- 壳层失败页（`pywebview_app.py:982` 起）读 `startup.log`＋`uvicorn.log` 尾段，是 `c-shell-render-resilience`（已合码未归档）delta spec 钉过的判据面。
- 2026-10-06 现场教训：`uvicorn.log` 空＝导入期崩掉，失败页只能干瞪眼——新的管道必须继续覆盖「导入期就死」的现场。
- 正文流式链路对中间件敏感（BaseHTTPMiddleware 包流式响应有历史坑），不能为记耗时引入缓冲。
- Windows 打包链有 cp1252 判例；测试基建有模块级 app 启动竞态判例。

## Goals / Non-Goals

**Goals:**
- 按天轮转＋保 5 天＋UTF-8 的后端文件日志，dev 与打包态行为一致（打包态经壳层注入目录）。
- **全部诊断日志单一目录**：壳层 `startup.log`／`pywebview.log` 连同后端按天日志一并落在 `logs/`，求诊只看一个目录。
- uvicorn 消息、业务 `__name__` logger、存量 `uvicorn.error` 调用汇入同一份按天文件，导入期崩溃现场可捕获。
- 请求一行一条（含耗时）、AI 调用一行一条（含失败分类），失败行升 WARNING。
- 隐私红线与测试隔离在实现层钉死。

**Non-Goals:**
- 业务域 event 级埋点（保存章纲/归档等）不铺开。
- 单实例互斥（多进程同写日志的根因）另项在案，不在本 change 解决。
- 日志查看 UI／自动上报；历史遗留日志文件（运行目录根的 `uvicorn.log` 等）不做清理或迁移。
- `port.json`／`render-hang.flag`／`shell.json` 等非日志运行时文件维持原位，不随迁。

## Decisions

**D1. Handler 拓扑：root＋「uvicorn」桥接，access 降级给请求中间件让路。**
`setup_logging()` 把按天文件 handler 挂到 root，并**直接挂到 `uvicorn` logger**（`uvicorn.error` 是其子 logger，业务钉名调用自然汇入）。不挂 `uvicorn.access`，改 `logging.getLogger("uvicorn.access").setLevel(WARNING)` 压掉逐请求行，由中间件出唯一请求行。备选「只挂 root 靠 propagate」被否：uvicorn 默认 log config（dev CLI 直跑）对 `uvicorn`/`uvicorn.access` 设 `propagate=False`，光挂 root 收不到；直接挂桥接对两种启动方式都确定。**双挂点的双写面必须钉死**：`log_config=None` 跳过 dictConfig 后，默认配置里 `uvicorn`/`uvicorn.access` 的 `propagate=False`（uvicorn/config.py:109-111）不再生效——record 会在 `uvicorn` 与 root 两个挂点各 emit 一次（同一 handler 对象写两行；dev 态被 dictConfig 挡住看不出，打包态必现）。`setup_logging` SHALL 显式 `logging.getLogger("uvicorn").propagate = False`（镜像 uvicorn 自身语义，两态确定性）。

**D2. 级别陷阱显式处理（否则静默丢行）。**
`log_config=None` 时 uvicorn 不跑 dictConfig，`uvicorn` logger 本体 NOTSET 会沿 root（默认 WARNING）判定，启动期 INFO 行全部被吞。`setup_logging` SHALL 显式 `root.setLevel(INFO)`＋`logging.getLogger("uvicorn").setLevel(INFO)`。这是本 change 最容易踩的隐形坑，设计层钉死。已实勘 uvicorn **0.52.1**：`configure_logging()` 在 `Config.__init__`（先于 app import），`log_config=None` 时 `log_level` 仍生效但只设 uvicorn.error/access/asgi 三个子 logger——上述补设与 access 压制的先后排序依赖此行为，test_logging_setup 以「uvicorn.error INFO 行落文件」断言钉住版本语义。root 提 INFO 的代价是第三方库 INFO 进文件/控制台（今天被 root WARNING 挡住）：`httpx`（每个上游请求一行、含完整 URL）/`httpcore`/`openai`/`sqlalchemy` SHALL 显式压回 WARNING——AI 调用观测由 D7 承载不损失信息，同时消除第三方 URL 进求诊文件的隐私面。

**D3. 挂载时机＝`main.py` 模块顶部（早于业务 import）＋打包态壳层预挂。**
uvicorn 字符串加载 `main:app`：`setup_logging()` 在 main.py 顶部先执行，随后任何 router import 炸掉的 traceback 由 uvicorn error logger 打出时，文件 handler 已在位——「导入期死亡」现场继续可考（对齐 2026-10-06 判据）。备选「lifespan 里挂」被否：lifespan 前的死（导入/绑定）恰好是失败页最需要的那段。残余缺口（main.py 自身语法错误＝setup 未执行）由壳层预挂补平：壳层起 uvicorn 前已把 backend_dir 插入 sys.path（pywebview_app.py:720-722），打包态在 `uvicorn.Config` 构造前先调 `setup_logging()`（幂等标记与 main 内调用合一），覆盖面拉平到优于旧 uvicorn.log；dev 态由 main.py 顶部调用兜底（dev 有控制台，语法错误类现场可直读）。

**D4. 轮转器＝标准 `TimedRotatingFileHandler`，`when="midnight"`、`backupCount=5`、`encoding="utf-8"`、`delay=True`＋同文限速 Filter。**
现文件名 `app.log`，轮转产物 `app.log.YYYY-MM-DD`（标准命名，历史文件按日期可辨），不做自定义 namer。`delay=True` 避免空跑时留空文件。**单文件体积护栏**：文件 handler 挂同文重复限速 Filter——窗口内同型消息（同 logger＋级别＋消息模板）只记首条＋重复计数，异常风暴（每请求 traceback）下当日体积有界，替代旧管道 2MB×3 的有界语义；「超限手动 doRollover」方案被否——同日后缀会被 os.remove 覆盖，丢掉早间日志。备选第三方库（loguru/concurrent-log-handler）被否：为单进程单 handler 引依赖不值。

**D5. 日志目录解析：`AINOVEL_LOG_DIR` 显式 > `DATA_ROOT/logs` 兜底，初始化时显式 mkdir。**
壳层在起 uvicorn 前 `os.environ.setdefault("AINOVEL_LOG_DIR", str(appdata/"logs"))`（appdata 即现有 uvicorn.log 所在的运行时目录）；dev 直跑落到数据目录 logs/，与数据同生命周期。`setup_logging` MUST 显式 `log_dir.mkdir(parents=True, exist_ok=True)`——logging 不创建父目录，漏建＝全新安装首条 emit 失败被 handleError 静默吞掉（整份日志静默消失，恰是本 change 要消灭的「空日志」形态）。关闭开关 `AINOVEL_LOG_OFF=1`（conftest 全局设置）→ 不挂文件 handler，测试零副作用。

**D6. 请求日志用纯 ASGI 中间件（非 BaseHTTPMiddleware），最后注册＝最外层。**
`request_logging.py` 提供 `add_middleware` 兼容的纯 ASGI 类：包 `send` 捕 status、`perf_counter` 计耗时、响应完成后落一行 `INFO`（method path status duration_ms）；异常路径 `finally` 兜底记 500。不缓冲、不碰流式响应体——正文流式现场保护（#663）语义零干扰。注册次序钉死：在 main.py 全部 `add_middleware`（CORS、loginless guard）**之后**注册＝最外层——被安全中间件短路拦下的响应（403 等）也 MUST 落行（攻击可见性是排障刚需，恰好是只挂内层时最先丢的那批）。logger 名 `api.request`，路径 `/api/health` 豁免。

**D7. ai_client 日志挂在 provider 调用出口（含重试包装的每次尝试）。**
成功：`INFO` 一行 `operation/model/host/耗时/tokens_in/out/ok`（tokens 复用现有 usage 提取）；失败：`WARNING` 一行带归一化分类（超时/上游拒绝/响应不可解析——与 `_raise_normalized` 的分类同源）＋ attempt 序号。请求/响应正文**不落全文**，只记字符数；`base_url` 只取 host；任何 header/Key 不进日志。

**D8. 壳层四处最小改动。**
① `log_config` 字典整体退役改传 `None`（附一行注释指向 backend-logging）；② 注入 `AINOVEL_LOG_DIR`；③ `startup.log`／`pywebview.log` 写入目标迁入 `logs/` 子目录（`log_line` 与 `attach_pywebview_log` 目标目录同改）；`log_line` 沿用现有回退链**仅插头不改尾**：`logs/` → 运行目录根 → 系统临时目录（pywebview_app.py:198-207 现链，mkdir 在链内逐级尝试、静默吞错）——启动判据宁可降级也不丢；④ 失败页日志尾段收集按同一回退链查找两份壳层日志＋最新一份后端按天日志，回退遗留的运行目录根 `uvicorn.log`。遗留 `uvicorn.log` 不删，老现场求诊不受影响。`port.json`／`render-hang.flag` 等非日志运行时文件维持原位。打包工具链的日志消费方（build_release.ps1 smoke 诊断、install_portable.bat/verify_pack_hardening.ps1 求诊文案）随迁移同批改口径——smoke 失败诊断读不到日志＝发版演练致盲，见 tasks 3.5。

**D9. 幂等用 handler 标记（同 pywebview.log 挂载先例）。**
handler 打 `_ainovel_daily` 属性，`setup_logging` 先扫现有 handlers 有标记即返回；防 pytest 反复导入 main、防 --reload 重挂。

## Risks / Trade-offs

- **Windows 轮转瞬间文件被占**（用户正拷日志/杀软扫描）：`doRollover` 抛 PermissionError 由 logging `handleError` 吞掉不崩进程，下一emit重试；接受。
- **多实例同写一个 logs 目录**：TimedRotatingFileHandler 非多进程安全，轮转竞态可能丢行——与现状 uvicorn.log 同级风险，根因（单实例互斥待立项）不在此解决；概率低、后果轻。
- **双写残留**：若壳层 `log_config` 忘退役会双份落盘——任务清单钉「grep 确认 log_config=None」判据。
- **归档竞态**：与未归档 `c-shell-render-resilience` 的 client-shell-startup delta 措辞交叠（uvicorn.log→按天文件），归档顺序已写进 proposal Impact——本 change 先归档，彼 change sync 时同批对齐措辞。
- **打包态 stdout=None**：壳层已有 devnull 垫底；`setup_logging` 仍对 `sys.stdout` 判空后再挂控制台 handler，防御顺序颠倒的场景。
