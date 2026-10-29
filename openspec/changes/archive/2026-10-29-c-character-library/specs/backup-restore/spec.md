# backup-restore — 规格增量（角色库段随包 v8）

## ADDED Requirements

### Requirement: 角色库段随包（配置包 v8）

备份格式 SHALL 从 v7 升至 v8：配置包 `config.yaml` SHALL 新增 `character_library` 段，承载账号级角色库全部角色卡的文本字段（名字、别名、人设、基础档案八格、认知 30 格、题材/定位/小类、来源信息）以及头像描述（full/thumb 各自 sha256 与字节数）；头像字节 SHALL 照图像资产先例以独立二进制条目入 zip（`character_library/avatars/{id}-{variant}.webp`），SHALL NOT 以 base64 塞进 yaml。资产包（逐书）SHALL NOT 携带角色库内容（角色库是账号级资产，与书无关）。导入 SHALL 幂等（按库卡 id 冲突即忽略）；头像文件缺失或被篡改（sha256 不符）时卡片 SHALL 照常入库并计入 warning，MUST NOT 阻断整包恢复；导入端遇到 v7 或更早配置包（无该段）SHALL 正常跳过、MUST NOT 报错。

#### Scenario: 换机恢复角色库

- **WHEN** 用户在新机导入 v8 配置包
- **THEN** 角色库全部角色卡及头像原样恢复，页头统计与库内分类不变

#### Scenario: 旧包缺段

- **WHEN** 导入 v7 或更早配置包
- **THEN** 角色库段缺失被跳过，其余段恢复不受影响，不出现报错
