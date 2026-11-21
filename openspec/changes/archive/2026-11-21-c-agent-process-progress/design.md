## Context

见 `proposal.md`。当前过程卡（#1108）已按事件顺序挂 assistant 消息 cards；工具卡头有 running 状态，但没有总进度。`step_end` 事件带 `args`，前端未用、process payload 未存。

## Goals / Non-Goals

**Goals:**
- 一行实时总进度（当前动作/第 N 步/已等秒数），收口变完成/用时；回放只显示步数。
- 工具卡展开可见参数预览；参数随 process 落盘。
- 零假进度：一切由真实 step 事件与起始时刻推导。

**Non-Goals:**
- 不做百分比进度条（总步数未知）；不展示完整工具原始输出（事件只有 summary）。
- 不改思考/工具卡既有折叠与顺序；不改后端 SSE 事件类型。

## Decisions

### 1. 状态行由前端过程缓冲派生
把 `procBufRef` 从 `{items}` 扩为 `{items, live, startedAt, endedAt, failed, waiting, replying}`；`toProcCards` 在列首插 `trace_status` 卡。步骤数＝tool items 数；当前动作＝等待授权（gate 停车）/ running tool / 最后一个 live thinking / 整理回答（正文开流或有过程项）/ 等待模型（提交后正文开流前）；回放 `processCardsFromPayload` 也插一张 `live:false` 的状态卡（只有步数）。
- 理由：所有数据已在现有事件/缓冲里；状态行随卡列同一 `threadUp` 更新，不需要每秒 SSE。
- 备选：后端发 progress 事件（需要新事件类型/心跳，过度）。

### 2. 计时在组件内
`TraceStatusCard` 在 `live` 时 `setInterval(1s)` 本地重渲染；`endedAt` 由 onDone/onError 写入缓冲；组件 live=false 停表。回放无 startedAt 不显示秒数。
- 理由：计时是纯展示，不该驱动 ChatAnywhere 重渲染/落盘。
- 备选：每秒 upsert 卡数据（浪费）。

### 3. 工具参数预览
`step_end.args` 前端截断 JSON 预览（≤600）写进 tool item；后端 `_consume` 同口径写 process item `args`（payload 增项）。工具卡 body 增「参数」行，等宽小字、可滚动。
- 理由：coding agent 要能看工具入参；截断防大字段撑卡；回放一致。
- 备选：完整 args 落盘（写工具可能带整段正文，撑会话文件，否决）。

### 4. 状态行样式
一行轻量：小图标（spinner/check/stop）＋文字，`font-size:12px`、`color:var(--muted)`、无重卡边框；与过程卡区分。所有色值走既有 token。

## Risks / Trade-offs

- [计时依赖前端本地时钟] → 仅展示用；前后端时钟差无影响（都用同一浏览器 Date.now）。
- [args 可能含长文本] → 600 字截断；完整内容仍在工具回执/产物卡。
- [状态行在回放无用时] → 只显示步数，明确不伪造时长。

## Migration Plan

- 纯前端展示＋payload 增项，无迁移；旧会话回放无 args/状态时长，只显示步数。

## Open Questions

（无）
