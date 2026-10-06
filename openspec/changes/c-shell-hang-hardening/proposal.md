# Proposal: c-shell-hang-hardening

## Why

2026-10-06 用户机（Windows 11，D:\AwesomeNovel，v0.28.1）出现「第二次启动白屏、窗口无响应、
关窗后任务管理器有残留进程」，三份现场日志（startup.log / uvicorn.log / pywebview.log）经
两轮独立复核（架构师视角＋代码审查视角，逐行对照 pywebview 6.2.1 源码）后定案：

1. **根因：js_api 暴露面把 pywebview 的枚举遍历引进了原生窗口树。**
   `NativeBridge.window_ref` 是**公开**类属性；pywebview 注入 JS API 时会递归遍历 js_api 对象的
   公开非方法属性（`webview/util.py:190/193/203-206`，只跳过 `_` 前缀名；`Window` 自身没标
   `_serializable` 逃生门），于是走进 `window_ref.native`（WinForms 控件树 → WebView2 COM）：
   跨线程 COM 全抛 `E_NOINTERFACE/只能从 UI 线程访问`，还有 `maximum recursion depth exceeded`
   （单行路径长 6000+ 字符）。**风暴本身不是死因**（注入线程的异常分支同样会 `loaded.set()`，
   util.py:236-238；run 1 两次注入都带着风暴正常完成）——死因是遍历里**某次取值阻塞**：
   run 2 的注入在 `_pywebviewready`(20:20:44.906) 之后只落了一条错误就再无输出。
2. **更重的观察：整进程在 20:20:44.923 之后停止执行。** run 2 缺的不只是 `loaded event fired`，
   还缺 20:21:44 必然要写的 `app page NOT loaded in 60s`（看门狗就等在 `loaded.wait`）与
   `GUI loop exited`；即 GIL 被卡在原生调用的线程占死、或进程已死。这解释了"白屏窗还在但
   无响应、退不掉"，也把"关窗后残留"定性为**该冻结进程本身**（其自愈链 render-hang.flag →
   安全模式 → 浏览器兜底全在同一进程里，GIL 被占死时一行都跑不到）。
3. **次因：`config.json` 写入的 Windows 共享冲突（真实但非白屏因）。**
   `save_local_config` 固定 tmp 名 + `os.replace`，撞瞬时句柄（杀软扫描/他实例并发写）即
   `WinError 32` → `check-auth` 500 一次（前端 `useAuthHeal` 自愈，用户可见但业务未断）。
   该 500 发生在**第一次**运行（uvicorn.log:12，PID 3188/端口 18768 段），第二次运行没有
   check-auth、全 200——原"白屏＝鉴权 500"的归因不成立。
4. **判据缺口**：uvicorn access 日志无时间戳（白屏期间后端还在不在服务判读不了）；看门狗
   `loaded.wait(60)` 期间一声不吭；进程级冻结时 Python 层任何自述都写不出（需要 C 层看门狗）。

## What Changes

- **js_api 暴露面契约（根因修）**：窗口引用改 `_window_ref`（pywebview 只跳过 `_` 前缀）；
  补**运行期守卫测试**（`dir(bridge)` 公开成员必须全部可调用）＋**打包 CI 静态门禁**
  （AST 检查 `NativeBridge` 类体与模块级 `bridge.<attr>=` 不许有非下划线属性）。
- **进程退出硬化**：`webview.start()` 返回后 → 有界优雅收尾（`uvicorn.Config`+`Server` 留句柄，
  置 `should_exit`，等线程回收 ≤3s）→ 无论成败 `os._exit(0)`：pywebview 的注入/DOM/bridge
  回调线程**都是非 daemon**（util.py:243/303/335），一旦卡住解释器退出会 join 它们 → 进程残留
  并长期占着数据目录句柄。SQLite 是 WAL、日志逐行 flush，强退不会写坏库（代价面＝在途请求）。
  **明确边界**：只覆盖"GUI 循环已退出"这一支；GIL 被原生调用占死的冻结形态它救不了
  （Timer 也要 GIL）。
- **卡死判据三件**：①uvicorn formatter 加 `%(asctime)s`；②装载看门狗在 `loaded.wait` 期间每
  10s 落一行心跳（不再死等 60 秒无输出）；③`faulthandler.dump_traceback_later(60, repeat)` 到
  `<运行目录>/hang-dump.txt`（C 层定时器，GIL 被占死仍能落盘全部线程栈），**装载成功后取消**，
  避免长会话无谓写盘。
