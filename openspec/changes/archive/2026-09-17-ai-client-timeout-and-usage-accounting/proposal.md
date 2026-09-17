# ai-client-timeout-and-usage-accounting

## Why

`AIClient` 构造 SDK 客户端时不设超时，走 OpenAI/Anthropic SDK 默认值（600s，含内置重试可叠至 ~20 分钟）——供应商挂起时用户点一次 AI 按钮要干等近 20 分钟才见 502。同时失败路径完全不落用量：旧端点 `except → raise 502` 直接丢弃 usage、`_judge_chat` 异常路径不回填已烧 token、`record_usage` 零 token 早退把失败记录也挡在库外——烧掉的钱在用量页不可见。character-settings-v2 验收（遗留 4.5）已定性为债务，本 change 收口。

## What Changes

- `AIClient` 构造时显式设置超时：非流式 `chat` 与流式 `chat_stream` 分级（判定类短调用收紧、长文流式放宽），并收敛 SDK 内置重试上限——最坏等待从 ~20 分钟降到可预期的秒级/分钟级。
- 超时与网络类失败的 502 文案可识别：用户能区分「网络慢/供应商无响应」与「供应商拒绝」。
- 失败也记账：7 个消费方文件（`settings/ai_router.py`、`write/router.py`、`write/auxiliary.py`、`settings/characters_ai.py`、`chapters/ai_draft.py`、`prompt/router.py`、`novels/router.py`）的 AI 端点在异常路径同样落 `record_usage`，operation 加 `_fail` 后缀区分（`TokenLog` 不加列、零 DDL）。样板 = `settings/characters_ai.py` 现役写法。
- `_judge_chat` 的 usage 回填改 `finally`：任何异常（超时/连接/解析）路径都把多次尝试累计的 token 填回调用方 usage dict，不再只有部分 ValueError 路径回填。
- `record_usage` 增加 force 通道：失败记账允许落零 token 行（保留「成功调用零 token 不落库防噪音」的既有语义）。

## Capabilities

### New Capabilities

- `ai-client`: AIClient 运行时行为纪律——超时分级、失败记账完整性、usage 回填保证。

### Modified Capabilities

（无——`model-api-config` 只覆盖配置页行为，`character-settings` 的 AI 四行需求不因本 change 变化。）

## Impact

- `client/backend/ai_client.py`：构造函数加 timeout/max_retries，`chat`/`chat_stream` 生效。
- `client/backend/settings/ai_router.py`：`_judge_chat` finally 回填 + 6 处端点异常路径补记账。
- `client/backend/write/router.py`、`write/auxiliary.py`、`chapters/ai_draft.py`、`prompt/router.py`、`novels/router.py`：异常路径补记账。
- `client/backend/api_configs/usage.py`：`force` 参数。
- `client/backend/settings/characters_ai.py`：已符合目标行为，仅对齐 `_fail` 后缀口径（如现役已区分则不动）。
- 测试：超时注入用例（mock SDK 挂起）、失败记账断言推广到 7 文件对应测试；全量 pytest 门禁。
