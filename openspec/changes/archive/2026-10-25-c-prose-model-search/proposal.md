# Proposal: c-prose-model-search

## Why

用户口径（2026-10-25）：「正文生成弹窗页面选择模型的组件要能支持快速搜索」。动因＝c-model-list-cap-300 把模型清单上限抬到 300 后（方舟单家实测 137 条），「AI 生成正文」弹窗的生成模型弹层在多配置场景下滚动物色一个模型已不可接受——需要一个输入即过滤的快速搜索。

## What Changes

- 生成模型弹层（`.mp-panel`）顶部增**搜索框**：打开弹层即聚焦；输入按**模型 id 或配置名**过滤（大小写不敏感），命中配置名＝该组全部模型保留，无一命中组整组隐藏；无匹配给空态文案「没有匹配的模型，换个词试试」。
- 键盘口径沿 ApiConfigForm 组合框先例：方向键在过滤结果中移光标、Enter 选中光标项、Esc 只收弹层不关生成弹窗、IME 组合期归输入法选词、选完/收层焦点回触发位（外点关闭除外）；每次重开弹层搜索词清零。
- 选择语义零变化：搜索只影响弹层候选呈现——默认本书模型、按次生效、重开回本书模型、「本书模型」标记随绑定等全部不变。

## Capabilities

- Modified: prose-writing —— Requirement「生成按次选择模型」增两条 SHALL（弹层快速搜索＋搜索键盘与重开清零），补两个场景（输入即过滤／键盘导航与重开清零）。

## Impact

- 前端：`client/frontend/src/components/novel/workbench/modals.tsx`（`ModelPicker` 增 query 状态＋过滤分组＋搜索框；触发位文案改从全量选项取）、`client/frontend/src/design/model-config.css`（新词 `.mp-search`）、`client/frontend/src/__tests__/AiModal.test.tsx`（+6 例）。
- 设计资产：`docs/design-c/prototypes/ADJUSTMENTS.md` 登记条目（`#modalAi` 不在 design-parity 场景清单，无像素基线变更）。
- 不动：后端、S端、按次模型对请求契约、`lib/panelAnchor.ts`、既有两条模型选择位 e2e（空查询＝全量选项，`data-model` 选择器不变）。

## Design Impact

- 受影响端：仅 C端。
- 受影响屏/弹层：仅「AI 生成正文」弹窗的生成模型弹层（顶部增一行搜索框；sticky 钉顶）。
- 共享段：不触碰（`model-config.css` 无 @cross 段）。
- 原型先行：不需要（产品化增强，原型 `book.html` `#modalAi` 保持静态演示；差异登记于 ADJUSTMENTS.md）。
