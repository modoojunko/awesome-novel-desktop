# C端 更新 runner 无控制台秒退根因修复（c-update-detached-ps-fix）

## Why

2026-10-24 生产真机 0.38→0.39 取证收官（同机第三次同签名事故，前两跳 0.35→0.36 弹旧版、
0.37→0.38 runner 无执行）：点「重启更新」→ 应用退出 → 无新窗。闭环证据链——

1. `startup.log` 有 `installer launched for v0.39 (attempt 1)`＝退出链消费标记、Popen 成功；
2. PowerShell/Operational 在同一秒有事件 40961（引擎初始化）但窗口内零 4104（脚本块执行），
   `installer-runner.log` 与当日 `installer.log` 双双不存在＝**脚本一行都没执行**；
3. 环境侧全排除：唯一 AV＝Windows Defender 且 ASR/检测零事件、AppLocker 休眠、Smart App
   Control 关闭、EncodedCommand 隐藏探针绿；
4. **对照实验定罪**（WMI `Win32_ProcessStartup.CreateFlags` 直通 `dwCreationFlags`，同机同秒
   同脚本只换旗标）：
   - `DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP`（0x208，与 `_spawn_install_runner` 完全一致）
     → 进程创建成功、脚本零执行、日志零行（生产死法逐字复现）；
   - `CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP`（0x08000200）→ 脚本三段留痕全落。

机理：powershell.exe 是控制台子系统程序；`DETACHED_PROCESS` 既不继承控制台（生产用户双击
启动，GUI 应用进程链上没有控制台）又禁止新建，PowerShell 引擎初始化完成后在控制台主机
初始化段静默退出。开发/lab 从控制台启动应用时子进程能攀到祖先控制台，故 V-1 真机验收
从未复现——「lab 绿、生产死」的分野线就是应用启动方式。

**影响面**：v0.37（runner 首随包）起，所有 Windows 用户走「重启更新」按钮的静默安装均
静默失败——自动链从未装上包，用户要么手动装（可能因目录继承坑装错位置），要么停留旧版。
0.40 必须带修复。

与在途 change 的关系：`c-update-fail-safe`（并行会话立项）覆盖失败兜底的大范围加固
（安装前快照/回滚、双 hive 目录继承、快捷方式连续性、Windows CI 真执行），立项时根因未明、
未含旗标修复。本 change 是**根因修复＋最小观测**，先行赶 0.40；fail-safe 的等待 `started`
有界确认/回退、快照、目录与快捷方式项在其上层继续，两者合并归档时以本 change 的
runner 日志契约为准对齐。

## What Changes

- **创建旗标修复（真凶）**：Windows runner 的 Popen 旗标从 `DETACHED_PROCESS|NEW_PROCESS_GROUP`
  改为 `CREATE_NO_WINDOW|NEW_PROCESS_GROUP`。argv（含 `-WindowStyle Hidden`）不变——
  对照实验已实证带 Hidden 的 CREATE_NO_WINDOW 形态可正常执行脚本。
- **runner 首行落痕**：执行体脚本在等待父进程之前先写一行 `started`（时间＋自身 pid＋父 pid），
  结束行（wait_ms/parent_alive_after_wait/installer_exit/install_seconds）格式不变——
  今后任何一层断链都有第一现场，`started` 有无即「执行体是否真的跑过」的第一判据。
- **安装结果回读与失败可见（最小面）**：下次启动的对拍（`_reconcile_pending`）在「标记版本
  ≠ 本机版本且执行日志存在」时回读结束行的 `installer_exit`，连同 `started` 有无一并落
  startup.log 与更新状态诊断字段（后端 `/api/update` 状态 JSON 新增只读字段），失败不再
  「点了重启就没影」。本 change **不新增 UI 组件/弹层**（OS 级 MessageBox 与应用内横幅
  归 c-update-fail-safe）；纯日志与状态字段，无 React 屏改动。
- **spawn 失败回退保底**：PowerShell `Popen` 抛异常（进程创建失败）时回退为直接 detached
  拉起安装器（v0.36 老链形态，Inno 是 GUI 子系统对无控制台免疫，已实证可用），留日志。
  这是**有代价的降级**——失去等尸保证（时序改由安装器自身背书：[Run] 严格装完后拉起），
  仅限执行体无法创建时启用，MUST NOT 复用为常规路径；仅当至少一个执行通道成功派发才
  递增 attempts，双失败不递增、下次退出重试。
- **测试**：旗标断言改钉 `CREATE_NO_WINDOW`（新增）；脚本形状断言增 `started` 首行；
  新增 spawn 失败回退直连的用例；存量 Windows runner 用例全部保绿（现有断言不钉
  creationflags，仅 argv 与脚本形状，无需改钉）。

**非目标**：不改 macOS runner 的换装算法（仅补一行 started 启动留痕）；不做等待
`started` 的有界确认/回退（fail-safe 的执行体确认机制，本 change 只落 `started` 痕）；
不做安装快照/回滚、双 hive 目录继承、快捷方式修复（c-update-fail-safe）；不新增任何
应用内 UI。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `client-auto-update`：「退出链静默安装」的 Windows 平台分派增加三件事——执行体创建旗标
  MUST 使用「无窗口但拥有控制台」的形态（CREATE_NO_WINDOW，禁止 DETACHED_PROCESS）；
  执行体 SHALL 在等待前先落 `started` 痕；Python 侧 spawn 失败 MUST 回退直接拉起安装器。
  启动期对拍增加安装结果回读（执行日志的 installer_exit 与 started 有无）并入诊断面。

## Design Impact

- 受影响端：C端（Windows 桌面壳层代码＋打包测试），不触 S端、不触两端共享设计令牌。
- 受影响屏/弹层：无 React 屏改动、无弹层、无文案入口——全部变化在壳层执行体与日志/
  诊断 JSON。后续若 fail-safe 落 OS 级提示或应用内横幅，届时按 design-language §5/§13
  另行走原型。
- 对象状态：无新增组件形态与语气词。
- 共享段：无。原型先行：不需要（非应用内界面）。
- 设计工件：实现侧自查（无设计工件）。

## Impact

- `client/packaging/build/pywebview_app.py`：`_spawn_install_runner` 旗标＋回退；
  `_install_runner_script` 首行 `started`；`_reconcile_pending` 回读执行日志与
  `installer_exit`、写诊断字段。
- `client/backend/update_check.py`：更新状态公开形状新增只读字段 `last_install_attempt`
  （来源：壳层写入的执行日志对拍结果；无新端点）。
- 测试：`client/backend/tests/test_packaging_shell_apply.py`（旗标/两平台首行/回退/对拍
  回读新增断言与用例）、`client/backend/tests/test_update_check.py`
  （`last_install_attempt` 状态字段三态/缺失/成功消失）。
- 兼容性：不改更新清单载荷、不改 pending 标记既有字段（不新增字段）、不改数据格式；
  macOS 仅补一行启动留痕（换装算法不动），其余平台路径零改动。旧版客户端不受影响
  （修复由新包自带）。
