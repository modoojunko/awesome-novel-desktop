## Context

见 `proposal.md`。当前三条链路决定实现方式：

- 思考能力已存在：`AIClient.chat_stream` 支持 `reasoning_content`/`thinking_delta`/内联 `<think>` 三来源，且支持调用方显式传 `thinking=` 压过配置；当前助手循环没传，所以跟随本书 API 配置（实测为关）。
- 模型按次覆盖对已存在：`get_ai_client_for_novel(novel_id, api_config_id=, model=)` 是正文生成弹窗的同款机制，校验（配置归属/未删/Key 可用/模型在清单）与流内可读错误都有先例。
- 会话是文件后端：assistant 行 payload 原样回放；工具行已有独立落盘，但 thinking 只发 SSE 不落盘（`router.py` 注释明示），回看必丢。

前端对话树由 `@agentscope-ai/chat` 的 ChatAnywhere 驱动：`Bubble` 先渲染 `cards` 再渲染 `content`，卡片按数组顺序排列，`updateMessage` 是浅合并。`OperateCard` 是同库的现成单行折叠卡（28px 头、点击展开、自带 title/description/icon/body），`ModelPicker` 是既有按配置分组的模型选择弹层。

## Goals / Non-Goals

**Goals:**
- 助手每轮思考开/关可控（默认开），模型可临时选择；两者都在输入底栏与授权 pill 同排。
- 思考与每次工具调用各自独立单行折叠泡泡，挂在本回合正文之上；正文干净。
- 思考与工具过程随回合落盘，切页签/重开书回看一致。
- 所有新 UI 使用库现成组件与既有 pill/令牌，不新增视觉形态。

**Non-Goals:**
- 不把助手模型选择写入本书绑定，不影响写作链路。
- 不引入新的 SSE 事件类型（沿用 thinking/step_start/step_end 等）。
- 不迁移旧会话；旧会话继续用既有「运行轨迹」折叠卡回放。
- 不做服务端持久化的用户偏好（思考/模型选择按线程存 localStorage）。

## Decisions

### 1. 思考开关走「显式按次参数」，不复用/改写 API 配置
`POST /assistant/chat` body 新增 `thinking: bool`；`LoopConfig` 增 `thinking: dict | None`，text/native 两分支都传 `chat_stream(thinking=...)`。
- 理由：已有 `_explicit_thinking_params` 与「显式传 thinking 时配置强度不搭车」的既有契约；端点拒绝时已有去参重试记忆，不会打断对话。默认开只影响助手，写作仍按配置。
- 备选：改 API 配置的 `thinking_enabled`（影响全书写作，否决）；新增助手专属配置项（要 DB/UI/迁移，超出本次范围）。

### 2. 模型选择走既有「按次覆盖对」，不落库
前端把选中的 `api_config_id+model` 随消息带上（等于本书模型时不发），`_stream_chat` 用它构造 client；校验失败走现有 `client_error` gate 流内提示。
- 理由：与正文生成弹窗同一语义/同一校验谓词，零新表；`client.resolve("haiku")` 与用量记账自动落到覆盖模型。
- 备选：写入 `grants`（要新增/改会话元数据与线程语义）；直接改本书绑定（会改写作模型，违背「只作用助手」）。

### 3. 过程用「每项一张卡」挂 assistant 消息，而不是一个组卡
`thinking` 事件 → 一张思考卡；`step_start` → 一张 running 工具卡；`step_end` → 原位补 note/ok/apiCalls。卡片数组按发生顺序放进本轮 assistant 消息的 `cards`，ChatAnywhere 先卡后正文。
- 理由：直接满足 boss「思考一个泡泡、每次工具一个泡泡、默认单行、点开全文、和正文区分」；卡片在正文之上是库的渲染顺序，无需自造布局。
- 备选：单张「思考与轨迹」组卡（当前实现，被否决）；独立消息（当前 trace 卡的做法，正文下方、回看顺序错）。

### 4. 视觉用 OperateCard，交互态自己控
两类卡都用 `OperateCard` + `OperateCard.LineBody`；图标用 `@agentscope-ai/icons` 的 loading/check/error/stop。思考卡头「思考中/思考过程」，工具卡头「工具名 + 一行摘要」；body 显示打算/结果/模型调用。
- 理由：库组件 28px 单行头、默认折叠、点击展开、title/description 自带 ellipsis，正好是 coding agent 的过程行；无远程图标依赖。
- 备选：`Accordion`（组卡形态）、`DeepThinking`（远程 apng 图标且自动塌陷，不满足「用户展开不丢」）。

### 5. 过程落盘在 assistant 行的 payload.process
`router._consume` 维护有序 items；`_finalize` 写入本轮 assistant 行 payload（`update_message_status` 增 payload 合并）；回放时 assistant 行带 process 就生成同样的卡片，并抑制该回合后续旧 tool 行的轨迹折叠。未收口的 running 项标 interrupted。
- 理由：一个回合一条消息、顺序天然正确；旧 tool 行继续保留给撤销/审计；旧会话零迁移。
- 备选：新建 process 表（迁移成本高）；把 process 写进 content（污染模型历史/复制）。

### 6. 底栏三控件同排，偏好按线程存 localStorage
`morePrefixActions` 放 `[模型 pill] [深度思考 pill] [授权 pill]` 的 flex-wrap 容器；模型 pill 复用 `ModelPicker`，思考 pill 为 `aria-pressed` 按钮；键按 `projectId:threadKey` 存 localStorage，挂载/切线程时读取。
- 理由：`footer` 插槽会另起一行（#1103 已踩），`morePrefixActions` 与发送同排；localStorage 是既有 UI 偏好载体（pack 弹窗/已读徽标同款），无需服务端迁移。
- 备选：写 grants（跨端持久但改会话语义）；新设置页（超出范围）。

### 7. 思考预算与容量口径
`ASSISTANT_STEP_MAX_TOKENS` 2048→4096（思考与动作 JSON 共用 max_tokens，防截断；env 仍可覆盖）；thinking 不再累加 `estCharsRef`（思考不进外发窗口，避免容量条虚高）。
- 理由：默认开思考后，2048 可能被 reasoning 吃掉导致 JSON 截断；容量条应反映真实外发窗口。

## Risks / Trade-offs

- [OperateCard 在窄 dock 的视觉与折叠态不符合预期] → 先用库默认 + 少量容器边框 CSS；真机走查不过就退回同库 `Accordion`（数据结构不变）。
- [默认开思考增加每步延迟与 token] → 底栏开关可即时关闭，只影响助手；step 预算有 env 兜底。
- [模型覆盖对因 Key 测试失败被拒] → 流内 readable gate 明示原因，作家可重选/切回本书模型，不静默替换。
- [旧会话与新会话回放形态不同] → 有 process 的回合用新泡泡；无 process 的旧回合保留原「运行轨迹」卡（含 ×N 去重），测试双态都钉。
- [卡片数组每次事件重建导致展开态丢失] → 卡片 id 稳定（`think-<n>` / `tool-<stepId>`），React 复用实例；只有 live→done 的思考头文字变化，不 remount。

## Migration Plan

- 无数据迁移：payload.process 是新增键，旧代码忽略、旧会话无该键走旧回放。
- 上线顺序：后端先发（body 新字段可选、payload 增项兼容）→ 前端发（发送新字段/渲染新卡）。
- 回滚：前端回滚后旧 UI 忽略 cards；后端回滚后旧 UI 忽略 payload.process，均不影响会话可读。

## Open Questions

（无）
