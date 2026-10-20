# C端 重启更新等尸 runner（c-silent-relaunch-runner）

## Why

v0.35→0.36 生产真机事故（2026-10-20）：用户点「重启更新」后，弹回的窗口**仍是旧版**
（右下角 0.35、就绪横幅复活），手动重开一次才到 0.36。定诊：

- 右下角版本号＝本地后端自报（构建期烘焙 `CLIENT_VERSION`）⇒ 显示 0.35 即旧 exe，
  不可辩；
- Inno `[Run]` 自动拉起严格在文件替换**之后**执行 ⇒ 弹回的旧窗口不可能是「装完自动
  拉起」，即安装器尚未换掉 exe 时就有窗口把用户接回旧版；
- 旧实现是退出链直接 `Popen` 安装器后立刻 `os._exit` 放锁——「Inno 初始化比进程死亡
  慢」是**赌注**（残余面：杀软首扫、残留实例占 exe ⇒ 安装器静默重试 4 次后中止）。
  而 lab 真机 V-1 验收形态本来就是「应用完全退出后」跑安装器——「等退出」这一步
  生产链上没人干。

用户最终能到 0.36，是弹回的旧窗口退出时 pending 重试（attempt=2，不受 TTL 拦）把包
装上的——链条「最终一致」，但「点了重启→弹回旧版当没事」违背「完成后自动重新打开」
的用户契约。

## What Changes

- **退出链静默安装改走等尸 runner**：全部闸门通过后，安装执行交给一个**位于安装目录
  之外**的 detached PowerShell 执行体——先等本应用进程完全退出（`Wait-Process`，有界
  60 秒），再**同步**执行静默安装器（argv 不变，含 `/AUTOLAUNCH=1`）。
- **结构性保证**：Inno 的自动拉起只在安装成功后发生 ⇒ 任何被拉起的窗口必然是新版本；
  安装未成功＝不拉起（旧版继续跑＋pending 重试＋手动链），绝不弹回旧版当没事。
- **安装执行留痕**：执行体把等待段结果（`wait_ms`／`parent_alive_after_wait`）与安装器
  退出码、耗时写入数据目录更新暂存区的 `installer-runner.log`——「弹回旧版」类时序
  事故事后判读的第一分辨点；「暂不」清理保留该文件。
- **实现要点**：脚本经 `-EncodedCommand`（UTF-16LE base64）下发——路径空格/中文/撇号
  零转义面；`powershell.exe` 取 WINDIR 全路径防 PATH 劫持（Win10/11 系统自带）。

**非目标**：不后台预装（Windows 锁运行中程序文件；A/B 双目录需拆「安装目录＝数据目录」
铁律，独立立项再议）；macOS 自动链；增量包。

## Capabilities

### Modified Capabilities

- `client-auto-update`: 「退出链静默安装」需求改 runner 形态——时序由安装目录外的
  分离执行体接管（等本进程死透→同步安装），新增「安装成功严格先于自动拉起」与
  「安装失败不拉起」保证，及执行留痕要求。

## Impact

- 实现：`client/packaging/build/pywebview_app.py`（`_install_runner_script` /
  `_spawn_install_runner` / `apply_pending_update`）、`client/backend/update_check.py`
  （auto-skip 清理保留 runner 日志）。
- 已合 main＝bca44e13（#903，CI 绿）；本 change 为**回溯建档**——实现先行，spec 补钉。
- 真机验收挂账（随下一发版）：新版点重启→弹回即新版；`installer-runner.log` 出现
  `installer_exit=0`；异常臂（占住 exe）→ 无人拉起、重开后 pending 重试升版。
