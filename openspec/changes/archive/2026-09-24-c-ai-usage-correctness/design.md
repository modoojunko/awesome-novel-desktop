## Context

见 proposal.md。落地相关现状（实勘）：

- `api_configs/usage.py:41-44`：`db.add` → `await db.commit()` → `except: await db.rollback()`——rollback 丢弃同会话全部暂存写入，且无日志。
- `novels/events.py:56-70`：`log_event_async` 同型（有 warning 日志但 rollback 同样连带）；同步版 `log_event` 直接 commit 无守卫。
- `ai_client.py:337-346`：`chunk.choices[0].delta` 裸取；done 事件 `tokens = usage.total_tokens`。`:361-370`：anthropic 只取 message_stop 的 output_tokens。
- 消费方：`write/router.py:104`、`write/auxiliary.py:190` 记 `tokens_out=event.tokens`。
- `_NETWORK_ERRORS`（:44）不含 IndexError——越界异常直接向上炸。

## Goals / Non-Goals

**Goals:**

- 记账/埋点失败的事故半径收敛到自身（SAVEPOINT），且可观测（warning 日志）。
- 流式 token 记账方向正确（in/out 拆分），usage-only 块与空流不炸。

**Non-Goals:**

- 不改 36+ 既有调用点的顺序约定（记账先于主写入仍是推荐姿势）。
- 不给 StreamEvent 增加重试/缓冲语义。
- 不为 events 埋点新增 capability 规格（无既有 capability 承载，写入路径与 usage 同批修，行为以测试钉住）。

## Decisions

**D1：`begin_nested()` SAVEPOINT 包住 add/flush；成功后仍显式 `commit()` 外层。**
保留既有「记账即提交」的时序副作用（36+ 调用点依赖），只在失败路径把回滚半径收到 savepoint。备选（已弃）独立 session 记账——需要跨会话传递连接配置且改变提交时序。

**D2：`StreamEvent` 增加 `tokens_in` 字段，`tokens` 语义收窄为输出侧。**
OpenAI done：`completion_tokens`（缺省回退 total）；anthropic：`message_start.usage.input_tokens`＋`message_stop.usage.output_tokens`。消费方两处补 `tokens_in=event.tokens_in`。

**D3：usage-only 块判空跳过；用量在循环内随块捕获。**
不再依赖循环变量在循环后仍可用的偶然行为（空流时旧实现会 NameError）。

## Risks / Trade-offs

- [savepoint 在 SQLite aiosqlite 上的兼容性] → SAVEPOINT 是标准能力；迁移/备份路径已用同机制（begin_nested）无问题。
- [tokens 语义收窄改变存量统计口径] → 旧口径本身错误（total 记输出侧）；切换只影响增量数据，历史行不回改。

## Migration Plan

分支内实施；无数据迁移；回滚 = revert 提交。
