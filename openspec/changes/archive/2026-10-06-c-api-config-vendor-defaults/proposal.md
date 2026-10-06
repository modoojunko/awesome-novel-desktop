# c-api-config-vendor-defaults — 选已知供应商预填 Base URL 与模型名称，用户只填 Key

## Why

创建模型配置对新手是道坎：要自己去厂商文档找 API 地址、弄清模型 id——内测（2026-10-05）用户就把 DeepSeek 控制台网页（`platform.deepseek.com/api_keys`）当 Base URL 填了进来。用户拍板（2026-10-05）：**用户选了已知供应商（如 DeepSeek），就默认把模型名称、Base URL 填好，用户只需要填 Key**。

此拍板**反转** 2026-09-06「URL 不预填」旧拍板：当年不预填是防猜错地址，如今改为「登记表内有据才填、填了可改」，比让用户裸填更不容易错。

## What Changes

- **供应商默认值登记表**（单一数据源）：键＝供应商×接口格式，值＝官方 Base URL＋默认模型名称＋备选模型候选。首批全量入册 DeepSeek（URL 与模型均有实测在案）；OpenAI/Anthropic/GLM/Kimi/Qwen 的 URL 与默认模型**按官方文档核对后登记、禁编造**（无据字段留空，沿用候选册「没有把握就留空」纪律）。
- **创建表单预填**：选登记表内供应商 → Base URL 与模型名称自动填好；用户只填 API Key 即可保存。表单新增「模型名称」输入框（落 `config.models` 首项；create 负载与落库补 `models` 支持）。预填字段可编辑，不是只读。
- **覆盖规则**：字段为空、或仍等于当前预填值（用户未手改）时，切供应商/切格式 SHALL 填入新登记值；**用户手改过的字段不被覆盖**。编辑态不做预填（供应商本就锁定、值是已存值）。
- **「OpenAI 兼容」等无登记值的供应商**：不预填（沿用 placeholder 示例域名引导），用户自填。
- **与保存门禁协同**（`c-api-config-save-gate`）：预填模型名进 `models` 后，保存门禁探针的模型 id 取用顺序中「配置已选模型」恒有值，消除「探针 id 是猜的」一类误拦。
- 明确不做：URL 自动「纠正/改写」用户输入（只在选供应商时刻填默认值）；朱雀 AI 检测面板（独立端点、无用户可填 URL）；已存配置的批量回填改写。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`: 「Base URL 不自动预填」需求**废除**（Reason：2026-10-05 拍板反转），新增「供应商默认值预填」需求承接（登记表、预填、覆盖规则、只填 Key）。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：模型配置页「添加 API Key」弹层（原型 `docs/design-c/prototypes/model-config.html`）——新增「模型名称」字段＋预填形态；「编辑配置」弹层不改。
- **对象状态**：仅输入框预填值（表单数据态），不新增提示语气/胶囊/条带形态；placeholder 沿用既有 FORMAT_PLACEHOLDER 族。
- **共享段**：不触碰（不改 base.css 令牌与基础组件类）。
- **原型先行**：需要——`model-config.html` 补「模型名称字段＋选 DeepSeek 预填只填 Key」形态（含 OpenAI 兼容不预填对照），偏差登记 `ADJUSTMENTS.md`。
- **设计工件产出**：实现侧自查（含 design:lint/design:check 门禁）。

## Impact

- `client/frontend/src/components/api-config/ProviderIcon.tsx`（或新 `vendorDefaults.ts`）：供应商默认值登记表。
- `client/frontend/src/components/api-config/ApiConfigForm.tsx`、`src/pages/ApiKeyConfigPage.tsx`：预填逻辑＋模型名称字段＋create 负载带 `models`。
- `client/backend/api_configs/schemas.py`、`service.py`：`CreateApiConfigBody` 与 `create_api_config` 支持 `models` 落库。
- 测试：vitest `apiConfigForm`（预填/覆盖/手改保护）、pytest（create 带 models 落库、探针用预填模型）、config-page e2e（选 DeepSeek 只填 Key 走通）。
- 原型：`docs/design-c/prototypes/model-config.html`＋`ADJUSTMENTS.md` 登记。
- 依赖：与 `c-api-config-save-gate` 同批实施最佳（探针 id 序列协同），互不阻塞。
