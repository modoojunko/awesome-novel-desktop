# storyline-settings

## MODIFIED Requirements

### Requirement: 归档域 schema 定稿（本 change 不实现）

- 主线进度与支线两条归档记录的 schema SHALL 按本 change 定稿：主线进度 `{ref, kind(event/revision), event, stage, note, review, created_at}`（幂等键=(ref,kind)，stage 枚举外值回退「发展」并原文记 note，审阅态统一叫 review，naive UTC，可审阅工作记录非只追加台账）；支线与伏笔台账合流（desc→description、intro_ref→introduced_in、生命周期→组归属、name/end_ref/review→新键，`kind:"subplot"` 新键用于注入过滤——支线注入独立预算（不挤占伏笔台账——台账 active 全量注入，≤8 上限已退役），hooks.priority 为数字串不得复用为「支线」标注）
- 本 change SHALL NOT 建归档表、不出归档界面；建表与录入/审阅交互随「正文归档」change

#### Scenario: 归档零实现
- **WHEN** 本 change 交付
- **THEN** 无归档表、无归档界面元素；主线进度/支线 schema 以设计文档形式留档供「正文归档」change 直接引用
