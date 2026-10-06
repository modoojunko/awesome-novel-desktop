# Tasks: c-shell-hang-hardening

## 0. 现场判定（已完成，证据在三份日志里）

- [x] 0.1 根因定位：`NativeBridge.window_ref` 公开属性 → pywebview `get_functions` 递归遍历原生
      窗口树（util.py:190/193/203-206 只跳 `_` 前缀；`Window` 无 `_serializable` 标记）→ 跨线程
      COM 报错 + 递归超限；**死因是遍历里某次取值阻塞**（异常分支也会 `loaded.set()`，util.py:236-238）
- [x] 0.2 更重观察：run 2 缺 `loaded event fired` 之外，还缺 20:21:44 必然出现的
      `app page NOT loaded in 60s` 与 `GUI loop exited` ⇒ 整进程停摆（GIL 被原生调用占死/已死）
- [x] 0.3 500 归属纠正：WinError 32 发生在**第一次**运行（uvicorn.log:12，PID 3188/端口 18768 段），
      第二次全 200 且无 check-auth ⇒ "鉴权 500 致白屏"不成立
- [x] 0.4 双视角独立复核（架构师＋代码审查）：核心判定成立；纠正"成百上千条错误"（实为 35 行）、
      "刷错误致 loaded 不置位"（因果不成立）两处口径；补出时间戳/心跳/faulthandler 三件判据

## 1. js_api 暴露面（根因修）

- [x] 1.1 `NativeBridge._window_ref` 改名＋类注释写明"下划线不是风格问题"（pywebview 只跳 `_` 前缀）
- [x] 1.2 运行期守卫测试：`dir(bridge)` 公开成员必须全部可调用（该测在 HEAD 上必红）
- [x] 1.3 打包 CI 静态门禁 `client/packaging/build/check_bridge_surface.py`（AST：类体与模块级
      `bridge.<attr>=` 不许非下划线属性）＋串进 `client-package.yml` 的打包入口 lint 步骤
- [x] 1.4 锁版本：`pywebview>=5.4.1` → `==6.2.1`（契约依赖未文档化的实现细节）

## 2. 进程退出硬化

- [x] 2.1 `uvicorn.Config`+`Server` 留模块级句柄；`stop_server_gracefully(timeout=3)`（置
      `should_exit`＋等 `_server_exited`）
- [x] 2.2 `main()` 末尾：`GUI loop exited` → 有界收尾 → 收尾日志（graceful=…）→ `os._exit(0)`
- [x] 2.3 边界写进注释：只覆盖"GUI 循环已退出"；GIL 冻结形态（Timer 也跑不到）不在担保内
- [x] 2.4 **WebView2 子树收口（Job Object）**：建 `KILL_ON_JOB_CLOSE` job 并把本进程拉起的
      `msedgewebview2.exe` 纳入（Toolhelp32 枚举，两拍：建窗后＋装载后）；**刻意不入 job 自身**
      （不误伤自愈重启的孩子、不依赖 breakaway 在嵌套 job 下的不确定性）；非 Windows 静默 no-op、
      任一 API 失败留日志降级——"关闭＝我们拉起的进程全没"从"正常路径尽力"升级为 OS 级保证
- [x] 2.5 兜底页文案：错误页＋超时提示明示"浏览器里打开的页面依赖本程序，关闭后不可用"
      （用户口径：兜底页不是我们的进程、不关它，但要讲清它随应用失效）

## 3. 卡死判据三件

- [x] 3.1 uvicorn formatter 加 `%(asctime)s`
- [x] 3.2 装载看门狗切片等待：每 10s 落一行 `app page still loading… {n}s/{上限}s`
- [x] 3.3 `arm_hang_dump()`/`cancel_hang_dump()`：`faulthandler.dump_traceback_later(60, repeat)` →
      `<运行目录>/hang-dump.txt`；装载成功后取消；退出前取消（flush＋关文件）

## 4. config.json 写入韧性

- [x] 4.1 唯一 tmp 名（pid＋随机串）＋进程内写锁＋`PermissionError` 6 次退避重试（≈0.75s）
- [x] 4.2 每次重试失败留 warn（尝试次数/错误/tmp 路径）；失败清理自身 tmp；缓存只在成功后更新
- [x] 4.3 语义保持**抛出**（评审裁断：吞掉＝状态丢失更难查；抛出＝有界自愈，前端 useAuthHeal 20s×3 重试）

