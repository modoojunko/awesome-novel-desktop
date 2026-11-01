## ADDED Requirements

### Requirement: 单书备份书级知识段

单书备份 SHALL 携带书级知识副本（条目行＋物化标签投影），恢复 SHALL 重建书级副本并重建标签索引；兼容键不升 format_version（旧导入端忽略未知段）。

#### Scenario: 换机恢复书级知识

- **WHEN** 单书备份在换机后恢复
- **THEN** 本书副本条目与标签索引重建，写法块选择行为与备份前一致
