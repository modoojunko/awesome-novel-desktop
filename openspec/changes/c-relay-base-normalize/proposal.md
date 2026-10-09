## Why

中转站（new-api 系）用户以裸域名 base（如 `https://api.kakouai.com`，无 `/v1`）配置后呈「清单绿、测试红」：models 探测对裸域名自动补 `/v1` 拉到清单，对话探针与生成调用却裸拼 `{base}/chat/completions` 打到网页壳上拿 200 HTML 判 `endpoint_mismatch`（2026-10-09 llm.log 生产日志实锤＋curl 三连实测钉死：裸 `/chat/completions` 回 200 `text/html`，`/v1/chat/completions` 为真 API）。SDK 生成调用同样直传裸 base——即使只修探针也会「测试绿、写作红」。10-08 观察①重启，本次有双重证据。

## What Changes

- 新增 `normalize_openai_base` 单源归一（openai 格式限定）：路径段以 `v+数字` 开头即算含版本段（`/v1`、`/v4`、`/v1beta/openai`），裸域名按 OpenAI 官方惯例补 `/v1`
- 四处共用同一归一：models 探测（`_openai_models_url` 收口）、对话探针主链、models 404 降级链、SDK 客户端构造（`ai_client._init_client`，`_base_url` 同步归一形）
- 版本段判据由行尾锚改段锚：修复 Gemini 官方兼容层（`…/v1beta/openai`，版本段在中段）被行尾锚误判「无版本段」而多补 `/v1` 的潜在错址
- `endpoint_mismatch`（200 网页体）错误文案追加补救指引「若地址确认无误，尝试在末尾补 /v1」（openai 格式专属；anthropic/ollama 该指引是空操作，不出——评审 2026-10-09）
- 不改 anthropic 格式（惯例相反：base 不带版本段，SDK 自拼 `/v1/messages`）、不改 ollama（已有剥 `/v1` 逻辑）、不在保存链路改写用户输入（落库保持原样）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`：「按接口格式调用大模型」（SDK 构造前归一）、「按接口格式探测连接」（对话探针主链＋404 降级与 models 探测同源归一、版本段段锚判据、网页体文案补出口）、「供应商默认值预填」（登记纪律理由句随归一更新——「SDK 不自补版本段」表述过时）

## Design Impact

- 受影响端：C端（后端）。S端 不涉及。
- 用户可见面：仅连接测试/拉清单的 `endpoint_mismatch` 错误文案一处追加补救指引（openai 格式专属）；无屏/弹层结构变化、无对象状态变化（不触状态语言总表）、不触双端共享段、不需要原型先行（实现侧自查）。
- 文案口径：补救语句为动词指令＋具体做法（「尝试在末尾补 /v1」），不引入内部术语，不新增语气词形态。

## 过程留痕

- 2026-10-08 曾按同方向修复（PR #747，含 403 降级另一观察），后因该轮反馈证伪整体回退（main 零触碰）；本次 kakou 案有 llm.log 生产日志＋curl 实测双证据，且范围收窄为归一化单项（403 分组权限降级不在本 change）。
- 2026-10-09 评审轮（review-agent）三项整改：①网页体「补 /v1」出口按格式分流（openai 专属，anthropic/ollama 不出）；②design 风险论证如实化——裸根端点改动前经 404 降级链端到端可用，本 change 显式接受「锁死」取舍（escape 出口待真实反馈另行立项）；③前端登记表三处理由句（「SDK 不自补版本段」表述过时）随归一化更新。
