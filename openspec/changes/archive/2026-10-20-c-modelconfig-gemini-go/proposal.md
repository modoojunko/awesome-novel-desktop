# C端 模型配置接入 Gemini 与 OpenCode Go（一期）

## Why

作家要求模型配置支持 Gemini 与 OpenCode Go 订阅入口。调研已定案（2026-10-20 会话，官方文档＋ZCode 内置注册表双源对拍）：Gemini 走官方 OpenAI 兼容层即可由现有 openai 协议路径承接；OpenCode Go 一把订阅 Key 按模型族分流，本期接入的 GLM/Kimi/DeepSeek/MiMo/Hy 等（chat 族）与 Claude Haiku/MiniMax/Qwen 系（anthropic 族）均落在现有两条协议路径上。两者只需登记与少量调用适配，无需新 SDK、无需新协议客户端。设计原型已过审（tab 方案拍板）：`docs/design-c/drafts/ai-novel-c端-模型配置-Gemini与OpenCodeGo-原型.html`。

## What Changes

- 供应商选择区改为「官方厂商｜中转 · 订阅制」两页 tab（复用接口格式段同款 `.seg` 形态）：官方页保持现有 8 家不变＋新增 Gemini；中转页承接存量「OpenAI 兼容」＋新增 OpenCode Go 两张方块（通用＝OpenAI 格式；Claude 系＝Anthropic 格式）。
- 供应商默认值登记表新增登记（登记纪律不变，均有官方文档依据）：Gemini（官方兼容层 Base URL，默认模型留空＋候选清单）、OpenCode Go · 通用（`https://opencode.ai/zen/go/v1`）、OpenCode Go · Claude 系（`https://opencode.ai/zen/go`，Anthropic 格式口径由 SDK 拼 `/v1/messages`）。
- 厂商锁定矩阵扩展：Gemini 锁 OpenAI 格式；两张 Go 方块分别锁定各自格式。
- 「OpenAI 兼容」引导文案收窄：Gemini 专属句移除（由 Gemini 方块承接），保留手填模型 id 与反代/转发指引两句。
- 新增调用适配（对用户无感）：Base URL 命中 opencode.ai 的请求自动附带稳定会话标识头 `x-opencode-session` 与产品 User-Agent（`ai-novel/<版本>`）；Gemini 供应商思考档位按 Gemini 契约换算下发（「深 max」→ high；关思考按 Gemini 口径下发，仅 Flash 系生效——表单提示文案已告知）。
- 出圈（另立 change）：OpenCode Go 的 Gemini（`gemini-4-argon`，需 Google 原生协议客户端）与 GPT/Grok 系（需 Responses 协议客户端）。设计原型以「待排期」角标表达此意图，本期不实现、不上中转页。

## Capabilities

### New Capabilities

（无——全部落点在既有 capability）

### Modified Capabilities

- `model-api-config`: ①新增「供应商分组页签」requirement（官方｜中转两页 tab 的分组与归属）；②「接口格式为配置的一级字段」锁定矩阵扩展（Gemini/两张 Go 方块的锁定态）；③「供应商默认值预填」登记表新增 Gemini 与 OpenCode Go 两条登记；④「未列厂商兼容模版引导」文案收窄（Gemini 句移除）；⑤新增「订阅入口与 Gemini 的调用适配」requirement（会话标识头＋产品 UA＋思考档位换算）。

## Impact

- 前端：`client/frontend/src/types/api-config.ts`（VendorId 枚举）、`components/api-config/vendorDefaults.ts`（登记表）、`components/api-config/ProviderIcon.tsx`（VENDORS／VENDOR_FORMAT_LOCK／新厂商字形）、`components/api-config/ApiConfigForm.tsx`（tab 渲染与选中流）。
- 后端：`api_configs/vendor.py`（KNOWN_VENDORS 展示识别 gemini/opencode）、`ai_client.py`（opencode 会话头/UA 附加、Gemini 思考档位换算）、`api_configs/connection.py`（VENDOR_MODEL_CANDIDATES 候选清单与前端登记对齐）。
- 不新增依赖；不触碰两端共享段（tab 复用现有 `.seg` 组件类，无新令牌/新组件词汇/新状态语言）。
- 风险记录：OpenCode Go 官方声明服务编程代理流量并监控滥用；本产品写作流量与该画像不符，存在账号限速/封禁风险——已向作家明示并确认推进（2026-10-20 拍板，风险自担）。

## Design Impact

- 受影响端：仅 C端。
- 受影响屏/弹层：模型配置页（`/config`）「添加 API Key」弹窗——供应商选择区（tab＋两页方块）、Base URL 提示文案、思考模式行提示、模型选择器候选；配置卡片、用量统计、朱雀页签均不受影响。
- 对象状态：无新增对象状态。tab 复用 `.seg` 的 on/lock 语义；「新」角标为静态徽标（非状态语言新增）；「待排期」角标仅存在于设计原型，本期不实现。
- 共享段：不触碰 → 不触发 `design-cross.mjs`，无双端同改任务。
- 原型先行：需要。设计稿已过审：`docs/design-c/drafts/ai-novel-c端-模型配置-Gemini与OpenCodeGo-原型.html`（七状态，真界面基线 HEAD@8bbf9459 实抓）；实现侧第一个任务将其转正到 `docs/design-c/prototypes/model-config.html` 并在 `ADJUSTMENTS.md` 登记（tab、新方块、引导文案收窄、思考提示等偏差项）。
- 设计工件：设计侧会话已产出（本 change 直接引用），实现侧按稿落地，无需新的设计侧产出。
