# write-archive-meta-sync 变更（增量）

## ADDED Requirements

### Requirement: 归档联动写伏笔 mentioned 引用列

- 章节归档时，系统 SHALL 把「本章引入的活跃伏笔」的 mentioned_in_chapter_id 更新为当前章 id（单条 UPDATE，替代旧「整文件读改写 status:mentioned」的做法）。
- 伏笔 status 枚举（active/resolved/abandoned）SHALL NOT 被归档联动修改；mentioned_in_chapter_id 仅作归档留痕，不参与注入与门禁判定。
- 归档联动 SHALL 幂等：重复归档同一章不改变已写入的引用。

#### Scenario: 归档本章给引入伏笔打上引用

- **WHEN** 归档第 3 章，且某活跃伏笔的 introduced_chapter_id 指向第 3 章
- **THEN** 该伏笔的 mentioned_in_chapter_id 被置为第 3 章的 id，status 仍为 active

#### Scenario: 归档其他章不误伤

- **WHEN** 归档第 5 章，而某伏笔引入于第 3 章
- **THEN** 该伏笔的 mentioned_in_chapter_id 保持不变

#### Scenario: 重复归档幂等

- **WHEN** 同一章被归档流程执行两次
- **THEN** 相关伏笔的 mentioned_in_chapter_id 值不变，status 不变
