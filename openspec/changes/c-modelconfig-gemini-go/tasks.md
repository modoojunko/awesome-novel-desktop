# Tasks — c-modelconfig-gemini-go

## 1. 原型先行（C端 用户可见改动，硬性流程第 1 步）

- [x] 1.1 将过审设计稿落为 `docs/design-c/prototypes/model-config.html` 的更新（供应商 tab 两页＋Gemini/Go 方块＋引导文案收窄＋思考提示；可从 `drafts/ai-novel-c端-模型配置-Gemini与OpenCodeGo-原型.html` 移植 graft 逻辑，宿主换成 model-config 屏现行基线），`npm run design:check` 矩阵中 model-config 相关对比通过
- [x] 1.2 在 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记偏差项：tab 两页、新方块与「新」角标、OpenAI 兼容引导文案收窄（Gemini 句移除）、Gemini 思考提示句、页签切换不清已选（原型未定义行为的补全，见 design §Decisions 2）；附注既有语义「编辑 base_url 触发厂商重检测，用户微调地址会掉回 OpenAI 兼容」（新方块与存量厂商同规矩）；并核对不含「待排期」方块与实现词汇

## 2. 前端：类型、登记表与锁定矩阵

- [x] 2.1 `types/api-config.ts` VendorId 枚举新增 `gemini`、`opencode-go-chat`、`opencode-go-claude`（三键与后端 KNOWN_VENDORS 逐字相等——落库走检测链、编辑回显按存储值，见 4.1 与 design §Decisions 8），`tsc --noEmit` 通过
- [x] 2.2 `ProviderIcon.tsx`：VENDORS 增三家（官方页 1 家＋中转页 2 家）、VENDOR_FORMAT_LOCK 增 `gemini: openai`、`opencode-go-chat: openai`、`opencode-go-claude: anthropic`、VENDOR_LABELS 与 VENDOR_ICON 同批补键（两者为全量映射，缺键则编辑弹窗回显 undefined/兜底字形）、新厂商字形（线性 SVG，与现风格同族）；单测覆盖锁定矩阵（含既有 8 家回归）
- [x] 2.3 `vendorDefaults.ts` 登记三条：`gemini×openai`＝`https://generativelanguage.googleapis.com/v1beta/openai/`（模型留空＋候选）、`opencode-go-chat×openai`＝`https://opencode.ai/zen/go/v1`、`opencode-go-claude×anthropic`＝`https://opencode.ai/zen/go`；候选清单与后端 VENDOR_MODEL_CANDIDATES 对齐；登记纪律测试（无据留空、版本段规则）通过

## 3. 前端：供应商分组页签

- [x] 3.1 `ApiConfigForm.tsx` 创建态渲染两页签（复用 `.seg` 类，官方厂商｜中转 · 订阅制），默认官方页；中转页＝OpenAI 兼容＋两 Go 方块（带「新」角标）；不渲染待排期方块；编辑态 `vfix` 不受影响；组件测试覆盖「默认官方页／切页见方块集／切页不清已选与已填」三场景
- [x] 3.2 「OpenAI 兼容」引导文案收窄（移除 Gemini 句，保留手填 id＋反代指引）；Gemini 选中态思考行提示句（「部分型号（Pro 系）始终会思考，『关闭』只对 Flash 系生效」）按稿落地；文案测试断言更新（含「不再出现 generativelanguage 地址」负断言）

## 4. 后端：厂商识别与调用适配

- [ ] 4.1 `api_configs/vendor.py` KNOWN_VENDORS 增三条**主机＋路径差异化**模式，键与前端方块 id 逐字相等（schema 白名单即 KNOWN_VENDORS，须与 2.x 同批否则创建 400）：`generativelanguage.googleapis.com`→`gemini`、`opencode.ai/zen/go/v1`→`opencode-go-chat`、`opencode.ai/zen/go`→`opencode-go-claude`（**登记顺序 /v1 在前防遮蔽**）；落库/编辑重检测回显即正确厂商名（service 存检测值）；单测覆盖识别、顺序遮蔽、兜底与白名单校验
- [x] 4.2 `api_configs/connection.py` VENDOR_MODEL_CANDIDATES 增三家候选（与前端 2.3 同源对齐），探测降级链路测试通过
- [x] 4.3 会话头/UA 注入**两处同口径**：`ai_client.py`（SDK default_headers）与 `api_configs/connection.py` 探针（`_build_probe` headers——探针是自建 httpx 请求，规格要求与生成同头）；主机命中 opencode.ai（含子域）时附 `x-opencode-session`（`base_url`＋api_key 摘要，进程内稳定、重启更换，见 design §Decisions 4）与 UA `ai-novel/<版本>`；非命中不附头；单测覆盖生成/探针两路径的附头/不附头/同配置同值/重启换值
- [x] 4.4 Gemini 思考档位换算**两处同口径**：`ai_client.py` `_thinking_params` 出口与 `connection.py` 探针思考参数构造（`_build_probe` payload）各加 gemini 分支——max→high、low/high 原样、关思考按 Gemini 语义（reasoning_effort 关闭形态，不发 GLM `thinking:{disabled}`）；单测覆盖三档＋关闭＋探针/生成同参＋非 gemini 供应商不受影响

