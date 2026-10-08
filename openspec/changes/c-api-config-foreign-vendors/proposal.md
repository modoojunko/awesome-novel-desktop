# c-api-config-foreign-vendors

## Why

2026-10-08 对国外三家大模型供应商的调研（anysearch 官方文档＋SDK 假服务器实证）结论：OpenAI、Anthropic 官方 API 均为「Base URL＋API Key」即可用（Anthropic SDK 自拼 `/v1/messages` 并自动带 `x-api-key`/`anthropic-version` 头）；Google Gemini 原生协议（`:generateContent`＋`x-goog-api-key`）与两者完全不同、后端不支持，但其官方 OpenAI 兼容层（`https://generativelanguage.googleapis.com/v1beta/openai/`，Bearer 鉴权，chat/completions 含流式）可在「OpenAI 兼容」模版下直用。据此用户拍板：**不加 Google 专属按钮**，以文案引导未列厂商走兼容模版（反代/转发服务同理解决国外访问）。

调研同时实锤两个现役缺陷：① OpenAI 预填登记值 `https://api.openai.com` 缺版本段——生成链路（AsyncOpenAI 以 base_url 直拼 `/chat/completions`，实证不会自补 `/v1`）对官方 API 404，按预填「只填 Key」的用户测试/生成必失败（Ollama 预填 `http://localhost:11434` 同病，Ollama 仅服务 `/v1/chat/completions`）；② 连接探针对 openai 格式的 models 404 直接判失败，Gemini 兼容层这类「无清单端点」的兼容地址被误杀（实际生成是通的）——404 降级生成探针目前仅 anthropic 格式享有。

## What Changes

- **修正预填登记值与生成链路同源**：登记纪律补一条「登记 Base URL SHALL 含版本段（与 SDK 生成调用同源可用）」；OpenAI 登记值改 `https://api.openai.com/v1`，Ollama 改 `http://localhost:11434/v1`（连带 openai 格式 placeholder 示例域名同步）。
- **探针 404 降级放开到 openai 格式**：连接测试中 openai 格式 models 探测 404 时，降级发「你好」最小生成探针（探针模型 id 取已选模型/该 vendor 候选；无任何 id 时维持「提示填写模型名」不降级），与 anthropic 格式降级同判据；降级探针也 404/405 时点名实际地址判负。只拉清单轻探针（fetch-models）保持零生成调用、404 语义不变。
- **新增兼容模版引导文案**：配置表单对未列厂商（以 Google Gemini 为例）给出一句话引导——走「OpenAI 兼容」模版＋官方兼容层地址 `https://generativelanguage.googleapis.com/v1beta/openai/`；并说明国外厂商可填反代/转发服务地址。不加 Google 专属按钮、后端协议面（openai/anthropic 两种）不变。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`：MODIFIED「供应商默认值预填」（登记值须含版本段与生成调用同源＋OpenAI/Ollama 登记值修正）；MODIFIED「按接口格式探测连接」（openai 格式 models 404 降级生成探针，原仅 anthropic）；ADDED「未列厂商兼容模版引导」（文案引导 Google Gemini 等走 OpenAI 兼容模版＋反代/转发说明）。

## Impact

- 前端：`client/frontend/src/components/api-config/vendorDefaults.ts`（openai/ollama 登记值）、`ProviderIcon.tsx`（FORMAT_PLACEHOLDER 示例域名）、`ApiConfigForm.tsx`（引导文案）；相关 vitest 适配。
- 后端：`client/backend/api_configs/connection.py`（openai 格式 404 降级生成探针）；`test_api_format.py` 等连接测试用例适配＋新增降级用例。
- 不动：后端协议面（openai/anthropic 两种）、`ai_client.py` 调用链、vendor 按钮清单（不加 Google）、fetch-models 轻探针零生成语义、在途 change `c-api-config-save-gate` 的保存闸门面（未跟踪于主检出，不与本分支相交）。
