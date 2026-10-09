# model-api-config delta — c-thinking-config

## ADDED Requirements

### Requirement: 思考参数可配

每个 API 配置 SHALL 携带思考参数二元组并落库：思考开关 `thinking_enabled`（布尔，默认
关）与思考强度 `thinking_effort`（`low`/`high`/`max`，默认 `low`——GLM-5.3 契约三档
`reasoning_effort`，整条链按「省 token 省延迟」取向取最省一档）。生成调用与连接探针
SHALL 按该配置下发思考参数：关＝`thinking:{type:disabled}`（与既有行为等价，存量配置
零变化）；开＝`thinking:{type:enabled}`＋顶层 `reasoning_effort`（openai 格式随
extra_body，anthropic 格式 thinking 走形参、effort 随 extra_body 透传）。effort SHALL
NOT 随「关」下发。「添加/编辑 API Key」弹窗 SHALL 提供两控件：思考模式（开启/关闭）与
思考强度（低 low/高 high/深 max，关闭时灰置且保留已选值），编辑态 SHALL 回读已存值。

判定/短答复类调用（`_judge_chat` 漏斗，volume-plan-ai 口径）SHALL 恒以显式关思考传参
压过配置；调用方显式传 `thinking` 时配置强度 SHALL NOT 搭车下发。端点打回思考参数时
SHALL 去参（`thinking`＋`reasoning_effort`）重试一次并记住该 base 不再主动发——判据
SHALL 含中文「思考」与 `reasoning`/`effort` 字样（GLM-5.3 拒关思考的报错是纯中文，仅
匹配英文 `thinking` 会漏判）；连接探针的触发 SHALL NOT 依赖文案措辞（带思考参数的 400
一律去参重试），去参重试时 SHALL 同步放大输出预算（强制思考模型会把预算花在推理上，
短预算只够思考、正文为空）。

#### Scenario: 配置 GLM-5.3 开思考 low

- **WHEN** 配置 `thinking_enabled=true`、`thinking_effort="low"` 后发起生成或连接测试
- **THEN** 请求携带 `thinking:{type:enabled}`＋`reasoning_effort:"low"`，GLM-5.3 正常回复

#### Scenario: 默认关思考与存量行为等价

- **WHEN** 配置不传思考参数（旧前端）或保持默认
- **THEN** 请求仅携带 `thinking:{type:disabled}`、无 `reasoning_effort`，落库回读为关/low

#### Scenario: GLM-5.3 关思考被拒自动去参重试

- **WHEN** 强制思考模型（GLM-5.3 系）对携带 `thinking:{type:disabled}` 的请求回 400
  （报错为纯中文「该模型始终思考，不支持关闭思考；请使用 low、high 或 max」）
- **THEN** 探针与生成调用均自动去掉思考参数重试一次并成功，连接测试判「连接正常」；
  重试请求 SHALL NOT 携带 `thinking`/`reasoning_effort`，且输出预算放大

#### Scenario: 判定类调用恒关思考

- **WHEN** 配置开思考后触发 JSON 判定/短答复类调用（卷规划等 `_judge_chat` 路径）
- **THEN** 请求显式携带 `thinking:{type:disabled}` 且不携带 `reasoning_effort`，
  判定类延迟与预算口径不变

#### Scenario: 表单两控件与编辑回读

- **WHEN** 在「添加 API Key」弹窗开启思考并选「深 max」后保存，再打开「编辑配置」
- **THEN** 保存的配置携带 `thinking_enabled=true`、`thinking_effort="max"`；编辑弹窗
  思考模式呈「开启」、强度呈「高/深」对应档位；关闭思考时强度控件灰置但保留已选值

#### Scenario: 备份与升级带回

- **WHEN** 导出配置备份包并在他处导入，或经版本升级迁入链带回旧库
- **THEN** 思考参数随行携带；旧包/旧库缺键时按关/low 兜底（与旧版运行行为等价）

## MODIFIED Requirements

### Requirement: 按接口格式探测连接

连接测试与模型列表拉取 SHALL 按配置的接口格式构造探测请求，探测目标一律为用户填写的 base_url：`openai` 格式 GET `{base}/models`（base 无版本段时按 OpenAI 惯例补 `/v1`，与生成调用同源推导）+ Bearer 头；`anthropic` 格式 GET `{base}/v1/models` + `x-api-key` 与 `anthropic-version` 头。探测 SHALL NOT 使用硬编码的官方域名。连接测试中 models 端点返回 404 时 SHALL 自动降级为最小生成探针（见下）验证鉴权与对话路径——anthropic 与 openai 两格式同享降级（Gemini 官方 OpenAI 兼容层等不提供模型清单端点的兼容地址因此可用）；只拉清单轻探针（见「模型清单自动拉取」）SHALL NOT 发起降级生成探针（保持零生成调用语义）。