## 5. 真机/真网关验证（编码完成后、合入前）

> 状态：待外部 Key（AI Studio／OpenCode 订阅均需作家提供）。5.3 的 zen 清单探测可匿名先行，其余两项等 Key 到位后补验——合入前完成。

- [ ] 5.1 Gemini 官方块真连：AI Studio Key 走通探针→保存→生成→拆书 JSON 契约（判据＝产出合法 JSON，验证 json_object 是否被兼容层等效映射；不支持则登记 anthropic 式 prompt 兜底为既有口径并在结果卡注明）
- [ ] 5.2 OpenCode Go 真连（**外部依赖：作家订阅 Key，验证前先行取得；未到位时可先完成 5.1/6.x**）：Go · 通用（GLM/Kimi 任一）与 Go · Claude 系（Claude Haiku 任一）各走通探针→保存→生成；抓包/日志确认 `POST https://opencode.ai/zen/go/v1/messages` 拼接形态与会话头/UA 在位（design §Risks 第二条的验钉）
- [ ] 5.3 获取模型按钮在三家新供应商下可用（zen `/v1/models`、兼容层 `/v1beta/openai/models`），失败时降级文案不阻塞手填

## 6. 回归与门禁

- [ ] 6.1 前端：vitest 全量（apiConfigForm/apiConfigParts/apiKeyConfigPage 存量套件更新后全绿）、`npm run design:lint`＋`npm run design:check`（不触共享段，预期无新增红；design-cross 免跑，依据 proposal Design Impact 判定）
- [ ] 6.2 后端：pytest 全量（vendor 识别/思考换算/会话头/候选清单新测试在位，`test_api_format.py` 段锚钉不回退）、ruff 通过
- [ ] 6.3 e2e：模型配置相关流（添加配置 tab 流、Gemini 预填流）更新后通过；手工过一遍七状态设计稿对照实现截图，差异登记 ADJUSTMENTS- [x] ks — c-modelconfig-gemini-go

## 1. 原型先行（C端 用户可见改动，硬性流程第 1 步）

- [x] 1.1 将过审设计稿落为 `docs/design-c/prototypes/model-config.html` 的更新（供应商 tab 两页＋Gemini/Go 方块＋引导文案收窄＋思考提示；可从 `drafts/ai-novel-c端-模型配置-Gemini与OpenCodeGo-原型.html` 移植 graft 逻辑，宿主换成 model-config 屏现行基线），`npm run design:check` 矩阵中 model-config 相关对比通过
- [x] 1.2 在 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记偏差项：tab 两页、新方块与「新」角标、OpenAI 兼容引导文案收窄（Gemini 句移除）、Gemini 思考提示句、页签切换不清已选（原型未定义行为的补全，见 design §Decisions 2）；附注既有语义「编辑 base_url 触发厂商重检测，用户微调地址会掉回 OpenAI 兼容」（新方块与存量厂商同规矩）；并核对不含「待排期」方块与实现词汇

## 2. 前端：类型、登记表与锁定矩阵

- [x] 2.1 `types/api-config.ts` VendorId 枚举新增 `gemini`、`opencode-go-chat`、`opencode-go-claude`（三键与后端 KNOWN_VENDORS 逐字相等——落库走检测链、编辑回显按存储值，见 4.1 与 design §Decisions 8），`tsc --noEmit` 通过
- [x] 2.2 `ProviderIcon.tsx`：VENDORS 增三家（官方页 1 家＋中转页 2 家）、VENDOR_FORMAT_LOCK 增 `gemini: openai`、`opencode-go-chat: openai`、`opencode-go-claude: anthropic`、VENDOR_LABELS 与 VENDOR_ICON 同批补键（两者为全量映射，缺键则编辑弹窗回显 undefined/兜底字形）、新厂商字形（线性 SVG，与现风格同族）；单测覆盖锁定矩阵（含既有 8 家回归）
- [x] 2.3 `vendorDefaults.ts` 登记三条：`gemini×openai`＝`https://generativelanguage.googleapis.com/v1beta/openai/`（模型留空＋候选）、`opencode-go-chat×openai`＝`https://opencode.ai/zen/go/v1`、`opencode-go-claude×anthropic`＝`https://opencode.ai/zen/go`；候选清单与后端 VENDOR_MODEL_CANDIDATES 对齐；登记纪律测试（无据留空、版本段规则）通过

