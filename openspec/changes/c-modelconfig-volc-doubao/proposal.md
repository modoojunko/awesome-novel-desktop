# C端 模型配置接入火山方舟（豆包 Seed 系）

## Why

作家要求文本模型支持火山方舟的豆包 Seed 系（指定 `doubao-seed-2-1-lite`，2026-10-24 控制台模型页）。调研与实测已定案（方舟模型目录元数据＋本机真 Key 探针，2026-10-24）：该模型在方舟官方声明支持 **Chat Completions `/api/v3/chat/completions`**（另有 Responses/Batch），app 现有 openai 协议路径可直接承接——开思考（`thinking enabled＋reasoning_effort low/max`）、关思考（`thinking disabled`）三种实发形态真弹全部 200，`reasoning_content` 独立思考字段与既有 DeepSeek/Qwen/Kimi 形态同款，流式转换零改动。模型规格：1M 上下文 / 256K 最大输出（思考 256K）、支持结构化输出与函数调用、输入 0.8 元/M・输出 2.7 元/M tokens（另，账号当前挂 50 万 token 免费推理包）——对拆书长上下文（`DECONSTRUCT_CAPS` 本就支持 1M 单遍归并）与日常写作都是高性价比选项。只需登记与预设，无需新 SDK、无需新协议客户端。

## What Changes

- 供应商选择区**官方厂商**页新增「豆包」方块（sub「火山方舟」，带「新」静态角标）；接口格式锁定 OpenAI 格式（方舟无 Anthropic 兼容口）。
- 供应商默认值登记表新增登记（登记纪律不变，均有官方目录元数据或真弹实测依据）：`doubao×openai`——Base URL `https://ark.cn-beijing.volces.com/api/v3`，默认模型 `doubao-seed-2-1-lite-260915`（**完整版本 id**：数据面裸名 `doubao-seed-2-1-lite` 实测 404「模型或推理接入点不存在」，版本化 id 实测 200），备选候选按方舟官方模型广场版本 id 登记 Doubao 文本家族。
- 后端厂商识别（`VENDOR_PATTERNS`）新增方舟主机模式：`ark.cn-beijing.volces.com` 精确登记，`ark.<region>.volces.com` 形态同族识别（其余 region 未登记预填值，仅落库识别归 `doubao`）。
- 后端探测候选清单（`VENDOR_MODEL_CANDIDATES`）新增 `doubao` 条目，与前端登记同源对齐。
- **思考参数零适配**：app 默认 openai 路径形态在方舟原样可用（2026-10-24 真 Key 探针：enabled＋low ✅ / disabled ✅ / enabled＋max ✅ 各 200）；已知契约边界——`thinking disabled` 与 `reasoning_effort` **同传会被拒**（400 Invalid combination），app 现有形态不会发出该组合（关思考路径只发 disabled），作为设计约束记录并在单测钉住。
- 「OpenAI 兼容」引导文案不动：方舟上托管的第三方模型（DeepSeek/Qwen 等）本就可经「OpenAI 兼容」手填方舟地址接入，不设专属按钮（识别链会自动归 `doubao` 厂商名展示，行为不变）。

## Capabilities

### New Capabilities

（无——全部落点在既有 capability）

### Modified Capabilities

- `model-api-config`: ①「供应商分组页签」官方厂商页承载集合扩展（新增豆包方块）；②「接口格式为配置的一级字段」厂商锁定矩阵扩展（豆包锁定 OpenAI 格式）；③「供应商默认值预填」登记表新增豆包登记（Base URL＋默认模型＋候选清单）。

## Impact

- 前端：`client/frontend/src/types/api-config.ts`（VendorId 枚举加 `doubao`）、`components/api-config/ProviderIcon.tsx`（VENDORS 方块＋VENDOR_FORMAT_LOCK＋VENDOR_LABELS）、`components/api-config/vendorDefaults.ts`（登记表）、`components/icons.tsx`（VENDOR_ICON 加 `doubao` 线性字形，与现风格同族）。
- 后端：`client/backend/api_configs/vendor.py`（VENDOR_PATTERNS 方舟主机模式）、`client/backend/api_configs/connection.py`（VENDOR_MODEL_CANDIDATES 候选）。
- `ai_client.py` 零改动（无 vendor 级思考/请求头适配——与 c-modelconfig-gemini-go 的关键差异，探针实测定案）。
- 不新增依赖；不触碰两端共享段（方块复用既有 `.vbtn`/`.seg` 组件类，无新令牌/新组件词汇/新状态语言）。
- 与图像域解耦：图像生成的 `volcengine` 供应商（`image_assets/`，含在途 c-image-volc-size-contract）配置域独立，Key 各自管理，本 change 不动。
- 风险记录：方舟模型须在控制台开通后方可调用（当前账号已开通且带免费包）；未开通账号会在连接测试得到 404 类报错，走既有「探针真实死因透传」口径呈现，无需新增文案。

## Design Impact

- 受影响端：仅 C端。
- 受影响屏/弹层：模型配置页（`/config`）「添加 API Key」弹窗——官方厂商页供应商方块集（新增一张）；Base URL/Key/模型行、思考行、配置卡片、用量统计、朱雀页签均不受影响。
- 对象状态：无新增对象状态。方块复用既有官方方块词汇（on 态、「新」静态角标＝沿用 Gemini/OpenCode Go 同款非状态语言徽标）。
- 共享段：不触碰 → 不触发 `design-cross.mjs`，无双端同改任务。
- 原型先行：需要（硬性流程）。`docs/design-c/prototypes/model-config.html` 官方页方块集补「豆包」方块＋ADJUSTMENTS.md 登记偏差项（新方块与「新」角标、锁格式），无其他界面变化。
- 设计工件：实现侧自查产出（无新交互形态，纯方块集扩展，复用既有组件词汇；不占用设计侧会话）。
