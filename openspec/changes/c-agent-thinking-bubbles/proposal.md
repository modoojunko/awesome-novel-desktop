## Why

截图里「思考与轨迹（进行中）」只有 `read_settings ✓` 一行，思考内容没体现。实锤根因有三层：书的模型配置 `thinking_enabled=0`（llm.log 全部 `thinking_chars=0`，但同配置显式带 `thinking:enabled` 实测能流出 reasoning_content）；思考事件只发 SSE 不落盘（回看必丢）；过程信息挤在一张正文下方的轨迹卡里，正文还重复追加 `● tool ✓` 文本行。boss 拍板：助手要完全对齐 coding agent 的过程呈现——思考、每次工具调用各自独立泡泡，默认单行、点开看全文，和正文区分；输入底栏与授权 pill 同排增加「深度思考」开关和模型选择。

## What Changes

- 助手输入底栏新增一行控制条（与现有授权 pill 同排）：**助手模型选择**（默认本书模型，选择只作用于助手对话、不改本书写作模型）＋**深度思考开关**（默认开，独立于模型配置的思考开关）。
- 对话流内新增两类独立过程泡泡（挂在回合气泡内、正文之上）：
  - **思考泡泡**：默认单行「思考中/思考过程」，点开看全文；实时增量更新同一条。
  - **工具泡泡**：一次调用一张，默认单行（工具名＋一行摘要），点开看打算、结果、本步模型调用；运行/成功/失败/打断各有状态。
- 正文不再追加 `● tool ✓` 文本行；思考不再计入上下文容量估算（思考不进外发窗口）。
- 思考与工具过程随本轮 assistant 消息落盘，重开书/切页签可原样回看；旧会话仍走既有「运行轨迹」折叠卡回放。
- 助手每轮可带 `thinking` 与 `api_config_id+model` 覆盖对；按次模型校验失败走现有流内可读 gate，不静默换模型。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `assistant-chat-ui`: 输入区控制条（模型/思考/授权三控件）常显可切；思考与工具各自独立单行折叠泡泡；正文与过程分离；过程落盘回看。
- `writing-assistant`: 流式事件呈现契约改为「思考泡泡 + 每工具一步泡泡 + 正文」；思考/工具过程随回合持久化、SHALL NOT 丢弃；思考开关优先级（显式按次开关 > API 配置）。
- `intro-genre-settings`: 模型书级粒度新增一个显式例外——助手对话可按会话选择按次覆盖模型，默认本书模型，不改本书绑定、不影响写作链路。

## Design Impact

- **受影响端**：仅 C端（client/frontend + client/backend）；不触 S端、不触两端共享段（base.css 令牌、pill/notice/sk/panel/f-err 家族均零改动）。
- **受影响屏/弹层**：工作台助手 dock（输入底栏 + 对话流过程卡）；不新增页面/弹层——模型选择复用既有 `ModelPicker` 分组弹层，思考开关为同排 pill。
- **对象状态**：思考中 / 思考完成（折叠可展开）；工具运行中 / 成功 / 失败 / 打断；深度思考开 / 关；模型＝本书模型 / 按会话覆盖。语气沿用现有 info/ok/warn/err，不新增胶囊形态、不新增字号档位、不引入裸 hex/emoji。
- **原型先行**：本改动落在助手 dock 内部，不在 `docs/design-c/prototypes/` 四屏 parity 基线（list/book/model-config）覆盖范围内；设计依据＝boss 2026-11-21 截图与文字拍板（过程单行折叠、点开全文、与正文区分、底栏三控件同排）。不需要改原型文件；实现侧按 `@agentscope-ai/chat` 现成组件落地，回归以 design:lint/design:check 取证。
- **设计工件产出**：实现侧自查（boss 指令即设计依据），无设计侧会话交付物。

## Impact

- 后端：`assistant/router.py`（body 新增 `thinking`/`api_config_id`/`model`；process 收集与落盘）、`assistant/loop.py`（`LoopConfig.thinking` 透传；step token 预算）、`assistant/session_store.py`（收尾 payload 合并）。
- 前端：`components/novel/chat/Aui2Dock.tsx`（底栏三控件、过程卡事件映射、回放）、`chat.css`、`lib/chatApi.ts`（请求体类型）；复用 `workbench/modals.tsx` 的 `ModelPicker` 与 `@agentscope-ai/chat` 的 `OperateCard`、`@agentscope-ai/icons`。
- 数据：会话 JSONL 的 assistant 行 payload 新增 `process`（思考/工具有序项）；旧会话零迁移、零影响。
- API：`POST /assistant/chat` 新增可选 body 字段；不新增端点、不改响应 schema（payload 增项向后兼容）。
- 依赖：无新依赖（`@agentscope-ai/chat`/`icons` 已在包内）。
