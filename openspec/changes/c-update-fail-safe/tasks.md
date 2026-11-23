# c-update-fail-safe · 任务

> **进度**：2026-11-23 已落两批——「记录切片」（§2，PR #1137）与「救援/连续性」
> （§3/§4，本批）。待：§5 Windows CI 假安装器、§6 真机验收（装包另批）。
> §1 的真机复现/本地夹具与 §6 的真机证据仍随真机批次补齐。

## 1. 设计影响与现场复现

- [ ] 1.1 界面影响判定：本 change 无 React 屏改动，失败提示为 OS 级 MessageBox/桌面文本（应用可能不可启动），依据 proposal「Design Impact」免原型先行；在 change 目录记录判定（含“若改应用内横幅则另补原型”的边界）
- [ ] 1.2 Windows 真机复现 0.37→0.38 失败形态：确认 `data/updates` 无 `installer-runner.log` 与 `installer.log`、`startup.log` 有 `installer launched`；用 `-EncodedCommand` 探针确认 `powershell.exe` 是否被安全软件/策略拦截；把结论写进 `design.md` 的 Context/Decisions（若实际是 Wait-Process 终止错误则调整回退时序）
- [ ] 1.3 用假安装器（写入标记后按环境变量返回 0/1）搭一个可重复的 runner 本地夹具，断言当前实现的日志只在安装器结束后出现；保存复现记录作为后续测试基线

## 2. 执行体三段留痕与出口回退

- [x] 2.1 重构 `_install_runner_script`：`started`（既有，保留）＋调用安装器前 `installer_start`＋`finally` 写 `finished (status/exit/retry/error)`（异常路径必写；`installer_exception`/`runner_exception` 两臂各记专属 status；保留 wait_ms 行供三态回读）；`test_packaging_shell_apply.py` 解码断言更新并通过（三段顺序＋finally 位置）
- [x] 2.2 `_spawn_install_runner`：Popen 成功写 `runner_spawned` 日志（startup.log）；`_wait_runner_started` 以 100ms 节奏等待 `runner: started` 最多 3s（按 `dispatched` 分段，历史行不冒充本次）；超时先杀残余 runner（防与直连双装）再回退 `_spawn_installer_direct`（同 argv/闸门，`DETACHED_PROCESS`）并双处写 `runner_fallback=direct`（执行日志＋startup.log）；「有 started 不回退 / 无 started 回退（含 kill 断言） / Popen 抛错回退 / 双失败上抛」四臂单测通过
- [x] 2.3 macOS runner 补 `finished (status/exit/detail)` 终局行（`started` 既有；换装算法零改动）；结构断言通过
- [x] 2.4 复核闸门（TTL/存在性/sha/平台）与 pending 语义未变；`pytest client/backend/tests/test_packaging_shell_apply.py client/backend/tests/test_update_check.py -q` → **98 passed**；backend 目录 ruff（CI 口径）全绿

## 3. 安装结果验收、重试、快照与可见失败

- [x] 3.1 安装前快照：runner 内 `robocopy /E` 把程序树复制到 `%LOCALAPPDATA%\AwesomeNovel\rollback\<目标版本>`，显式 `/XD` 排除 `data`、`logs`（书稿永不复制）；robocopy 退出码 ≥8（空间/权限不足等）＝`snapshot_failed`，放弃静默安装并走可见失败；脚本结构钉（本机无 Windows，robocopy 实跑证据随 6.6 真机臂）
- [x] 3.2 安装结果验收＋重试＋回滚：验收＝退出码 0 且 `{app}\<程序名>` 存在且大小 >0；失败在同一次退出链内重试安装器一次（`retry` 真实计数进 finished/metrics）；仍失败→用快照 `robocopy /MIR`（同排除）恢复程序树，状态记 `rollback_restored`/`rollback_failed`；结构钉＋`retry` 计数断言
- [x] 3.3 用户可见失败说明：finally 内 `System.Windows.Forms.MessageBox`（含版本/状态/退出码/错误/数据目录/手动下载地址）＋桌面 `爱小说更新失败-<时间戳>.txt`；`AINOVEL_RUNNER_HEADLESS=1` 时只写文件；脚本结构钉（headless 开关随 env 进脚本）
- [x] 3.4 快照清理挂在 `_reconcile_pending` 的「pending.version == current」分支：新版首次运行确认后删 `rollback/<版本>`；「装完但新版没起来」时快照保留（下次退出链仍可用）；单测覆盖确认后删除
- [x] 3.5 快照目录在 `data\updates\` 之外（`%LOCALAPPDATA%\AwesomeNovel\rollback`），不在用户「暂不」清理的误删范围；卸载器 [UninstallRun] 补清 `{localappdata}\AwesomeNovel`（指针＋快照）

## 4. 安装目录连续性与快捷方式

- [x] 4.1 应用启动时原子写 `%LOCALAPPDATA%\AwesomeNovel\install_dir.txt`（仅冻结态，内容为 `get_install_dir()` 绝对路径）；写失败只留日志不阻断启动；单测覆盖写入（tmp 目录隔离）
- [x] 4.2 安装器 `[Code]`：读指针文件 → 校验目录存在且可写（写探针文件）→ 否则读 HKCU/HKLM 的 64/32 位视图卸载登记项 `Inno Setup: App Path`/`InstallLocation`；在 `InitializeWizard`/`CurPageChanged(wpSelectDir)` 覆盖 `WizardForm.DirEdit.Text`；`/DIR` 明确给出时保持其优先级；结构钉（真机 per-user→admin 证据随 4.4）
- [x] 4.3 桌面快捷方式：`[Icons]` 桌面项改 `{autodesktop}`；自动更新参数去掉 `/MERGETASKS=!desktopicon`；`[Code]` 在 `ssPostInstall` 只修复已存在的 `.lnk`，不强行创建；结构钉＋回归（argv 不含 MERGETASKS）
- [ ] 4.4 记录一条真机证据：0.37 per-user 装于 `D:\AwesomeNovel` → 双击 0.38 admin 安装器，目录页预填 `D:\AwesomeNovel`；把 `installer.log` 与截图路径写入任务

## 5. Windows CI 真执行

- [x] 5.1 独立 workflow（`.github/workflows/client-packaging-selftest.yml`）＋`client/packaging/build/runner_selftest.py`：windows-latest 上用**真 PowerShell** 跑生成脚本＋假安装器（.cmd，计次/删标记模拟装半截），三臂断言——一次成功（ok/retry=0/快照在/data 未动）、首败重试成功（安装器 2 次/retry=1/不做恢复）、两次失败（`rollback_restored`/程序树被 /MIR 恢复/data 未动）＋headless 桌面失败说明文件
- [x] 5.2 「PowerShell 不可用」→ direct fallback 由既有单测覆盖（`test_runner_spawn_failure_falls_back_to_direct_installer` 断言 `runner_fallback=direct` 双处留痕；WINDIR 置空仍会回落到 PATH 的 powershell，无法在 CI 稳定伪造「完全不可用」，e2e 臂不做）
- [ ] 5.3 stub 安装器目录继承测试：需 iscc 编译安装器＋PyInstaller dist（CI 成本高）——**降级为真机验收项**（4.4/6.7 同臂）
- [x] 5.4 workflow 以 `pull_request` paths 触发（client/packaging/** 与打包测试）＝PR 门禁，不依赖签名 secret；实际 run 记录见 PR 描述

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
