# model-api-config Delta — 国外厂商接入口径修正（登记值同源＋探针 404 降级放开＋兼容模版引导）

## MODIFIED Requirements

### Requirement: 供应商默认值预填

系统 SHALL 提供供应商默认值登记表（键＝供应商×接口格式，值＝官方 Base URL＋默认模型名称＋备选模型候选），作为创建表单预填的单一数据源。登记纪律＝有据才登记（实测或厂商官方文档），无据字段 SHALL 留空，SHALL NOT 编造；登记的 Base URL SHALL 与生成调用链路同源可用——SDK 生成调用以 base_url 直拼请求路径（不自补版本段），登记值须含版本段（OpenAI 官方为 `https://api.openai.com/v1`，Ollama 为 `http://localhost:11434/v1`），SHALL NOT 登记缺版本段的裸域名（生成 404 的死值）；首批全量登记 DeepSeek，其余内置供应商按官方文档核对后登记。

创建模型配置时，用户选中登记表内的供应商（或切换接口格式）后，表单 SHALL 自动填入该「供应商×接口格式」登记的 Base URL 与默认模型名称，用户只需填写 API Key 即可保存；「模型」SHALL 为创建表单的一级字段，形态为**模型选择器**（自动拉取清单，见「模型清单自动拉取」）：登记的默认模型名称为清单到位前的初值（清单到位后默认选中清单首项，登记值不优先）；清单为空或拉取失败时 SHALL 退为手填输入（登记默认模型名称为初值）。保存后选中值（或手填值）SHALL 为该配置模型列表首项。预填字段 SHALL 可编辑。字段为空、或仍等于预填值（用户未手改）时，SHALL 随供应商/格式切换更新为新登记值；用户手改过的字段 SHALL NOT 被覆盖。「OpenAI 兼容」等无登记值的供应商 SHALL NOT 预填（沿用 placeholder 示例域名引导；清单自动拉回后的默认选中不算预填）。编辑已有配置 SHALL NOT 施加预填（沿用已存值）。

#### Scenario: 选 DeepSeek 只填 Key 即可保存

- **WHEN** 用户在添加弹窗选择 DeepSeek 供应商
- **THEN** Base URL 与模型初值自动填为登记默认值，用户填入 API Key 后自动拉取清单并默认选中清单首项（登记值不优先），保存成功，配置的 Base URL 为登记值、模型列表首项为选中值

#### Scenario: 预填字段可编辑且手改不被覆盖

- **WHEN** 用户把预填的 Base URL 改成自己的地址后切换供应商再切回
- **THEN** 用户改过的 Base URL 保持不变（不被预填值覆盖）；未手改的字段随所选供应商更新为对应登记值

#### Scenario: 无登记值的供应商不预填

- **WHEN** 用户选择「OpenAI 兼容」供应商
- **THEN** Base URL 与模型初值留空（placeholder 引导），不自动填入任何猜测值（清单自动拉回后的默认选中不算猜测值）

#### Scenario: 登记表无据字段留空

- **WHEN** 某供应商的默认模型 id 尚无实测或官方文档依据
- **THEN** 该供应商的模型初值留空（由自动拉取清单默认选中或用户自填），SHALL NOT 编造模型 id

#### Scenario: 登记值与生成调用同源（缺版本段的裸域名不登记）

- **WHEN** 用户选择 OpenAI（或 Ollama）供应商、按预填值只填 API Key 保存，并触发连接测试或生成
- **THEN** 请求命中官方真实路径（OpenAI `POST {base}/chat/completions` 即 `/v1/chat/completions`），SHALL NOT 因预填值缺版本段而 404

### Requirement: 按接口格式探测连接

