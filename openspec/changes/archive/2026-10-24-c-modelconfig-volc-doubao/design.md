# Design — c-modelconfig-volc-doubao

## Context

文本模型配置的供应商体系由三张登记表＋一条识别链构成（c-modelconfig-gemini-go 已把这套机制跑通）：

- 前端 `types/api-config.ts` VendorId 枚举（schema 白名单的前端半边）；
- `vendorDefaults.ts` VENDOR_DEFAULTS（创建预填）＋`ProviderIcon.tsx` VENDORS/VENDOR_FORMAT_LOCK/VENDOR_LABELS＋`icons.tsx` VENDOR_ICON（全量映射，缺键回显兜底字形）；
- 后端 `api_configs/vendor.py` VENDOR_PATTERNS（主机＋路径正则，**顺序敏感**，键＝落库 vendor 值与编辑回显）＋`api_configs/connection.py` VENDOR_MODEL_CANDIDATES（探测候选兜底）。

方舟（火山方舟 Ark）的文本调用面：OpenAI 兼容 Chat Completions `https://ark.cn-beijing.volces.com/api/v3/chat/completions`，模型以完整版本 id 调用。本 change 的实证基础（2026-10-24，arkcli 模型目录元数据＋真 Key 数据面探针）：

| 事实 | 证据 |
|---|---|
| Chat Completions 官方声明支持；thinking/结构化输出/函数调用均支持 | 模型目录 `models get doubao-seed-2-1-lite`（api_support.chat_completions.support=true） |
| **裸名不可调**：`doubao-seed-2-1-lite` → 404「模型或推理接入点不存在」 | 数据面探针实测；版本 id `doubao-seed-2-1-lite-260915` 200 |
| 开思考＋low：`{"thinking":{"type":"enabled"},"reasoning_effort":"low"}` → 200，`reasoning_content` 独立字段（与 DeepSeek/Qwen/Kimi 同款），reasoning_tokens 单独计数 | 数据面探针实测 |
| 关思考：`{"thinking":{"type":"disabled"}}` → 200，finish=stop 零思考 token | 同上 |
| 开思考＋max：`reasoning_effort:"max"` → 200（方舟认 max 档，无需换算） | 同上 |
| **禁组合**：`disabled` 与 `reasoning_effort` 同传 → 400「Invalid combination of reasoning_effort and thinking type」 | 同上 |
| 规格：1M 上下文 / 256K 最大输出（思考 256K）；输入 0.8・输出 2.7 元/M tokens；限流 3 万 RPM | 模型目录 limits/pricing/rate_limit |

app 现有 openai 路径思考形态（`ai_client.py` `_thinking_params`）：开＝`{thinking:{enabled}, reasoning_effort:<档位>}`、关＝`{thinking:{disabled}}`（**关思考路径从不带档位**）——与方舟契约天然对齐，禁组合形态 app 不会发出。

## Goals / Non-Goals

**Goals:**

- 官方页新增豆包方块＋登记表三件套（VendorId/VENDORS/VENDOR_DEFAULTS/VENDOR_FORMAT_LOCK/VENDOR_ICON/VENDOR_LABELS/VENDOR_PATTERNS/VENDOR_MODEL_CANDIDATES）一次落齐，键逐字相等。
- 预填、连接测试、生成、思考、模型清单/候选兜底全部走既有 openai 路径既有机制，零调用层适配。

**Non-Goals:**

- 不引入火山引擎 Python SDK（第三条协议管线会绕开 StreamEvent/思考剥离/探针/账目/TokenLog 全套既有机器，且图像侧 `volcengine` 适配器已是裸 HTTP 先例）。
- 不接方舟 Responses API（app 无该协议客户端；Chat Completions 已覆盖全部需求）。
- 不为方舟托管的三方模型（DeepSeek/Qwen on Ark）设专属按钮——经「OpenAI 兼容」手填方舟地址即可，识别链归 `doubao` 仅影响展示名。
- 不与图像生成配置域共享 Key 或配置结构（`image_assets/` 的 volcengine 供应商独立，含在途 c-image-volc-size-contract）。
- 不做其他 region（如海外 cn 外节点）的预填登记——仅识别兼容。

