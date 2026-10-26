# c-mac-relaunch-frontmost · 任务

## 1. 影响判定

- [x] 1.1 界面影响判定：本 change 无 React 屏改动、无应用内文案（纯 OS 级窗口行为），
      依据 proposal「Design Impact」免原型先行；在 change 目录记录判定结论。

## 2. 壳层自激活（client/packaging/build/pywebview_app.py）

- [x] 2.1 新增 `_activate_to_front()`：`sys.platform != "darwin"` 直接 return；
      darwin 下 `from AppKit import NSApplication`＋
      `NSApplication.sharedApplication().activateIgnoringOtherApps_(True)`，整段
      try/except 吞异常；验证：三臂单测通过（见 3.1）。
- [x] 2.2 `_on_window_shown` 回调接线：`window shown` 日志行之后调用
      `_activate_to_front()`，成功落 `window activated (front)`、异常落
      `window activate FAILED: …`（startup.log 诊断面，与 shown 同级）；验证：
      回调源形状断言（含激活调用与两行日志）通过。

## 3. 测试（client/backend/tests/test_packaging_shell_apply.py）

- [x] 3.1 `_activate_to_front` 三臂：darwin＋假 AppKit（sys.modules 注入）断言
      `activateIgnoringOtherApps_` 以 True 被调用；`sys.platform='win32'` 断言 AppKit
      不被导入且零异常；假 AppKit 抛错断言吞掉不外抛。
- [x] 3.2 `_on_window_shown` 形状断言：含 `_activate_to_front` 调用、
      `window activated (front)`、`window activate FAILED` 三串；存量用例保绿不改钉。

## 4. 回归

- [x] 4.1 后端全量：`cd client/backend && python -m pytest`（存量全绿＋新增三臂；
      带覆盖口径与 CI 一致）。验证：退出码 0，记录通过数。
- [x] 4.2 门禁结论登记：无 UI 改动（引用 proposal Design Impact 判定）——
      design:lint/design:check/tsc/design-cross 不涉，照 precedent（c-update-detached-ps-fix
      4.2）登记「未触前端、命令不涉」。

## 5. 发版与真机验收（0.41 同车）

- [ ] 5.1 真机正常臂：事故 Mac（0.40）自动更新到 0.41 点「重启更新」→ 新版窗口出现
      **且在前台**（全屏空间下应把用户带过去）；`installer-runner.log` 首行
      `runner: started`＋尾行 `installer_exit=0`（同车验 #945 首跳）；startup.log 含
      `window shown`＋`window activated (front)` 两行。记录日志尾段。
- [ ] 5.2 真机对照臂：Dock 手动启动 → 前台行为与升级前一致（无回归）；startup.log 两行
      照落。
- [ ] 5.3 Windows 观察臂（不改代码）：0.40→0.41 点「重启更新」，记录 Inno
      `/AUTOLAUNCH` 拉起的新窗是否到前台；不置前则另案立项（Win32 前台请求）。
- [x] 5.4 OpenSpec 归档随实现 PR：sync `client-auto-update` MODIFIED delta 到主 spec，
      change 移入 `openspec/changes/archive/`，`openspec validate --strict` 通过并记录输出。
