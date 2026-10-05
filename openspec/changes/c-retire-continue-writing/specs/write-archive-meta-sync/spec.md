## REMOVED Requirements

### Requirement: 续写完成后刷新 DB 章元数据

**Reason**：AI 续写功能全链退役（c-retire-continue-writing）——`continue_writing`/`stream_continue` 已删除，续写后刷新 DB 章行的场景不复存在。

**Migration**：整章生成（`/write` POST）的落库刷新由「write_chapter 流完成刷新 DB 章元数据」requirement 承载，行为不变；历史续写产生的 `chapter_versions` 快照保留只读。