## Decisions

1. **vendor id＝`doubao`，按钮 label「豆包」＋sub「火山方舟」**。与 kimi/qwen/glm 的「模型家族名」命名同构；sub 行承载平台名（`.vsub` 已有渲染面，OpenCode Go 同款）。备选「火山方舟」作主 label 被否：官方页现有 9 家全是模型/产品品牌短名，四字平台名与其余方块视觉重量不齐。后端 display_name「豆包（火山方舟）」。
2. **版本段直觉沿用既有登记纪律**：方舟地址自带 `/api/v3` 版本段，与「登记值须显式含版本段」规则一致（SDK 直拼 `{base}/chat/completions`，不依赖归一）。`normalize_openai_base` 对已含版本段的地址不重复补段（「中段版本段不重复补版本段」既有口径兼容）。
3. **模型 id 一律完整版本 id**（裸名数据面 404 实测）。默认模型 `doubao-seed-2-1-lite-260915`（唯一真弹 200 实证过的 id）；候选按官方广场元数据登记 Seed 2.1 家族：`doubao-seed-2-1-lite-260915`、`doubao-seed-2-1-pro-260915`、`doubao-seed-2-1-turbo-260628`（三方元数据 `name+primary_version` 拼法与 lite 实证拼法一致，实现期真机抽验兜底）。旧 Seed 2.0 系不进候选（有更优 default，清单纪律「有据才登记」不挡但按克制原则不堆旧代）。
4. **VENDOR_PATTERNS 识别模式**：`^https://ark\.cn-beijing\.volces\.com`（精确登记 region）在前，`^https://ark\.[a-z0-9-]+\.volces\.com`（其余 region 兜底识别）在后——两条都归 `doubao`；无同主机多键问题，无 gemini-go 的 `/v1` 遮蔽坑。用户自建反代指向方舟的不在识别范围（归 openai-compat，行为不受影响）。
5. **思考零适配**：三形态真弹 200 实证（见 Context 表）。仍保留既有兜底网作为安全垫——`_is_thinking_rejection` 拒绝自动去参重试＋按 base 记忆，方舟未来改契约时降级可用而非报错。`disabled+档位` 禁组合作为单测钉（防未来代码路径把档位漏进关思考形态）。
6. **思考强度档位直通**：方舟认 low/max（实测），medium/low/high/max 直通不换算——与 gemini（max→high 换算）、zen claude（adaptive 裸形态）不同，本厂商是第一个「零换算」的思考厂商。
7. **模型清单拉取**：`GET /api/v3/models` 是否可用未验证（实现期真机核实）。不可用时走既有降级链：models 404 → 降级生成探针判连通；模型选择器退手填＋候选清单（`NO_MODEL_LIST_NOTE_OPENAI` 口径）。两条路都有既有机制，无需新增。
8. **不新增 spec Requirement**：无新交互语义（预填/锁定/分组页签全是既有 requirement 的数据行扩展）；探针实证作为 design 记录与单测钉，不进 spec。

## Risks / Trade-offs

- **候选 id 拼法风险**：pro/turbo 的版本 id 依广场元数据拼法推定（lite 已实证该拼法）。缓解：任务 5 真机抽验，404 则按实拉清单修正登记（登记纪律允许实测修正）。
- **/models 未知**：若方舟不提供清单接口，模型选择器退手填＋候选——功能可用性不受损，仅 UX 略降（与 deepseek/gemini 清单失败同一出口）。
- **未开通账号体验**：模型未在控制台开通时探针得 404 类死因，按既有「真实死因透传」呈现；不新增引导文案（报错已含方舟原文，用户可循控制台开通）。
- **折价面**：lite 是全模态模型（图文音视输入），app 仅用文本输入——能力冗余但无害，价格不因文本-only 变化。
