# Proposal: c-shell-render-resilience

## Why

第二轮启动卡死现场（2026-10-06，测试同学 Windows 11 机 `%APPDATA%\AwesomeNovel\startup.log`，v0.28）：

1. **窗口内应用页装载不上（主症状）**：后端就绪（38s）、导航已发出，但 60 秒内 WebView2 连
   NavigationCompleted 都没发生。判据来自 pywebview 6.2.1 实现：`loaded` 事件在
   `NavigationCompleted → 注入 JS` 链上置位，且**不判导航成败**（连接被拒也会置位）——
   所以超时＝整条 WebView2 链没走完，不是前端 JS 报错、也不是"后端拒绝连接"。
2. **后端就绪时间剧烈波动（伴生）**：同一台机器 38s（首跑）→ 7s → >60s（直接判"后端启动
   超时"）。uvicorn 日志级别是 WARNING，lifespan 进度（db_lifecycle / seeding /
   startup complete）全被吞掉——现场只剩一个空文件，无法归因。
3. 五次启动没有一次窗口正常关闭（无 `GUI loop exited`），全是挂死后强杀；其间没有任何
   安全网，用户只能反复重试。

首轮修复（shell-startup-diagnostics）把"永久静默 splash"变成了有判据的日志＋浏览器兜底＋
错误页，但**根因未除**，且现有证据不足以定罪（缺 WebView2 版本、pywebview 侧判据、
后端 access 日志）。

**已核对的关键事实**（决定本轮可用的杠杆，来自 WebView2 官方文档）：
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` 环境变量与注册表值对
`CreateCoreWebView2EnvironmentWithOptions` 的参数是**追加**语义（replace 语义只适用于
browserExecutableFolder / userDataFolder）——所以壳层可以注入浏览器参数而不与 pywebview
自塞的 `--disable-features=ElasticOverscroll` 冲突，也不需要改 pywebview。

## What Changes

- **可调参数文件 `<appdata>/shell.json`（可选）**：`webview_args`（追加给 WebView2 的参数）／
  `backend_timeout`／`app_load_timeout`（5..600 秒）／`safe_mode`。缺省＝行为与现状完全一致；
  非法值回落默认并留一行日志——配置文件永远不能把启动打崩。
- **装载挂死自愈（两段）**：
  - 装载看门狗超时 → 落 `render-hang.flag`（持久标记）；
  - **Windows 安装版且本次不是安全模式** → 自动拉起新实例并让位退出（新实例读标记进
    安全模式：追加 `--disable-gpu`）；安全模式再挂就只剩浏览器兜底＋错误页——链条最多
    转一轮，防死循环；非 Windows／dev 模式保持现状（浏览器兜底＋错误页）。
  - 出口：删 `render-hang.flag` 或 `shell.json` 写 `"safe_mode": false`（日志与错误页都写明）。
- **证据补齐（让下一轮能定罪）**：startup.log 增记 `safe_mode`／生效参数／WebView2 Runtime
  版本；pywebview 自己的调试日志（Loading URL / loaded event fired）旁路到 `pywebview.log`
  （GUI 模式下 stderr 是 devnull，否则是黑洞）；uvicorn 日志级别 WARNING→INFO，**并开 access
  日志**——用来判断"渲染进程的请求到底有没有走到后端"（没走到＝卡在 WebView2/网络栈侧）；
  uvicorn.log 加轮转上限（2MB×3），防长期使用无限增长。
- **不做**：不改错误页/浏览器兜底语义；不加单实例互斥（多开行为待现场证据）；不做按显卡
  型号自动关 GPU 之类的启发式。

**`--disable-gpu` 的性质（重要）**：它是**候选修法**（WebView2/GPU 渲染层假设），不是已证实
的根因。判定实验列入 tasks（用当前 v0.28 包＋环境变量 A/B，**无需新包**）——实验结论决定
安全模式参数是否要调整（如换 `--disable-gpu-compositing`／`--use-angle=swiftshader`，
`shell.json` 已留出口）。

## Capabilities

### New Capabilities

- `client-shell-startup`: 桌面壳启动链契约首立——既有的留痕/兜底/迁移行为（此前无 spec 承载），
  加本轮的"可调参数＋装载挂死自愈＋判据补齐"。

### Modified Capabilities

（无）

## Impact

- `client/packaging/build/pywebview_app.py`：新增 shell.json 读取、安全模式与自愈重启、
  WebView2 版本读取、pywebview 日志旁路、uvicorn 日志级别与轮转；`check_backend_and_navigate`
  改吃会话配置。
- `client/backend/tests/test_packaging_shell_startup.py`：13 例 → 27 例（新增 14 例：可调参数 6、
  安全模式与自愈 6、杂项 2）。
- 无前端改动、无接口契约改动、打包流水线（client-package.yml）不变。
