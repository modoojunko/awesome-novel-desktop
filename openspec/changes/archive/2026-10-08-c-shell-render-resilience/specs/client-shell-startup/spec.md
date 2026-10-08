## ADDED Requirements

### Requirement: 运行目录选择（安装目录可写优先，用户目录兜底）

壳层运行时文件（`startup.log`／`uvicorn.log`／`pywebview.log`／`port.json`／`error.html`／
`loading.html`／`render-hang.flag`／`shell.json`）SHALL 统一落在「运行目录」；选择规则：
Windows 安装版且**实测**安装目录可写（写探针文件成功后即删）时＝安装目录（与 `data\` 同根，
用户一眼找得到）；不可写（典型：装到 `C:\Program Files` 且标准用户运行）SHALL 回落
`%APPDATA%\AwesomeNovel`；macOS 与 dev（未冻结）SHALL 保持 `%APPDATA%\AwesomeNovel`／
`~/Library/Application Support/AwesomeNovel`（macOS 上该目录同时是书稿数据目录，dev 不往
项目目录写）。启动日志 SHALL 记录本次运行目录。任何情况下 MUST NOT 出现「诊断文件写不出来」
的静默路径（最次回落系统临时目录）；各文件的实际位置以错误页/日志写出的绝对路径为准。

#### Scenario: 装到用户可写目录（默认位置/便携安装）
- **WHEN** Windows 安装版从可写安装目录（如 `D:\AwesomeNovel`）启动
- **THEN** `startup.log` 等运行时文件落在安装目录根，错误页与日志都写出该绝对路径

#### Scenario: 装到不可写目录
- **WHEN** 安装目录不可写（Program Files + 标准用户）
- **THEN** 运行目录回落 `%APPDATA%\AwesomeNovel`，启动链与全部诊断能力照常

#### Scenario: 旧位置调参兼容
- **WHEN** 运行目录＝安装目录，而 `%APPDATA%\AwesomeNovel\shell.json` 存在（v0.28.1 时代指引的位置）
- **THEN** 该文件仍被读取（运行目录同名文件优先），startup.log 留一行「取自旧位置」提示

### Requirement: 启动链全程留痕与失败兜底

桌面壳 SHALL 在启动链每一步写带时间戳的 `<运行目录>/startup.log` 行，且 SHALL 在失败路径给出
可见兜底；写日志 MUST NOT 依赖 UI 线程（窗口挂死时仍要能落盘）。关键分界行 SHALL 至少包含：
`shell main() entered`（带 exe/frozen/数据目录）、`window shown`、`server thread started`、
`backend ready (port …)`、`navigation dispatched; waiting for app page load...`、
`app page loaded` 或 `app page NOT loaded in {N}s`、`backend NOT ready`、
`server thread FATAL`、`showing error page`。

- 后端线程一退出（含启动期异常）SHALL 使健康轮询立即判负，MUST NOT 干等满超时；
- 等待后端就绪期间 SHALL 每约 15 秒落一行心跳（已等待秒数＋本次探测分类：连接被拒＝uvicorn
  尚未监听、多半仍在导入 app；已监听但无响应＝lifespan/app 启动进行中）；判负文案 SHALL 区分
  「线程已退出」与「超时但线程仍在导入/启动」两种死因，MUST NOT 用一句含糊话同时覆盖两者
  （2026-10-06 现场该文案被两次误读成"后端崩了"）；
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

#### Scenario: 后端是慢不是死
- **WHEN** 后端超过就绪超时（默认 180 秒）仍未就绪，或中途才就绪
- **THEN** startup.log 留有连续心跳行（含探测分类），判负行点名「后端线程仍活着，多半还在导入/启动中」；线程真退出时判负行才写 `server thread exited`

### Requirement: 陈旧 port.json 每启动清理

壳 SHALL 在每次 GUI 启动时先清除 `<运行目录>/port.json`，使健康轮询只会连上本次进程的后端。
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

壳 SHALL 读取可选的 `<运行目录>/shell.json`，支持键：`webview_args`（追加给 WebView2 的浏览器
参数）、`backend_timeout`、`app_load_timeout`（秒，收敛到 5..600）、`safe_mode`（bool，显式
开关安全模式）。文件缺失或键缺省时行为 SHALL 与默认完全一致；非法 JSON、非对象、类型不符或
越界值 SHALL 回落默认（越界值夹取到边界）**并留日志**（含原值，现场可对照自己写了什么），
MUST NOT 阻断启动。超时取用优先级 SHALL 为 shell.json > 环境变量（`AI_NOVEL_BACKEND_TIMEOUT` /
`AI_NOVEL_APP_LOAD_TIMEOUT`）> 默认值；后端就绪默认 **180 秒**（2026-10-06 现场：首次冷启动
被杀软首扫＋慢盘拖到 >60 秒被判死，第二次才进得来），应用页装载默认 60 秒。

#### Scenario: 现场不改包放宽等待
- **WHEN** 测试同学在 shell.json 写 `{"backend_timeout": 300, "app_load_timeout": 90}`
- **THEN** 后端就绪等待与装载看门狗分别按 300/90 秒执行，startup.log 可读出生效值

#### Scenario: 坏配置文件不影响启动
- **WHEN** shell.json 内容不是合法 JSON，或写了 `"backend_timeout": "abc"` / `99999` 这类不可用值
- **THEN** 启动按默认参数（越界值夹到边界）继续，startup.log 逐键留下回落说明与原值

### Requirement: 装载挂死自愈（标记 → 安全模式 → 自愈重启）

装载看门狗超时 SHALL 在 `<运行目录>/render-hang.flag` 落持久标记。此后每次启动判定安全模式：
shell.json 的 `safe_mode` 显式值优先，否则标记存在即安全模式。安全模式 SHALL 通过
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` 追加 `--disable-gpu`（该变量为**追加**语义，MUST NOT
覆盖既有值；必须在窗口创建之前生效）。标记一旦置位 SHALL 保持（同机同 WebView2 运行时上默认
渲染路径已被证明会挂），出口为删除标记文件或 shell.json 写 `"safe_mode": false`。

