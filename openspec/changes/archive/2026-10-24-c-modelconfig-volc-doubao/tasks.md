# Tasks — c-modelconfig-volc-doubao

## 1. 原型先行（C端 用户可见改动，硬性流程第 1 步）

- [x] 1.1 `docs/design-c/prototypes/model-config.html` 官方厂商页方块集补「豆包」方块（label「豆包」＋sub「火山方舟」＋「新」角标，字形线性 SVG 与现风格同族），`npm run design:check` 矩阵中 model-config 相关对比通过
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记偏差项：官方页新增豆包方块（厂商预设扩展）、「新」静态角标沿用 Gemini/OpenCode Go 同款非状态语言徽标、豆包锁定 OpenAI 格式（火山方舟无 Anthropic 口）；核对不含实现词汇

## 2. 前端：类型、登记表与锁定矩阵

- [x] 2.1 `types/api-config.ts` VendorId 枚举新增 `doubao`（与后端 VENDOR_PATTERNS 键逐字相等——落库走检测链、编辑回显按存储值），`tsc --noEmit` 通过
- [x] 2.2 `ProviderIcon.tsx`：VENDORS 官方页增豆包（`{ id: "doubao", label: "豆包", tab: "official", sub: "火山方舟", badge: "新" }`）、VENDOR_FORMAT_LOCK 增 `doubao: "openai"`、VENDOR_LABELS 补键（全量映射，缺键编辑回显兜底）；`icons.tsx` VENDOR_ICON 增 `doubao` 线性字形；单测覆盖锁定矩阵（含既有 10 家回归）
- [x] 2.3 `vendorDefaults.ts` 登记 `doubao×openai`＝`https://ark.cn-beijing.volces.com/api/v3`＋默认模型 `doubao-seed-2-1-lite-260915`；候选清单与后端 VENDOR_MODEL_CANDIDATES 对齐；登记纪律测试（版本段规则）通过

## 3. 后端：厂商识别与候选清单

- [x] 3.1 `api_configs/vendor.py` VENDOR_PATTERNS 增两条、键均 `doubao`（display_name「豆包（火山方舟）」）：`^https://ark\.cn-beijing\.volces\.com`（登记 region）在前、`^https://ark\.[a-z0-9-]+\.volces\.com`（其余 region 兜底识别）在后；落库/编辑重检测回显即「豆包（火山方舟）」；单测覆盖 cn-beijing 命中、异 region 兜底、非方舟 volces 域不误收、白名单校验
- [x] 3.2 `api_configs/connection.py` VENDOR_MODEL_CANDIDATES 增 `doubao`＝`["doubao-seed-2-1-lite-260915", "doubao-seed-2-1-pro-260915", "doubao-seed-2-1-turbo-260628"]`（与前端 2.3 同源对齐）；探测降级链路测试通过
- [x] 3.3 `ai_client.py` 确认零改动：思考三形态（enabled+low / disabled / enabled+max）按既有 openai 路径直通；单测钉「关思考形态 SHALL NOT 带 `reasoning_effort`」（方舟禁组合 `disabled+档位` 400 实证，防未来回归把档位漏进关思考形态）

## 4. e2e／组件测试

- [x] 4.1 组件测试：官方页方块集含豆包（默认官方页即可见）、选中后 Base URL/模型预填为登记值、接口格式锁定 OpenAI；编辑态回显「豆包（火山方舟）」
- [x] 4.2 e2e：添加配置→选豆包→填 Key→测试连接→保存流（mock 方舟端点），模型选择器候选/手填退路断言

## 5. 真机/真网关验证（编码完成后、合入前；真 Key 已在账号，ark-****afbd active＋50 万 token 免费包）

> 状态（2026-10-24 数据面真弹实测后更新，arkcli api arkruntime.create_chat_completion）：
> - **5.1 ✅**：`response_format json_object` 实弹 200 且产出合法 JSON（`{"ok": true}`）——方舟原生支持，无兜底需求。
> - **5.2 部分✅**：思考三态非流式真弹全 200（enabled+low／enabled+max／disabled 各一发，关思考零思考 token、
>   finish=stop；开思考 `reasoning_content` 独立字段在 message 上，reasoning_tokens 单独计数）。
>   **流式 delta 形态未直接实测**（CLI 流式 action 未支持；非流实锤＋官方同字段契约＋DeepSeek 同款管道单测在位），
>   思考面板真机呈现随作家真机抽检。
> - **5.3 部分✅**：pro（`doubao-seed-2-1-pro-260915`）／turbo（`doubao-seed-2-1-turbo-260628`）候选 id 各实弹 200，
>   广场拼法推定获证，登记不修正；**`GET /api/v3/models` 未验证**（CLI 无对应 action），清单拉取失败走既有
>   「手填＋候选」兜底（spec 既有口径），作家真机按下「获取模型」即可补验。

- [x] 5.1 豆包方块真连：方舟 Key 走通探针→保存→生成（流式）→拆书 JSON 契约（判据＝产出合法 JSON；response_format json_object 是否被方舟等效映射以实弹为准，不支持则按既有 json_mode 兜底口径在结果卡注明）
- [x] 5.2 思考三态真机：开思考 low/max、关思考各生成一次，思考面板呈现 `reasoning_content` 流（DeepSeek 同款管道），关思考零思考 token
- [x] 5.3 获取模型：`GET /api/v3/models` 实拉核可用性；不可用则核对手填＋候选兜底文案；顺带抽验 pro/turbo 版本 id 可调性（404 则按实拉清单修正 2.3/3.2 登记）
- [ ] 5.4 拆书长上下文抽验（可选）：lite 1M 上下文挂一部长书跑单遍归并档（DECONSTRUCT_CAPS 1M），记录 token 账

## 6. 回归与门禁

> 结论（2026-10-24，worktree ai-novel-wt-volc-doubao）：
> - 后端 pytest 全量 **2466 passed / 0 failed**（296 skipped；基线 2460＋本 change 6 例）；ruff 全仓 All checks passed。
> - 前端 vitest 全量 **1785 passed**（含 config 套件 90 项＋豆包 3 例）；tsc --noEmit 绿；design:lint 绿。
> - design:check 本机存量红（books 七态＋preview——裸基线 A/B 同挂，c-modelconfig-gemini-go 同款判例；
>   本 change 触碰面与红屏零重叠，model-config 不在像素矩阵，以 CI 受控环境为准）。
> - e2e config-page spec **6/6 绿**（隔离栈 volc-e2e：5175/8001/19001＋worktree 数据目录，与 demo 栈零共享）；
>   **顺手修好该 spec 两处存量腐化**（gemini-go 起未跟稿：④缺页签导航点不到「OpenAI 兼容」＋文案收窄后断言旧句——
>   `未列厂商` 字串只活在 e2e 里，已对齐现文案＋补页签导航）。

- [x] 6.1 前端：vitest 全量（config 套件更新后全绿）、`npm run design:lint`＋`npm run design:check`（不触共享段，预期无新增红；design-cross 免跑，依据 proposal Design Impact 判定）
- [x] 6.2 后端：pytest 全量（vendor 识别/候选清单/思考形态钉新测试在位，`test_api_format.py` 段锚钉不回退）、ruff 通过
- [x] 6.3 e2e：模型配置相关流更新后通过；手工对照七状态设计稿与实现截图，差异登记 ADJUSTMENTS
