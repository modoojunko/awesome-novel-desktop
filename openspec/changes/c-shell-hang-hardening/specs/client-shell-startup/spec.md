## ADDED Requirements

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

### Requirement: 壳层关键路径的依赖版本锁定

打包依赖中的 pywebview SHALL 钉死到已验证的具体版本（当前 6.2.1）。理由：js_api 暴露面契约
依赖"只跳过 `_` 前缀名"这一**未文档化**的实现细节，浮动版本会让该契约在升级后静默失效。

#### Scenario: 打包依赖解析到恒定版本
- **WHEN** 打包链安装依赖
- **THEN** 装到的 pywebview 恒为钉死值（当前 6.2.1），不会因解析到新版本而静默改变注入/枚举行为