「连接正常」的最终判据 SHALL 是收到格式正确的最小生成回复（2026-10-05 拍板），SHALL NOT 仅凭 models 探测的地位码、可达性或鉴权通过：models 探测的 200 响应体 SHALL 为 API JSON——返回网页等非 JSON 体 SHALL 判失败并提示检查 Base URL（典型：网站首页/SPA 对任意路径回 200 HTML）。可达且鉴权通过后，SHALL 向对话接口发一条真实最小生成探针：用户消息「你好」、思考参数按配置下发（与生成调用同一约定：关＝禁思考；开＝`thinking:{type:enabled}`＋`reasoning_effort`，见「思考参数可配」；端点对带思考参数的请求回 400 时 SHALL 去掉思考参数重试一次，触发 SHALL NOT 依赖错误文案措辞，重试时 SHALL 放大输出预算）、短输出预算（足出一句短答复），与生成调用同址同鉴权头——`openai` 格式 `POST {base}/chat/completions`，`anthropic` 格式 `POST {base}/v1/messages`。探针收到「响应体符合接口格式且含可见回复文本」的响应 SHALL 判「连接正常」；非 2xx、响应体不符合接口格式、回复文本为空 SHALL 一律判失败并给可读原因——400/422 类业务性拒绝（探针模型 id 不被接受等）SHALL NOT 视为通过（原「探针 id 是猜的不拦」口径作废），错误 SHALL 点名所试模型 id 与实际请求地址。探针模型 id 取用顺序：配置已选模型 > 模型列表首个 > 该 vendor 候选 id 首个 >（anthropic 无列表降级时）占位探测模型；openai 格式 404 降级的探针模型 id 取用顺序：配置已选模型（含表单手填初值）> 该 vendor 候选 id 首个，两者皆无时 SHALL NOT 降级（无 id 的生成探针必然无意义），按「提示填写模型名」判失败。无任何可用模型 id（openai 格式模型列表为空且该 vendor 无候选）时 SHALL 判失败并提示填写模型名，SHALL NOT 仅凭可达性或鉴权通过报「连接正常」（原「跳过对话探针」口径作废）。

#### Scenario: Anthropic 格式探测用户地址

- **WHEN** 测试一条 `api_format=anthropic`、base_url 为 GLM Anthropic 地址的配置
- **THEN** 探测请求发往 `{base}/v1/models` 并携带 x-api-key 头，成功时拉取到模型列表

#### Scenario: models 端点缺失时降级探活

- **WHEN** anthropic 格式探测 `{base}/v1/models` 返回 404
- **THEN** 自动改发「你好」最小生成探针（`POST {base}/v1/messages`，思考参数按配置），收到格式正确的回复即报「连接正常」且不报错误

#### Scenario: openai 格式 models 404 同享降级探活

- **WHEN** openai 格式探测 models 端点返回 404（如 Gemini 官方兼容层 `…/v1beta/openai` 不提供清单端点），且配置已选模型（含表单手填初值）或该 vendor 候选 id 可用
- **THEN** 自动改发「你好」最小生成探针（`POST {base}/chat/completions`，思考参数按配置，与生成同址同鉴权头），收到格式正确的回复即报「连接正常」且不报错误

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
- **THEN** 连接测试追加一条 `POST {base}/chat/completions` 最小生成探针（消息「你好」、思考参数按配置、与生成同址同鉴权头）；收到格式正确且含可见回复文本的响应判「连接正常」，非 2xx、体格式不符或空回复判失败，404/405 失败时点名实际请求地址与核对提示；强制思考模型（GLM-5.3 系）拒「关思考」的 400 SHALL 去参重试一次后按重试结果判定，SHALL NOT 将该拒法原样透传为测试失败

#### Scenario: anthropic 格式对话探针

- **WHEN** `anthropic` 格式的 models 探测成功且取得探针模型 id
- **THEN** 连接测试同样追加一条 `POST {base}/v1/messages` 最小生成探针（消息「你好」、思考参数按配置，探针模型 id 取列表首个）；收到格式正确（content 文本块）且含可见回复文本的响应判「连接正常」，格式不符或空回复判失败——判据双格式统一，SHALL NOT 仅凭 models 探测报「连接正常」

#### Scenario: 探针回复格式不正确不算通

- **WHEN** 最小生成探针返回 2xx 但响应体不符合接口格式（网页/错误信封），或可解析但回复文本为空
- **THEN** 判连接失败并提示检查 Base URL 与模型配置，SHALL NOT 报连接正常

#### Scenario: 探针模型被拒不算通并点名所试 id

- **WHEN** 最小生成探针因模型 id 不被接受（400/404 类业务性拒绝）失败——含去参重试后仍败（重试 400 与思考参数无关时回原始响应）
- **THEN** 判连接失败（不按「探针 id 是猜的」放行），错误信息点名所试模型 id 与实际请求地址

#### Scenario: 无可用模型 id 不报连接正常

- **WHEN** openai 格式 models 探测返回空列表且该 vendor 无候选 id
- **THEN** 判连接失败并提示填写模型名，SHALL NOT 仅凭可达性或鉴权通过报「连接正常」
