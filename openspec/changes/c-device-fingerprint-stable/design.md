# c-device-fingerprint-stable — Design

## Context

`client/backend/auth_local/service.py` 里两个函数（`generate_pc_hash` / `collect_device_profile`）各自实现了一份只含 Windows `wmic` 三连的采集逻辑，macOS/Linux 上全部静默失败退化为 `platform.node()`。指纹每次登录实时重算，S端 按 `(user_id, fingerprint)` 去重——主机名一漂就多一台设备。`pc_hash` 虽因 config.json 首写持久化而表面稳定，但 config 丢失重生成后同样漂移（legacy 轮换事故实证过 config 重建路径）。动因详见 proposal.md。

## Goals / Non-Goals

**Goals:**
- 单一平台身份 helper，三平台（macOS/Windows/Linux）都取硬件/系统级稳定标识，带占位值检测与静默降级链
- `pc_hash` 与 `fingerprint` 同源；同机重装 config 不换身份
- `wmic` 全部退役；S端 与传输契约零改动

**Non-Goals:**
- 不改 S端 设备去重键、授权/配对/轮询任何契约
- 不做指纹的 config.json 持久化缓存（spec 已定为 MUST NOT）
- 不处理「用户手动改 IOPlatformUUID/MachineGuid」等对抗性场景（本产品指纹用于设备档案展示与去重，不是防篡改锚点；配对安全由 challenge/配对密钥体系承担，见 `device-auth-page` spec）
- 不清理 S端 存量重复设备行（零用户基线，无存量需要清）

## Decisions

1. **单 helper 同源，两个出口截断不同**：`_platform_identity() -> str` 返回原始标识串；`generate_pc_hash` = sha256[:32]（沿用现形态），`collect_device_profile.fingerprint` = sha256 全长。备选「各自独立实现」被否——两份逻辑正是本次缺陷的成因（两处 wmic 复制粘贴漂移），单一事实源是教训对齐。

2. **macOS 用 `ioreg` 而非 `system_profiler`**：`ioreg -rd1 -c IOPlatformExpertDevice` 单命令、输出确定性高、毫秒级；`system_profiler SPHardwareDataType` 输出本地化（中文系统键名会变）、秒级。解析用行正则 `"IOPlatformUUID"\s*=\s*"(...)"`，该输出格式十数年未变。

3. **Windows 用 PowerShell `Get-CimInstance`，MachineGuid 用 `reg query`**：`wmic` 在 Win11 24H2 默认移除，属定时炸弹（现有三条 wmic 一并退役）。`powershell -NoProfile -NonInteractive -Command "(Get-CimInstance Win32_ComputerSystemProduct).UUID"` 冷启约 1–2s，仅在登录时调用可接受；沿用现有 5s 子进程超时。`reg query HKLM\SOFTWARE\Microsoft\Cryptography /v MachineGuid` 普通用户可读、毫秒级。

4. **Linux 走 `/etc/machine-id`**（兜 `/var/lib/dbus/machine-id`）：dev 容器/e2e 主路径。容器内每容器随机——与现状（容器 hostname 随机）等价，不劣化；测试如需稳定身份由 fixture 显式注入（见决策 6）。

5. **进程内 memoize，不落盘**：helper 首次成功后缓存到模块级变量（登录时算一次即可，避免 Windows PowerShell 重复冷启）；config.json 不加字段（spec 契约）。测试注入用参数/monkeypatch 而非改缓存。

6. **e2e 兼容策略**：全量 e2e 在本地 docker 栈跑，容器身份随机不影响用例内部自洽（播种与断言在同一次运行内同源）；既有用例若硬编码了 pc_hash 值，改为从被测进程同款 helper/config 读取。**改后端必须重建 docker 容器**（镜像内模板代码，旧容器会假绿）。

7. **存量授权硬切**：升级后旧 pc_hash 落库的授权记录命中不了，首次登录走一次浏览器重新授权。备选「双读兼容（同时上报新旧 pc_hash）」被否——零真实用户，双模复杂度无收益（对齐 09-18 拍板：兼容包袱全可丢）。

## Risks / Trade-offs

- [极老主板 SMBIOS UUID 为全 0/全 F 占位] → spec 强制占位值检测，落入 MachineGuid → 主机名链；占位值覆盖率极低且有三级兜底
- [PowerShell 在个别精简版系统缺失] → 降级 `reg query` MachineGuid → 主机名；命令不存在走 OSError 降级链，不阻塞登录
- [ioreg 输出格式未来变化] → 行正则解析失败按无效值降级主机名，行为不劣于现状
- [旧 pc_hash 授权记录失效] → 一次性浏览器重授权；发布说明提及（零真实用户，影响面=作者本机演练环境）
- [e2e 用例硬编码身份值被打破] → 实现期排查 `pc_hash` 在测试代码中的硬编码点，全部改为运行时同源读取；容器重建纳入跑测前置

## Migration Plan

单 PR 合入 main，随下版打包带出。S端 零改动、无 DB 迁移。回滚 = revert 单 commit（`pc_hash` 会再变一次身份，同样以一次重授权收敛，无数据损坏路径）。

## Open Questions

（无）
