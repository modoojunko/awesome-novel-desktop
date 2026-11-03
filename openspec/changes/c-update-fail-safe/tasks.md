# c-update-fail-safe · 任务

## 1. 设计影响与现场复现

- [ ] 1.1 界面影响判定：本 change 无 React 屏改动，失败提示为 OS 级 MessageBox/桌面文本（应用可能不可启动），依据 proposal「Design Impact」免原型先行；在 change 目录记录判定（含“若改应用内横幅则另补原型”的边界）
- [ ] 1.2 Windows 真机复现 0.37→0.38 失败形态：确认 `data/updates` 无 `installer-runner.log` 与 `installer.log`、`startup.log` 有 `installer launched`；用 `-EncodedCommand` 探针确认 `powershell.exe` 是否被安全软件/策略拦截；把结论写进 `design.md` 的 Context/Decisions（若实际是 Wait-Process 终止错误则调整回退时序）
- [ ] 1.3 用假安装器（写入标记后按环境变量返回 0/1）搭一个可重复的 runner 本地夹具，断言当前实现的日志只在安装器结束后出现；保存复现记录作为后续测试基线

## 2. 执行体三段留痕与出口回退

- [ ] 2.1 重构 `_install_runner_script`：在任何等待前写 `started`，调用安装器前写 `installer_start`，用 `try/finally` 写 `finished`（含 status/exit/retry/错误摘要）；`$ErrorActionPreference` 与日志函数在异常路径仍可写；更新 `client/backend/tests/test_packaging_shell_apply.py` 的解码断言并通过
- [ ] 2.2 `apply_pending_update` 在 `Popen` 前后写 `runner_spawned` 日志；`Popen` 后以 100ms 节奏等待 `started` 最多 3 秒；超时回退 `_spawn_installer_direct`（同一组闸门与 argv，`DETACHED_PROCESS`）并写 `runner_fallback=direct`；单测覆盖“有 started 不回退 / 无 started 回退 / Popen 失败”三臂并通过
- [ ] 2.3 macOS runner 补 `started` 与 `finished` 两行（不改换装算法）；解码/结构测试通过
- [ ] 2.4 复核闸门（TTL/存在性/sha/平台）与 pending 语义未变；`pytest client/backend/tests/test_packaging_shell_apply.py client/backend/tests/test_update_check.py` 全绿并把输出摘要记入任务

## 3. 安装结果验收、重试、快照与可见失败

