# model-api-config Specification

## Purpose

模型配置屏的接口格式能力：让每条 API 配置显式声明 OpenAI 或 Anthropic 接口格式，系统按该格式调用大模型、探测连接，并保证存量配置与备份包平滑兼容。

## Requirements

### Requirement: 接口格式为配置的一级字段

每条模型配置 SHALL 持久化一个接口格式字段 `api_format`，取值仅为 `openai` 或 `anthropic`，默认 `openai`。接口格式与供应商正交：同一供应商的配置可分别声明两种格式。

#### Scenario: 新建配置默认 OpenAI 格式
- **WHEN** 用户添加配置且未显式选择接口格式
- **THEN** 该配置保存后 `api_format` 为 `openai`

#### Scenario: 厂商锁定矩阵
- **WHEN** 用户在添加弹窗选择 OpenAI、Anthropic 或 Ollama 供应商
- **THEN** 接口格式控件呈置灰锁定态，分别固定为 OpenAI 格式、Anthropic 格式、OpenAI 格式，不可切换
- **WHEN** 用户选择 GLM、Kimi、DeepSeek、Qwen 或 OpenAI 兼容供应商
- **THEN** 接口格式控件可在 OpenAI 格式 / Anthropic 格式间切换

### Requirement: 供应商默认值预填

系统 SHALL 提供供应商默认值登记表（键＝供应商×接口格式，值＝官方 Base URL＋默认模型名称＋备选模型候选），作为创建表单预填的单一数据源。登记纪律＝有据才登记（实测或厂商官方文档），无据字段 SHALL 留空，SHALL NOT 编造；登记的 Base URL SHALL 与生成调用链路同源可用——SDK 生成调用以 base_url 直拼请求路径（不自补版本段），登记值须含版本段（OpenAI 官方为 `https://api.openai.com/v1`，Ollama 为 `http://localhost:11434/v1`），SHALL NOT 登记缺版本段的裸域名（生成 404 的死值）；首批全量登记 DeepSeek，其余内置供应商按官方文档核对后登记。

创建模型配置时，用户选中登记表内的供应商（或切换接口格式）后，表单 SHALL 自动填入该「供应商×接口格式」登记的 Base URL 与默认模型名称，用户只需填写 API Key 即可保存；「模型」SHALL 为创建与编辑表单的一级字段（2026-10-09 拍板，修复「编辑页没有模型可选、实际测试连接又要用模型」——连接测试必须用模型做真实生成探针，已存配置恒用模型列表首项，探针模型失败后用户须能在编辑页改选），形态为**模型选择器**（自动拉取清单，见「模型清单自动拉取」）：登记的默认模型名称为清单到位前的初值（清单到位后默认选中清单首项，登记值不优先）；清单为空或拉取失败时 SHALL 退为手填输入（登记默认模型名称为初值）。保存后选中值（或手填值）SHALL 为该配置模型列表首项。预填字段 SHALL 可编辑。字段为空、或仍等于预填值（用户未手改）时，SHALL 随供应商/格式切换更新为新登记值；用户手改过的字段 SHALL NOT 被覆盖。「OpenAI 兼容」等无登记值的供应商 SHALL NOT 预填（沿用 placeholder 示例域名引导；清单自动拉回后的默认选中不算预填）。编辑已有配置 SHALL NOT 施加预填（沿用已存值）：模型选择器初值 SHALL 为该配置已存模型列表首项（＝该配置已选模型/探针优先模型），清单种子＝已存模型列表（弹层立即可改选或手填清单外 id），已存初值视同手改（SHALL NOT 被拉取/测试的「清单首项」默认选中覆盖）；编辑保存时改选值 SHALL 置模型列表首项（保留其余已存项按原序，超上限截断对齐手动路径），留空 SHALL 省略模型列表字段（沿用已存值，与「留空则保留当前密钥」同语义）。

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

#### Scenario: 编辑弹窗改选模型并保存置首

