# device-fingerprint Specification

## Purpose

定义 C端 设备身份标识（`pc_hash` 与 device_profile.fingerprint）的跨平台采集契约：平台硬件标识源优先级链、无效值检测、兜底顺序，以及「同一台机器无论网络环境如何变化、重复登录均产生同一身份」的稳定性保证。解决 macOS/Windows 上指纹退化为主机名哈希、随网络漂移导致 S端 反复注册新设备的问题。

## Requirements

### Requirement: 平台标识源优先级链

C端 设备身份标识 SHALL 按以下优先级链采集，取第一个有效值：

1. **macOS**：`ioreg -rd1 -c IOPlatformExpertDevice` 输出中的 `IOPlatformUUID` 值；
2. **Windows**：PowerShell `Get-CimInstance Win32_ComputerSystemProduct` 返回的 SMBIOS 系统 UUID；
3. **Windows 兜底**：注册表 `HKLM\SOFTWARE\Microsoft\Cryptography` 下的 `MachineGuid`；
4. **Linux**：`/etc/machine-id` 文件内容；
5. **终极兜底**：`platform.node()`（现状主机名，行为等同旧实现）。

系统 SHALL NOT 依赖 `wmic` 采集任何身份信息（该命令自 Windows 11 24H2 起默认移除）。采集链中任一级命令不存在、执行失败或超时，SHALL 静默落入下一级，MUST NOT 使登录流程失败。

#### Scenario: macOS 上取 IOPlatformUUID

- **WHEN** C端 在 macOS 上采集设备身份，`ioreg` 输出包含合法 `IOPlatformUUID`
- **THEN** 身份标识派生自该 UUID，与主机名无关

#### Scenario: 采集级失败静默降级

- **WHEN** 某一级标识源命令不存在、返回非零或超时
- **THEN** 跳过该级继续尝试下一级，采集过程不抛错、不阻塞登录

#### Scenario: 全链失败兜底主机名

- **WHEN** 所有平台级标识源均不可用
- **THEN** 身份标识退化为 `platform.node()` 哈希，行为与旧实现一致

### Requirement: 无效值检测

每个标识源的采集结果 SHALL 先做有效性判定再被采纳：空串、去掉连字符后全为 `0`、或全为 `F`（大小写不敏感）的值视为无效，MUST 落入下一级标识源。极老旧主板可能输出全 0/全 F 占位 UUID，不得将其当作唯一身份。

#### Scenario: 全 0 占位 UUID 不被采纳

- **WHEN** 某平台返回的 UUID 为 `00000000-0000-0000-0000-000000000000`
- **THEN** 该值被判定无效，身份标识取自优先级链的下一级

### Requirement: pc_hash 与设备指纹同源

`pc_hash`（配对/轮询锚点）与 device_profile.fingerprint（设备档案）SHALL 派生自同一平台身份标识（同一 helper 的同一取值），仅哈希截断长度不同（沿用现有输出形态）。config.json 丢失导致 `pc_hash` 重新生成时，同机重生成 SHALL 得到与丢失前相同的值，MUST NOT 因主机名漂移而变成新身份。

**存量策略（零用户基线硬切）**：升级前已按旧 pc_hash 落库的本地授权记录不再兼容——升级后首次登录须在浏览器重新授权一次。S端 侧授权/配对/轮询契约（URL 形态、参数名、响应形状）MUST 保持不变。

#### Scenario: 同机重生成 pc_hash 不漂移

- **WHEN** 用户删除本地 config.json 后在原机器重新登录
- **THEN** 重新生成的 `pc_hash` 与删除前一致，S端 既有授权记录仍可命中

#### Scenario: 换网络后重复登录不产生新设备

- **WHEN** 用户从 Wi-Fi A 切换到 Wi-Fi B（主机名被网络环境改写）后再次登录
- **THEN** 采集到的设备身份不变，S端 不会新增设备记录

### Requirement: 指纹实时计算不落盘

设备身份标识 SHALL 在使用时实时采集，MUST NOT 新增 config.json 持久化字段缓存身份值。硬件级标识本身稳定，落盘缓存反而引入磁盘镜像克隆后沿用源机旧身份的风险。

#### Scenario: 不新增持久化字段

- **WHEN** 登录流程采集设备身份并上报 S端
- **THEN** config.json 的字段集与既有定义一致（不出现身份缓存键）
