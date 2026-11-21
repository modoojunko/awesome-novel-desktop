## Why

过程卡已经有了（思考/工具/正文顺序、默认单行折叠、点开展全文、落盘回看），但 coding agent 还差一行**总体进度**：现在只能从每张卡的状态猜「跑到第几 步、等了多久、当前在干嘛」。spec 的「生成中态（阶段行＋已等秒数）」也只落了半截。补一行实时状态（当前动作/第 N 步/已等秒数）＋工具卡展开可见本步参数，整个过程才完整。

## What Changes

- 过程卡列首新增 `trace_status` 行（非折叠）：生成中显示「运行中 · 当前动作 · 第 N 步 · 已等 Xs」；收口显示「完成/已停止 · N 步 · 用时 X」。
  - 数据全部来自真实事件：步骤数＝已完成的工具步数，当前动作＝正在执行的工具/思考中/整理回答/等待模型/等待授权（授权卡停车时），秒数＝本轮起始至今；不渲染假进度。
  - 计时在组件内 `setInterval`（live 时），不靠每秒 SSE；收口停表。
  - 回放显示「完成 · N 步」（无逐秒计时，payload 不存起止时刻）。
- 工具卡展开新增「参数」行：取 `step_end.args` 的截断 JSON 预览（≤600 字），与「打算/结果/模型调用」并列；process payload 增 `args` 预览，回放同样可见。
- 前端过程缓冲从 `{items}` 扩为 `{items, live, startedAt, endedAt, failed, waiting, replying}`；提交时即出状态行（不再等第一个 thinking/step）；正文开流切「整理回答」；授权卡下发即显示「等待授权」，批复后恢复。
- 测试：状态行 live/finish/回放、步骤计数、计时（fake timers）、工具参数展开、payload args。
- 不做：不显示完整工具原始输出（事件只有 summary）；不做全局进度条（步数未知）；不改正文/思考/工具卡既有顺序。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `assistant-chat-ui`: 新增「过程进度行与工具参数」要求（实时总进度一行＋工具参数预览；真实事件驱动）。

## Design Impact

- **受影响端**：C端前端（Aui2Dock/chat.css）＋后端 process payload（args 预览增项）；无 S端、无共享设计段、无原型（dock 内部，沿用 OperateCard/token）。
- **对象状态**：运行中/完成/已停止；当前动作（思考中/执行工具/整理回答）；步骤数/已等秒数。
- **设计工件**：无（沿用既有状态语言与卡面，新增一行轻量状态条）。

## Impact

- `client/frontend/src/components/novel/chat/Aui2Dock.tsx`（过程缓冲/状态卡/工具参数）
- `client/frontend/src/components/novel/chat/chat.css`
- `client/frontend/src/lib/chatApi.ts`（AgentEvent.args）
- `client/backend/assistant/router.py`（process item args 预览）
- 测试：`Aui2Dock.test.tsx`、`test_assistant_chat_stream_http.py`
- 无数据/API/schema 迁移；payload 增项向后兼容。
