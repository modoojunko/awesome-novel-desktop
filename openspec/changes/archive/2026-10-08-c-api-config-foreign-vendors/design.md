# Design — c-api-config-foreign-vendors

## Context

调研实证（2026-10-08，SDK 假服务器＋官方文档）：

- AsyncOpenAI 以 `base_url` 直拼请求路径：裸域名 → `POST {域名}/chat/completions`（不自补 `/v1`，官方 404）；带 `/v1` → 正确。AsyncAnthropic 裸域名自拼 `/v1/messages` 并自动带 `x-api-key`＋`anthropic-version: 2023-06-01` 头——Anthropic 无此问题。
- Google Gemini 原生协议（`x-goog-api-key`＋`:generateContent`）后端不支持；官方 OpenAI 兼容层 `https://generativelanguage.googleapis.com/v1beta/openai/`（Bearer）支持 chat/completions 含流式，可走「OpenAI 兼容」模版直配。
- 现役缺陷：① `vendorDefaults.ts` 登记 OpenAI `https://api.openai.com`、Ollama `http://localhost:11434` 均缺版本段——探针 `_openai_models_url` 对裸域名补 `/v1/models` 显得能通，生成链路（`ai_client.py` 原样透传 base_url 给 SDK）404，探针与生成不一致；② `connection.py` 探针 404 降级生成探针仅 anthropic 格式享有（`_build_probe` 的 `fallback` 只在 anthropic 分支构造），Gemini 兼容层这类无清单端点的 openai 格式地址被 models 404 直接判负。

## Goals / Non-Goals

**Goals:**

- OpenAI / Ollama 按预填「只填 Key」全链可用（登记值与生成调用同源）。
- 无清单端点的 openai 格式兼容地址（Gemini 兼容层为代表）能通过连接测试。
- 未列厂商有文案引导（Gemini 兼容层地址＋手填模型 id＋反代/转发说明）。

**Non-Goals:**

- 不加 Google 专属按钮（拍板 2026-10-08）。
- 不动后端协议面（openai/anthropic 两种）、`ai_client.py` 调用链。
- 不动 fetch-models 轻探针的零生成语义与 404 判负口径（openai/ollama 格式仍判失败提示核对）。
- 不做 Gemini 原生协议适配、不做反代服务本身。

## Decisions

1. **登记值修正在登记表单源，不在生成链路补 URL。**
   备选：在 `ai_client._init_client` 给 openai 协议裸域名自动补 `/v1`。否决——生成链路补 URL 会改变所有存量配置的语义（第三方兼容端点路径形状千奇百怪：GLM `/api/paas/v4`、Qwen `/compatible-mode/v1`，自动补版本段对它们是破坏性的），而登记值只影响预填初值、用户可改，爆炸半径最小。连带把 openai 格式 `FORMAT_PLACEHOLDER` 示例域名改为带 `/v1`。

