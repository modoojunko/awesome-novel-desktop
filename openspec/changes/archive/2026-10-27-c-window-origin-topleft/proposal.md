# C端 窗口初始位置钉主屏左上角（c-window-origin-topleft）

## Why

Windows 的窗口默认定位走 CW_USEDEFAULT 级联——每次拉起（冷启、更新拉起、pending 重试）
都比上一次错开一格，多次之后窗口一路漂到桌面右下角（用户采证：0.42 更新拉起的新窗
落在右下角）。壳层 `create_window` 目前只传 width/height 不传 x/y
（`pywebview_app.py` 尺寸块约 :1385），位置完全交给系统默认。用户期望：窗口每次都和
桌面左上角对齐，位置可预期。

## What Changes

- 壳层在现有屏幕自适应块里**一并求主屏左上角**：`webview.screens[0]` 的 `x`/`y`
  （pywebview 6.x），5.x 无 x/y 或屏幕信息不可得时回退 `(0, 0)`。
- `webview.create_window` 新传 `x=win_x, y=win_y`，双平台同款——Windows 级联、
  macOS 随机偏移都收拢为「主屏左上角」一个可预期位置。
- 非 pywebview 窗口路径（`--smoke` 无 GUI、error page 分支）不受影响。

**非目标**：不做窗口位置持久化记忆（用户没要）；不做多屏跟随/记忆最后所在屏
（恒主屏）；不精算任务栏 workarea（底置任务栏下窗口 `height-60` 天然不压；侧/顶
置任务栏属边缘态，v1 接受）；不改窗口尺寸算法。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `client-shell-startup`：新增「窗口初始位置」requirement——桌面壳窗口 SHALL 锚定
  主屏左上角（屏幕信息不可得时回退 (0,0)），并附场景。该能力现有 requirement
  （启动链留痕等）零改动。

## Design Impact

- 受影响端：C端（Windows/macOS 桌面壳窗口初始坐标）；**无 React 屏改动**，不触 S端。
- 受影响屏/弹层：无；无新增对象状态、无文案。
- 共享段：无触碰。
- 原型先行：不需要（OS 级窗口几何，非应用内界面）。
- 设计工件：实现侧自查。

## Impact

- `client/packaging/build/pywebview_app.py`：屏幕块加 `win_x`/`win_y` 计算＋
  `create_window` 传 `x`/`y`；可测性抽 `_window_origin(screen)` helper。
- 测试：`client/backend/tests/test_packaging_shell_apply.py` 增 origin 三臂
  （6.x 属性／5.x 回退／异常回退）＋`create_window` 传参形状断言。
- 真机验收：Windows（灰度或晋升后的下一跳/冷启）新窗落主屏左上角；macOS 看标题栏
  与菜单栏关系（如被菜单栏压住，darwin 侧 y 加菜单栏常量平替，不进 spec）。
- 兼容性：不改尺寸算法、不触更新链与数据格式；`--smoke`/无头路径零变化。
