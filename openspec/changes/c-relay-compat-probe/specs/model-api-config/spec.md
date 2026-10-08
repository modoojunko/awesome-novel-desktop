## MODIFIED Requirements

### Requirement: 按接口格式探测连接

连接测试与模型列表拉取 SHALL 按配置的接口格式构造探测请求，探测目标一律为用户填写的 base_url：`openai` 格式 GET `{base}/models`（base 无版本段时按 OpenAI 惯例补 `/v1`，与生成调用同源推导——models 探测、对话探针、生成调用共用同一归一：路径含 v+数字段（`/v1`、`/v4`、`/v1beta`）即视为已有版本段不改写，裸域名补 `/v1`）+ Bearer 头；`anthropic` 格式 GET `{base}/v1/models` + `x-api-key` 与 `anthropic-version` 头。探测 SHALL NOT 使用硬编码的官方域名。连接测试中 models 端点返回 403 或 404 时 SHALL 自动降级为最小生成探针（见下）验证鉴权与对话路径——anthropic 与 openai 两格式同享降级（404：Gemini 官方 OpenAI 兼容层等不提供模型清单端点的兼容地址因此可用；403：中转站按分组权限拒绝清单访问而 token 本身有效，2026-10-08 lunarfox 实锤「无权访问 gpt特定版分组」——对话路径可能完全可用，SHALL NOT 拿清单 403 短路判「认证失败」形成假阴性）；models 端点返回 401（Key 无效）SHALL 保持硬判鉴权失败，SHALL NOT 降级（对话必同样 401）；只拉清单轻探针（见「模型清单自动拉取」）SHALL NOT 发起降级生成探针（保持零生成调用语义）。

「连接正常」的最终判据 SHALL 是收到格式正确的最小生成回复（2026-10-05 拍板），SHALL NOT 仅凭 models 探测的地位码、可达性或鉴权通过：models 探测的 200 响应体 SHALL 为 API JSON——返回网页等非 JSON 体 SHALL 判失败并提示检查 Base URL（典型：网站首页/SPA 对任意路径回 200 HTML）。可达且鉴权通过后，SHALL 向对话接口发一条真实最小生成探针：用户消息「你好」、关闭思考（与生成调用同一禁思考约定，端点拒绝该参数时去掉重试一次）、短输出预算（足出一句短答复），与生成调用同址同鉴权头——`openai` 格式 `POST {base}/chat/completions`，`anthropic` 格式 `POST {base}/v1/messages`。探针收到「响应体符合接口格式且含可见回复文本」的响应 SHALL 判「连接正常」；非 2xx、响应体不符合接口格式、回复文本为空 SHALL 一律判失败并给可读原因——400/422 类业务性拒绝（探针模型 id 不被接受等）SHALL NOT 视为通过（原「探针 id 是猜的不拦」口径作废），错误 SHALL 点名所试模型 id 与实际请求地址。探针模型 id 取用顺序：配置已选模型 > 模型列表首个 > 该 vendor 候选 id 首个 >（anthropic 无列表降级时）占位探测模型；openai 格式 403/404 降级的探针模型 id 取用顺序：配置已选模型（含表单手填初值）> 该 vendor 候选 id 首个，两者皆无时 SHALL NOT 降级（无 id 的生成探针必然无意义），按「提示填写模型名」判失败。无任何可用模型 id（openai 格式模型列表为空且该 vendor 无候选）时 SHALL 判失败并提示填写模型名，SHALL NOT 仅凭可达性或鉴权通过报「连接正常」（原「跳过对话探针」口径作废）。

#### Scenario: Anthropic 格式探测用户地址

- **WHEN** 测试一条 `api_format=anthropic`、base_url 为 GLM Anthropic 地址的配置
- **THEN** 探测请求发往 `{base}/v1/models` 并携带 x-api-key 头，成功时拉取到模型列表

#### Scenario: 裸域名 base 全链同源归一

- **WHEN** openai 格式 base 无版本段（如裸域名中转站 `https://api.example.com`，其站 SPA 对任意非 `/v1` 路径回 200 网页）
- **THEN** models 探测、对话探针与生成调用均按补 `/v1` 推导，SHALL NOT 出现「清单拉得到、探测/生成打到非版本路径网页」的半通形态；自带版本段的 base（`/v1`、`/api/paas/v4`、`compatible-mode/v1`、Gemini 兼容层 `/v1beta/openai`）SHALL 原样保留不改写

#### Scenario: models 端点缺失时降级探活

- **WHEN** anthropic 格式探测 `{base}/v1/models` 返回 404
- **THEN** 自动改发「你好」最小生成探针（`POST {base}/v1/messages`，禁思考），收到格式正确的回复即报「连接正常」且不报错误

