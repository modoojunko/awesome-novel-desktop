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
  - **Windows 安装版、本次非安全模式、且本进程不是重启代** → 自动拉起新实例并让位退出
    （新实例读标记进安全模式：追加 `--disable-gpu`）；重启守卫**不依赖"下一代会进安全模式"**
    ——父进程向子进程注入重启深度标记（环境变量），子进程再挂就不再重启；`shell.json` 显式
    `"safe_mode": false` 时不重启。任何路径都不会出现无限重启链，兜底为浏览器兜底＋错误页；
    非 Windows／dev 模式保持现状。
  - 出口：删 `render-hang.flag` 或 `shell.json` 写 `"safe_mode": false`（日志与错误页都写明）。
- **证据补齐（让下一轮能定罪）**：startup.log 增记 `safe_mode`／生效参数／WebView2 Runtime
  版本；pywebview 自己的调试日志（Loading URL / loaded event fired）旁路到 `pywebview.log`
  （GUI 模式下 stderr 是 devnull，否则是黑洞）；uvicorn 日志级别 WARNING→INFO，**并开 access
  日志**——用来判断"渲染进程的请求到底有没有走到后端"（没走到＝卡在 WebView2/网络栈侧）；
  uvicorn.log 加轮转上限（2MB×3），防长期使用无限增长。
- **不做**：不改错误页/浏览器兜底语义；不加单实例互斥（多开行为待现场证据）；不做按显卡
  型号自动关 GPU 之类的启发式。

### 第二轮现场追加（2026-10-06 夜，用户机 Windows 11）

- **运行目录改到安装目录优先**（用户拍板"文件都在安装目录"）：运行时文件（startup.log／
  uvicorn.log／pywebview.log／port.json／error.html／loading.html／render-hang.flag／
  shell.json）从固定 `%APPDATA%\AwesomeNovel` 改为「安装目录**实测可写**就用安装目录，
  否则回落 %APPDATA%」——便携安装下与 `data\` 同根，用户一眼找得到；装到 Program Files 的
  机器保持原兜底（诊断文件必须永远写得出来）。`shell.json` 额外认 `%APPDATA%` 旧位置（v0.28.1
  指引的落点），命中留日志提示搬迁。卸载器补 `[UninstallDelete]` 清安装目录里的运行时产物。
- **后端就绪等待：默认 60→180 秒＋等待期心跳＋判负文案分因**：用户机首次冷启动被杀软首扫＋
  慢盘拖到 >60 秒被判死（第二次才进得来）。现默认 180 秒；等待期每 ~15 秒落一行心跳
  （已等秒数＋探测分类：连接被拒＝仍在导入 app／已监听无响应＝lifespan 进行中）；
  判负文案区分「线程已退出」与「超时但线程仍在导入/启动」——旧文案
  `timeout / server thread exited` 被现场两次误读成"后端崩了"。

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
  改吃会话配置；运行目录选择（安装目录优先/appdata 兜底）；就绪等待心跳与判负分因。
- 打包链路随行：`client-package.yml`（Windows smoke 两候选目录定位 port.json/日志）、
  `build_release.ps1`（同）、`installer.iss`（`[UninstallDelete]` 清安装目录里的运行时产物）、
  `install_portable.bat`（完成提示改口径）。
- `client/backend/tests/test_packaging_shell_startup.py`：13 例 → 42 例。
