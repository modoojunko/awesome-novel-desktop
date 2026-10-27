# c-window-origin-topleft · 设计

## Context

- 现状：`pywebview_app.py` main() 尺寸块（约 :1384-1394）取 `webview.screens[0]`
  求 `win_w/win_h`，`create_window`（:1397）只传 width/height——x/y 缺席，Windows
  走 CW_USEDEFAULT 级联（越拉越右下），macOS 走系统隐式定位（实测 40,33 偏移）。
- pywebview 6.2.1 的 `Screen` 只有 `x/y/width/height`（5.x 仅 `resolution` 元组），
  **无 workarea**——任务栏避让没有现成数据源。

## Decisions

- **D1 主屏原点直锚，不精算 workarea**：`win_x = screen.x`、`win_y = screen.y`
  （6.x）／`(0, 0)`（5.x 或异常）。理由：用户诉求字面＝「桌面左上角对齐」；底置
  任务栏（绝对多数形态）下窗口高 `height-60` 天然不压任务栏；侧/顶置任务栏属
  边缘态，v1 接受（真要 workarea 得 ctypes `SPI_GETWORKAREA`/NSScreen.visibleFrame
  双平台各写一套，收益不配复杂度）。
- **D2 与尺寸块同 try 同风格降级**：origin 计算并进现有 try/except（5.x/异常 →
  `(0, 0)`），不新增失败面；`create_window` 恒传 `x=win_x, y=win_y`（无「条件
  传参」分支，kwargs 恒定便于形状断言）。
- **D3 macOS 菜单栏**：spec 场景钉「标题栏不被菜单栏遮挡」；实现以真机实测为准——
  若 `y=screen.y` 被菜单栏压住，darwin 侧 `win_y += 28`（菜单栏高度常量）平替，
  属实现细节不进 spec。验收臂含 macOS 冷启肉眼看。
- **D4 可测性抽 helper**：`_window_origin(screen) -> tuple[int, int]` 三臂单测
  （6.x 属性臂／5.x resolution 臂／异常臂），`create_window` 传参用源码形状断言
  （与 #952 接线断言同口径——main() 内联块无独立入口可测）。
- **D5 非目标**：位置持久化、多屏跟随、workarea 精算、尺寸算法改动（引 proposal
  非目标段）。

## 测试设计

- `_window_origin` 三臂：假 screen（有 x/y 属性）→ 取 x/y；仅 resolution 元组 →
  (0,0)；`_raise` 假对象 → (0,0)，均不外抛。
- `create_window` 形状断言：源内 `x=win_x`、`y=win_y`、`_window_origin(` 三串在场。
- 回归：后端全量 CI 口径；ruff 闸内（tests 文件）全绿；壳层文件在 ruff 闸外
  （A/B 对拍无新增账）。

## 风险

- macOS 菜单栏遮挡（D3 兜底预案在）；负坐标副屏布局下主屏原点仍为 (0,0)（Windows
  多屏惯例主屏原点即 0,0，screen.x 透传保证正确）。