- **config.json 写入韧性**：唯一 tmp 名（pid＋随机串）＋进程内写锁＋`PermissionError` 短退避
  重试（6 次 ≈0.75s）＋每次重试留 warn；**仍抛出**（重试后仍失败＝真故障，静默吞掉会造成
  "文件与内存缓存都不更新却报成功"的状态丢失，比一次可自愈的 500 难查得多）。
- **锁版本**：`pywebview>=5.4.1` → `pywebview==6.2.1`——本修法依赖"只跳 `_` 前缀名"这一
  **未文档化**的实现细节，浮动版本会让行为门禁失真。
- **WebView2 子树随应用退出（Windows Job Object）**：建 `KILL_ON_JOB_CLOSE` job 并把本进程拉起的
  `msedgewebview2.exe` 纳入（Toolhelp32 枚举，建窗后＋装载后两拍）；**刻意不把壳进程自身放入
  job**——自愈重启的孩子是普通子进程不能被误杀，且嵌套 job 下 `CREATE_BREAKAWAY_FROM_JOB` 不可控。
  效果：正常退出／`os._exit`／任务管理器强杀／崩溃，OS 都会把 job 内进程一并收掉（用户口径：
  关闭＝不留任何我们拉起的进程）。非 Windows 静默 no-op，失败降级记日志。
- **兜底页语义明示**：浏览器兜底页不属于"我们拉起的进程"（不结束用户浏览器），但错误页与超时
  提示 SHALL 写明"该页面依赖本程序，关闭后不可用"——各层语义与用户理解对齐。

- **不做（记录理由，另轮评估）**：
  - **单实例互斥**：日志里无任何双实例并发证据、与本次故障无关；但它是**数据安全项**——`PUT
    /chapters/{ref}/prose` 是无 If-Match 的 last-write-wins 自动保存，双实例会真丢稿，且我们
    "清陈旧 port.json"会删掉另一个活实例的 port.json。形态须含"唤醒已有窗口"，另立 change。
  - **bridge 方法源校验**（窗口被导到远端页面时 `pick_folder/open_folder/default_dirs` 归那个源
    所有）：安全加固，另轮。
  - **前端首屏自检卡**（后端冻结时白屏无任何触达用户的提示；渲染进程是独立进程、JS 还活着）：
    另轮。
  - **middleware 读 config.json 与 service 缓存双口径合并**（`auth_local/middleware.py:11-24`
    每请求无缓存开文件）：动 auth 面、收益小于风险，本批只做写入侧。
  - **`save_local_config` 挪 `run_in_threadpool`**：重试 sleep 会占用事件循环 ≤0.75s（量级可接受；
    首启 `generate_pc_hash` 跑 PowerShell 属同族存量问题），另轮。

## Capabilities

### New Capabilities

- `local-config-store`: C端 本地配置文件（`config.json`）的原子写与占用/并发韧性。

### Modified Capabilities

- `client-shell-startup`: 追加三条——js_api 暴露面契约（公开面只许方法）、进程退出与强制收尾、
  卡死判据（时间戳/看门狗心跳/C 层线程栈 dump）。

## Impact

- `client/packaging/build/pywebview_app.py`：`_window_ref` 改名＋注释、`uvicorn.Config/Server`
  留句柄＋`stop_server_gracefully()`、`main()` 末尾强退收尾、`arm/cancel_hang_dump()`、
  看门狗切片心跳、uvicorn formatter 加时间戳。
- `client/backend/auth_local/service.py`：`save_local_config` 唯一 tmp＋写锁＋重试＋warn。
- `client/packaging/build/requirements.txt`：pywebview 钉 `==6.2.1`。
- 新增 `client/packaging/build/check_bridge_surface.py`（AST 门禁）＋
  `.github/workflows/client-package.yml` 在打包入口 lint 步骤后串联它。
- 测试：`client/backend/tests/test_packaging_shell_startup.py`（守卫＋心跳＋收尾顺序＋
  faulthandler 装卸）、新增 `client/backend/tests/test_auth_local_config_write.py`（重试/失败清理/
  唯一 tmp）。
- 用户侧复验：换包后第二次启动不再白屏；关窗后任务管理器无 `AwesomeNovel.exe` 残留；
  `<运行目录>/startup.log` 出现装载心跳行、`hang-dump.txt` 仅在异常时留有内容。