#### Scenario: openai 格式 models 404 同享降级探活

- **WHEN** openai 格式探测 models 端点返回 404（如 Gemini 官方兼容层 `…/v1beta/openai` 不提供清单端点），且配置已选模型（含表单手填初值）或该 vendor 候选 id 可用
- **THEN** 自动改发「你好」最小生成探针（`POST {base}/chat/completions`，禁思考，与生成同址同鉴权头），收到格式正确的回复即报「连接正常」且不报错误

#### Scenario: openai 格式 models 403 同享降级探活（中转站分组权限）

- **WHEN** openai 格式探测 models 端点返回 403（中转站按分组权限拒绝清单访问、token 本身有效，如 lunarfox「无权访问 gpt特定版分组」），且配置已选模型（含表单手填初值）或该 vendor 候选 id 可用
- **THEN** 自动改发「你好」最小生成探针（`POST {base}/chat/completions`，禁思考，与生成同址同鉴权头），收到格式正确的回复即报「连接正常」并附「端点拒绝模型清单访问（403）」说明——SHALL NOT 按鉴权失败判死（假阴性）

#### Scenario: models 403 降级对话同样 403 如实判鉴权失败

- **WHEN** models 端点返回 403 且降级的最小生成探针同样返回 403
- **THEN** 判连接失败（auth_error）并携带上游错误原文——降级只换判定依据，SHALL NOT 放行也不假阳性

#### Scenario: openai 格式 404 降级无 id 不降级

- **WHEN** openai 格式探测 models 端点返回 403 或 404，且既无已选模型（表单模型初值也为空）也无该 vendor 候选 id
- **THEN** 判连接失败并提示填写模型名，SHALL NOT 发起无 id 的生成探针，SHALL NOT 仅凭可达性或鉴权通过报「连接正常」

#### Scenario: models 401 保持硬判鉴权失败

- **WHEN** models 端点返回 401（Key 无效/失效）
- **THEN** 直接判鉴权失败并携带上游原文，SHALL NOT 发起降级探针（对话必同样 401）

#### Scenario: 降级探针打到错误地址

- **WHEN** 任一格式的 models 探测端点返回 403 或 404，降级的最小生成探针返回 404 或 405（Base URL 指向的地址不提供对话接口）
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

### Requirement: 模型清单自动拉取

系统 SHALL 提供「只拉清单」轻探针：按与连接测试完全相同的端点构造（`openai` 格式 GET `{base}/models`（base 无版本段补 `/v1`）+ Bearer 头；`anthropic` 格式 GET `{base}/v1/models` + `x-api-key` 与 `anthropic-version` 头；ollama GET `/api/tags`，一律打用户填写的 base），仅请求模型清单端点，SHALL NOT 发起对话探针（不产生生成调用）。新端点 `POST /api-configs/fetch-models` 接收 raw 配置（vendor/base_url/api_key/api_format，未保存态），返回 `{ok, status, models, candidates?, note?, error?}`。200 响应体非 API JSON（网页等）SHALL 判失败并提示核对 Base URL；**anthropic 格式** 404 SHALL 返回空清单＋该 vendor 候选 id＋「端点不提供模型列表」说明（与连接测试降级同判据，但不发生成请求）；**openai 格式** 403 SHALL 同按零生成语义返回 ok＋空清单＋候选 id＋「端点拒绝模型清单访问（常见于中转站分组权限限制）」说明（2026-10-08 lunarfox 实锤：token 有效仅清单被拒——SHALL NOT 判「认证失败」误导用户；anthropic/ollama 格式 403 保持鉴权失败硬判）；openai/ollama 格式 404 SHALL 按异常响应判失败并提示核对（SHALL NOT 误诊为「无清单端点」）；非 ollama 且 Key 为空 SHALL 判鉴权失败。

创建表单的字段顺序 SHALL 为「Base URL → API Key → 模型」（2026-10-07 拍板：Key 失焦拉到的清单直接喂给紧随其下的模型选择器）。创建表单中，API Key 失焦且非空时 SHALL 自动调用轻探针拉取清单（Ollama 免 Key：供应商或 Base URL 确定后即拉）；vendor、Base URL、接口格式变更且 Key 已填时 SHALL 重拉。在途请求管理：同参数重复触发（在途或已成功）SHALL 不再发起新请求；参数已变的在途响应 SHALL 作废（不落地）；供应商/格式切换作废清单时 SHALL 连同在途请求一并作废。清单到位后模型选择器 SHALL 默认选中**清单首项**（2026-10-07 二次拍板「默认选第一个就好，不评估价值」——登记表默认模型不优先，预填值只作清单到位前的初值）；用户手动改选或手填后 SHALL NOT 被后续自动刷新覆盖（含在途响应迟到时）。选择器 SHALL 带搜索，且 SHALL 始终保留手动填写出口（清单非空时手填用于清单外 id；清单为空/拉取失败时为主入口）。拉取失败 SHALL NOT 阻塞表单（提示可重试）。「测试连接」返回的模型清单 SHALL 同步刷新选择器选项（连接失败信封携带的清单同样刷新——失败但清单真实时用户可改选正确模型；默认选中仅在成功时执行）。

