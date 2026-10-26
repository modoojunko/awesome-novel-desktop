# c-mac-relaunch-frontmost · 设计

## Context（定案档案，2026-10-26 本机实证）

- 时间线：15:27:50 点「重启更新」（POST /api/update-check/apply）→ 15:27:51 退出＋
  runner 派发 → 15:28:04 runner 尾行 `wait_s=0 parent_alive_after_wait=0 install_ok=1
  detail=install ok install_seconds=13 relaunched=1` → 15:28:03 新实例 shell main 进入
  ＋`applied v0.40 confirmed (reconcile)`。全链 12 秒。
- 用户体感「没拉起来」：四份启动日志（boot→shown→loaded）与 16:04 手动启动逐行同形；
  手动实例窗口探针实存（爱小说，40,33，1648×1021）。差异唯一在启动来源：runner 后台
  `open` vs Dock 手动。
- 激活缺口：壳层 `pywebview_app.py` 无任何激活调用（rg activate/frontmost 零命中）；
  打包钉 `pywebview==6.2.1`，其 cocoa 平台层亦不主动 `activateIgnoringOtherApps`。
  macOS 14+ 后台启动的应用不会自行到前——pywebview 只 `makeKeyAndOrderFront`，钥匙
  窗口在后台会话拉起时落在前台应用之后（或另一桌面空间）。
- 数据零丢失：换装不动 `~/Library/Application Support/AwesomeNovel`；当日「空书架」
  系该机 v0.39 库常态（无 novels），非事故。

## Decisions

- **D1 激活放壳层、不放 runner**：`window events.shown` 回调（pywebview_app.py
  `_on_window_shown`，约 :1396）是唯一挂点——此时窗口已真实呈现，`NSApp` 已就绪。
  runner 侧 `osascript activate` 兜底**不做**：后台进程发 Apple Events 触发
  「发送事件到应用」授权弹窗的风险大于收益；壳层自激活覆盖一切后台拉起来源
  （更新 runner、`open`/脚本、登录项恢复）。
- **D2 无条件＋幂等**：不区分「本次是否更新拉起」（没有可靠来源旗标，且手动启动时
  系统本已给前台，重复激活无害）。darwin 才走，其他平台直接 return。
- **D3 API 选型**：`NSApplication.sharedApplication().activateIgnoringOtherApps_(True)`
  ——macOS 14 起 deprecated 但仍生效（系统按「应用自激活于自身启动窗口」豁免）；
  pyobjc 已随 pywebview 依赖在场，零新增打包体积。若真机验收发现未来 macOS 忽略
  deprecated 调用，备选 `NSApp.activate()`（无参新 API）在实现 PR 内可平替，spec 不钉
  具体 API 名。
- **D4 失败可见**：激活成功落一行 `window activated (front)`，异常落 `window activate
  FAILED:…`——与 `window shown` 同级诊断面（startup.log），排障时与 15:28 事件同判读。
  异常 MUST 吞掉不阻断启动链（`shown` 回调内抛错会打断 pywebview 事件分发）。
- **D5 不动 runner 契约/不动 Windows**：换装算法与 runner 日志三段契约属
  c-update-detached-ps-fix（已合 0.40）；Windows Inno `/AUTOLAUNCH` 的前台行为列为
  0.41 真机验收观察项（本 change 不改 Windows 代码、不加 spec 要求——先观察再定）。

## 测试设计

- helper `_activate_to_front()` 独立成函数便于三臂单测（`test_packaging_shell_apply.py`
  扩展，同文件已 import 壳层模块）：
  - darwin 臂：monkeypatch `sys.platform='darwin'`＋注入假 `AppKit` 模块（sys.modules）
    → 断言 `activateIgnoringOtherApps_` 以 True 被调用；
  - 非 darwin 臂：`sys.platform='win32'` → AppKit 不被导入、零异常；
  - 异常臂：假 AppKit 抛错 → 吞掉不外抛。
- 回调接线断言：`_on_window_shown` 源内含激活调用（子串断言，与现有脚本形状断言同口径）。

## 风险

- 未来 macOS 忽略 deprecated 激活 API → 真机验收臂盯 0.41 拉起前台表现，失效则按 D3
  备选平替（不触 spec）。
- 全屏空间场景：激活会把用户从前台应用拽走（更新场景正是用户意图，可接受；手动日常
  启动系统本就给前台，行为不变）。