- **WHEN** 用户编辑一条已存模型列表的配置，从选择器改选另一模型后保存
- **THEN** 保存成功且模型列表首项＝改选值（后续卡片测试连接优先用它），其余已存项按原序保留；重新打开编辑弹窗时模型字段初值＝该改选值

#### Scenario: 编辑态模型留空沿用已存值

- **WHEN** 用户清空编辑弹窗的模型名称字段后保存
- **THEN** 更新请求省略模型列表字段（沿用已存值，与「留空则保留当前密钥」同语义），已存模型列表不变

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

### Requirement: 编辑态可改接口格式

编辑已有配置时供应商保持锁定，接口格式 SHALL 允许修改且不弹二次确认；修改后该配置已拉取的模型列表与最近测试结果 SHALL 立即失效，需重新测试。

#### Scenario: 改格式后模型缓存失效
- **WHEN** 用户编辑一条已有模型列表的配置并切换接口格式后保存
- **THEN** 该配置的模型列表与测试状态被清空，配置卡提示需重新测试

### Requirement: 按接口格式调用大模型

大模型调用 SHALL 依据配置的 `api_format` 选择对应契约：`openai` 走 chat/completions 报文，`anthropic` 走 Anthropic messages 报文。显式 `api_format` SHALL 优先于任何基于 URL 字符串的格式推断；仅当配置无格式信息（旧数据回退路径）时才按「URL 含 anthropic 即 anthropic」推断。

#### Scenario: 显式格式压过 URL 猜测
- **WHEN** 一条 `api_format=anthropic` 的配置，其 base_url 不含 "anthropic" 字样
- **THEN** 调用走 Anthropic messages 契约且正常收到回复
- **WHEN** 一条 `api_format=openai` 的配置，其 base_url 含 "anthropic" 字样
- **THEN** 调用走 OpenAI chat/completions 契约

#### Scenario: 两种格式全链路可用
- **WHEN** 分别以 GLM 的 OpenAI 格式地址与 Anthropic 格式地址（`https://open.bigmodel.cn/api/anthropic`）各建一条配置并触发生成
- **THEN** 非流式与流式生成均正常返回，token 用量正常计入

### Requirement: 按接口格式探测连接

连接测试与模型列表拉取 SHALL 按配置的接口格式构造探测请求，探测目标一律为用户填写的 base_url：`openai` 格式 GET `{base}/models`（base 无版本段时按 OpenAI 惯例补 `/v1`，与生成调用同源推导）+ Bearer 头；`anthropic` 格式 GET `{base}/v1/models` + `x-api-key` 与 `anthropic-version` 头。探测 SHALL NOT 使用硬编码的官方域名。连接测试中 models 端点返回 404 时 SHALL 自动降级为最小生成探针（见下）验证鉴权与对话路径——anthropic 与 openai 两格式同享降级（Gemini 官方 OpenAI 兼容层等不提供模型清单端点的兼容地址因此可用）；只拉清单轻探针（见「模型清单自动拉取」）SHALL NOT 发起降级生成探针（保持零生成调用语义）。

