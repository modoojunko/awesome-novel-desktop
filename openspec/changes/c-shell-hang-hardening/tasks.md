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
- [x] 5.4 全量 `client/backend` pytest：**1963 passed / 1 skipped / 0 failed**（68s；与 main 基线零新增红）
- [ ] 5.5 提交＋PR；Windows 侧真机复验（用户）：第二次启动不白屏、关窗无残留进程、
      `hang-dump.txt` 仅异常时有内容

## 6. 记录在案、不在本批（另轮评估）

- [ ] 6.1 单实例互斥（**数据安全项**：`PUT /chapters/{ref}/prose` 无 If-Match＝last-write-wins，
      双实例真丢稿；且"清陈旧 port.json"会删掉另一个活实例的 port.json）——形态须含"唤醒已有窗口"
- [ ] 6.2 bridge 方法源校验（窗口被导到远端页面时 `pick_folder/open_folder/default_dirs` 归那个源）
- [ ] 6.3 前端首屏自检卡（后端冻结时白屏无提示；渲染进程是独立进程、JS 尚活）
- [ ] 6.4 `auth_local/middleware.py` 无缓存读 config 与 service 缓存双口径合并
- [ ] 6.5 `save_local_config` 挪 `run_in_threadpool`（重试 sleep 占事件循环 ≤0.75s）
- [ ] 6.6 `--smoke` 加不了"pywebview.log 零风暴"断言（无头跑没有窗口/注入）——故改用运行期守卫＋AST 门禁
