## ADDED Requirements

### Requirement: openai 流式消息组包保留工具历史

OpenAI 兼容流式调用组包 SHALL 保留 messages 中的工具历史字段：assistant 行的 `tool_calls` 与 tool 行的 `tool_call_id` 原样下发；vendor=deepseek 时另保留 assistant 行的 `reasoning_content`（思考模式下带 tools 的历史回传要求）。未获能力位允许的 vendor SHALL NOT 收到 `reasoning_content`（避免未知字段被端点拒绝）。文本协议/不带 tools 的调用不受影响，消息仍按 role+content 下发。

#### Scenario: 工具历史保真
- **WHEN** 调用方传入含 assistant(tool_calls) 与 tool(tool_call_id) 行的历史
- **THEN** 实发请求的 messages 保留这些字段与值，不被压成纯 role+content

#### Scenario: DeepSeek 思考回传
- **WHEN** vendor=deepseek 且历史 assistant 行带 reasoning_content
- **THEN** 实发请求保留 reasoning_content

#### Scenario: 其它 vendor 不附加思考字段
- **WHEN** vendor 非 deepseek 且历史行带 reasoning_content
- **THEN** 实发请求不包含 reasoning_content，工具历史字段照常保留
