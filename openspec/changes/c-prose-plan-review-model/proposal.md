# 提案：正文方案卡可选生成模型＋生成前提示词评审闸（c-prose-plan-review-model）

## Why

对话框正文方案卡（`prose_plan`）是正文生成的唯一入口：卡上展示提示词全文与选中写法条目，作家点「开始生成」才开流。现在卡上有两个缺口：

1. **没有生成模型选项**。后端与前端其实早已具备按次模型对能力（`write/router.py` 的 `{api_config_id, model}`、`streamChapterWrite` 的 `modelSelection`、AiModal 的「生成模型」行），但方案卡桥接把模型参数丢了：`handleProsePlanStart` 只传 `prompt + kbPicks`，`startWriting(prompt, undefined, extras)` 恒传 `undefined`——作家无法在卡上为这一章换模型。现状默认走本书模型（不继承对话模型），但卡面不显示、不可改。
2. **「评审后生成」没有钉成契约**。方案卡已展示提示词全文，但没有任何规格声明「未点开始生成不得调用 write」；模型默认值也没有声明「不得继承助手对话底栏所选模型」。对话底栏的模型选择只作用于对话回合，不应顺延到正文生成。

boss 口径（2026-11-27）：正文生成前的提示词必须拿给作家评审，采纳后方可生成；推送给作家的卡要有大模型选项，不可默认继承对话框的大模型。

## What Changes

- **方案卡增「生成模型」行**：复用既有 `ModelField`/`ModelPicker`（`.mp-*` 组合框与弹层族），放在提示词块之后、「开始生成」之前；默认选中本书模型（`project.ai_config_id + ai_model`），弹层内标注「本书模型」；可选模型（含默认项）少于 2 个或 AI 未就绪时 SHALL NOT 渲染该行（与 AiModal 同口径）。
- **默认值不继承对话框模型**：方案卡的模型默认值 SHALL 取本书模型，SHALL NOT 读取助手对话底栏所选模型；对话模型只作用于对话回合。
- **选择随卡透传**：方案卡「开始生成」时把 `{api_config_id, model}` 作为 `model_selection` 随 payload 交给宿主；选本书模型时按 `undefined` 传递（走后端 `effective_model`，请求与既有链路逐字一致）。
- **评审闸写进契约**：卡上提示词全文可见（折叠可展开，已有）；未点「开始生成」SHALL NOT 发起 write 调用；已有正文的再生成仍先过既有确认弹窗。
- **卡内提示词编辑不在本次**：作家要改提示词仍在对话里让 agent 改后重出卡；卡面不新增编辑器（避免与对话编排的单一事实源冲突）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `prose-writing`：新增「对话框正文方案卡按次选模型与生成前评审」Requirement——方案卡模型行、默认本书模型且不继承对话模型、选择透传、评审闸。

## Impact

- 前端：`components/novel/chat/Aui2Dock.tsx`（方案卡渲染模型行＋`proseStart` payload 带选择）、`components/novel/NovelWorkspace.tsx`（`handleProsePlanStart` → `pendingStartRef` → `startWriting` 透传）、`components/novel/workbench/modals.tsx`（把 `ModelField`/`ModelPicker` 抽成可复用导出，AiModal 行为不变）。
- 后端：无需改动——`write/router.py` 已支持 `{api_config_id, model}` 按次覆盖并在开流前校验；`ProseWriteExtras` 与 `streamChapterWrite` 已支持 `modelSelection`。
- 测试：前端单测（方案卡模型行默认值/透传/单模型不渲染）、e2e（换模型生成走覆盖对）、既有 dialogProse 回归。
- **Design Impact**：受影响端＝C端；屏/弹层＝工作台·章节 → AI 对话 dock → 正文方案卡（`prose_plan`）；对象状态＝复用既有模型选择器与按钮态，无新状态语言、无新语气档；不触碰两端共享段（base.css 令牌/共享组件类）；需要原型先行（`docs/design-c/prototypes/book.html` 的对话 dock 方案卡补「生成模型」行＋`ADJUSTMENTS.md` 登记）；设计工件由实现侧自查产出。
