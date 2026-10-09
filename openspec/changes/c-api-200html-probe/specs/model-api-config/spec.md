# model-api-config Delta — 200 网页体降级探对话接口（内测反馈#1 残余）

## MODIFIED Requirements

### Requirement: 按接口格式探测连接

连接测试与模型列表拉取 SHALL 按配置的接口格式构造探测请求，探测目标一律为用户填写的 base_url：`openai` 格式 GET `{归一 base}/models`＋ Bearer 头——归一＝版本段归一（2026-10-09 kakou 中转案）：base 路径无任何版本段时按 OpenAI 惯例补 `/v1`，自带版本段原样保留；版本段判据＝路径段以 `v+数字` 开头即算（`/v1`、`/v4`、`/v1beta/openai`），SHALL NOT 行尾锚定（漏判中段版本段会向 Gemini 官方兼容层 `…/v1beta/openai` 误补出 `…/v1beta/openai/v1/models` 死址）；归一为探测与生成调用的同源单判据——models 探测、对话探针（主链与判废降级链）、生成调用 SHALL 命中同一归一地址，SHALL NOT 出现「清单打归一地址、对话打裸路径」的半通形态；`anthropic` 格式 GET `{base}/v1/models` + `x-api-key` 与 `anthropic-version` 头（不适用版本段归一）。探测 SHALL NOT 使用硬编码的官方域名。连接测试中 models 端点返回 404、或返回 200 但响应体非 API JSON（网页体/软错误信封）时 SHALL 自动降级为最小生成探针（见下）验证鉴权与对话路径——anthropic 与 openai 两格式同享降级（Gemini 官方 OpenAI 兼容层等不提供模型清单端点的兼容地址、网关对未知路径回 200 网页的可用端点因此可用）；只拉清单轻探针（见「模型清单自动拉取」）SHALL NOT 发起降级生成探针（保持零生成调用语义）。

「连接正常」的最终判据 SHALL 是收到格式正确的最小生成回复（2026-10-05 拍板），SHALL NOT 仅凭 models 探测的地位码、可达性或鉴权通过：models 探测的 200 响应体 SHALL 为 API JSON——返回网页等非 JSON 体时 SHALL 先按上段降级探对话接口：降级探针探通 SHALL 报「连接正常」并按「无清单端点」口径返回空模型清单＋该 vendor 候选 id＋「端点不提供模型列表」说明（该端点确不提供清单，探针探通只证对话路径可用）；降级探针亦不通（真网页站的对话接口也 HTML/不存在）SHALL 判失败并**保留体判废原文案**（openai 格式的错误指引 SHALL 含「若地址确认无误，尝试在末尾补 /v1」补救出口，anthropic 格式 SHALL NOT 出该指引），SHALL NOT 以探针文案顶替。可达且鉴权通过后，SHALL 向对话接口发一条真实最小生成探针：用户消息「你好」、思考参数按配置下发（与生成调用同一约定：关＝禁思考；开＝`thinking:{type:enabled}`＋`reasoning_effort`，见「思考参数可配」；端点对带思考参数的请求回 400 时 SHALL 去掉思考参数重试一次，触发 SHALL NOT 依赖错误文案措辞，重试时 SHALL 放大输出预算）、短输出预算（足出一句短答复），与生成调用同址同鉴权头——`openai` 格式 `POST {归一 base}/chat/completions`，`anthropic` 格式 `POST {base}/v1/messages`。探针收到「响应体符合接口格式且含可见回复文本」的响应 SHALL 判「连接正常」；非 2xx、响应体不符合接口格式、回复文本为空 SHALL 一律判失败并给可读原因——400/422 类业务性拒绝（探针模型 id 不被接受等）SHALL NOT 视为通过（原「探针 id 是猜的不拦」口径作废），错误 SHALL 点名所试模型 id 与实际请求地址。探针模型 id 取用顺序：调用方显式覆盖（2026-10-09：已存配置连接测试 `POST /api-configs/{id}/test` 的可选请求体字段 `model`——编辑弹窗改选模型后试连用；空/缺省视同未提供）> 配置已选模型 > 模型列表首个 > 该 vendor 候选 id 首个 >（anthropic 无列表降级时）占位探测模型；models 判废（404 或 200 非 API 体）降级的探针模型 id 取用顺序：调用方显式覆盖 > 配置已选模型（含表单手填初值）> 该 vendor 候选 id 首个，两者皆无时 openai 格式 SHALL NOT 降级（无 id 的生成探针必然无意义）——404 场景按「提示填写模型名」判失败，200 体判废场景保留体判废原文案。无任何可用模型 id（openai 格式模型列表为空且该 vendor 无候选）时 SHALL 判失败并提示填写模型名，SHALL NOT 仅凭可达性或鉴权通过报「连接正常」（原「跳过对话探针」口径作废）。覆盖模型仅影响当次探针取 id，SHALL NOT 单独改变落库清单的保头顺序（落库保头仍按配置已选模型，见「模型清单自动拉取」）。同一请求体 SHALL 支持 `thinking_enabled`/`thinking_effort` 思考参数覆盖（编辑弹窗拨动思考后未保存即试连，表单当前值优先；None/缺省按已存配置）——该端点的探测判据与保存后的生成行为保持一致。

#### Scenario: Anthropic 格式探测用户地址

- **WHEN** 测试一条 `api_format=anthropic`、base_url 为 GLM Anthropic 地址的配置
- **THEN** 探测请求发往 `{base}/v1/models` 并携带 x-api-key 头，成功时拉取到模型列表

#### Scenario: 裸域名 base 探测与生成同归一（中转站网页壳案）