装载挂死且判定允许时 SHALL 自愈重启：仅限 Windows 安装版（冻结）、本次非安全模式、且**本进程
不是重启代**——壳 SHALL 拉起新实例并让位退出。重启守卫 MUST NOT 依赖「下一代必然进入安全模式」
这一前提（标记可能写失败，用户也可能显式关闭安全模式）：父进程 SHALL 向子进程注入重启深度
标记（环境变量），子进程再挂时 MUST NOT 继续重启；`shell.json` 显式 `safe_mode: false` 时
SHALL NOT 自愈重启。任何路径都 MUST NOT 出现无限重启链，兜底为浏览器打开＋错误页，且跳过
重启的原因 SHALL 落日志。

#### Scenario: 首次挂死自动带着安全模式回来
- **WHEN** Windows 安装版一次启动装载挂死（本次非安全模式）
- **THEN** 落 render-hang.flag，壳拉起新实例并退出；新实例 startup.log 显示 safe_mode=true 与 `--disable-gpu`，装载成功则应用可用

#### Scenario: 安全模式再挂不再重启
- **WHEN** 已处于安全模式的一次启动再次装载挂死
- **THEN** 不再拉起新实例，走浏览器兜底＋错误页，startup.log 保留完整判据

#### Scenario: 标记写失败也不会成重启环
- **WHEN** 装载挂死且 render-hang.flag 写盘失败（磁盘/权限/杀软），父进程已拉起新实例
- **THEN** 新实例（重启代）再次挂死时不拉起任何实例，走浏览器兜底＋错误页，startup.log 写明 `auto relaunch 跳过`

#### Scenario: 非 Windows / dev 模式保持现状
- **WHEN** macOS 或未冻结的 dev 模式发生装载挂死
- **THEN** 不重启，行为与首轮一致（日志＋浏览器兜底＋错误页）

### Requirement: 启动判据落盘（能分辨卡在哪一层）

除 startup.log 外，壳 SHALL 落以下判据：本次 `safe_mode` 与生效的 WebView2 参数；WebView2
Runtime 版本（Windows 注册表读取，非 Windows 或读不到记 `unknown`，MUST NOT 抛错）；pywebview
自身调试日志旁路到 `<运行目录>/pywebview.log`（Loading URL / loaded event fired 等）。
后端 uvicorn 日志级别 SHALL 为 INFO（含 access 日志——用于判断渲染进程的请求是否到达后端），
且 MUST NOT 无限增长（轮转上限）。

#### Scenario: 用日志分辨"没到后端"还是"到了没渲染完"
- **WHEN** 再次发生窗口内装载不上
- **THEN** 若 uvicorn.log 无对应请求行 ⇒ 请求未离开 WebView2 侧；若有请求行而 pywebview.log 无 `loaded event fired` ⇒ 渲染进程侧未完成，两种判据可直接区分
