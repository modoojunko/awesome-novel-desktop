# client-shell-startup Specification

## Purpose

pywebview 壳层（启动器）的启动链与退出语义：运行目录与可调参数、启动全程留痕与判据落盘、挂死自愈、js_api 暴露面契约、进程退出收尾与依赖版本锁定。实现侧见 client/packaging。

## Requirements

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

### Requirement: js_api 暴露面契约（公开面只许方法）

壳层注入给 pywebview 的原生桥对象 SHALL NOT 在公开（非 `_` 前缀）成员上挂任何**非可调用**
对象。理由：pywebview 注入 JS API 时递归遍历 js_api 的公开非方法属性来收集可调用对象
（`webview/util.py` `get_functions`，只跳过 `_` 前缀名），把窗口/控件等原生对象挂成公开属性
会把整棵 WinForms/WebView2 树拖进遍历——跨线程 COM 访问全部报错、并可能在某次取值上阻塞
（2026-10-06 现场：装载注入段停摆、白屏且 `loaded` 永不置位）。窗口引用 SHALL 以 `_` 前缀
命名。契约 SHALL 由**运行期守卫测试**（公开成员必须可调用）与**打包 CI 静态门禁**（AST 检查
类体与模块级桥实例赋值）双钉。

#### Scenario: 公开面泄漏被两道门禁同时拦下
- **WHEN** 给桥（或其模块级实例）新增一个公开的非方法属性
- **THEN** 运行期守卫测试红、打包 CI 的 AST 门禁红（事前可红，不必等到现场白屏）

#### Scenario: 正常暴露面
- **WHEN** 桥只暴露 `pick_folder` / `pick_save_file` / `pick_open_file` / `open_folder` / `default_dirs`
- **THEN** 公开成员全部可调用，pywebview 的枚举只登记函数签名、不再深入任何原生对象

### Requirement: 卡死判据（时间戳／看门狗心跳／C 层线程栈）

壳层与后端 SHALL 提供三件判据，使"进程在启动期停摆"这类现场可判读：
- uvicorn 日志格式 SHALL 带时间戳（`%(asctime)s`）——否则"白屏期间后端是否仍在服务"无法判读；
- 应用页装载看门狗 SHALL 在等待期间每约 10 秒落一行心跳（已等待秒数／上限），MUST NOT 死等
  满超时而无任何输出；
- 壳 SHALL 用 `faulthandler.dump_traceback_later`（周期 60 秒，repeat）把**全部线程栈**按需
  dump 到 `<运行目录>/hang-dump.txt`——C 层定时器在 GIL 被原生调用占死时仍能落盘；装载成功后
  SHALL 取消该 dump（避免长会话无谓写盘）。

#### Scenario: 下一次白屏 5 分钟定案
- **WHEN** 再现"窗口活着但页面永不装载"的现场
- **THEN** startup.log 有连续装载心跳、uvicorn.log 各请求带时间戳；若 Python 已停摆，`hang-dump.txt` 里留有各线程栈（含卡在哪个调用）

### Requirement: 进程退出与强制收尾（不留残留进程）

GUI 主循环退出（`webview.start()` 返回）后，壳 SHALL 先做**有界**的后端收尾：请 uvicorn 退出
（置 `should_exit`）并等待服务线程回收，等待上限 SHALL ≤3 秒；随后 SHALL 无条件强制退出进程
（`os._exit`），MUST NOT 依赖"所有线程都会自己结束"。理由：pywebview 的注入／DOM 回调／bridge
调用线程**均为非 daemon**（`webview/util.py` 三处 `Thread(...)`），一旦卡住，解释器退出时的
`threading._shutdown()` 会 join 它们 → 进程残留在任务管理器、并长期持有数据目录文件句柄
（现场"僵尸实例"即此形态）。强制退出前 SHALL 落一行收尾日志（含优雅收尾是否成功）。

边界（写进实现注释）：本要求只覆盖"GUI 循环已退出"这一支；GIL 被原生调用占死的冻结形态下
Python 层任何定时器都跑不到，不在本要求担保范围内。

#### Scenario: 关窗即退，不留进程
- **WHEN** 用户关闭主窗口
- **THEN** startup.log 依次出现 `GUI loop exited (window closed)` 与收尾行（graceful=…），进程立即结束；任务管理器中无 `AwesomeNovel.exe` 残留

#### Scenario: 优雅收尾超时不阻塞用户
- **WHEN** 后端线程在 3 秒内没有回收
- **THEN** 壳仍强制退出（收尾行 graceful=false），MUST NOT 无限等待

### Requirement: 退出不留我们拉起的进程（含 WebView2 子树）

用户口径（关闭即全关）：应用窗口关闭后，系统里 MUST NOT 残留 `AwesomeNovel.exe`，也 MUST NOT
残留**由它拉起**的 WebView2 进程（`msedgewebview2.exe`）。实现 SHALL 以操作系统级机制兜住
"任何死法"（正常退出、强制下线、被任务管理器强杀、崩溃）：Windows 上 SHALL 建
`KILL_ON_JOB_CLOSE` 的 Job Object 并把 WebView2 子树纳入（可覆盖异步启动，须多拍枚举）；
MUST NOT 把壳进程自身放入该 job（会误伤自愈重启拉起的子进程，且嵌套 job 下 breakaway 不可控）。
非 Windows SHALL 静默 no-op；枚举为空或任一 API 失败 SHALL 记一行日志后降级继续（正常关窗仍有
pywebview 的 dispose 软清理兜底）。用户自己的浏览器进程 MUST NOT 被本机制结束；浏览器兜底页
SHALL 以文案明示"其依赖本程序、关闭后不可用"。

#### Scenario: 强杀之后也不留 WebView2 进程
- **WHEN** 用户在任务管理器里强制结束 `AwesomeNovel.exe`（窗口线程已卡死、没有代码能跑）
- **THEN** 由它拉起的 `msedgewebview2.exe` 随 job 句柄关闭被系统一并结束

#### Scenario: 正常关窗的两道保险
- **WHEN** 用户正常关闭窗口
- **THEN** 依次发生：pywebview dispose＋等浏览器进程退出（≤3s，软清理）→ 壳的有界后端收尾（≤3s）→ `os._exit`；job 兜住任何漏网子进程

#### Scenario: 非 Windows/无 WebView2 环境下零副作用
- **WHEN** 在 macOS/dev 或枚举不到 WebView2 子进程的环境运行
- **THEN** 该机制静默 no-op／只记一行日志，不影响启动与退出

### Requirement: 壳层关键路径的依赖版本锁定

打包依赖中的 pywebview SHALL 钉死到已验证的具体版本（当前 6.2.1）。理由：js_api 暴露面契约
依赖"只跳过 `_` 前缀名"这一**未文档化**的实现细节，浮动版本会让该契约在升级后静默失效。

#### Scenario: 打包依赖解析到恒定版本
- **WHEN** 打包链安装依赖
- **THEN** 装到的 pywebview 恒为钉死值（当前 6.2.1），不会因解析到新版本而静默改变注入/枚举行为
