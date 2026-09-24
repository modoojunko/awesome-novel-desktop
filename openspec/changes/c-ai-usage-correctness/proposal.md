## Why

两处「记账/埋点写失败 → 回滚调用方整个 session」的助手（`api_configs/usage.py` 的 `record_usage` 与 `novels/events.py` 的 `log_event_async`）在失败路径上会把同会话已暂存的**主流程写入一并回滚**，且 `record_usage` 连日志都没有——这正是历史「record_usage FK 静默回滚」雷区的根因，且新代码（events.py）又复制了一份。虽然当前 36+ 调用点顺序安全（记账先于主写入），但契约本身是「先 add 主数据再记账」就会静默丢数据的雷。

另外 `chat_stream` 的 OpenAI 分支有两处正确性问题：`chunk.choices[0]` 裸取索引——OpenAI 兼容供应商（DeepSeek 等）流末会发 `choices=[]` 的 usage chunk，IndexError 不在 `_NETWORK_ERRORS` 白名单内，已成功的生成被记成 `*_fail`；流式 done 事件只带 `total_tokens` 并整体记入 `tokens_out`——**tokens_out 虚高、tokens_in 恒 0**，用量统计系统性失真。

## What Changes

- `record_usage` / `log_event_async` / `log_event` 改 **SAVEPOINT（`begin_nested`）**语义：记账失败只回滚自身 SAVEPOINT，主流程写入不受牵连；失败记 warning 日志（含 operation/event_type），不再全静默。
- `chat_stream` OpenAI 分支：跳过 `choices=[]` 的块；done 事件按 `completion_tokens`/`prompt_tokens` 拆分。
- `StreamEvent` 增加 `tokens_in` 字段；anthropic 流从 `message_start` 抓 `input_tokens`。
- 消费方（`write/router.py`、`write/auxiliary.py`）记账补 `tokens_in=event.tokens_in`。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `ai-client`: 新增「记账失败不得回滚主流程写入」「流式用量按输入/输出拆分」「流式 usage 块不得中断生成」三条要求。

## Impact

- `client/backend/ai_client.py`（StreamEvent、chat_stream 两分支）、`api_configs/usage.py`、`novels/events.py`、`write/router.py`、`write/auxiliary.py`。
- 测试：usage/events 失败路径单测、OpenAI 流末 usage chunk 单测。
- 无前端改动；`StreamEvent.tokens` 语义收窄为「输出侧 tokens」（此前 OpenAI 流式误记 total）。