「连接正常」的最终判据 SHALL 是收到格式正确的最小生成回复（2026-10-05 拍板），SHALL NOT 仅凭 models 探测的地位码、可达性或鉴权通过：models 探测的 200 响应体 SHALL 为 API JSON——返回网页等非 JSON 体 SHALL 判失败并提示检查 Base URL（典型：网站首页/SPA 对任意路径回 200 HTML）。可达且鉴权通过后，SHALL 向对话接口发一条真实最小生成探针：用户消息「你好」、关闭思考（与生成调用同一禁思考约定，端点拒绝该参数时去掉重试一次）、短输出预算（足出一句短答复），与生成调用同址同鉴权头——`openai` 格式 `POST {base}/chat/completions`，`anthropic` 格式 `POST {base}/v1/messages`。探针收到「响应体符合接口格式且含可见回复文本」的响应 SHALL 判「连接正常」；非 2xx、响应体不符合接口格式、回复文本为空 SHALL 一律判失败并给可读原因——400/422 类业务性拒绝（探针模型 id 不被接受等）SHALL NOT 视为通过（原「探针 id 是猜的不拦」口径作废），错误 SHALL 点名所试模型 id 与实际请求地址。探针模型 id 取用顺序：调用方显式覆盖（2026-10-09：已存配置连接测试 `POST /api-configs/{id}/test` 的可选请求体字段 `model`——编辑弹窗改选模型后试连用；空/缺省视同未提供）> 配置已选模型 > 模型列表首个 > 该 vendor 候选 id 首个 >（anthropic 无列表降级时）占位探测模型；openai 格式 404 降级的探针模型 id 取用顺序：调用方显式覆盖 > 配置已选模型（含表单手填初值）> 该 vendor 候选 id 首个，两者皆无时 SHALL NOT 降级（无 id 的生成探针必然无意义），按「提示填写模型名」判失败。无任何可用模型 id（openai 格式模型列表为空且该 vendor 无候选）时 SHALL 判失败并提示填写模型名，SHALL NOT 仅凭可达性或鉴权通过报「连接正常」（原「跳过对话探针」口径作废）。覆盖模型仅影响当次探针取 id，SHALL NOT 单独改变落库清单的保头顺序（落库保头仍按配置已选模型，见「模型清单自动拉取」）。

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

#### Scenario: 已存配置按覆盖模型试连

- **WHEN** 用户在编辑弹窗改选模型后点「测试连接」且未重敲 API Key（走已存密钥的配置测试端点）
- **THEN** 对话探针以改选模型为探针 id（改选模型被拒时错误点名该 id）；未改选/留空时仍按已存模型列表首项

### Requirement: 模型清单自动拉取

系统 SHALL 提供「只拉清单」轻探针：按与连接测试完全相同的端点构造（`openai` 格式 GET `{base}/models`（base 无版本段补 `/v1`）+ Bearer 头；`anthropic` 格式 GET `{base}/v1/models` + `x-api-key` 与 `anthropic-version` 头；ollama GET `/api/tags`，一律打用户填写的 base），仅请求模型清单端点，SHALL NOT 发起对话探针（不产生生成调用）。新端点 `POST /api-configs/fetch-models` 接收 raw 配置（vendor/base_url/api_key/api_format，未保存态），返回 `{ok, status, models, candidates?, note?, error?}`。200 响应体非 API JSON（网页等）SHALL 判失败并提示核对 Base URL；**anthropic 格式** 404 SHALL 返回空清单＋该 vendor 候选 id＋「端点不提供模型列表」说明（与连接测试降级同判据，但不发生成请求）；openai/ollama 格式 404 SHALL 按异常响应判失败并提示核对（SHALL NOT 误诊为「无清单端点」）；非 ollama 且 Key 为空 SHALL 判鉴权失败。

