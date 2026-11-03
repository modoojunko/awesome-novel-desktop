# c-update-fail-safe · 设计

## Context

见 `proposal.md` 的 Why。当前实现的关键事实：

- `client/packaging/build/pywebview_app.py` 的 `apply_pending_update` 在退出链尾部
  spawn detached PowerShell runner，然后立刻 `_force_exit`；Python 侧**不等待、不检查**
  执行体是否真的开始。
- runner 脚本（`_install_runner_script`）只在安装器退出后写一行 `installer-runner.log`；
  脚本开头没有落痕，`Add-Content` 也不在 `finally` 里。PowerShell 被拦截或脚本在
  `Wait-Process` 阶段终止时，磁盘上没有任何“执行体已运行”的证据。
- 本次真机日志事实：runner 被拉起但 `installer-runner.log` 与 `installer.log` 均缺失，
  安装器未执行；重装前旧 `AwesomeNovel.exe` 与 `data\` 仍在，桌面图标失效是陈旧快捷
  方式而非安装器删文件。Inno 的“删目标再改名”风险仍在，作为失败兜底的设计对象。
- Inno 的 `[Files]` 替换是「写临时文件 → 删除目标 → 改名」；删除成功后改名失败会中止
  安装，且 `/SUPPRESSMSGBOXES` 会把致命错误框静默掉。若此时旧 exe 已删除，用户就得到
  一个“无程序可启动”的安装。
- `installer.iss` 的 `UsePreviousAppDir=yes` 由 Inno 的 `FindPreviousData` 实现，只读
  `InstallModeRootKey`（admin→HKLM，per-user→HKCU）。自动链一直 `/CURRENTUSER`，
  手动双击走 admin，跨模式时看不到旧路径，回落到 `DefaultDirName`。
- `db-generation` 的候选扫描只覆盖当前数据目录（既定裁定），所以换目录后空书架、无
  迁移卡不是 bug，而是该裁定的可预期结果；本 change 不扩扫描范围，改为在安装期保持
  目录连续。

## Goals / Non-Goals

**Goals:**

- 让“执行体是否真的开始跑”成为可判定事实；未运行时自动回退直接安装，不再出现
  “日志写了 launched、实际什么都没发生”。
- 让自动更新失败**可见、可恢复**：重试、快照回滚、至少保证旧版可启动、留下用户看得懂
  的失败说明与手动出口。
- 让手动重装/修复安装默认沿用最近一次安装目录，不再因安装模式切换落到默认目录。
- 让桌面快捷方式在更新后仍指向当前程序。
- 用 Windows CI 真执行 runner 与 stub 安装器，补上 archived c-silent-relaunch-runner
  明确记录过但未覆盖的真机缺口。

**Non-Goals:**

- 不做 A/B 双目录安装或启动器切换（archived c-silent-relaunch-runner 的非目标）。
- 不改变数据目录随程序目录走的便携式裁定；不扩迁移候选扫描范围。
- 不改 macOS 的 DMG 换装算法；只补执行开始/终局留痕。
- 不改变更新清单载荷、pending 标记既有字段的语义、数据格式。
- 不实现“自动修复用户已删除的桌面图标”；只修复已存在的快捷方式，缺失时可创建
  per-user 快捷方式（spec 的 MAY）。

## Decisions

1. **执行体三段留痕 + 出口侧有界等待**

   runner 脚本结构改为：

   ```
   $ErrorActionPreference = 'Continue'
   Write-ExecutionLog 'started pid=...'
   try {
     Wait-Process ...（有界）
     Write-ExecutionLog 'installer_start ...'
     & installer ...
   } catch { ... }
   finally {
     Write-ExecutionLog "finished status=... installer_exit=... ..."
   }
   ```

   - `started` 必须在任何可能阻塞的步骤（`Wait-Process`）之前写；`finally` 保证异常
     路径也有终局记录。
   - Python 侧在 `Popen` 前先写 `runner_spawned` 日志行，`Popen` 后以 100ms 节奏轮询
     执行日志最多 `RUNNER_START_TIMEOUT`（默认 3 秒），看到 `started` 才 `_force_exit`。
   - 选 3 秒而不是等 `installer_start`：PowerShell 冷启动 ~1 秒；`Wait-Process` 最长
     60 秒不能拖住关窗。只要确认脚本开始执行，后续失败由 runner 自己记录/提示。
   - 备选：让 Python 一直等到 `installer_start`——否决，会把关窗拖到 60 秒，违背
     “点重启秒级关窗”的既有契约。

2. **未启动即回退直接安装**

   有界等待内没有 `started` ⇒ 视为执行体未运行（典型：安全软件/ASR/AppLocker 拦
   `powershell.exe -EncodedCommand`），退出链直接以 `DETACHED_PROCESS` 拉起安装器
   （c-silent-relaunch-runner 之前的形态），参数与闸门完全一致，并写
   `runner_fallback=direct` 日志。

   - 这重新引入了 #903 修掉的“安装器可能跑在活进程上”的竞态，但只在 runner 已被证明
     不可用的环境发生；比“什么都不发生”严格更好。Inno 自身的 4 次重试兜住残余锁窗。
   - 备选：用 `cmd /c start` 或 `wscript` 作为第二 runner——否决，仍然依赖被拦的
     shell 层，不如直接 CreateProcess 安装器。

3. **安装前快照 + 结果验收 + 有界重试 + 可见失败**

   - 快照位置：`%LOCALAPPDATA%\AwesomeNovel\rollback\<from_version>\`（安装目录之外，
     与数据目录分离）。快照只复制程序树（exe、`_internal`、许可文本等），**排除**
     `data\`、`logs\` 与运行时文件，避免把书稿复制一遍。
   - 快照方式：第一版用 `robocopy /E` 完整复制（简单、可验证）；检查可用空间 ≥ 程序树
     大小 × 1.2，不足则放弃本次静默安装并给出可见提示。硬链接快照作为后续优化项，
     不阻塞本 change。
   - 验收：安装器退出码为 0 **且** `{app}\AwesomeNovel.exe` 存在（可启动性以
     `Test-Path` + 文件大小 > 0 判定；不在 runner 里启动 GUI 验证）。
   - 重试：失败后重跑安装器一次。仍失败则 `robocopy snapshot {app} /MIR`（排除
     `data\`、`logs\`）恢复程序树，再把失败写进执行日志与用户可见说明。
   - 可见失败：优先 `System.Windows.Forms.MessageBox`（标题/正文含版本、失败阶段、
     数据目录、官网下载地址；Yes/No＝打开数据目录/关闭），同时写
     `%USERPROFILE%\Desktop\爱小说更新失败-<timestamp>.txt` 作为持久件。runner 在
     `finally` 里调用，保证异常路径也能提示。CI/无交互环境用
     `AINOVEL_RUNNER_HEADLESS=1` 跳过 MessageBox，只写文件。
   - 快照清理：不在安装器退出后立刻删；由新版首次启动的 `_reconcile_pending` 在
     `pending.version == current` 时清理 `rollback/<version>`。这样“装完但新版没起来”
     时快照仍在，下次退出链还能用。

4. **安装目录连续性：指针优先，双 hive 兜底**

   应用在 `main()` 取到 `get_install_dir()` 后写
   `%LOCALAPPDATA%\AwesomeNovel\install_dir.txt`（覆盖式，内容为绝对路径）。安装器
   `[Code]` 的目录预填逻辑：

   1. 读指针文件；目录存在且可写 → 用。
   2. 否则读 HKCU 与 HKLM（`Software\Microsoft\Windows\CurrentVersion\Uninstall` 及
      `WOW6432Node` 视图）里同一 AppId 的 `Inno Setup: App Path` / `InstallLocation`；
      取存在且可写的候选。
   3. 都不可用 → `{localappdata}\Programs\AwesomeNovel`。

   实现上保留 `UsePreviousAppDir=yes` 处理同 hive 场景；在 `InitializeWizard` /
   `CurPageChanged(wpSelectDir)` 用上述结果覆盖 `WizardForm.DirEdit.Text`。自动链的
   `/DIR` 明确给出时以 `/DIR` 为准（Inno 的 command-line 优先级），不会被覆盖逻辑
   改写。指针文件写失败不影响启动，只留日志。

   - 备选：改 `DefaultDirName={code:...}` 完全接管——也能做，但会改变 `UsePreviousAppDir`
     的既有语义，回归面更大；先用“覆盖 DirEdit”的最小改动，Windows stub 测试验证
     静默/交互两条路径。

5. **快捷方式连续性**

   - `[Icons]` 的桌面项从 `{commondesktop}` 改为 `{autodesktop}`（Inno 按安装模式解析
     到公用/用户桌面），解决 per-user 静默安装写不了公用桌面的老问题。
   - 自动更新参数把 `/MERGETASKS=!desktopicon` 改为不强制取消；若用户历史上取消过该
     任务（`UsePreviousTasks` 保留取消状态），安装器 `[Code]` 在 `ssPostInstall` 检查
     `{autodesktop}` 下已存在的 `.lnk`，存在则用 `WScript.Shell` 更新其 TargetPath；
     不存在则不创建（尊重用户选择）。
   - 应用侧不新增快捷方式修复代码，避免重复职责；若后续发现安装器路径无法覆盖，再
     在 shell 启动段补一个幂等修复。

6. **Windows CI 真执行**

   在 `client-package.yml` 的 Windows job 增加一个 `runner self-test` 步骤（或独立
   workflow）：

   - 用一段 PowerShell 生成 runner 脚本（直接调用 `_install_runner_script`，或复制
     其模板），把安装器换成一个假的 `.cmd`/`.exe`：写 `installer-ran.txt` 后按环境
     变量返回 0/1，并可模拟“删除目标 exe”。
   - 断言：日志顺序 `started → installer_start → finished`；exit code 透传；失败重试
     ≤1；快照恢复后假 exe 存在；headless 失败说明文件存在。
   - 用 `Start-Process` 模拟“PowerShell 不可用”臂：把 `WINDIR` 指向一个没有
     powershell.exe 的临时目录，断言 Python 侧走 direct fallback 并留日志。
   - stub 安装器目录继承：用 Inno 编一个 2MB 的 stub（`UsePreviousAppDir` + 同一段
     `[Code]`），先 per-user 装到临时目录，再 admin 模式不带 `/DIR` 跑第二遍，断言
     `installer.log` 的第二遍安装目录仍是第一遍目录。若 CI 的 Inno/权限限制使该臂
     不可行，降级为真机验收项并在 tasks 里注明。

## Risks / Trade-offs

- **快照体积/耗时**：完整复制程序树可能数百 MB，首次更新明显变慢。缓解：排除
  `data`/`logs`；空间预检不足则跳过静默安装；后续可换硬链接快照。
- **MessageBox 在无交互会话不可见**：RDP 断开/服务会话下用户看不到。缓解：同时写
  桌面文本件；CI 用 headless 变量。
- **direct fallback 重新引入竞态**：只在 runner 未启动时使用；Inno 4 次重试兜底；
  失败仍走快照/可见提示。
- **跨 hive 目录候选可能选到旧安装**：指针是应用每次启动写入的，优先级最高；registry
  候选要求目录存在且可写；用户仍可在目录页改。
- **`{autodesktop}` 改变既有图标位置**：admin 装仍落公用桌面，per-user 落用户桌面，
  符合 Inno 语义；需要在 Windows 真机确认旧图标不被重复创建。
- **CI 无交互桌面**：MessageBox/安装器 GUI 行为无法完全模拟；stub 测试覆盖逻辑分支，
  真机验收补最终判据。
- **PowerShell 脚本复杂度上升**：快照/恢复/重试都在 PS 里；用 `try/finally` + 明确的
  退出码，CI 真执行；失败时 Python 的 direct fallback 仍是最后防线。

## Migration Plan

- 代码随下一发版（0.39）发布；无数据迁移、无清单载荷变更。
- 发布顺序：先合实现与 Windows CI 自测 → 打 0.39 → 在 0.38 真机验证
  「正常升级」「模拟 PowerShell 被拦（direct fallback）」「模拟安装器失败（快照恢复）」
  三条臂。
- 回滚策略：若 runner 新形态在真机出现不可恢复问题，可临时把 `apply_pending_update`
  切回 direct Popen（保留 pending/日志契约），不改数据；安装器的目录继承与快捷方式
  修复可独立保留。

## Open Questions

- 无阻塞性问题。快照采用完整复制还是硬链接、快捷方式修复放在安装器 `[Code]` 还是
  shell 启动段，均不影响 spec 的外部行为，可在实现时按 Windows CI 验证结果选择。