连接测试的对话探针失败时，失败信封 SHALL 携带已提取的模型清单（models 端点 GET 已成功的真实数据）——手填错 id 后重测，清单照常落库，书内选择面板立刻有正确候选可选（自恢复闭环，无需删配置重建）。服务端连接测试自动落库路径 SHALL 与手写路径执行一致的清单归一化（去空白/去重保序），清单条数超过上限 SHALL 截断保留前 N 条而非原样超限落库；落库 SHALL **保头**——配置当前默认模型（models 首项＝用户登记/手选值）在清单内时置于结果首位（不限是否触发截断：保住「首项＝已选模型」语义，下次探针优先用它；截断时尤甚——SHALL NOT 被供应商顺序挤出截断窗）；测试响应体与落库 SHALL 为同一份归一化清单。

#### Scenario: Key 失焦自动拉清单并默认选中首项
- **WHEN** 用户在添加弹窗选择供应商、填入 API Key 后焦点离开 Key 输入框
- **THEN** 表单自动向该供应商清单端点发起轻探针拉取，成功后模型选择器弹层可选全部拉回的模型 id，默认选中清单首项（登记表默认模型在清单内也不优先）

#### Scenario: 登记默认不优先（2026-10-07 二次拍板「不评估价值」）
- **WHEN** 用户选择 DeepSeek 并填入 Key，自动拉取返回含登记默认模型 `deepseek-v4-pro` 的清单（首项为 `deepseek-flash`）
- **THEN** 默认选中清单首项 `deepseek-flash`（预填初值 `deepseek-v4-pro` 仅作清单到位前的显示值），保存后模型列表首项为选中值

#### Scenario: Ollama 免 Key 即拉
- **WHEN** 用户选择 Ollama 供应商（无需 API Key）
- **THEN** Base URL 确定后即自动拉取 `/api/tags` 本地模型清单，无需等待 Key 输入

#### Scenario: 无清单端点退手填兜底
- **WHEN** anthropic 格式端点对 `/v1/models` 返回 404（不提供模型列表）
- **THEN** 轻探针返回空清单＋候选 id＋说明，选择器内保留手填输入行与候选 chips，用户手填模型 id 后可正常保存（首项落库）

#### Scenario: 中转站清单 403 退手填兜底
- **WHEN** openai 格式端点对 models 清单返回 403（分组权限限制，token 本身有效）
- **THEN** 轻探针返回 ok＋空清单＋候选 id＋「拒绝清单访问」说明，表单呈现说明而非「认证失败」，用户手填模型 id 后可正常保存（首项落库）

#### Scenario: 拉取失败不阻塞保存
- **WHEN** 轻探针网络失败或鉴权失败
- **THEN** 模型字段呈现失败提示与「重新拉取」出口，表单其余字段可继续填写并保存（不因拉取失败锁死）

#### Scenario: 测试连接结果刷新清单
- **WHEN** 用户点「测试连接」且测试成功返回模型清单
- **THEN** 选择器选项以测试返回的清单刷新；用户此前手动改选的值在清单内时保持不变

#### Scenario: 超长清单落库截断且保头
- **WHEN** 连接测试拉回的模型清单超过上限（如百炼返回逾百条），且配置当前默认模型排在供应商清单尾部
- **THEN** 自动落库前归一化（去空白/去重）并截断保留前 N 条，配置默认模型置于截断结果首位不被截掉，测试响应体与落库为同一份清单；后续手动 PUT 模型列表 SHALL NOT 因存量超限被拒

#### Scenario: 未超限重测同样保头
- **WHEN** 配置当前默认模型（用户手选值）排在供应商清单第二位及以后，重测拉回的清单未超上限
- **THEN** 落库清单把该默认模型置于首位（首项＝已选模型语义，下次探针优先用它），其余按供应商原序跟随

#### Scenario: 探针失败仍带回清单（自恢复闭环）
- **WHEN** 用户手填了清单外的模型 id 保存，连接测试的 models GET 成功但对话探针因该 id 被拒
- **THEN** 测试判失败并点名所试 id，但失败信封携带已提取的真实清单并照常落库，书内选择面板可直接改选正确模型，无需删除配置重建
