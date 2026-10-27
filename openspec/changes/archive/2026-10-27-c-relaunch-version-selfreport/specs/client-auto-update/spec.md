# client-auto-update（delta）

## ADDED Requirements

### Requirement: 更新拉起新实例的版本自报

自动拉起的新实例 SHALL 自报其**真实烘焙版本**（构建期写入产物清单的
`client_version`）：打包产物 MUST 以烘焙清单为版本事实源，MUST NOT 让上一版实例
经执行体环境链（runner 环境继承、安装器中转、拉起传播）传递的版本值覆盖烘焙值；
版本自报 MUST 覆盖启动日志版本字段、版本徽章与更新状态查询的 `current`。执行体
创建/传递环境时 SHALL NOT 向下游传播上一版实例的烘焙派生键（如 `CLIENT_VERSION`、
`CLIENT_UPDATE_URL(_FALLBACK)`、`SERVER_API_BASE(_FALLBACK)`、`PUBLIC_SERVER_API`、
`PORTAL_URL`）。非冻结（开发）形态的 env 覆盖能力 SHALL 保留，行为不变。

#### Scenario: 灰度跳后新实例自报新版本

- **WHEN** 用户点「重启更新」，执行体换装成功并自动拉起新版实例
- **THEN** 新实例的启动日志版本字段、版本徽章与更新状态查询 `current` 均为
  新烘焙版本，MUST NOT 停留在上一版版本号；更新状态不得因此恒报「有更新」

#### Scenario: 执行体环境不传播烘焙派生键

- **WHEN** 退出链创建执行体并传递环境（Windows Popen／macOS 显式 env dict）
- **THEN** 烘焙派生键被剥离，执行体及其拉起链拿不到上一版实例的版本值；
  其余环境变量（PATH、系统键等）原样保留

#### Scenario: 开发形态 env 覆盖保留

- **WHEN** 非冻结形态以 `AI_NOVEL_CLIENT_VERSION` 等 env 覆盖启动
- **THEN** env 覆盖行为与历史一致，烘焙缺失时回退语义不变
