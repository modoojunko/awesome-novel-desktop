# c-device-fingerprint-stable

## Why

C端 设备指纹在 macOS 上全部退化成「当前主机名」的哈希：采集逻辑只实现了 Windows 专用的 `wmic` 三连（CPU/主板/硬盘），命令在 macOS 不存在、异常被静默吞掉，兜底落到 `platform.node()`。macOS 主机名随网络环境漂移（换 Wi-Fi、局域网同名冲突自动加 "(2)" 后缀、改电脑名），导致**同一台机器每次登录都被 S端 注册成一台新设备**（S端 按 `(user_id, fingerprint)` 唯一去重，指纹变=新设备行）。实勘证据：本机 `wmic` 不存在、`platform.node()` 返回 `modoojunkodeMacBook-Pro.local`；指纹在每次登录时实时重算、不落盘。

## What Changes

- **指纹采集链跨平台重写**（`collect_device_profile` / `generate_pc_hash` 共用的身份源）：
  - macOS：`ioreg -rd1 -c IOPlatformExpertDevice` 解析 `IOPlatformUUID`（主板固件级，重装系统不变）；
  - Windows：PowerShell `Get-CimInstance Win32_ComputerSystemProduct` 取 SMBIOS 系统 UUID（与 IOPlatformUUID 同源），**弃用 `wmic`**（Windows 11 24H2 起已被移除，现有三条 wmic 调用是定时炸弹）；
  - Windows 兜底：注册表 `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid`（普通用户可读）；
  - Linux（开发容器/e2e）：`/etc/machine-id`；
  - 终极兜底：现行为 `platform.node()`。
  - 每级产物做**占位值检测**：空串、全 0、全 F（大小写不敏感）视为无效，落入下一级。
- **`pc_hash` 对齐同一身份源**（一机一身份，单一事实源 helper）：`generate_pc_hash` 改走同一平台标识链。当前 `pc_hash` 只因 config.json 首次持久化才表现稳定——config 丢失重生成后仍会漂到新身份（legacy 轮换事故里真实发生过 config 重建）；对齐后重生成不再变身份。**BREAKING（零用户基线下选择硬切）**：已存在的本地授权记录按旧 pc_hash 落库，升级后首次需在浏览器重新授权一次；S端 侧契约（URL 形态、authorize/check-auth/exchange 参数）零改动。
- **行为不变量**：指纹仍在登录时实时计算（不新增 config.json 落盘字段——硬件级标识本身稳定，落盘反而引入克隆盘旧身份风险）；S端 设备去重键 `(user_id, fingerprint)` 不变；device_profile 的编码/传输契约不变（`device-auth-page` 既有要求不受影响）。
- 清理：`wmic` 相关采集代码全部退役。

## Capabilities

### New Capabilities
- `device-fingerprint`: C端 设备身份标识的跨平台采集契约——平台标识源优先级链、占位值检测、兜底顺序、`pc_hash` 与 device_profile.fingerprint 同源约束、稳定性保证（同机重登同身份）。

### Modified Capabilities

（无——`device-auth-page` 只约束 device_profile 的传输/编码与授权动作契约，不涉及指纹内容语义；S端 零改动。）

## Impact

- **代码**：`client/backend/auth_local/service.py`（`generate_pc_hash`、`collect_device_profile`，抽公共平台身份 helper）；其余模块零触碰（`pc_hash` 全部消费方只透传 config.json 里已持久化的值，`auth_local/router.py`、`auth_local/models.py`、`models/user.py` 均不受影响）。
- **S端**：零改动（`authorize_device` 的 `(user_id, fingerprint)` 去重、`device_profile` 解析均保持）。
- **测试**：C端 后端容器 pytest（新增 macOS/Windows/Linux 采集链单测，mock 子进程）；受影响 e2e 场景复验（本地 docker 栈全量）；S端 e2e 不受影响。
- **用户可见界面**：无（纯后端逻辑；S端「我的设备」页展示内容会自然收敛为一台真机，属缺陷修复结果，非 UI 改动）。设计门禁（design:lint/check/cross）不适用。
- **发版**：随下版带出；存量安装（当前无真实用户）首次登录需浏览器重新授权一次。