创建表单的字段顺序 SHALL 为「Base URL → API Key → 模型」（2026-10-07 拍板：Key 失焦拉到的清单直接喂给紧随其下的模型选择器；编辑表单同序）。创建表单中，API Key 失焦且非空时 SHALL 自动调用轻探针拉取清单（Ollama 免 Key：供应商或 Base URL 确定后即拉）；vendor、Base URL、接口格式变更且 Key 已填时 SHALL 重拉。编辑表单同口径（2026-10-09）：API Key 重填后失焦且非空（或 Ollama 免 Key）SHALL 自动拉取，显式「获取模型」按钮同样可用——raw 轻探针需要明文 Key，Key 未重填时按钮 SHALL 禁用并提示重填（已存清单已在选择器中可选，不阻塞改选）；编辑态接口格式切换作废清单时 SHALL NOT 施加供应商预填（沿用已存值）。在途请求管理：同参数重复触发（在途或已成功）SHALL 不再发起新请求；参数已变的在途响应 SHALL 作废（不落地）；供应商/格式切换作废清单时 SHALL 连同在途请求一并作废。清单到位后模型选择器 SHALL 默认选中**清单首项**（2026-10-07 二次拍板「默认选第一个就好，不评估价值」——登记表默认模型不优先，预填值只作清单到位前的初值；编辑态已存初值视同手改，SHALL NOT 被覆盖）；用户手动改选或手填后 SHALL NOT 被后续自动刷新覆盖（含在途响应迟到时）。选择器 SHALL 带搜索，且 SHALL 始终保留手动填写出口（清单非空时手填用于清单外 id；清单为空/拉取失败时为主入口）。拉取失败 SHALL NOT 阻塞表单（提示可重试）。「测试连接」返回的模型清单 SHALL 同步刷新选择器选项（连接失败信封携带的清单同样刷新——失败但清单真实时用户可改选正确模型；默认选中仅在成功时执行）。

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

#### Scenario: 拉取失败不阻塞保存
- **WHEN** 轻探针网络失败或鉴权失败
- **THEN** 模型字段呈现失败提示与「重新拉取」出口，表单其余字段可继续填写并保存（不因拉取失败锁死）

#### Scenario: 测试连接结果刷新清单
- **WHEN** 用户点「测试连接」且测试成功返回模型清单
- **THEN** 选择器选项以测试返回的清单刷新；用户此前手动改选的值在清单内时保持不变

#### Scenario: 编辑态重填 Key 自动拉取与获取模型
- **WHEN** 用户编辑配置时重填 API Key 后失焦（或 Ollama 免 Key），或点「获取模型」
- **THEN** 按当前参数发起轻探针，清单到位刷新选择器，已存初值（已选模型）不被「清单首项」默认选中覆盖；Key 未重填时「获取模型」按钮禁用并提示重填，已存清单仍可在弹层改选

#### Scenario: 超长清单落库截断且保头
- **WHEN** 连接测试拉回的模型清单超过上限（如百炼返回逾百条），且配置当前默认模型排在供应商清单尾部
- **THEN** 自动落库前归一化（去空白/去重）并截断保留前 N 条，配置默认模型置于截断结果首位不被截掉，测试响应体与落库为同一份清单；后续手动 PUT 模型列表 SHALL NOT 因存量超限被拒

#### Scenario: 未超限重测同样保头
- **WHEN** 配置当前默认模型（用户手选值）排在供应商清单第二位及以后，重测拉回的清单未超上限
- **THEN** 落库清单把该默认模型置于首位（首项＝已选模型语义，下次探针优先用它），其余按供应商原序跟随

#### Scenario: 探针失败仍带回清单（自恢复闭环）
- **WHEN** 用户手填了清单外的模型 id 保存，连接测试的 models GET 成功但对话探针因该 id 被拒
- **THEN** 测试判失败并点名所试 id，但失败信封携带已提取的真实清单并照常落库，书内选择面板可直接改选正确模型，无需删除配置重建

### Requirement: 存量配置迁移等价

本地库升级 SHALL 幂等新增接口格式字段并回填存量行：base_url 含 "anthropic" 或供应商为 anthropic 的配置回填为 `anthropic`，其余为 `openai`，与升级前的运行时格式推断严格等价；重复启动 SHALL NOT 重复迁移或改变结果。

#### Scenario: 升级零行为变化
- **WHEN** 存量用户升级到新版并照常使用任一旧配置生成
- **THEN** 走的接口格式与升级前一致

### Requirement: 配置删除撤销与名称让位

