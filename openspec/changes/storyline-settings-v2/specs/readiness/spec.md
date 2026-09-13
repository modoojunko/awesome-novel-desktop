# readiness arc（第 05 项主线）判据

## ADDED Requirements

### Requirement: arc 内容判据（第 05 项主线）

- arc SHALL 进 readiness 内容判据（与既有 7 项同表注册）：`story_arc.fullstory` 或 `ending{scene, hero, tone}` 任一非空即已填
- legacy 形状 SHALL 在读取边界归一后再判：legacy `premise` 非空即视为已填（迁移由存储层双写承载，判据只看归一后的形状）
- arc 全空 SHALL 报未填（中文），且空内容确认被后端 400 拒绝（沿「完成设定」判据，defaults 不适用于本项——主线无默认内容）

#### Scenario: 只有全景即已填
- **WHEN** 主线只填了 fullstory，三问全空
- **THEN** arc 不报缺失

#### Scenario: 只有基调即已填
- **WHEN** 主线只填了 ending.tone
- **THEN** arc 不报缺失

#### Scenario: legacy premise 书归一为已填
- **WHEN** 旧书 story_arc 只有 legacy premise 非空
- **THEN** arc 不报缺失

#### Scenario: 全空报未填
- **WHEN** 主线没有任何内容时点击「确认完成」
- **THEN** arc 报缺失（中文），确认被 400 拒绝
