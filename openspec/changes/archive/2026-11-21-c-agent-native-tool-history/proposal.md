## Why

DeepSeek 官方文档（思考模式/Tool Calls）明确：请求带 `tools` 时，历史轮次的 `tool_calls`、`tool_call_id` 与 `reasoning_content` **必须完整回传**；即使该轮未实际调用工具，漏回传也返回 400。当前 `AIClient.chat_stream` 在 openai 分支把 messages 压成 `{role, content}`，丢掉 `tool_calls`/`tool_call_id`；native 循环也没累积 `reasoning_content`。现有 native 测试用假 client 直接吃 messages，绕过了压扁，所以一直绿；真实 GLM/OpenAI 原生 FC 从第二步起就会残缺，强制 DeepSeek native 时更会 400。文本协议（DeepSeek 默认路径）不带 tools，不受影响。

## What Changes

- `AIClient.chat_stream`（openai 分支）组包 SHALL 保留 `tool_calls`、`tool_call_id`；DeepSeek vendor 另保留 `reasoning_content`（其它 vendor 不附加未知字段）。
- `AgentLoop` native 分支逐步累积思考文本，按 client 的「需要回传思考」能力位挂到 assistant 转写行（有工具调用的行与最终收口行都挂）；`build_outbound_window(native=True)` 透传 `reasoning_content`。范围＝**同一 run 的多步循环**；跨轮历史仍按既有 user/assistant 文本投影——DeepSeek 原生跨轮在 native 转写持久化前不启用（能力矩阵默认不路由），GLM/OpenAI 的跨轮文本投影不需要 reasoning 回传。
- `AIClient` 新增 `requires_reasoning_echo()` 能力位：openai 协议＋vendor=deepseek → True；避免把 DeepSeek 专用字段发给其它供应商。
- 补测试：工具历史组包保真（deepseek 带 reasoning_content、glm 不带）、native 两步循环第二次请求含 assistant 的 tool_calls/tool_call_id/reasoning_content、最终行也带 reasoning_content。
- 不变：文本协议（无 tools）不回传思考；会话落盘的 process 仍只用于 UI 回放。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `writing-assistant`: 「agent 循环为多步工具调用且受护栏约束」增加原生工具历史完整性契约与场景。
- `ai-client`: 新增「openai 流式消息组包保留工具历史」要求（tool_calls/tool_call_id/DeepSeek reasoning_content）。

## Design Impact

- **受影响端**：仅 C端后端（client/backend）；无前端/UI 改动，无 S端、无共享设计段、无原型先行。
- **对象状态**：无新增用户可见状态；错误面仍是既有 `error` 事件。
- **设计工件**：无（纯协议正确性修复，实现侧自查）。

## Impact

- `client/backend/ai_client.py`（chat_stream 组包、能力位）
- `client/backend/assistant/loop.py`（native 转写行挂 reasoning_content）
- `client/backend/assistant/context.py`（native 外发窗口透传）
- `client/backend/tests/test_ai_client_native_tools.py`、`tests/test_assistant_loop_native.py`
- 不影响现有会话文件/数据；无需迁移。