删除模型配置 SHALL 为软删：行保留（`status="deleted"`），支撑前端撤销窗口内 `POST /api-configs/{id}/restore` 复活同一 id（配置名/加密 Key/Base URL 原样回来）；软删行 SHALL NOT 出现在任何配置列表与可用配置面；删除仍 SHALL 置空受影响项目的 `ai_config_id`（既有级联契约不变）。活跃（`status != "deleted"`）配置之间重名 SHALL 拒绝（409「名称已被使用」，创建与改名同判）。名字只被软删行占着时，系统 SHALL 让软删行自动改名让位（形态 `{原名}（已删除 {行id}）`，嵌行主键保证唯一；软删行不在任何列表出现，让位名用户不可见），此后新建同名与改名到该名 SHALL 放行（2026-10-08 用户拍板翻转原「tombstone 永久占名」口径：撤销窗口过期后被看不见的行堵死重建＝「没删干净」体感）。朱雀保留名 SHALL NOT 参与让位：`vendor="zhuque"` 的行（任何状态）与「朱雀 AI 检测」撞名时一律 SHALL 409（`get_zhuque_config` 按 name+vendor 单槽位查行，名字被普通配置借走＝朱雀行永久查不到）。让位改名与调用方随后的写入 SHALL 分批落库（SQLite 唯一约束逐行检查，同批自撞）；create/update 路由对唯一约束冲突 SHALL 兜底转 409（回滚，SHALL NOT 以 500 形态漏出）。改名接口的名称长度契约 SHALL 与创建一致（1–100）。

#### Scenario: 撤销窗口内删除恢复原名
- **WHEN** 用户删除配置后在撤销窗口内点撤销
- **THEN** 同一 id 复活为活跃，名称/密钥/Base URL 原样保留，列表重新可见

#### Scenario: 软删后同名重建放行
- **WHEN** 用户删除配置「X」后（撤销窗口已过期）新建同名「X」
- **THEN** 创建成功进列表；旧软删行仍在库但已让出名称（改为不可见的让位名），不再报「名称已被使用」

#### Scenario: 重建同名后撤销两配置并存
- **WHEN** 用户删除「X」→ 重建同名「X」→ 又点撤销复活旧行
- **THEN** 两份配置并存且名称互不冲突（复活行带让位名）

#### Scenario: 改名到软删占名放行
- **WHEN** 用户把配置 B 改名为已删配置 A 占用的名字
- **THEN** 改名成功，A 行让位、B 行启用新名

#### Scenario: 朱雀保留名一律 409
- **WHEN** 用户以「朱雀 AI 检测」为名创建或改名普通配置，且该名被朱雀行（含软删）占用
- **THEN** 一律 409 拒绝，朱雀行不被让位改名

#### Scenario: 极端序约束兜底不出 500
- **WHEN** 让位名与既有字面名相撞（或并发交错）触发唯一约束冲突
- **THEN** 创建/改名路由回滚并返回 409「名称已被使用」，不产生 500

### Requirement: 备份包接口格式前向兼容

配置包导出 SHALL 在每条 api_config 中包含 `api_format` 键（加键兼容契约内，不升 format_version）；导入 SHALL 接受缺失该键的旧包并默认 `openai`，接受含该键的新包并逐条还原。

#### Scenario: 新旧包互导
- **WHEN** 新版导出的配置包导入新版，或旧版导出（无 api_format 键）的配置包导入新版
- **THEN** 前者接口格式逐条一致还原，后者全部落 `openai` 且不报错

### Requirement: 配置域请求失败语义统一

模型配置域的请求（配置列表、连接探测、模型候选、用量统计、切换历史、设备激活）SHALL 经统一请求出口发起，失败时呈现与其他域一致的可读语义：认证失效回登录页、服务不可用给统一提示、会员门控给出升级出口；SHALL NOT 把原始状态码（如「HTTP 401」「HTTP 503」）直接呈现给用户。

#### Scenario: 配置列表失败不露原始状态码

- **WHEN** 配置列表请求失败（服务不可用）
- **THEN** 呈现统一的服务不可用提示与重试出口，不出现「HTTP 503」

#### Scenario: 模型就绪态失败可见

