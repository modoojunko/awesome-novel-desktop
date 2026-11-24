## ADDED Requirements

### Requirement: assistant-execute 执行能力键

`lib/features.ts` SHALL 在 FeatureKey 词汇表新增 `assistant-execute`，`FEATURES` 注册表 minTier 为 `standard`；`minTierOf("assistant-execute")` 返回 `"standard"`，`isMemberFeature` 为 true。快照存在时，执行可用性 SHALL 由快照 features 是否含该键判定；快照缺失或字段不全时 SHALL 按兜底口径**未授权**处理（锁定），MUST NOT 因快照缺失默认放行。

#### Scenario: 免费快照锁定执行
- **WHEN** 快照 features 不含 `assistant-execute`（免费/none）
- **THEN** `useFeature("assistant-execute")` 返回 false，助手执行类入口呈锁定态

#### Scenario: 标准起快照放行
- **WHEN** 快照 features 含 `assistant-execute`（standard/pro/max/trial）
- **THEN** `useFeature("assistant-execute")` 返回 true，执行可用性交由授权梯度继续管控

#### Scenario: 快照缺失按锁定兜底
- **WHEN** 本地无完整快照且重同步不可得
- **THEN** `assistant-execute` 视为未授权（false），不因缺数据放行执行

#### Scenario: 旧客户端兼容
- **WHEN** 旧客户端收到含 `assistant-execute` 的快照
- **THEN** 未知键被忽略，不报错、不影响既有功能判定
