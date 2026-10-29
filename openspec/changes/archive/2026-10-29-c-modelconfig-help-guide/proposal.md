# c-modelconfig-help-guide

## Why

作家配置 API Key 时的高频卡点（2026-10-28/29 Gemini 与 OpenCode Go 实测中再次确认）：不知道去哪领 Key、不知道选哪个方块、Base URL 不知道抄到哪一截、测试连接报错不会归因。表单里只有零散的字段级提示（cf-hint），缺一份「从零到用上」的完整步骤说明。boss 2026-10-29 拍板：做一份按 **OpenAI / Anthropic / Google 三类接口格式**组织的配置步骤帮助，原型（`docs/design-c/drafts/ai-novel-c端-模型配置-配置步骤指南-原型.html`）已过审并二次拍板弹窗固定尺寸。

## What Changes

- 新增「配置指南」弹窗（复用应用 Modal 体系，**固定尺寸 880×760**，内容区超高内部滚动）：
  - 三页签＝**OpenAI 格式｜Anthropic 格式｜Google 系**，与表单「接口格式」切换器同名同序；
  - 每页签同构内容：适用范围（覆盖的供应商方块 chips）＋四步步骤（领 API Key〔含各家领 Key 地址速查表〕→ 选方块贴 Key → 选模型/手填 id → 测试连接）＋折叠「常见问题」（401/404/地址抄写/清单拉不到/思考模式报错/超时，按「现象→用户动作」写）；
  - 全文作家语汇，无实现词汇（协议/SDK/端点/探针等）。
- 两处入口：
  1. 模型配置列表页页头「添加 API Key」左侧新增「配置指南」副按钮；
  2. 添加配置弹窗供应商方块区下方一行引导「不知道怎么填？看三步配置指南……」，点击打开指南并按当前已选供应商自动定位页签（Anthropic／OpenCode Go·Claude 系→Anthropic 格式；Gemini→Google 系；其余→OpenAI 格式）。
- 纯前端改动：无后端、无路由变更；指南文案落为组件内常量表（地址表数据化，便于复核增补）。
- 原型与设计说明随 PR 入库（`docs/design-c/drafts/` 四件）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`: 新增「配置步骤指南」requirement——指南弹窗的页签结构、内容骨架、固定尺寸、两处入口与定位规则。

## PR 分拆

单 PR：实现＋本 change 四件套＋sync/归档（项目规约：归档随实现 PR 走）。
