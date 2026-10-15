# c-inline-think-strip

## Why

MiniMax M2/M3 系（OpenAI 协议原生格式）把思考内容以 `<think>…</think>` 内联在 `content` 字段交付（官方文档明示该格式需手动解析），而客户端层 openai 路径对 content 原样透传——思考全文流进正文、落库、计字数（实测一章 2,273 字开头即英文思考全文）。DeepSeek/Qwen/Kimi 走独立 `reasoning_content` 字段天然无此问题；anthropic 协议思考是独立块也无此问题。唯一泄漏面就是 openai 路径的 content 通道。

## What Changes

- openai 兼容路径新增**响应侧内联思考剥离**：响应文本以 `<think>` 开头时，截至首个 `</think>`（含）的整段从交付文本中移除；非 `<think>` 开头的响应一个字不动。
- 流式与非流式同构生效：
  - 非流式 `chat()`：返回前剥前缀；
  - 流式 `chat_stream()`：以缓冲状态机实现——`<think>`/`</think>` 标签可能裂在 chunk 边界，缓冲判明前不产出；判明为思考段的内容被丢弃（不产出任何事件），判明为正文的缓冲即时放行。
- **首字守卫口径对齐**：内联思考期间不产出正文事件、守卫不撤销——首个「非思考」正文片段到达才撤守卫（原口径「首个 `delta.content` 即撤」会被内联思考缴械，思考再久都不判死）。守卫上限值、判死行为、去参重开禁令均不变。
- 剥离后的思考内容本期**直接丢弃**（与 `reasoning_content`、anthropic `thinking_delta` 现行处理同口径）；思考的呈现是另一个 change（c-thinking-display）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `ai-client`：
  - **ADDED** Requirement「内联思考不得混入交付文本」：openai 兼容路径响应侧剥 `<think>…</think>`，流式/非流式同构；非该形态响应零改动；剥离发生任何异常时按原样交付兜底（剥离是尽力而为的净化，不得因净化自身抛错毁掉正常生成）。
  - **MODIFIED** Requirement「AI 调用必须有显式超时」：首字守卫的「首个正文片段」口径排除内联思考段——思考期守卫持续在计，正文首字到达才撤销。

## Impact

- `client/backend/ai_client.py`：`chat()`（openai 分支出口）、`chat_stream()`（openai 分支增量放行逻辑＋守卫撤点）。
- `client/backend/tests/`：`test_ai_client_layering.py` / `test_chat_stream_usage.py` 一带补行为钉（跨 chunk 裂标签、无 `<think>` 不动、守卫不因思考撤、非流式剥前缀）。
- 无前端改动、无 API 契约变化（对调用方完全透明）、无界面改动（不涉 Design Impact；文案零变化）。
