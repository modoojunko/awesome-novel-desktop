## ADDED Requirements

### Requirement: 退役字段硬拒清单须完备

卷纲保存对「已退役字段」的显式拒绝清单 SHALL 覆盖全部已退役键（含 `plot_nodes`）：携带任一退役键 SHALL 返回 422 与可读文案，MUST NOT 静默忽略造成「请求成功但不落库」。清单演进 MUST 与规格退役声明同步。

#### Scenario: plot_nodes 显式携带被拒

- **WHEN** `PUT /volumes/{ref}` 携带 `plot_nodes`
- **THEN** 返回 422，文案指明该字段已退役；不出现 200 静默不落库

#### Scenario: 未携带退役键照常保存

- **WHEN** 正常卷纲保存（不含任何退役键）
- **THEN** 行为与既有口径一致（422 仅针对显式携带的退役键）
