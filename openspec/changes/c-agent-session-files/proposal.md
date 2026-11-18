# c-agent-session-files：助手会话改 coding-agent 式文件存储

## Why

boss 拍板（2026-11-18）：agent 的 session 要像 coding agent 一样存安装目录下的 session 目录，按 id+日期存文件。

现状：助手会话存 SQLite 两表（assistant_sessions/assistant_messages）。考古：这套机制本来就移植自 OpenWorker 的「每会话 JSONL append-only」，批A 时改成了 DB 表——现在改回文件形态，OpenWorker 原版机制（id 白名单/append-only/自愈/整段重写）当年全留了语义注释，平移有蓝本。文件化的直接收益：作家会话可直读可备份（像 .claude/projects 一样肉眼可查）、删库不丢对话、与 coding agent 心智一致。

## What Changes

- **存储载体切换**：`DATA_ROOT/sessions/<novel_id>/` 目录，文件名 `<日期>__<thread>__<session_id>.jsonl`（id+日期口径）；JSONL append-only——首行 meta（thread/novel/user/grants/page_cursor/compaction/时间戳），后续每行一条消息/事件
- **session_store 平移为文件后端**：对外函数签名保持（get_or_create/load_messages/append_message/update_message_status/touch_session/compaction/reset），router 调用面零变化；db 参数退役
- **/new 语义对齐 coding agent**：新开会话＝新文件（新 session id＋当天日期），旧文件留档不删——「session 目录里能看到历史」正是文件化的意义
- **存量迁移**：启动一次性迁移——DB 两表读出写 JSONL，DB 行保留作归档备份（代码不再读）；迁移幂等（目标文件已存在即跳过）
- **自愈平移**：加载时悬挂 streaming 行收尾为 error（现逻辑平移）；崩溃尾半行容忍（JSONL 惯例，读时跳过）

## Capabilities

### New Capabilities
- `assistant-session-files`——助手会话文件存储：目录布局、文件契约、迁移、解析与自愈

### Modified Capabilities
<!-- 无：assistant-effects / assistant-nav / writing-assistant 的行为契约不变；本 change 只换会话持久化载体 -->

## Impact

- 受影响端：C端（S端无关；不触碰两端共享段；不碰令牌/组件词汇/状态语言——无 UI 变化）
- 受影响屏：无新屏；助手对话回看（GET /session）返回契约不变，前端零改动
- 数据面：`DATA_ROOT/sessions/` 新目录；DB 两表停止读写（保留存量归档）；writer_profile/memory/decisions 等其余六表不动
- 原型先行：否（纯存储层，无视觉）
- 设计工件：实现侧自查
- 风险点：会话解析从 UNIQUE 索引变目录扫描（每书线程 ≤10，代价可忽略）；写路径从事务变文件追加（单进程 asyncio 串行，无锁需求）
