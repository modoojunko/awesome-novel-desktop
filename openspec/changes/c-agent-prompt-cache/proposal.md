## Why

DeepSeek 上下文硬盘缓存按**完整前缀单元**命中（默认开启）：system 与历史前缀稳定时，后续轮次可复用输入缓存；前缀里只要有一处动态内容（进度/记忆），整段缓存即失效。当前助手系统前缀把 `book_brief`（含进度/字数/frontier 状态）与书级 memory/decision 段都拼在 system 里——写作进度一变，系统前缀就变，历史再长也几乎命中不了。llm.log 也没有缓存命中指标，无法验证。把动态内容挪到当前 user 消息尾部（页面 note 已在尾部），并记录 `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens`。

## What Changes

- `build_book_brief` 拆为稳定/动态两段：稳定段（书名/题材）进 system 前缀；动态段（进度/字数/frontier 真值）拼到当前 user 消息尾部的 L2 note。
- 书级 memory/decision 段从 system 前缀移到当前 user 消息尾部（与页面/聚焦/画像/未保存标记同段）；system 前缀只留身份/围栏/动作协议/工具目录/稳定书情与域纪律。
- `AIClient.chat_stream`（openai 分支）在供应商返回 `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens` 时，`ai_call` 留痕行追加 `cache_hit=`/`cache_miss=`；未返回不输出，零行为变化。
- 测试：稳定/动态 brief 拆分（进度变化不改稳定段）、system 前缀不含动态进度、缓存字段进日志。
- 不做：持久化 L2 note（页面/画像会过期）；compact 不变。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `writing-assistant`: 「会话存储与 compact」增加「书级冻结前缀只放稳定内容，动态进度/记忆/页面注入在当前 user 消息尾部」的缓存友好约束。
- `ai-client`: 新增「流式缓存命中留痕」要求（有则记、无则不加）。

## Design Impact

- **受影响端**：仅 C端后端（client/backend）；无前端/UI 改动，无 S端、无共享设计段、无原型先行。
- **对象状态**：无新增用户可见状态；llm.log 增可选字段。
- **设计工件**：无（内部提示词组织与可观测性优化）。

## Impact

- `client/backend/assistant/context.py`（brief 拆分、note 组装）
- `client/backend/assistant/router.py`（system 用稳定段；动态段/memory 进 note）
- `client/backend/ai_client.py`（缓存字段解析与留痕）
- `client/backend/tests/test_assistant_router_helpers.py`、`tests/test_ai_client_logging.py`
- 不影响会话文件/API/schema；无迁移。
