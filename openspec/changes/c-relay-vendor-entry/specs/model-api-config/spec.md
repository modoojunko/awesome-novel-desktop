## ADDED Requirements

### Requirement: 中转站接入入口

供应商网格 SHALL 提供独立的「中转站 API」按钮（vendor=`relay`，与「OpenAI 兼容」并存——后者承载 Gemini 官方兼容层等自建端点）。选中「中转站 API」时表单 SHALL 展示中转站口径引导：Base URL 填站方给出的接口地址（通常以 `/v1` 结尾）、API Key 用站方后台生成的令牌、模型清单拉不到（如中转站按分组权限拒绝访问的 403）时直接手填模型 id。探测与调用 SHALL 复用既有 openai/anthropic 协议路径（SHALL NOT 为 relay 新增调用实现或探针分支——vendor 仅 ollama 有协议特例）。中转站域名形态任意、SHALL NOT 被域名检测识别，保存「中转站 API」配置 SHALL 以 `vendor_override=relay` 显式登记 vendor（展示名「中转站 API」），SHALL NOT 依赖 URL 推断。「中转站 API」SHALL NOT 登记预填值（站方地址/模型各不相同，无据不登记）。

#### Scenario: 选中中转站按钮出现口径引导

- **WHEN** 用户在添加弹窗点选「中转站 API」
- **THEN** 表单出现中转站引导（/v1 填法、站方令牌、清单 403 时手填模型 id、连接测试实际验证对话路径），Base URL 与模型名称均为空不预填

#### Scenario: 保存显式登记 relay 身份

- **WHEN** 用户选中「中转站 API」、填入任意站方地址与 Key 后保存
- **THEN** 配置落库 vendor=`relay`、展示名「中转站 API」（经 vendor_override 显式登记，SHALL NOT 因域名检测落入其他厂商或兜底）；连接测试与生成走 openai 协议路径

#### Scenario: 探测复用协议路径无特例

- **WHEN** 对「中转站 API」配置执行连接测试或模型清单拉取
- **THEN** 行为与 openai 格式探测完全一致（含 403/404 降级链与版本段归一），SHALL NOT 因 vendor=relay 走任何专属分支

#### Scenario: 存量 OpenAI 兼容配置不受影响

- **WHEN** 展示一份既有 vendor=openai-compat 的配置（升级前创建）
- **THEN** 卡片照常以「OpenAI 兼容」展示并可编辑，SHALL NOT 被迁移或改写为 relay

## MODIFIED Requirements

### Requirement: 未列厂商兼容模版引导

对未列入供应商按钮清单的大模型厂商（后端协议面仅 openai/anthropic 两种），系统 SHALL 以配置表单文案承接引导，SHALL NOT 为不支持的原生协议（如 Google Gemini 原生 `:generateContent`）增设供应商按钮。选择「OpenAI 兼容」供应商时，表单 SHALL 展示兼容模版引导文案，内容 SHALL 包含：① Google Gemini 官方 OpenAI 兼容层地址 `https://generativelanguage.googleapis.com/v1beta/openai/`（配 Gemini API Key 即用，走 Bearer 鉴权）；② 该类地址拉取模型清单可能失败，手填模型 id（如 `gemini-2.5-pro`）即可；③ 转发/中转站接入 SHALL 引导使用「中转站 API」按钮（2026-10-08 拍板独立入口；原「OpenAI/Anthropic 等按钮同样支持改 Base URL 指向反代」句式作废——反代口径收编进中转站按钮的专属引导）。

#### Scenario: 选择 OpenAI 兼容可见引导文案

- **WHEN** 用户在创建（或编辑）表单选择「OpenAI 兼容」供应商
- **THEN** 表单可见兼容模版引导文案，含 Gemini 官方兼容层地址示例与手填模型 id 说明，转发/中转站需求指向「中转站 API」按钮

#### Scenario: Gemini 兼容层全流程可用

- **WHEN** 用户选「OpenAI 兼容」、填入兼容层地址与 Gemini API Key、手填模型 id 后点「测试连接」并保存
- **THEN** 连接测试经 models 404 降级生成探针判「连接正常」，保存成功后生成正常（清单拉取失败不阻塞保存，按「模型清单自动拉取」既有口径退手填）

#### Scenario: 不增设未支持协议的按钮

- **WHEN** 用户查看供应商按钮清单
- **THEN** 按钮清单不含 Google/Gemini 原生协议按钮（引导由文案承接，见 2026-10-08 拍板）