- **WHEN** openai 格式 base_url 为裸域名（如 `https://api.kakouai.com`——中转站网页壳对任意非 `/v1` 路径回 200 网页）
- **THEN** models 探测命中 `{base}/v1/models`，对话探针（含判废降级）与生成调用同命中 `{base}/v1/chat/completions`，SHALL NOT 出现「清单绿、测试红」半通形态（清单打到归一地址、对话打到裸路径网页）

#### Scenario: 中段版本段不重复补版本段

- **WHEN** openai 格式 base_url 为 Gemini 官方兼容层（`https://generativelanguage.googleapis.com/v1beta/openai`，版本段 `/v1beta` 在路径中段）
- **THEN** models 探测命中 `…/v1beta/openai/models`、对话探针命中 `…/v1beta/openai/chat/completions`，SHALL NOT 误判「无版本段」而追补出 `…/v1beta/openai/v1/…` 死址

#### Scenario: models 端点缺失时降级探活

- **WHEN** anthropic 格式探测 `{base}/v1/models` 返回 404
- **THEN** 自动改发「你好」最小生成探针（`POST {base}/v1/messages`，思考参数按配置），收到格式正确的回复即报「连接正常」且不报错误

#### Scenario: openai 格式 models 404 同享降级探活

- **WHEN** openai 格式探测 models 端点返回 404（如 Gemini 官方兼容层 `…/v1beta/openai` 不提供清单端点），且配置已选模型（含表单手填初值）或该 vendor 候选 id 可用
- **THEN** 自动改发「你好」最小生成探针（`POST {归一 base}/chat/completions`，思考参数按配置，与生成同址同鉴权头），收到格式正确的回复即报「连接正常」且不报错误

#### Scenario: openai 格式 404 降级无 id 不降级

- **WHEN** openai 格式探测 models 端点返回 404，且既无已选模型（表单模型初值也为空）也无该 vendor 候选 id
- **THEN** 判连接失败并提示填写模型名，SHALL NOT 发起无 id 的生成探针，SHALL NOT 仅凭可达性或鉴权通过报「连接正常」

#### Scenario: 降级探针打到错误地址

- **WHEN** 任一格式的 models 探测端点判废（404 或 200 非 API 体）触发降级，降级的最小生成探针返回 404 或 405（Base URL 指向的地址不提供对话接口）
- **THEN** 判连接失败并提示核对 Base URL 与接口格式（点名降级探针实际请求地址），SHALL NOT 报连接正常

#### Scenario: 网页地址不算通

- **WHEN** 探测地址对 models 端点返回 200 但响应体是网页（非 JSON），且降级的最小生成探针也打不通（404/405 或同为网页体——真网页站的对话接口也 HTML/不存在）
- **THEN** 判连接失败并保留体判废原文案：「该地址返回的不是 API 数据——请检查 Base URL 是否填成了网站地址（若地址确认无误，尝试在末尾补 /v1）」

#### Scenario: anthropic 格式网页体不提示补 /v1

- **WHEN** anthropic 格式探测地址返回 200 但响应体是网页（非 JSON），且降级的最小生成探针（占位探测模型）也打不通
- **THEN** 判连接失败并保留体判废原文案提示检查 Base URL，SHALL NOT 含「补 /v1」指引（该格式惯例 base 不带 /v1，探针侧会剥掉，补了是空操作）

#### Scenario: 200 网页体网关 + 对话接口正常 → 放行

- **WHEN** 配置的 base_url 是「对未知路径回 200 网页、真实生成接口正常」的网关（如 ccswitch 类中转站），连接测试的 models 探测拿到 200 网页体，且配置已选模型（含表单手填初值）或该 vendor 候选 id 可用
- **THEN** 自动改发「你好」最小生成探针（与 404 降级同址同头同 id 链，思考参数按配置），收到格式正确且含可见回复文本的回复即报「连接正常」，并按「无清单端点」口径返回空模型清单＋候选 id＋说明

#### Scenario: 200 网页体 + 无探针 id 不降级

- **WHEN** openai 格式 models 探测拿到 200 网页体，且既无已选模型（表单模型初值也为空）也无该 vendor 候选 id
- **THEN** 判连接失败并保留体判废原文案，SHALL NOT 发起无 id 的生成探针

#### Scenario: 轻探针体判废不发生成探针（零生成调用守恒）

- **WHEN** 只拉清单轻探针（创建表单自动拉清单）的 models 探测拿到 200 网页体
- **THEN** 按失败返回体判废文案（提示核对 Base URL），SHALL NOT 发起任何对话探针

#### Scenario: openai 格式对话探针

- **WHEN** `openai` 格式的 models 探测成功且取得探针模型 id
- **THEN** 连接测试追加一条 `POST {归一 base}/chat/completions` 最小生成探针（消息「你好」、思考参数按配置、与生成同址同鉴权头）；收到格式正确且含可见回复文本的响应判「连接正常」，非 2xx、体格式不符或空回复判失败，404/405 失败时点名实际请求地址与核对提示；强制思考模型（GLM-5.3 系）拒「关思考」的 400 SHALL 去参重试一次后按重试结果判定，SHALL NOT 将该拒法原样透传为测试失败

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

#### Scenario: 已存配置按覆盖模型试连

- **WHEN** 用户在编辑弹窗改选模型后点「测试连接」且未重敲 API Key（走已存密钥的配置测试端点）
- **THEN** 对话探针以改选模型为探针 id（改选模型被拒时错误点名该 id）；未改选/留空时仍按已存模型列表首项

#### Scenario: 已存配置按表单思考值试连

- **WHEN** 用户在编辑弹窗拨动思考开关/强度（尚未保存）后点「测试连接」且未重敲 API Key
- **THEN** 探针按表单当前思考参数发（与保存后的生成行为同判据）；未拨动时按已存配置
