# client-shell-startup（delta）

## ADDED Requirements

### Requirement: 窗口初始位置锚定主屏左上角

桌面壳创建主窗口时 SHALL 将窗口初始位置锚定在**主显示器左上角**：位置取主屏屏幕
原点（与屏幕自适应尺寸同一来源、同一降级风格），MUST NOT 依赖操作系统窗口级联等
不可预期的默认定位。屏幕信息不可得时 SHALL 回退坐标 (0, 0)。位置计算失败 MUST NOT
阻断窗口创建（无 x/y 信息时窗口仍按回退坐标创建）。

#### Scenario: Windows 更新拉起新窗落主屏左上角

- **WHEN** 应用窗口被创建（冷启、更新拉起、pending 重试任一路径），主屏信息可得
- **THEN** 窗口初始位置为主屏左上角（屏幕原点），不随系统级联默认漂移到右下角

#### Scenario: 屏幕信息不可得回退 (0,0)

- **WHEN** 屏幕枚举失败或无 x/y 信息（如 pywebview 5.x 仅 resolution 元组、无头环境）
- **THEN** 窗口以坐标 (0, 0) 创建，创建流程不因位置信息缺失而失败

#### Scenario: macOS 菜单栏不吞标题栏

- **WHEN** macOS 上窗口锚定主屏左上角
- **THEN** 窗口标题栏完整可见（不被系统菜单栏遮挡；如屏幕原点被菜单栏覆盖，
  darwin 侧以菜单栏高度为最小 y 偏移）