连接测试与模型列表拉取 SHALL 按配置的接口格式构造探测请求，探测目标一律为用户填写的 base_url：`openai` 格式 GET `{base}/models`（base 无版本段时按 OpenAI 惯例补 `/v1`，与生成调用同源推导）+ Bearer 头；`anthropic` 格式 GET `{base}/v1/models` + `x-api-key` 与 `anthropic-version` 头。探测 SHALL NOT 使用硬编码的官方域名。连接测试中 models 端点返回 404 时 SHALL 自动降级为最小生成探针（见下）验证鉴权与对话路径——anthropic 与 openai 两格式同享降级（Gemini 官方 OpenAI 兼容层等不提供模型清单端点的兼容地址因此可用）；只拉清单轻探针（见「模型清单自动拉取」）SHALL NOT 发起降级生成探针（保持零生成调用语义）。

「连接正常」的最终判据 SHALL 是收到格式正确的最小生成回复（2026-10-05 拍板），SHALL NOT 仅凭 models 探测的地位码、可达性或鉴权通过：models 探测的 200 响应体 SHALL 为 API JSON——返回网页等非 JSON 体 SHALL 判失败并提示检查 Base URL（典型：网站首页/SPA 对任意路径回 200 HTML）。可达且鉴权通过后，SHALL 向对话接口发一条真实最小生成探针：用户消息「你好」、关闭思考（与生成调用同一禁思考约定，端点拒绝该参数时去掉重试一次）、短输出预算（足出一句短答复），与生成调用同址同鉴权头——`openai` 格式 `POST {base}/chat/completions`，`anthropic` 格式 `POST {base}/v1/messages`。探针收到「响应体符合接口格式且含可见回复文本」的响应 SHALL 判「连接正常」；非 2xx、响应体不符合接口格式、回复文本为空 SHALL 一律判失败并给可读原因——400/422 类业务性拒绝（探针模型 id 不被接受等）SHALL NOT 视为通过（原「探针 id 是猜的不拦」口径作废），错误 SHALL 点名所试模型 id 与实际请求地址。探针模型 id 取用顺序：配置已选模型 > 模型列表首个 > 该 vendor 候选 id 首个 >（anthropic 无列表降级时）占位探测模型；openai 格式 404 降级的探针模型 id 取用顺序：配置已选模型（含表单手填初值）> 该 vendor 候选 id 首个，两者皆无时 SHALL NOT 降级（无 id 的生成探针必然无意义），按「提示填写模型名」判失败。无任何可用模型 id（openai 格式模型列表为空且该 vendor 无候选）时 SHALL 判失败并提示填写模型名，SHALL NOT 仅凭可达性或鉴权通过报「连接正常」（原「跳过对话探针」口径作废）。

#### Scenario: Anthropic 格式探测用户地址

- **WHEN** 测试一条 `api_format=anthropic`、base_url 为 GLM Anthropic 地址的配置
- **THEN** 探测请求发往 `{base}/v1/models` 并携带 x-api-key 头，成功时拉取到模型列表

#### Scenario: models 端点缺失时降级探活

- **WHEN** anthropic 格式探测 `{base}/v1/models` 返回 404
- **THEN** 自动改发「你好」最小生成探针（`POST {base}/v1/messages`，禁思考），收到格式正确的回复即报「连接正常」且不报错误

#### Scenario: openai 格式 models 404 同享降级探活

- **WHEN** openai 格式探测 models 端点返回 404（如 Gemini 官方兼容层 `…/v1beta/openai` 不提供清单端点），且配置已选模型（含表单手填初值）或该 vendor 候选 id 可用
- **THEN** 自动改发「你好」最小生成探针（`POST {base}/chat/completions`，禁思考，与生成同址同鉴权头），收到格式正确的回复即报「连接正常」且不报错误

#### Scenario: openai 格式 404 降级无 id 不降级

- **WHEN** openai 格式探测 models 端点返回 404，且既无已选模型（表单模型初值也为空）也无该 vendor 候选 id
- **THEN** 判连接失败并提示填写模型名，SHALL NOT 发起无 id 的生成探针，SHALL NOT 仅凭可达性或鉴权通过报「连接正常」

#### Scenario: 降级探针打到错误地址

- **WHEN** 任一格式的 models 探测端点返回 404，降级的最小生成探针返回 404 或 405（Base URL 指向的地址不提供对话接口）
- **THEN** 判连接失败并提示核对 Base URL 与接口格式（点名降级探针实际请求地址），SHALL NOT 报连接正常

