## ADDED Requirements

### Requirement: 安装位置继承与快捷方式连续性

安装器在交互与静默安装时 SHALL 以「最近一次有效安装目录」作为目录页预填值与默认安装
目录，MUST NOT 仅因本次安装模式（per-user 与 per-machine）与上次不同而回落到产品默认
目录。判定 SHALL 同时考虑 HKCU 与 HKLM（含 32 位注册表视图）中同一 AppId 的卸载登记
（`Inno Setup: App Path` / `InstallLocation`），以及应用维护的、位于安装目录之外的
用户级安装路径指针；候选目录 MUST 实际存在且可写，失效候选 MUST 被忽略。应用 SHALL
在成功启动后写入/更新该指针；指针缺失或损坏 MUST NOT 阻断安装。

自动更新成功后，系统 SHALL 保证桌面快捷方式指向当前安装目录的主程序：已有快捷方式
MUST 被修复到当前目标；无快捷方式时 MAY 创建 per-user 快捷方式。MUST NOT 因
`/MERGETASKS=!desktopicon` 留下指向旧目录或不存在程序的桌面快捷方式。

#### Scenario: per-user 旧装后 admin 手动重装仍沿用旧目录

- **WHEN** 0.37 以 per-user（HKCU）安装在 `D:\AwesomeNovel`，用户双击 0.38 安装器
  （admin 模式，无 `/CURRENTUSER`）
- **THEN** 安装位置页预填 `D:\AwesomeNovel`，而不是 `%LOCALAPPDATA%\Programs\AwesomeNovel`

#### Scenario: 安装路径指针兜底

- **WHEN** 当前安装模式对应的注册表 hive 中没有旧安装登记，但应用写入的用户级安装
  路径指针存在且指向有效目录
- **THEN** 安装器采用该指针目录作为预填值

#### Scenario: 失效路径被忽略

- **WHEN** 旧登记或指针指向的目录已不存在或不可写
- **THEN** 安装器忽略该候选并回落标准默认目录，MUST NOT 预填不存在的路径

#### Scenario: 更新后桌面快捷方式可达

- **WHEN** 自动更新成功完成（安装目录可能发生变化）
- **THEN** 桌面快捷方式目标为当前安装目录的主程序，双击可启动新版；不再留下指向旧
  目录或不存在程序的快捷方式
