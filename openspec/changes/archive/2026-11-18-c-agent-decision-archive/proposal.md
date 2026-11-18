# c-agent-decision-archive：决策档案分层记忆——半年前的决定不忘

## Why

boss 问（2026-11-18）：会话分成文件后，半年前作家做的决定，近期 agent 还记不记得？

现状盘点：书级决策（remember_decision 工具落的 DB 表）跨会话注入系统提示词，但注入预算只有 1200 字、超限**从最旧截断**——决定条数一多，半年前的（最旧）先被挤掉；模型当时忘调 remember 的更是压根没进记忆。会话文件化后原始对话永不丢，但「存了≠想得起来」——没有注入与召回，等于存在磁盘里的遗忘。

方案（boss 拍板立项）：coding agent 同构的分层记忆——**决策档案文件化永不截断＋注入降级为索引＋按需召回工具**。CLAUDE.md 三件套的等价物：常驻摘要＋全量在盘＋agent 自己读。

## What Changes

- **决策档案文件化**：`DATA_ROOT/decisions/<novel_id>.jsonl` append-only 全量留档（id/decision/reason/created_at），永不截断——半年前的决定原文永远在
- **决策写路径切文件**：add_decision/list_decisions 改文件后端（remember_decision/recall_book_memory 工具与 delete_book_memory 删书级联同步）；DB book_decisions 表存量启动迁移（幂等＋fail-soft，行保留归档）——套路与 c-agent-session-files 完全一致
- **分层注入**：render_memory_section 从「截断丢弃」改为「预算内最近决策全文 → 超预算老决策降级一行索引（日期＋一句话）→ 尾注告知在档总数」——模型看索引知道缺什么，不会幻觉「没有这条决定」
- **新工具 recall_decisions**：按关键词/时间从档案拉历史决策全文（文件小，子串过滤即可，不引向量库）；read 类免授权，进共享读集合

## Capabilities

### New Capabilities
- `assistant-decision-archive`——决策档案：文件契约、分层注入、召回工具、迁移

### Modified Capabilities
<!-- 无：assistant-effects/assistant-nav 不受影响；记忆注入段是 assistant 会话系统提示词的内部组成，writing-assistant spec 未对决策注入立 Requirement -->

## Impact

- 受影响端：C端（S端无关；无 UI 变化；不触碰两端共享段与设计语言）
- 数据面：`DATA_ROOT/decisions/` 新目录；DB book_decisions 表存量迁移后归档不再读写；book_agent_memory（写作规矩 800 字层）本 change 不动
- 行为面：注入段新增索引行与尾注（系统提示词内部文本，非用户可见 UI 文案——口径仍守念出声红线，索引用作家词汇不出现内部术语）
- 原型先行：否（纯后端存储与注入逻辑）
- 风险点：索引行预算需设上限（防老决策太多撑爆提示词）；召回工具输出需截长（单条超长决策裁剪）
