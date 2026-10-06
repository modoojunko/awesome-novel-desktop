## ADDED Requirements

### Requirement: 启动链全程留痕与失败兜底

桌面壳 SHALL 在启动链每一步写带时间戳的 `<appdata>/startup.log` 行，且 SHALL 在失败路径给出
可见兜底；写日志 MUST NOT 依赖 UI 线程（窗口挂死时仍要能落盘）。关键分界行 SHALL 至少包含：
`shell main() entered`（带 exe/frozen/数据目录）、`window shown`、`server thread started`、
`backend ready (port …)`、`navigation dispatched; waiting for app page load...`、
`app page loaded` 或 `app page NOT loaded in {N}s`、`backend NOT ready`、
`server thread FATAL`、`showing error page`。

- 后端线程一退出（含启动期异常）SHALL 使健康轮询立即判负，MUST NOT 干等满超时；
- 数据目录不可写 SHALL 落 FATAL＋traceback（Windows 附"装到用户可写目录"提示）；
- 轮询线程任何异常 MUST NOT 静默：SHALL 落日志并尽力装错误页；
- 启动失败页 SHALL 同时带 startup.log 与 uvicorn.log 尾段（真实死因常在后者的日子居多），
  并 SHALL 写明日志目录、可调参数文件路径与安全模式出口。

#### Scenario: 停在启动页且零日志的形态不再出现
- **WHEN** 后端线程在早段失败（典型：数据目录无写权限）
- **THEN** startup.log 出现 `server thread FATAL` 与 traceback，轮询线程随即判负并显示带两份日志尾段的错误页，用户不再面对永久 splash

#### Scenario: 导航已发出但应用页不装载
- **WHEN** 导航已发出而应用页在看门狗时长内未装载
- **THEN** startup.log 落 `app page NOT loaded in {N}s — UI/renderer hang suspected`，并按下方自愈/兜底要求继续处置

### Requirement: 陈旧 port.json 每启动清理

壳 SHALL 在每次 GUI 启动时先清除 `<appdata>/port.json`，使健康轮询只会连上本次进程的后端。
清理失败 SHALL 留日志且 MUST NOT 阻断启动。

#### Scenario: 上一实例未退干净
- **WHEN** 上一实例崩溃残留 port.json 后再次启动
- **THEN** 本次启动先删除该文件，轮询不会连到旧进程的端口

### Requirement: 运行目录换名无痛迁移（AI Novel → AwesomeNovel）

在 macOS（该目录即书稿数据目录）SHALL 于首启把旧名目录原子换名为 `AwesomeNovel`，并在旧路径
留指向新目录的符号链接；换名失败（被占用/权限不足）SHALL 继续使用旧目录，MUST NOT 丢数据。
Windows 侧该目录只是运行数据（日志/端口），SHALL 直接使用新名、不迁移旧目录。

#### Scenario: macOS 装回旧版本仍找得到书
- **WHEN** 旧版本用户升级后再次运行旧版本
- **THEN** 旧路径软链仍指向新目录，旧版本照常读到自己的书

### Requirement: 运行时可调参数（shell.json）

壳 SHALL 读取可选的 `<appdata>/shell.json`，支持键：`webview_args`（追加给 WebView2 的浏览器
参数）、`backend_timeout`、`app_load_timeout`（秒，收敛到 5..600）、`safe_mode`（bool，显式
开关安全模式）。文件缺失或键缺省时行为 SHALL 与默认完全一致；非法 JSON、非对象、类型不符或
越界值 SHALL 回落默认并留日志，MUST NOT 阻断启动。超时取用优先级 SHALL 为
shell.json > 环境变量（`AI_NOVEL_BACKEND_TIMEOUT` / `AI_NOVEL_APP_LOAD_TIMEOUT`）> 默认 60 秒。

#### Scenario: 现场不改包放宽等待
- **WHEN** 测试同学在 shell.json 写 `{"backend_timeout": 120, "app_load_timeout": 90}`
- **THEN** 后端就绪等待与装载看门狗分别按 120/90 秒执行，startup.log 可读出生效值

#### Scenario: 坏配置文件不影响启动
- **WHEN** shell.json 内容不是合法 JSON
- **THEN** 启动按默认参数继续，startup.log 增一行读取失败说明

### Requirement: 装载挂死自愈（标记 → 安全模式 → 自愈重启）

装载看门狗超时 SHALL 在 `<appdata>/render-hang.flag` 落持久标记。此后每次启动判定安全模式：
shell.json 的 `safe_mode` 显式值优先，否则标记存在即安全模式。安全模式 SHALL 通过
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` 追加 `--disable-gpu`（该变量为**追加**语义，MUST NOT
覆盖既有值；必须在窗口创建之前生效）。标记一旦置位 SHALL 保持（同机同 WebView2 运行时上默认
渲染路径已被证明会挂），出口为删除标记文件或 shell.json 写 `"safe_mode": false`。

装载挂死且判定允许时 SHALL 自愈重启：仅限 Windows 安装版（冻结）且**本次不是安全模式**——
壳 SHALL 拉起新实例并让位退出（新实例读标记进安全模式）；安全模式再挂 MUST NOT 继续重启
（只剩浏览器兜底＋错误页），MUST NOT 出现无限重启链。

#### Scenario: 首次挂死自动带着安全模式回来
- **WHEN** Windows 安装版一次启动装载挂死（本次非安全模式）
- **THEN** 落 render-hang.flag，壳拉起新实例并退出；新实例 startup.log 显示 safe_mode=true 与 `--disable-gpu`，装载成功则应用可用

#### Scenario: 安全模式再挂不再重启
- **WHEN** 已处于安全模式的一次启动再次装载挂死
- **THEN** 不再拉起新实例，走浏览器兜底＋错误页，startup.log 保留完整判据

#### Scenario: 非 Windows / dev 模式保持现状
- **WHEN** macOS 或未冻结的 dev 模式发生装载挂死
- **THEN** 不重启，行为与首轮一致（日志＋浏览器兜底＋错误页）

### Requirement: 启动判据落盘（能分辨卡在哪一层）

除 startup.log 外，壳 SHALL 落以下判据：本次 `safe_mode` 与生效的 WebView2 参数；WebView2
Runtime 版本（Windows 注册表读取，非 Windows 或读不到记 `unknown`，MUST NOT 抛错）；pywebview
自身调试日志旁路到 `<appdata>/pywebview.log`（Loading URL / loaded event fired 等）。
后端 uvicorn 日志级别 SHALL 为 INFO（含 access 日志——用于判断渲染进程的请求是否到达后端），
且 MUST NOT 无限增长（轮转上限）。

#### Scenario: 用日志分辨"没到后端"还是"到了没渲染完"
- **WHEN** 再次发生窗口内装载不上
- **THEN** 若 uvicorn.log 无对应请求行 ⇒ 请求未离开 WebView2 侧；若有请求行而 pywebview.log 无 `loaded event fired` ⇒ 渲染进程侧未完成，两种判据可直接区分
