## Why

DeepSeek 思考模式文档：思考模式默认开启，**effort 默认 high**（映射 minimal/low→low、medium/high→high、max/ultra→max）。助手底栏的「深度思考」开关显式传 `thinking:{type:enabled}`，但 `AIClient._explicit_thinking_params` 不带 effort——实际按供应商默认 high 跑，模型配置里的 `thinking_effort=low`（省 token 省延迟的默认）被静默忽略。助手的每次工具步都烧一遍高思考，延迟/成本与配置预期不符。

## What Changes

- `AIClient._explicit_thinking_params`：显式 enabled 且**未自带 effort** 时，按该配置的 `thinking_effort` 补齐——GLM 嵌套进 `thinking{}`（顶层会被静默吞掉），其余 vendor 随顶层 `reasoning_effort`（与配置开思考同款形态）；显式自带 effort 以显式为准，不覆盖。
- 显式 disabled（判定类恒关思考）SHALL NOT 搭车配置强度——既有行为不变；Gemini/opencode-go-claude 的既有映射不变。
- 端点已知不支持思考参数（进程内记忆）时，显式 enabled 也直接不发参数（不再多打一次被拒请求）。
- 测试：显式 enabled 带配置 low/GLM 嵌套/显式 effort 优先/disabled 不带 effort/不支持 base 不发。
- 不做：不改前端三档选择器（底栏仍是开/关；强度沿用模型配置）；不改判定类路径。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`: 「思考参数可配」的显式传参口径细化——显式 disabled 不搭车强度；显式 enabled 未带 effort 时按配置强度下发，显式 effort 优先。

## Design Impact

- **受影响端**：仅 C端后端（ai_client）；无前端/UI、无 S端、无共享设计段、无原型。
- **对象状态**：无新增用户可见状态；模型配置的「思考强度」对助手思考开关真正生效。
- **设计工件**：无（协议参数对齐）。

## Impact

- `client/backend/ai_client.py`（`_explicit_thinking_params` 及 enabled 参数构造）
- `client/backend/tests/test_ai_client_layering.py` / `test_ai_client_native_tools.py`
- 无数据/API/schema 迁移；判定类与默认关思考路径零变化。
