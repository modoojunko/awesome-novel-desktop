# world-settings 变更（增量）

## REMOVED Requirements

### Requirement: lore-keeping 随归档生长

**Reason**: 归档建议「stateless 不落库＋面板暂存区＋不采纳即丢弃」的旧口径由 archive-reconcile 的收尾提案制取代（用户拍板：产出一律待确认，不确认不进全书）。
**Migration**: 新契约见本变更 ADDED 的「lore-keeping 随归档生长（提案制）」；lore-apply 的 (key, origin) 幂等语义原样保留，既有已入账条目不受影响。

## ADDED Requirements

### Requirement: lore-keeping 随归档生长（提案制）

- 归档章节时系统 SHALL 产出世界要素建议，**经后台收尾提案制落 `chapter_reconcile` 待确认行（kind=lore）**——覆盖 history/extra/factions 条目集（`set` 归属随建议给出，缺失/非法回落 extra）；段落型 01-03 SHALL NOT 被改写；人物变化 SHALL 由收尾的出场引用状态变化承载（char_states），不在本建议内。
- 建议 SHALL NOT 随归档响应即焚、SHALL NOT 进入任何面板暂存区：归档响应不再携带建议列表；采纳统一在「操作」页签的收尾区逐条确认。
- 建议条目 SHALL 带章节来源 origin；采纳经 `POST .../reconcile/{id}/accept` 走 lore-apply 幂等合并（同一 origin 重复归档/重跑 SHALL NOT 产生重复条目，同章同类未决提案 SHALL 覆盖而非堆积）。
- lore 建议 SHALL 与「归档生成章节摘要」偏好互相独立（均只看会员门控）。

#### Scenario: 归档产生提案行（不随响应即焚）
- Given 会员用户归档第 12 章且本书模型就绪
- When 后台收尾完成
- Then 世界要素建议以 kind=lore 的待确认行出现在该章「操作」页签；归档响应本身不含建议列表

#### Scenario: 采纳入账幂等
- Given 一条 kind=lore 待确认提案（origin=第 12 章）
- When 作者点「采纳」，随后同名目同来源的条目再次入账
- Then 世界设定仅一条该条目（(key, origin) 幂等），提案行标记已采纳

#### Scenario: 驳回不入账且留痕
- Given 一条 kind=lore 待确认提案
- When 作者点「驳回」
- Then 世界设定不变、后续写章不引用该条；提案行标记已驳回（留痕，不再出现待确认计数）