- [ ] 3.1 实现安装前快照：`%LOCALAPPDATA%\AwesomeNovel\rollback\<from_version>\`，复制程序树并排除 `data\`/`logs\`；按程序树大小 ×1.2 做空间预检；快照失败则放弃静默安装并写可见提示；用临时目录夹具验证排除项与失败分支
- [ ] 3.2 实现安装结果验收：exit code=0 且 `{app}\AwesomeNovel.exe` 存在且大小>0；失败自动重试一次；仍失败用 `robocopy /MIR` 从快照恢复程序树（排除 `data\`/`logs\`）；用假安装器验证“首次失败→重试成功”“两次失败→快照恢复后旧 exe 存在”两臂
- [ ] 3.3 实现用户可见失败说明：`System.Windows.Forms.MessageBox`（Yes=打开数据目录）＋桌面 `爱小说更新失败-<timestamp>.txt`；`AINOVEL_RUNNER_HEADLESS=1` 时只写文件；断言异常路径（try/finally）也必写说明与日志
- [ ] 3.4 快照清理挂在 `_reconcile_pending` 的“pending.version == current”分支（新版首次运行确认后删除 `rollback/<version>`）；单测覆盖“未确认不删 / 确认后删”
- [ ] 3.5 更新 `auto-skip`/清理逻辑的保留清单与注释，确保快照目录不在“暂不”清理的误删范围；测试通过

## 4. 安装目录连续性与快捷方式

- [ ] 4.1 应用启动时原子写 `%LOCALAPPDATA%\AwesomeNovel\install_dir.txt`（内容为 `get_install_dir()` 绝对路径）；写失败只留日志不阻断启动；单测覆盖写入与失败分支
- [ ] 4.2 安装器 `[Code]`：读指针文件 → 校验目录存在且可写；否则读 HKCU/HKLM（含 `WOW6432Node` 视图）的 `Inno Setup: App Path`/`InstallLocation`；在 `InitializeWizard`/`CurPageChanged(wpSelectDir)` 覆盖 `WizardForm.DirEdit.Text`；`/DIR` 明确给出时保持其优先级；stub 安装器或真机验证 per-user→admin 沿用旧目录
- [ ] 4.3 桌面快捷方式：`[Icons]` 桌面项改 `{autodesktop}`；自动更新参数去掉 `/MERGETASKS=!desktopicon`（按 `checkedonce`/`UsePreviousTasks` 语义处理）；`[Code]` 在 `ssPostInstall` 只修复已存在的 `.lnk`，不强行创建；Windows 验证 admin/per-user 两种模式无重复图标、旧快捷方式目标被修正
- [ ] 4.4 记录一条真机证据：0.37 per-user 装于 `D:\AwesomeNovel` → 双击 0.38 admin 安装器，目录页预填 `D:\AwesomeNovel`；把 `installer.log` 与截图路径写入任务

## 5. Windows CI 真执行

- [ ] 5.1 在 `client-package.yml` 的 Windows job（或独立 workflow）增加 runner self-test：假安装器返回 0/1，断言 `started → installer_start → finished` 顺序、exit code 透传、失败重试 ≤1、快照恢复、headless 说明文件
- [ ] 5.2 增加“PowerShell 不可用”臂：把 `WINDIR` 指向无 `powershell.exe` 的临时目录（或桩掉 `_spawn_install_runner`），断言 Python 走 direct fallback 且日志含 `runner_fallback=direct`
- [ ] 5.3 增加 stub 安装器目录继承测试：per-user 装临时目录 → admin 无 `/DIR` 再装，断言第二遍仍用第一遍目录；若 CI 权限/Inno 限制不可行，降级为真机验收项并在任务里注明原因
- [ ] 5.4 把 Windows self-test 接入 PR 门禁（不依赖签名 secret），记录一次实际 run URL 与结论

## 6. 回归与真机验收

- [ ] 6.1 后端测试：`python -m pytest client/backend/tests/test_packaging_shell_apply.py client/backend/tests/test_update_check.py -q` 全绿，记录通过数
- [ ] 6.2 前端零回归：`cd client/frontend && npm run design:lint && npx tsc --noEmit`；本 change 未改 `client/frontend`，记录“未改前端、命令照跑零回归”的实际输出结论
- [ ] 6.3 跨端/共享段判定：本 change 只动 C端 shell/安装器，不触 `base.css` 令牌与共享组件类；按 proposal「Design Impact」免 `scripts/design-cross.mjs`，在回归记录中写明依据
- [ ] 6.4 真机正常臂：0.38→0.39 点重启→新版自动启动；`installer-runner.log` 依次有 `started/installer_start/finished installer_exit=0`；books 零改动；记录日志尾段
- [ ] 6.5 真机异常臂 A（PowerShell 被拦）：用策略/临时改名使 `powershell.exe` 不可用，点重启→direct fallback 安装成功或失败可见；记录 `runner_fallback=direct` 与结果
- [ ] 6.6 真机异常臂 B（安装器失败）：占住/删除目标 exe 或注入失败，断言重试、快照恢复、可见失败说明与数据目录出口；记录 `installer-runner.log` 与桌面说明
- [ ] 6.7 真机异常臂 C（目录继承）：per-user 旧装→admin 手动重装仍预填旧目录；桌面快捷方式更新后指向当前 exe；记录 `installer.log`/截图
- [ ] 6.8 文档与发版：更新 `docs/ops` 更新失败排障手册（日志位置、回退/恢复行为、数据找回步骤）与 v0.39 更新说明；记录文档 diff
- [ ] 6.9 OpenSpec 归档随实现 PR：sync 两份 delta 到主 spec（`client-auto-update` MODIFIED、`installer-release` ADDED），把 change 移入 `openspec/changes/archive/`，`openspec validate --strict` 通过；记录输出