#### Scenario: 网页地址不算通

- **WHEN** 探测地址对 models 端点返回 200 但响应体是网页（非 JSON）
- **THEN** 判连接失败并提示「该地址返回的不是 API 数据——请检查 Base URL」

#### Scenario: openai 格式对话探针

- **WHEN** `openai` 格式的 models 探测成功且取得探针模型 id
- **THEN** 连接测试追加一条 `POST {base}/chat/completions` 最小生成探针（消息「你好」、禁思考、与生成同址同鉴权头）；收到格式正确且含可见回复文本的响应判「连接正常」，非 2xx、体格式不符或空回复判失败，404/405 失败时点名实际请求地址与核对提示

#### Scenario: anthropic 格式对话探针

- **WHEN** `anthropic` 格式的 models 探测成功且取得探针模型 id
- **THEN** 连接测试同样追加一条 `POST {base}/v1/messages` 最小生成探针（消息「你好」、禁思考，探针模型 id 取列表首个）；收到格式正确（content 文本块）且含可见回复文本的响应判「连接正常」，格式不符或空回复判失败——判据双格式统一，SHALL NOT 仅凭 models 探测报「连接正常」

#### Scenario: 探针回复格式不正确不算通

- **WHEN** 最小生成探针返回 2xx 但响应体不符合接口格式（网页/错误信封），或可解析但回复文本为空
- **THEN** 判连接失败并提示检查 Base URL 与模型配置，SHALL NOT 报连接正常

#### Scenario: 探针模型被拒不算通并点名所试 id

- **WHEN** 最小生成探针因模型 id 不被接受（400/404 类业务性拒绝）失败
- **THEN** 判连接失败（不按「探针 id 是猜的」放行），错误信息点名所试模型 id 与实际请求地址

#### Scenario: 无可用模型 id 不报连接正常

- **WHEN** openai 格式 models 探测返回空列表且该 vendor 无候选 id
- **THEN** 判连接失败并提示填写模型名，SHALL NOT 仅凭可达性或鉴权通过报「连接正常」

## ADDED Requirements

### Requirement: 未列厂商兼容模版引导

对未列入供应商按钮清单的大模型厂商（后端协议面仅 openai/anthropic 两种），系统 SHALL 以配置表单文案承接引导，SHALL NOT 为不支持的原生协议（如 Google Gemini 原生 `:generateContent`）增设供应商按钮。选择「OpenAI 兼容」供应商时，表单 SHALL 展示兼容模版引导文案，内容 SHALL 包含：① Google Gemini 官方 OpenAI 兼容层地址 `https://generativelanguage.googleapis.com/v1beta/openai/`（配 Gemini API Key 即用，走 Bearer 鉴权）；② 该类地址拉取模型清单可能失败，手填模型 id（如 `gemini-2.5-pro`）即可；③ 国外厂商可填反代/转发服务地址接入（OpenAI/Anthropic 等按钮同样支持改 Base URL 指向反代）。

#### Scenario: 选择 OpenAI 兼容可见引导文案

- **WHEN** 用户在创建（或编辑）表单选择「OpenAI 兼容」供应商
- **THEN** 表单可见兼容模版引导文案，含 Gemini 官方兼容层地址示例、手填模型 id 说明与反代/转发地址说明

#### Scenario: Gemini 兼容层全流程可用

- **WHEN** 用户选「OpenAI 兼容」、填入兼容层地址与 Gemini API Key、手填模型 id 后点「测试连接」并保存
- **THEN** 连接测试经 models 404 降级生成探针判「连接正常」，保存成功后生成正常（清单拉取失败不阻塞保存，按「模型清单自动拉取」既有口径退手填）

#### Scenario: 不增设未支持协议的按钮

- **WHEN** 用户查看供应商按钮清单
- **THEN** 按钮清单不含 Google/Gemini 原生协议按钮（引导由文案承接，见 2026-10-08 拍板）
