# C端 更新拉起窗口置前（c-mac-relaunch-frontmost）

## Why

2026-10-26 真机定案：macOS 更新链 0.39→0.40 换装、拉起、启动期对拍**全链 12 秒全绿**
（runner 日志 `install_ok=1 relaunched=1`、reconcile 落账），但用户体感是「点重启更新没
拉起来」——runner 从后台会话 `open` 的新实例不抢焦点（可能落在前台应用之外的桌面空间），
四份启动日志与手动启动逐行同形、窗口实存（1648×1021 探针实证），用户却从头到尾没看见。
壳层与打包钉定的 pywebview 6.2.1 均无任何激活调用。该感知断点让每次正常的自动升级都被
当成「更新失败」重演（本机当日连开四次、Windows 事故档案三次垫底），必须在下一版收口。

## What Changes

- 壳层（`client/packaging/build/pywebview_app.py`）在 GUI 窗口呈现后**自激活到前台**：
  macOS 调用 AppKit `NSApplication activateIgnoringOtherApps_`（pyobjc 已随 pywebview
  打包依赖在场），调用结果落启动日志（成功/失败各一行，失败可见）。
- 自激活为**无条件**（darwin 平台）：手动启动场景系统本就授予前台，调用幂等无害；
  后台拉起场景由此强制到前。
- 非 darwin 平台与 AppKit 缺失/异常一律静默跳过（no-op，不阻断启动链）。
- 不改 runner 脚本（`open` 后 osascript activate 兜底不做——后台进程发 Apple Events 有
  权限弹窗风险，主修在壳层即覆盖一切后台拉起来源）。
- Windows 安装器 `/AUTOLAUNCH=1` 拉起的置前行为不在本 change 改动，0.41 真机验收顺带
  观察并记录（如不置前另案立项）。

**非目标**：不改换装算法与 runner 留痕契约（c-update-detached-ps-fix 已定）；不改
pywebview 上游；不做 Windows 置前改动。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `client-auto-update`：「退出链静默安装」 requirement 增补拉起可见性——被自动拉起的
  新版窗口 SHALL 成为前台窗口（应用在 GUI 窗口呈现时自激活，结果留启动日志）；新增
  「自动拉起窗口必须到前台」场景。

## Design Impact

- 受影响端：C端（Windows/macOS 桌面壳进程行为）；**无 React 屏改动**，不触 S端。
- 受影响屏/弹层：无；无新增对象状态、无新文案（不触 design-language §13）。
- 共享段：无触碰。
- 原型先行：不需要（非应用内界面，纯 OS 级进程行为；沿用 c-update-detached-ps-fix 的
  Design Impact 判定口径）。
- 设计工件：实现侧自查。

## Impact

- `client/packaging/build/pywebview_app.py`：新增自激活 helper＋`window events.shown`
  回调挂接＋启动日志两行。
- 测试：`client/backend/tests/test_packaging_shell_apply.py` 增自激活三臂
  （darwin 调用／非 darwin no-op／AppKit 异常不阻断）。
- 真机验收：0.41 发版后事故 Mac（0.40）点「重启更新」，新窗必须出现在前台——与
  #945 的 0.40→0.41 首跳验收同车执行。
- 兼容性：不改变更新清单、pending/runner 日志契约、数据格式；手动启动路径行为不变。
