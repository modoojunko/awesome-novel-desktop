# 设计：c-update-detached-ps-fix

## 根因与证据（定案，不再开放）

- 死因：`_spawn_install_runner` 用 `DETACHED_PROCESS`（0x8）创建 powershell.exe。
  powershell.exe 属控制台子系统，`DETACHED_PROCESS` 下进程无控制台且不得新建；生产用户
  双击启动应用（GUI 子系统，进程链无控制台）→ 引擎初始化完成（事件 40961）后控制台
  主机初始化失败 → 脚本零执行（零 4104、零日志）→ Inno 从未启动。
- 证据链（2026-10-24 真机）：`installer launched` 日志在、40961 同秒在、零 4104、双日志
  无、Defender/AppLocker/SAC 全排除、EncodedCommand 探针绿；WMI `CreateFlags` 对照实验
  ——0x208 复刻＝创建成功零执行，0x08000200＝全段执行。
- lab 从未复现的原因：lab 从控制台启动应用，执行体能 `AttachConsole` 到祖先控制台。

## 改动设计

### 1. 旗标（真修复）

`_spawn_install_runner`：

```python
flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(
    subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
```

- `CREATE_NO_WINDOW`：进程有隐藏控制台（conhost 在场但不可见），PS 主机初始化正常——
  对照实验 d2 实证脚本全段执行；`-WindowStyle Hidden` 保留（argv 不变，d2 同形态已验证，
  对隐藏控制台调用 ShowWindow 无害）。
- `CREATE_NEW_PROCESS_GROUP` 保留（与父进程 Ctrl 信号组隔离，语义不变）。
- macOS/Linux：Linux 路径零改动；macOS `_install_runner_script_macos` **补一行 started**——
  实况是 `log()` 只在结束行被调用一次、并无首行留痕，spec 的启动痕要求平台中立，故在
  `log()` 定义后、等待循环前补 `log "started (runner_pid=$$ parent=$UPD_PARENT)"`（一行
  bash，与 Windows 同串 `runner: started`，跨平台「started 有无＝执行体是否跑过」判据
  统一）。

### 2. runner 脚本首行落痕

`_install_runner_script` 生成的脚本在 **`$log = …` 赋值之后、`$w0 = Get-Date` 之前**插入
（started 行引用 `$log` 与 `$parent`，插到变量块之前会求得空串、`Add-Content` 在
`SilentlyContinue` 下静默失败——started 恒缺，恰好废掉这条第一判据）：

```
Add-Content -Path $log -Value ("{0} runner: started (runner_pid={1} parent={2})" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $PID, $parent) -ErrorAction SilentlyContinue
```

- 结束行格式**不变**（`{ts} runner: wait_ms=… parent_alive_after_wait=… installer_exit=…
  install_seconds=…`）——存量断言与事故判读口径不动。
- `$PID` 是 PowerShell 内置只读变量（无需定义）。
- 日志写入仍全程 `-ErrorAction SilentlyContinue`：执行日志写不出去不阻断安装主链。
- macOS 侧见 §1（一行 `log "started …"`）；回读解析按平台行文取安装结果：
  `installer_exit=`（Windows）或 `install_ok=`（macOS，1→0／0→1 映射退出码），
  `runner: started` 两平台同串。

### 3. spawn 失败回退直连

`_spawn_install_runner` 内 `subprocess.Popen(...)` 包 try：`OSError`（含
FileNotFoundError）时回退：

```python
subprocess.Popen(installer_argv, close_fds=True, creationflags=DETACHED)
```

- **回退是有代价的降级，仅在执行体无法创建时启用**：直接拉起＝失去等尸保证（回到
  #903 之前的竞速形态，父进程 os._exit 与 Inno 初始化赛跑）。可接受的依据：窗口仅
  毫秒级（Popen 返回到 _force_exit）＋Inno 对文件锁自带重试＋安装器 [Run] 严格在装完
  后才拉起（「被拉起的必是新版本」仍由安装器自身背书）＋v0.36 前代链同形态在本机
  实证成功。DETACHED 对 Inno 安全（GUI 子系统；对照实验证明 DETACHED 只杀控制台
  子系统程序）。此降级 MUST NOT 被复用为常规路径。
- 回退动作落 startup.log（`auto-update: runner spawn failed, fallback to direct installer`）；
  异常不再原样上抛改为主链继续。
- **attempts 记账语义**：仅当至少一个执行通道（runner 或直连）成功派发才递增 attempts；
  两者都抛异常＝不递增，pending 留给下次退出重试（与现有 spawn 失败语义一致——
  环境性故障不烧重试预算）。
