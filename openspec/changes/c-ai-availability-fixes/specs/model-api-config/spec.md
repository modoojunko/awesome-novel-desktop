## MODIFIED Requirements

### Requirement: 按接口格式探测连接

连接测试与模型列表拉取 SHALL 按配置的接口格式构造探测请求，探测目标一律为用户填写的 base_url：`openai` 格式 GET `{base}/models`（base 无版本段时按 OpenAI 惯例补 `/v1`，与生成调用同源推导）+ Bearer 头；`anthropic` 格式 GET `{base}/v1/models` + `x-api-key` 与 `anthropic-version` 头。探测 SHALL NOT 使用硬编码的官方域名。anthropic 格式下 models 端点返回 404 时 SHALL 自动降级为一条 max_tokens=1 的最小请求验证鉴权，降级探针成功（2xx）即报连接正常；降级探针返回 404/405 SHALL 判「对话接口不可达」并提示核对 Base URL 与接口格式，SHALL NOT 报连接正常。

「连接正常」的判据 SHALL 是对话路径可用，SHALL NOT 仅凭 models 探测的地位码：200 响应体 SHALL 为 API JSON——返回网页等非 JSON 体 SHALL 判失败并提示检查 Base URL（典型：网站首页/SPA 对任意路径回 200 HTML）。`openai` 格式在取得探针模型 id（模型列表首个；列表为空时用该 vendor 的候选 id）后 SHALL 追加一条 `POST {base}/chat/completions` 的最小对话探针（max_tokens=1，与生成调用同址同鉴权头）；该探针返回 404/405 SHALL 判失败并点名实际请求地址与核对提示；探针的 400/422 类业务性拒绝（探针 id 不被接受等）SHALL NOT 拦截。

#### Scenario: Anthropic 格式探测用户地址
- **WHEN** 测试一条 `api_format=anthropic`、base_url 为 GLM Anthropic 地址的配置
- **THEN** 探测请求发往 `{base}/v1/models` 并携带 x-api-key 头，成功时拉取到模型列表

#### Scenario: models 端点缺失时降级探活
- **WHEN** anthropic 格式探测 `{base}/v1/models` 返回 404
- **THEN** 自动改发最小验证请求，鉴权通过（2xx）即报「连接正常」且不报错误

#### Scenario: 降级探针打到错误地址
- **WHEN** anthropic 格式下 `{base}/v1/models` 返回 404，降级的最小请求返回 404 或 405（Base URL 指向的地址不提供对话接口）
- **THEN** 判连接失败并提示核对 Base URL 与接口格式，SHALL NOT 报连接正常

#### Scenario: 网页地址不算通
- **WHEN** 探测地址对 `GET {base}/v1/models` 返回 200 但响应体是网页（非 JSON）
- **THEN** 判连接失败并提示「该地址返回的不是 API 数据——请检查 Base URL」

#### Scenario: openai 格式对话探针
- **WHEN** `openai` 格式的 models 探测成功且取得探针模型 id
- **THEN** 连接测试追加一条 `POST {base}/chat/completions`（max_tokens=1，与生成同址同鉴权头）最小对话探针；探针 2xx 判「连接正常」，404/405 判失败并点名实际请求地址与核对提示
