## Why

内测（2026-10-05，四档套餐首发批）暴露的两个 AI 可用性问题：

1. **门禁互换（严重，#679 引入）**：四档接入时 `POST /write`（正文生成）误挂 `ai-polish`（MAX）、`POST /write/polish`（去AI味）误挂 `ai-generate`（PRO）——PRO/trial 用户 AI 生成正文被 403（付费买的能力用不了），去AI味反被 PRO 档白拿。口径单源明确（`docs/contracts/entitlement-defaults.json` v2、`features.ts`、tier-plan-four-tiers tasks 3.2「ai-polish×1（去AI味 /polish）」）：`ai-generate`=PRO、`ai-polish`=MAX 且全仓仅 `/polish` 一个消费点。现有 e2e 漏网原因：`ai-write-route` 只断言「非 404」（403/409 都算注册成功），去AI味用例种的是 max 档。
2. **上游 405 不可诊断（内测反馈截图）**：用户点「去AI味」收到 `AI 生成失败，可重试：Error code: 405 - {'detail': 'Method Not Allowed'}`——上游模型服务对请求地址拒绝（FastAPI/Starlette 风格 405 响应体），经 SDK `APIStatusError` 原样透传，用户无从知道该改哪里；且「测试连接」只探 models 端点——网站首页对任意路径回 200 HTML 也会「测试通过」，坏配置一路走到生成期才炸。

## What Changes

- **门禁归位**：`write/router.py` 两处 `@ai_feature` 互换回位——`POST /write`→`ai-generate`，`POST /write/polish`→`ai-polish`；补档位回归钉（standard→403 pro / trial 过门 / pro 打 polish→403 max）。
- **生成期可诊断**：`ai_client.py` 对上游 404/405 归一为 `AIRequestError`——文案点名实际请求地址（`{base}/chat/completions` 或 `{base}/v1/messages`，SDK 同源拼法）与「模型配置」去处；其余状态（400/401/429…）保持 SDK 原始报错透传，不改写供应商业务信息。非流式与流式（正文生成）两条路径同归一。
- **连接测试收紧**（`api_configs/connection.py`）：「通」的判据从「models 探测的地位码」改为「真实最小生成收到格式正确回复」（2026-10-05 用户拍板）——
  - 200 响应体必须为 API JSON：网页/非 JSON 体判失败（此前 SPA 首页 200 HTML 会误报「连接正常」）；
  - anthropic 降级探针打到错误地址（404/405）判失败（此前对一切非 401/403 都报「连接正常」）；
  - 可达且鉴权通过后发真实最小生成探针：消息「你好」、关闭思考（`ai_client` 同款禁思考约定，端点拒绝该参数时去参重试一次）、短输出预算，与生成同址同鉴权头（openai `POST {base}/chat/completions`／anthropic `POST {base}/v1/messages`，models 缺失的降级路径同此探针）；**收到接口格式正确且含可见回复文本的回复才判「连接正常」**——非 2xx、体格式不符、空回复一律判失败；400/422 类业务性拒绝不再放行（原「探针 id 是猜的不拦」口径作废），错误点名所试模型 id 与实际请求地址；探针模型 id 取用顺序＝配置已选模型→列表首个→vendor 候选首个→anthropic 占位探测模型。
- 明确不做：Base URL 自动改写/预填（沿用 2026-09-06「URL 不预填」拍板，本次只做判据收紧与错误诊断）；非 404/405 的生成期错误文案不改写。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`: 「按接口格式探测连接」收紧——连接判据改为「真实最小生成收到格式正确回复」（非 JSON 200 判败、「你好」禁思考最小生成、格式正确回复才算通、探针模型被拒点名所试 id）。

## Impact

- `client/backend/write/router.py`（门禁两行归位）
- `client/backend/ai_client.py`（`AIRequestError` ＋ 404/405 归一；`_guarded`/`chat_stream` 共用）
- `client/backend/api_configs/connection.py`（判据收紧＋对话探针）
- 测试：`tests/test_ai_feature_http.py`（档位回归钉 4 条）、`tests/test_ai_client_upstream_errors.py`（新增 4 例）、`tests/test_api_format.py`（连接判据 6 例＋fake 扩展）、`tests/conftest.py`（SDK stub 补 `APIStatusError`）
- 无前端改动（错误文案经既有 502 / 连接测试错误位透出）；config-page e2e 走 `127.0.0.1:1` 网络错误路径，不受判据收紧影响