## 3. 前端：供应商分组页签

- [x] 3.1 `ApiConfigForm.tsx` 创建态渲染两页签（复用 `.seg` 类，官方厂商｜中转 · 订阅制），默认官方页；中转页＝OpenAI 兼容＋两 Go 方块（带「新」角标）；不渲染待排期方块；编辑态 `vfix` 不受影响；组件测试覆盖「默认官方页／切页见方块集／切页不清已选与已填」三场景
- [x] 3.2 「OpenAI 兼容」引导文案收窄（移除 Gemini 句，保留手填 id＋反代指引）；Gemini 选中态思考行提示句（「部分型号（Pro 系）始终会思考，『关闭』只对 Flash 系生效」）按稿落地；文案测试断言更新（含「不再出现 generativelanguage 地址」负断言）

## 4. 后端：厂商识别与调用适配

- [ ] 4.1 `api_configs/vendor.py` KNOWN_VENDORS 增三条**主机＋路径差异化**模式，键与前端方块 id 逐字相等（schema 白名单即 KNOWN_VENDORS，须与 2.x 同批否则创建 400）：`generativelanguage.googleapis.com`→`gemini`、`opencode.ai/zen/go/v1`→`opencode-go-chat`、`opencode.ai/zen/go`→`opencode-go-claude`（**登记顺序 /v1 在前防遮蔽**）；落库/编辑重检测回显即正确厂商名（service 存检测值）；单测覆盖识别、顺序遮蔽、兜底与白名单校验
- [ ] 4.2 `api_configs/connection.py` VENDOR_MODEL_CANDIDATES 增三家候选（与前端 2.3 同源对齐），探测降级链路测试通过
- [ ] 4.3 会话头/UA 注入**两处同口径**：`ai_client.py`（SDK default_headers）与 `api_configs/connection.py` 探针（`_build_probe` headers——探针是自建 httpx 请求，规格要求与生成同头）；主机命中 opencode.ai（含子域）时附 `x-opencode-session`（`base_url`＋api_key 摘要，进程内稳定、重启更换，见 design §Decisions 4）与 UA `ai-novel/<版本>`；非命中不附头；单测覆盖生成/探针两路径的附头/不附头/同配置同值/重启换值
- [ ] 4.4 Gemini 思考档位换算**两处同口径**：`ai_client.py` `_thinking_params` 出口与 `connection.py` 探针思考参数构造（`_build_probe` payload）各加 gemini 分支——max→high、low/high 原样、关思考按 Gemini 语义（reasoning_effort 关闭形态，不发 GLM `thinking:{disabled}`）；单测覆盖三档＋关闭＋探针/生成同参＋非 gemini 供应商不受影响

## 5. 真机/真网关验证（编码完成后、合入前）

> 状态：待外部 Key（AI Studio／OpenCode 订阅均需作家提供）。5.3 的 zen 清单探测可匿名先行，其余两项等 Key 到位后补验——合入前完成。

- [ ] 5.1 Gemini 官方块真连：AI Studio Key 走通探针→保存→生成→拆书 JSON 契约（判据＝产出合法 JSON，验证 json_object 是否被兼容层等效映射；不支持则登记 anthropic 式 prompt 兜底为既有口径并在结果卡注明）
- [ ] 5.2 OpenCode Go 真连（**外部依赖：作家订阅 Key，验证前先行取得；未到位时可先完成 5.1/6.x**）：Go · 通用（GLM/Kimi 任一）与 Go · Claude 系（Claude Haiku 任一）各走通探针→保存→生成；抓包/日志确认 `POST https://opencode.ai/zen/go/v1/messages` 拼接形态与会话头/UA 在位（design §Risks 第二条的验钉）
- [ ] 5.3 获取模型按钮在三家新供应商下可用（zen `/v1/models`、兼容层 `/v1beta/openai/models`），失败时降级文案不阻塞手填

## 6. 回归与门禁

- [ ] 6.1 前端：vitest 全量（apiConfigForm/apiConfigParts/apiKeyConfigPage 存量套件更新后全绿）、`npm run design:lint`＋`npm run design:check`（不触共享段，预期无新增红；design-cross 免跑，依据 proposal Design Impact 判定）
- [ ] 6.2 后端：pytest 全量（vendor 识别/思考换算/会话头/候选清单新测试在位，`test_api_format.py` 段锚钉不回退）、ruff 通过
- [ ] 6.3 e2e：模型配置相关流（添加配置 tab 流、Gemini 预填流）更新后通过；手工过一遍七状态设计稿对照实现截图，差异登记 ADJUSTMENTS
