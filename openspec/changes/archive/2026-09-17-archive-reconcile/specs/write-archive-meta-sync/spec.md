# write-archive-meta-sync 变更（增量）

## MODIFIED Requirements

### Requirement: 归档联动写伏笔 mentioned 引用列

- 章节归档时，系统 SHALL 把「本章引入的活跃伏笔」的 mentioned_in_chapter_id 更新为当前章 id（单条 UPDATE，替代旧「整文件读改写 status:mentioned」的做法）。
- 伏笔 status 枚举（active/resolved/abandoned）SHALL NOT 被归档联动修改；mentioned_in_chapter_id 仅作归档留痕，不参与注入与门禁判定。
- 归档联动 SHALL 幂等：重复归档同一章不改变已写入的引用。
- 伏笔的「埋下/收束」登记 SHALL NOT 由归档联动自动写库：归档收尾对「本章埋下/本章收束」产出**待确认提案**（含证据句），作者采纳后经伏笔服务写入；mentioned 留痕不受提案制影响。
- 归档联动即刻生效部分 SHALL 保持：archives 行、threads 状态更新、章状态迁移；AI 收尾类联动（设定变化提取/关系建议/伏笔登记/lore 建议/角色状态变化）SHALL 改为后台提案制（落 chapter_reconcile 待确认行），SHALL NOT 随归档响应即焚，SHALL NOT 未确认即写对象；归档响应 SHALL 返回收尾任务标识而非内联建议列表。

#### Scenario: 归档本章给引入伏笔打上引用

- **WHEN** 归档第 3 章，且某活跃伏笔的 introduced_chapter_id 指向第 3 章
- **THEN** 该伏笔的 mentioned_in_chapter_id 被置为第 3 章的 id，status 仍为 active

#### Scenario: 归档其他章不误伤

- **WHEN** 归档第 5 章，而某伏笔引入于第 3 章
- **THEN** 该伏笔的 mentioned_in_chapter_id 保持不变

#### Scenario: 重复归档幂等

- **WHEN** 同一章被归档流程执行两次
- **THEN** 相关伏笔的 mentioned_in_chapter_id 值不变，status 不变

#### Scenario: 埋下/收束走提案而非自动写库

- **WHEN** 归档第 3 章，AI 判断「本章埋下伏笔 X」「本章收束伏笔 Y」
- **THEN** 产生两条伏笔登记类待确认提案（含证据句），X/Y 的 status 与引用列不被自动修改；作者采纳 X 后经伏笔服务写入

#### Scenario: lore 建议不再即焚

- **WHEN** 归档一章且 AI 识别出两条世界要素建议
- **THEN** 两条建议成为待确认行，作者稍后在收尾区采纳（走 lore-apply 幂等合并），关闭页面不丢失

#### Scenario: 角色状态变化落出场引用

- **WHEN** AI 收尾提取出「沉舟：从犹豫到决意」
- **THEN** 该章出场引用行（沉舟）的 state_change 被写入/覆盖，legacy YAML（character-setting/*.yaml 的 state_history）不再追加