- **WHEN** 模型状态探测失败（非 ok 响应或网络错误）
- **THEN** 就绪态呈现失败/未知语义（不静默停留在旧值），并提供重试入口

#### Scenario: 会员门控出口

- **WHEN** 配置域请求收到会员门控拒绝（member_required）
- **THEN** 呈现升级引导出口，与主栈口径一致

### Requirement: Key 静态加密与钥匙同库自包含

- API Key 静态加密的 Fernet 钥匙 SHALL 存储**在数据库内**（应用级元数据 KV 表的一行）；**稳态运行** SHALL NOT 依赖数据目录中的独立钥匙文件（仅两处一次性读取：首启钥匙初始化、库间迁入的密钥转接）。库（含钥匙行）SHALL 成为自包含单元——凡库整体移动/备份/恢复之处，钥匙随行，密文保持可解。
- 钥匙生命周期 SHALL 与库绑定：不存在钥匙行时，启动期 SHALL 按以下顺序初始化——①若数据目录存在旧钥匙文件且内容**合法**（可通过 Fernet 构造校验），SHALL 将其内容**原样**迁入库（零重加密，存量密文保持可解，迁移对用户无感）；②文件不存在或内容**非法**（空/截断/非 Fernet 格式）时 SHALL 生成新钥匙入库并记 warning（非法文件原样保留不删，库内既有密文按「密文无法解密」引导重填）。迁移成功后旧文件 SHALL **保留**（退役为只读遗留，不再参与任何逻辑）——同机新旧版本混跑/回滚时旧版读文件、新版读库行，两者内容一致，密文保持可解。
- 启动期钥匙初始化 SHALL 在数据库结构就绪（建表/补列/指纹戳）之后、任何需要加解密的启动步骤（含 `config.json`→User、User→ApiConfig 迁移中的 Key 加密）与任何 AI 加解密调用之前完成；并发首启同时写入钥匙行时 SHALL 以「先落库者胜、后到者重读装载」消解（迁移来源相同则内容一致，零分叉）；初始化失败 SHALL 快速失败（明确报错），SHALL NOT 静默退化为「全部密文不可解」且无提示。
- **安全取舍 SHALL 显式化**：钥匙入库后「库文件单独流出时 Key 不可读」的保护视为放弃（db 流出即钥匙流出）。备份链路行为不变：导出包内 Key 保持明文、导入时以本地钥匙重加密，包内既无密文也无钥匙材料。
- 密文无法解密（钥匙更换/丢失致旧密文成死文） SHALL 属可恢复状态：设置页重新保存 Key 即以当前钥匙重加密，**无需删除配置或重建绑定**。
- **库间迁入链路的密钥转接**：通过库迁移端点把旧库数据迁入当前库时，系统 SHALL 做**密钥转接**——对目标库中按当前钥匙不可解、且能用「源库钥匙行」或「数据目录旧钥匙文件」解开的 `api_configs` 密文行，SHALL 按当前钥匙**重加密后原地改写**，使用户无需重填；转接 SHALL 幂等、SHALL NOT 影响目标库既有可解密文、SHALL NOT 写入源库。仅当两把源钥匙均不可得（或该行无法解开）时，SHALL 在迁入报告与结果呈现中**按条计数**提示「N 条配置的 Key 需重新粘贴」；该状态的运行期表现由「密文无法解密」的 503 引导承接。源库钥匙 SHALL 仅被只读读取，SHALL NOT 搬入目标库（`app_meta` 仍不随行）。

#### Scenario: 旧钥匙文件存在时迁移零感

- Given 库内无钥匙行，数据目录存在旧 `.fernet_key` 文件（内容合法），且库内有以该钥匙加密的 `enc:` 密文
- When 应用启动完成
- Then 钥匙行内容等于旧文件内容，存量配置的 Key 保持可解（用户无需重填）；旧文件保留且内容不变