## 5. 测试与验收

- [x] 5.1 shell 测试：公开面守卫、看门狗心跳、退出收尾顺序（graceful＋强退）、faulthandler 装卸
- [x] 5.2 新测试文件 `tests/test_auth_local_config_write.py`：瞬态重试成功、持续占用报错＋无 tmp 残件、唯一 tmp 名
- [x] 5.3 `ruff`（含打包 CI 同款 F821）改动文件零新增；`openspec validate --strict` 通过
- [x] 5.4 全量 `client/backend` pytest：**1967 passed / 1 skipped / 0 failed**，**连跑 4 次全绿**。
      途中揪出并修掉**存量 flaky**：`test_up12_retention_and_cleanup` 原用 `time.sleep(0.01)` 造序，
      而三件套 mtime 取 `int(max(主,-wal,-shm))`（**整秒**，schema_version.py:172）——全量跑批下
      同秒并列 ⇒ "保留最近 2 份"变任意序（判据：pristine main 全量 4 连跑红 1 次、本分支红 2/2）；
      改用例显式造秒级递增 mtime（主＋sidecar 一起 utime，再取 stamp）
- [ ] 5.5 提交＋PR；Windows 侧真机复验（用户）：
      ① 第二次启动不白屏；② 关窗后任务管理器无 `AwesomeNovel.exe` 且**无我们拉起的
      `msedgewebview2.exe`**；③ 从任务管理器强杀后再看一遍同样无残留（Job Object 的判据场景）；
      ④ `startup.log` 出现 `webview containment…纳入 N 个`；⑤ `hang-dump.txt` 仅异常时有内容

## 5b. 评审整改（review-agent，2026-10-06 第三轮）

- [x] **P2｜ctypes 句柄管线**：为 `CreateToolhelp32Snapshot` / `CreateJobObjectW` / `OpenProcess`
      显式声明 `restype = wintypes.HANDLE`（及入参 `argtypes`，含 `Process32FirstW/NextW` /
      `SetInformationJobObject` / `AssignProcessToJobObject` / `CloseHandle`）。实测过的两个后果：
      ① 默认 `c_int` 让失败返回的 `-1` 与 `c_void_p(-1).value`（2^64-1）**恒不相等** ⇒ 567 行那条
      失败判据是死代码（枚举失败被当成"0 个子进程"的正常路径）；② 截断句柄回传 CloseHandle 等。
      同步把判据改成 `if not snap or snap == c_void_p(-1).value`（0＝NULL、-1＝INVALID_HANDLE_VALUE）。
- [x] **P2 附带｜日志分段**：`job 已建` / `子进程 N 个，打开 M 个，纳入 K 个` / "枚举到却 0 纳入"
      三条分开写——否则真机验收里"这台机器没有 WebView2 子进程"与"机制静默失效"长得一模一样
      （并把 `k32` 取用挪到确有子进程时，空枚举不再碰 windll）。
- [x] **P3｜用例可移植**：`noop_off_windows` 加 `skipif(win32)`（真 Windows 上该调用会真实建 job，
      断言前提不成立）；`degrades_on_failure` 改为 monkeypatch 注入失败，不再依赖"非 Windows 没有
      `ctypes.windll`"这一平台差异（原写法在真 Windows 上必红）。新增 `logs_are_segmented` 用例。

## 6. 记录在案、不在本批（另轮评估）

- [ ] 6.1 单实例互斥（**数据安全项**：`PUT /chapters/{ref}/prose` 无 If-Match＝last-write-wins，
      双实例真丢稿；且"清陈旧 port.json"会删掉另一个活实例的 port.json）——形态须含"唤醒已有窗口"
- [ ] 6.2 bridge 方法源校验（窗口被导到远端页面时 `pick_folder/open_folder/default_dirs` 归那个源）
- [ ] 6.3 前端首屏自检卡（后端冻结时白屏无提示；渲染进程是独立进程、JS 尚活）
- [ ] 6.4 `auth_local/middleware.py` 无缓存读 config 与 service 缓存双口径合并
- [ ] 6.5 `save_local_config` 挪 `run_in_threadpool`（重试 sleep 占事件循环 ≤0.75s）
- [ ] 6.6 `--smoke` 加不了"pywebview.log 零风暴"断言（无头跑没有窗口/注入）——故改用运行期守卫＋AST 门禁
