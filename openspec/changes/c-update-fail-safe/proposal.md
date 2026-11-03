# C端 更新链失败兜底（c-update-fail-safe）

## Why

2026-10-21 生产真机 0.37→0.38 事故：用户点「重启更新」后应用退出，再没有新窗口；桌面快捷方式指向的不是当前安装目录，双击报找不到程序（自动更新从不刷新桌面图标）；用户手动从 `data/updates` 装 0.38，第一次安装没有继承 `D:\AwesomeNovel`，落到默认 `%LOCALAPPDATA%\Programs\AwesomeNovel`，新数据目录看不到旧库，空书架且没有迁移卡；其后用户把 0.38 重装回 `D:\AwesomeNovel`，旧安装目录与 `data` 仍在，并已成功把 0.37 数据迁移到 0.38、书架恢复。本 change 不处理这次已经恢复的数据，而是处理链条本身的失败不可见，以及下次升级的目录/快捷方式连续性。

定位：0.37 首次随包的 detached PowerShell runner 被拉起（`startup.log` 有 `installer launched`），但 `data/updates` 下既没有 `installer-runner.log` 也没有 Inno `installer.log`，说明 runner **没有执行到安装器**；旧 `AwesomeNovel.exe` 在重装前仍在，用户看到的“没有程序”是桌面快捷方式指向了旧目录/旧路径，不是自动安装器删除了 exe。退出链此时已经关窗，pending 重试又依赖应用下次启动；runner 不执行时没有任何可观察信号，失败对用户完全不可见。第一次手动安装落到默认目录则是 Inno `UsePreviousAppDir` 只读「当前安装模式对应的注册表 hive」：自动链一直 `/CURRENTUSER`（HKCU），手动双击走 admin（HKLM），看不到旧路径；数据候选扫描又只看当前 `data/`，于是书“消失”。

归档的 c-silent-relaunch-runner 已把这类风险写成「由 pending 重试＋手动链兜底（可恢复）」，本次真机证明该假设不成立：runner 不执行时没有任何可观察信号，用户也不知道旧安装目录在哪。必须把「执行体是否真的跑了」变成可判据，并为失败准备可见出口和旧版回滚。

## What Changes

- **执行留痕前置**：runner 在任何等待之前先写 `started`，调用安装器前写 `installer_start`；所有路径（成功/失败/异常）都写 `finished`。Python 侧在 spawn 后写 `spawned` 标记，并在有界时间内等待 `started`。
- **runner 未启动即回退**：有界等待内没有 `started`（PowerShell 被拦/脚本未执行）⇒ 退出链回退到**直接 detached 拉起安装器**（c-silent-relaunch-runner 之前的形态），并留日志；不允许“日志写了 launched、实际什么都没发生”。
- **安装结果验收与重试**：安装器退出后校验 exit code 与 `{app}\AwesomeNovel.exe` 是否存在/可启动；失败自动重试一次；仍失败则恢复安装前快照（或至少保证旧版可启动）并留下**用户可见**的失败说明（含数据位置与手动下载出口）。
- **安装前回滚快照**：runner 在动安装器前对当前安装目录做一份可回滚快照（完整复制或 NTFS 硬链接快照），空间/权限不足则跳过静默安装、回手动链并给出可见提示。成功升级后清理快照。
- **安装目录连续性**：安装器在交互/静默安装时从 **HKCU 与 HKLM（含 32 位视图）** 两处读取最近的 `Inno Setup: App Path`，并优先采用仍然存在的目录；应用在用户级目录（安装目录之外）维护一份中立的安装路径指针，供注册表记录缺失或跨安装模式时兜底。
- **桌面快捷方式连续性**：自动更新成功后修复/创建当前安装目录的快捷方式，不再让 `/MERGETASKS=!desktopicon` 留下指向旧目录的死图标。
- **Windows 真执行验收**：在 Windows CI 用假安装器跑 runner（启动留痕、等待、退出码、回退、快照），并用 stub 安装器验证 per-user→admin 的目录继承；真机补“PowerShell 被拦”“安装器失败后 exe 缺失”两个异常臂。

**非目标**：不做 A/B 双目录安装（archived c-silent-relaunch-runner 的既定非目标）；不改数据格式/迁移链；不改 macOS runner 的换装算法（只补启动留痕口径）。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `client-auto-update`: 「退出链静默安装」增加执行体启动判据、失败回退、安装结果验收/重试/回滚、可见失败；runner 日志契约从“结束后一行”改为“开始/安装开始/结束”三段。
- `installer-release`: 新增「安装位置继承与快捷方式连续性」要求——安装器跨 HKCU/HKLM 继承旧目录、应用维护中立安装路径指针、更新后快捷方式指向当前 exe。

## Design Impact

- 受影响端：C端（Windows 桌面壳/安装器），不触 S端、不触两端共享设计令牌。
- 受影响屏/弹层：无 React 屏改动；失败提示为 OS 级 MessageBox/桌面说明文本（应用可能已不可启动，不能依赖应用内 UI）。若后续选择应用内横幅，另行按 design-language §5/§13 补原型。
- 对象状态：失败提示使用 err 语气（仅用于 OS 级说明文本/未来应用内横幅的登记，不新增组件形态）。
- 共享段：无。原型先行：不需要（非应用内界面）。
- 设计工件：实现侧自查；OS 级提示文案按 §13“补救语句必须带可点击出口”给出手动下载/数据目录出口。

## Impact

- `client/packaging/build/pywebview_app.py`：runner 脚本、spawn 等待、回退、快照/验收、日志契约。
- `client/packaging/build/installer.iss`：`[Code]` 跨 hive 读旧路径；快捷方式修复；安装路径指针读取。
- `client/packaging/build/build_release.ps1` / `.github/workflows/client-package.yml`：Windows 真执行测试与 stub 安装器测试。
- 测试：`client/backend/tests/test_packaging_shell_apply.py`、新增 Windows runner/installer stub 测试。
- 文档/运维：更新失败排障手册（日志位置、回退行为、数据找回步骤）。
- 兼容性：不改变更新清单载荷、pending 标记既有字段（可新增字段）、数据格式；旧版本包仍可被新客户端识别。