2. **openai 格式 404 降级复用 anthropic 降级管道——降级请求三件套在 `_build_probe` 构造、payload 在 404 分支现解（2026-10-08 后端评审定形）。**
   - **fallback 携带 reply_fn**：`_build_probe` 的 fallback 从 `(url, headers, payload)` 改为 `(url, headers, reply_fn)`——现状 404 分支在调用点烤死 `_anthropic_reply_text`（`connection.py` 404 分支），openai 降级的 chat/completions 回复用 anthropic 提取器解析必得空文本恒判负。openai 分支补 `POST {base}/chat/completions`＋Bearer 头＋`_openai_reply_text`；anthropic 分支沿用现有 url/头并把 `_anthropic_reply_text` 装进 fallback。
   - **payload 现解（id 链下放）**：payload 不在 `_build_probe` 烤死——现状烤死 `_ANTHROPIC_PROBE_MODEL`，`preferred_model` 传不进 fallback，已选模型被无视（存量 spec-code 分歧：spec 写「已选模型 > 列表首个 > 候选首个 > 占位」，代码恒用占位），本次一并修齐。404 分支以 `_probe_model([], vendor_id, preferred_model)` 现解：anthropic 链尾垫 `_ANTHROPIC_PROBE_MODEL`（404 时列表恒空，实际链＝已选模型 > 候选首个 > 占位）；openai 链尾**不垫**——凭空猜 `gpt-*` 类 id 对兼容端点是噪音，无 id 不降级、按「提示填写模型名」判负。
   - **`test_connection` 的 404 分支放开**：从「`fallback is not None`」自然承接两格式，无需新分支；降级探针也 404/405 时沿用既有判负文案并点名实际请求地址。fetch-models 轻探针只解构 fallback 之前的返回位（fallback 整体被忽略），元组形状变更不破坏其解构。
   - **note 按格式分支**：`NO_MODEL_LIST_NOTE` 现尾句「把接口格式改成 openai 后重新测试即可自动获取」是 anthropic 视角，对 openai 格式降级成功是自我循环——拆双格式版本（openai 版去掉该尾句，anthropic 版原样），消费点共三处按各自上下文选版：`test_connection` 404 降级成功路径、`fetch_models` anthropic 404 分支（恒 anthropic 版）、`GET /api-configs/{id}/model-candidates`（按该配置的 `api_format` 选版，评审补查点——`router.py` 函数内 import 处）。

3. **models 端点启发式（`/v\d+$` 才不补 /v1）不改。**
   备选：给 `…/v1beta/openai` 形状加特例。否决——404 降级放开后该形状自愈（补错 `/v1/models` 得 404 → 降级生成探针打 `{base}/chat/completions` 正确命中），为单一形状加启发式不如让「404 → 试对话路径」成为通用兜底；fetch-models 保持判负不误诊（其提示语「地址少了 /v1」对新形状虽不精确，但手填模型 id 的出口已覆盖）。

4. **引导文案挂「OpenAI 兼容」供应商的表单区，不弹窗不新页。**
   文案三要素（Gemini 兼容层地址、手填模型 id、反代/转发说明）落在创建/编辑表单的 Base URL 区域下方一行小字，随供应商选择显隐（选「OpenAI 兼容」时显示）；`FORMAT_PLACEHOLDER` 同步带版本段。判定标准：表单是用户填 URL 的现场，文案就地生效成本最低。

## Risks / Trade-offs

- [降级放开后，真·填错路径的 openai 格式配置从「HTTP 404 异常响应」变为「先降级再判负」，失败反馈多一跳] → 判负文案点名降级探针实际地址＋既有核对提示，用户可读性不降；测试断言按新信封更新。
- [openai 格式 404 降级会对「慢端点＋错路径」多打一条生成请求，产生少量计费流量] → 最小预算（与既有「你好」探针同口径，短输出＋禁思考），仅 404 时一条，可接受。
- [登记值变更影响 e2e/单测里钉了旧预填值的用例] → 随实现更新断言；预填值本身有登记纪律与登记表单源，测试只对登记表断言不散落硬编码。
- [`VENDOR_MODEL_CANDIDATES` 现仅 deepseek 有值，「候选垫底」对 openai 降级是空腿——降级 id 实际只有「已选/手填模型」一条腿，Gemini 直配流依赖用户先填模型 id（2026-10-08 评审确认有意行为：候选纪律＝有据才登记，无据不猜）] → 由引导文案「手填模型 id」承接；用例矩阵把「openai-compat＋已手填模型 id」列为降级主路径。
- [404 降级串行两跳（models GET＋生成探针）最坏 2×超时预算，前端等待变长] → 接受；真机 Gemini 直配冒烟时观察体验，必要时再单独立项调探针超时。

## Migration Plan

纯行为修正，无数据迁移：存量已保存配置的 base_url 不动（用户已存的裸域名 OpenAI 配置仍需手改 URL，登记值只影响新建预填）；回滚即还原登记值与探针分支。

## Open Questions

（无——三处口径均已在调研与拍板中定形。）
