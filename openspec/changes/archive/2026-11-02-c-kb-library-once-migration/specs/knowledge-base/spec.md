## ADDED Requirements

### Requirement: 角色库存量一次性迁移

系统 SHALL 在老版角色库（character_library 表，deprecated）存在某账号存量卡且该账号尚未迁移过时，于该账号首次触达库域读面（知识库条目列表或角色库卡列表）时，把该账号存量卡整账号一次性镜像搬入知识库条目（src_kind=character_library_migration、src_ref=character_library、src_key=原卡 id）。迁移 SHALL 幂等（重复执行零副本）；SHALL NOT 以常驻启动钩子形式运行（一次性升级迁移，非例行自愈）；迁移失败 SHALL NOT 阻断读面（降级返回现有数据，下次触达重试）。

#### Scenario: 升级用户首次触达库域即见老卡

- **WHEN** 由老版本升级而来、character_library 存有存量卡且 kb_entries 无 migration 来源条目的账号，请求知识库条目列表或角色库卡列表
- **THEN** 系统先把该账号全部存量卡镜像为知识库条目（概念=角色设定，逐格映射与既有迁移端点一致），本次响应即包含迁移后的条目

#### Scenario: 迁移一次后自熄

- **WHEN** 该账号已存在 migration 来源条目时再次触达任一库域读面
- **THEN** 探测即返、不产生任何写入；作家在知识库中删除过的迁移卡 SHALL NOT 被复活

#### Scenario: 无存量账号零成本

- **WHEN** character_library 中该账号无任何行
- **THEN** 单次索引点查即返，不产生任何知识库条目写入
