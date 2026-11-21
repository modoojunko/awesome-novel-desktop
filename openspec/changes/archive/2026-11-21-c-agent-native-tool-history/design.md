## Context

见 `proposal.md`。关键现状（`client/backend/ai_client.py` openai 分支）：

```python
for m in messages:
    openai_messages.append({"role": m["role"], "content": m["content"]})
```

`assistant/context.py::build_outbound_window(native=True)` 已经把 `tool_calls`/`tool_call_id` 放进窗口，但 `chat_stream` 组包时又丢掉；native 循环的 assistant 行也没 `reasoning_content`。现有测试用假 client 绕过组包，故未暴露。

## Goals / Non-Goals

**Goals:**
- 真实 openai 协议端点的原生 FC 多步循环不再因历史残缺 400。
- DeepSeek 带 tools 时按官方要求回传 reasoning_content；其它 vendor 不沾这个字段。
- 文本协议/无 tools 路径行为零变化。

**Non-Goals:**
- 不改前端/UI/会话文件格式（process 仅 UI 回放）。
- 不新增 native 供应商白名单（DeepSeek 仍默认 text；本修复让强制/未来启用时可用）。
- 不处理 anthropic 协议的 thinking block/signature（native 仅 openai 协议）。

## Decisions

### 1. 组包保留工具字段，不重建消息
`chat_stream` 复制消息时保留 `tool_calls`/`tool_call_id`；`reasoning_content` 仅当 `requires_reasoning_echo()` 为真（openai＋vendor=deepseek）才保留。
- 理由：OpenAI 协议要求 tool 行带 `tool_call_id`、assistant 行带 `tool_calls`；DeepSeek 文档要求带 tools 时历史 reasoning_content 完整回传。未知字段只发给明确支持的 vendor，避免其它端点 400。
- 备选：调用方传完整 OpenAI SDK 消息对象（改动面大、类型不兼容）。

### 2. native 循环在转写行挂 reasoning_content（同一 run 多步）
逐步累积 `ev.thinking`；仅当 `self._reasoning_echo`（client 能力位）为真时，写进 assistant 行的 `reasoning_content`（工具调用行与最终收口行都写）。
- 理由：同 run 的下一步 native 请求需要按步回传；只挂最后一条不够。
- 边界：跨轮历史仍按 `_history_transcript` 的 user/assistant 文本投影；DeepSeek 原生跨轮需要持久化 native 转写（tool_calls/step reasoning），另立项；当前能力矩阵不默认路由 DeepSeek native。
- 备选：只挂工具调用行（文档明确最终行也要回传，否决）。

### 3. `build_outbound_window(native=True)` 透传 reasoning_content
- 理由：外发窗口是唯一组装点；只改 chat_stream 不够，窗口层会先丢。
- 文本协议分支保持只 role+content。

### 4. 能力位放在 AIClient
`requires_reasoning_echo()`：`_provider=="openai" and vendor=="deepseek"`。
- 理由：循环不感知 vendor 细节；测试 fake 无该方法时 `getattr` 默认 False，旧测试零改动。

## Risks / Trade-offs

- [其它 OpenAI 兼容端点也要求 reasoning_content] → 目前只按官方文档对 DeepSeek 回传；后续有实证再扩能力位。
- [compact 窗口保留 tool_calls 但丢 reasoning_content] → `build_outbound_window` 只透传存在字段；compact 的保留段是原行，字段随行保留；摘要段无 tool_calls。若未来 compact 重建 assistant 行，需同批带上 reasoning_content。
- [native 仍默认不对 DeepSeek 启用] → 本修复是前置条件，不改变路由白名单；同 run 多步已修，跨轮 DeepSeek native 仍需 native 转写持久化（另立项）。
- [prime 首步是服务端合成的 tool_calls 行，没有模型 reasoning_content] → GLM/OpenAI 不受影响；DeepSeek 强制 native 的 prime 路径不在保证范围（默认不路由），需要时另补占位/持久化策略。

## Migration Plan

- 纯请求组装修复，无数据迁移、无 API/schema 变化。
- 回滚：还原 `chat_stream` 组包与 native 行字段即可；不影响已落盘会话。

## Open Questions

（无）
