# c-thinking-config — 思考开关与强度可配，GLM-5.3 强制思考模型全链可用

## Why

内测配 GLM（glm-5.3-flashx，OpenAI 格式）实锤：连接测试探针 400——「该模型始终思考，
不支持关闭思考；请使用 low、high 或 max」。根因两层：

1. **契约变化**：GLM-5.3 系列强制思考，`thinking:{type:disabled}` 直接被打回；思考强度
   改走**顶层参数 `reasoning_effort`**（low/high/max，官方迁移指引明确「disabled 要改成
   enabled 并设 effort」）。而整条链（探针＋生成）硬编码禁思考，没有出路。
2. **重试判据漏判**：探针与 `ai_client` 的「端点拒参时去参重试」判据是错误文本里含英文
   `thinking`——GLM 的拒法是**纯中文**，判据不命中，重试不触发，400 直透用户。

即便重试判据修好，「关思考」对强制思考模型也只是「不打自招的降级」。思考开关与强度
（low→max）本是模型能力，应当作配置交给用户，而不是焊死在代码里。

## What Changes

- **配置面**：`api_configs` 新增 `thinking_enabled`（默认关）＋`thinking_effort`
  （low/high/max，默认 low）两列（带 DDL 默认，迁入链按列交集自动带回）；创建/编辑
  契约、响应、备份导出/导入同批携带。「添加/编辑 API Key」弹窗新增两控件：思考模式
  （开启/关闭）＋思考强度（低 low/高 high/深 max，关闭时灰置、值保留）。
- **下发面**：生成调用与连接探针按配置下发——关＝`thinking:{type:disabled}`（现状语义，
  存量配置零变化）；开＝`thinking:{type:enabled}`＋顶层 `reasoning_effort`（openai 格式
  走 extra_body；anthropic 格式 thinking 走形参、effort 随 extra_body 透传）。
- **重试加固**：端点打回思考参数时去参（`thinking`＋`reasoning_effort`）重试一次并记住
  该 base——判据扩为含中文「思考」/`reasoning`/`effort`；连接探针更进一步：带思考参数的
  400 **不看文案一律去参重试**（探针是一次性用户动作，多一次请求换判稳），两次都 400 时
  回更贴切的那份响应。去参重试时探针输出预算放大（32→1024）：强制思考模型去参后会把
  预算花在推理上，32 只够思考、正文为空，探针会误判「回复为空」。
- **判定类让位**：JSON 判定/短答复类调用（`_judge_chat` 单漏斗）恒以显式关思考传参压过
  配置——volume-plan-ai spec 钉住的「判定类走关闭思考路径」口径不变；显式传 thinking 时
  配置强度不搭车（关思考还带 effort 自相矛盾）。
- 明确不做：原生 Anthropic 的 `budget_tokens` 映射（开思考缺 budget 被原生端点拒时走
  去参降级）；思考配置按业务动作分档（判定类恒关除外）；朱雀检测配置不受影响（独立面板）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`: 新增「思考参数可配」要求（两字段契约、下发语义、判定类让位、
  去参重试不看文案、探针预算放大、表单两控件、备份/迁入带回）；「按接口格式探测连接」
  的探针思考措辞同步（禁思考→按配置下发＋去参重试口径）。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：模型配置页「添加 API Key」/「编辑配置」弹层（原型
  `docs/design-c/prototypes/model-config.html`，两控件随本 change 登记 ADJUSTMENTS）。
- **共享段**：不触碰（复用 `.seg`/`.label-row`/`.cf-hint` 既有类，零新 CSS）。
- **风险**：`_THINKING_UNSUPPORTED_BASES` 是 base 级进程记忆——同 base 下「一个配置关
  思考触发记忆、另一个配置开思考」时后者强度不生效（发不出参数）。范围极窄，接受并在
  design.md 记录。

## Impact

- 后端：`models/api_config.py`、`api_configs/{schemas,service,router,connection}.py`、
  `ai_client.py`、`settings/ai_router.py`、`backup/{export,importer}.py`。
- 前端：`types/api-config.ts`、`components/api-config/ApiConfigForm.tsx`、
  `hooks/useApiConfigs.ts`、`pages/ApiKeyConfigPage.tsx`。
- 测试：探针 GLM 中文拒法回归钉、思考开启下发钉、去参重试＋记忆钉、CRUD roundtrip 钉、
  表单控件钉。