- 说明边界：Popen 成功但脚本零执行（本次生产死法）在 Python 侧不可同步探测——那半边
  由 `started` 痕＋启动期回读补观测，有界等待确认/二次回退归 c-update-fail-safe。

### 4. 安装结果回读与失败可见（最小面）

`_reconcile_pending` 的「标记版本 ≠ 本机版本」分支扩展：

- 回读执行日志文本：找 `runner: started`（启动痕）与 `installer_exit=`（结束行；macOS
  按 §2 的 `install_ok=` 映射）。执行日志是**追加语义**（Windows `Add-Content`／macOS
  `>>`，attempts 上限 2 ⇒ 日志可含两次尝试的行），匹配 MUST 取**最后一次**出现（或按
  尝试分段取末段）——首次匹配会把上一次尝试的 started 张冠李戴到最近一次（如 attempt 1
  有痕、attempt 2 脚本又死在 started 之前）。
- 产出三态：`runner_started + exit=<n>`（执行体跑了，退出码可见）/
  `runner_started`（跑了但没跑完）/ `no runner log`（执行体从未运行）——均以**最近一次
  尝试**为准。
- 落两处：startup.log 一行（`auto-update: last install attempt for v{version}: …`）＋
  更新状态诊断字段。
- 状态字段定名 `last_install_attempt`：壳层将对拍结果写入数据目录
  （`data/updates/last-install-attempt.json`，单 JSON：version/attempts/
  runner_started/installer_exit/recorded_at——attempts 自 pending 带出：`≥1`＋无
  started＝「派发未执行」（本 change 针对的死法），`==0`＝「未派发」（TTL 过期/未走到
  退出链），排障一眼分诊）；`update_check.py` 的状态聚合读取该文件并入公开状态的
  `last_install_attempt` 只读字段（无新端点；**文件缺失＝键不出现，非 null 占位**——
  `test_update_check.py:54` 等存量全等断言 `assert st == {…}` 在 null 占位下会炸）。
- **写入须原子**：tmp＋rename 落盘（对齐 pending.json 的 `.tmp` 惯例），防后端读到
  半截 JSON。
- **「暂不」清扫语义**：跳过更新的清理白名单（applied.json/installer.log/
  installer-runner.log）不含本文件，用户点「暂不」会把它一并扫掉——语义可接受
  （记录随该版本一起被放弃），登记防将来当 bug 误报。
- **成功路径清理**：reconcile 的版本匹配分支（写 applied＋清 pending）SHALL 同步删除
  `last-install-attempt.json`——升级已成功，过期失败记录不得常驻诊断面误报。
- 不新增 UI 组件：`last_install_attempt` 字段先供诊断面/后续 fail-safe 的横幅消费。

## 测试设计

- `test_packaging_shell_apply.py`：
  - 新增旗标钉：Popen kwargs 的 `creationflags` 含 `CREATE_NO_WINDOW` 位、不含
    `DETACHED_PROCESS` 位（非 Windows 平台跳过语义按现有平台桩口径，直接断言常量位
    组合即可，无需真 Windows）。
  - 脚本形状：解码脚本含 `runner: started` 首行（在 `Wait-Process` 之前）。
  - 新增 `test_runner_spawn_failure_falls_back_to_direct_installer`：Popen 首抛
    OSError、第二次成功；断言第二次 Popen 的 argv[0]＝暂存安装器路径、flags 含
    DETACHED 位、日志含 fallback 行、pending attempts 记账仍递增。
  - 存量用例（argv/脚本形状/attempts）保绿不改钉。
- `test_packaging_shell_apply.py`：对拍回读——标记版本≠本机版本＋执行日志形态（三态＋
  append 两次尝试取末段）→ startup.log 行＋`last-install-attempt.json` 三态正确。
- `test_update_check.py`：状态聚合读取该文件并入 `last_install_attempt`（三态＋缺失＋
  成功消失）。
- 红线：macOS **存量断言不改钉**（已核实全部为子串断言、不撞新增行——含
  `installer-runner.log` not in script 的零转义面钉：started 行走 `$$`/`$UPD_PARENT`
  与 env，日志路径字面量仍不进脚本文本）；`pending.json` 字段集不变。

## 风险与回滚

- 风险最低项是旗标：唯一行为变化＝执行体多了个隐形控制台；对安装器（GUI 子系统）无感。
- 回退直连只在 spawn 抛异常时触发，正常机器路径不变。
- 全量回滚＝revert 单 commit，无数据/格式迁移。