#### Scenario: 旧钥匙文件非法时按不存在处理

- Given 库内无钥匙行，数据目录存在 `.fernet_key` 文件但内容为空或截断（Fernet 构造失败）
- When 应用启动完成
- Then 生成新钥匙入库（记 warning），非法文件原样保留；库内既有 `enc:` 密文按「密文无法解密」引导重填，SHALL NOT 因非法钥匙内容在加解密时抛未处理异常

#### Scenario: 旧钥匙文件不存在时生成新钥匙

- Given 库内无钥匙行，数据目录不存在旧钥匙文件
- When 应用启动完成
- Then 生成新钥匙入库；库内既有 `enc:` 密文解不开，相关配置按「密文无法解密」引导重填（不 500）

#### Scenario: 库整体迁移带钥匙

- Given 应用已初始化钥匙行的数据目录
- When 将该数据目录的库文件整体移动到另一环境并启动
- Then 钥匙随库行生效，库内全部密文保持可解

#### Scenario: 库间迁入完成密钥转接（正常态无感）

- Given 新库已用自身钥匙初始化；通过迁移端点迁入含 `enc:` 密文的旧库，且源库钥匙行或旧钥匙文件可读
- When 迁入完成
- Then 迁入的报告与结果呈现均**不出现**「需重新粘贴」；目标库中这些配置以当前钥匙可解密；目标库既有密文不受影响；源库字节不变

#### Scenario: 库间迁入带死文密文时报告提示

- Given 源库含 `enc:` 密文，而源库无钥匙行且旧钥匙文件缺失或内容非法
- When 迁入完成
- Then 报告给出按条计数「N 条配置的 Key 需重新粘贴」；目标库这些行保持原样；运行期按「密文无法解密」引导（503 `no_key`），SHALL NOT 500

#### Scenario: 备份包不含钥匙材料

- Given 用户导出备份包并导入另一台库（钥匙行不同）的实例
- When 导入完成
- Then 导入的配置 Key 以本地钥匙重加密后可用（既有明文导出/重加密导入行为不变），备份包内不存在钥匙材料

### Requirement: Key 判据与引导（两个 Key 世界互不顶替）

- 「已配写作大模型 Key」判据 SHALL 单源在判定层 `user_has_ai_key`（门控层不得内联重写）：候选取 active 行、按**可解密口径**（死文不算已配）、排除 `vendor="zhuque"`，并保留旧 `User.api_key` 与 config.json 的迁移期兜底。
- 会员调用**使用大模型的功能**而该判据为假时，端点 SHALL 返回 503 且文案指向写作大模型配置口（「模型配置 → 写作大模型」）；SHALL NOT 用不区分 Key 归属的含糊措辞（如「AI 服务未配置」）让用户不知道该配哪把 Key。
- 朱雀 Key 的配置状态 SHALL NOT 参与该判据：只配朱雀 SHALL NOT 影响任何大模型功能的可用性判定；对称地，写作大模型 Key SHALL NOT 顶替朱雀 Key——朱雀检测未配置时按其自身 503 引导（见 zhuque-detection）。

#### Scenario: 只配朱雀 → 大模型功能提示去配大模型

- **GIVEN** 会员只配了朱雀 Key（无任何写作大模型 Key）
- **WHEN** 调用任一需要写作大模型的功能
- **THEN** 返回 503，文案含「写作大模型」并指向「模型配置 → 写作大模型」；SHALL NOT 因朱雀行存在而放行、再在更深处失败

#### Scenario: 只配大模型 → 朱雀功能各自引导

- **GIVEN** 会员只配了写作大模型 Key（未配朱雀）
- **WHEN** 打开模型配置页朱雀页签，或发起朱雀检测
- **THEN** 页签配置动作照常可完成（配置不分套餐权益）；检测返回 503 `zhuque_not_configured` 指向朱雀配置口——写作大模型配置 SHALL NOT 顶替朱雀 Key
