## Context

见 proposal.md「Why」。实现面现状：

- 后端 `write/router.py` 已支持按次模型对：body 可选 `{api_config_id, model}`，校验后走 `override_client`，`used_model = override_model`；不传走 `effective_model(project)`（本书模型）。
- 前端 `lib/ai.ts` 的 `streamChapterWrite(projectId, ref, cb, promptOverride?, modelSelection?, extras?)` 已会把模型对写进 body；`ProseWriteExtras` 目前只有 `kbPicks`。
- `ProsePane.startWriting(prompt?, modelSelection?, extras?)` 已支持；但对话框方案卡桥接 `NovelWorkspace.tsx:370` 恒传 `undefined`，`handleProsePlanStart` 也未读模型字段。
- `workbench/modals.tsx` 内已有 `ModelField`：`useModelStatus(projectId)` 取清单，默认 `bookValue`＝本书模型，选本书模型时 `onChange(null)`，`aiState !== ready` 或选项 <2 不渲染；文案「仅本次生成生效，不改本书模型」。该组件目前只在 AiModal 内使用、未导出。

## Goals / Non-Goals

**Goals：**
- 方案卡可为本章正文按次换模型；默认本书模型；不继承对话模型。
- 选择随「开始生成」透传到 write body；选本书模型时链路与现状逐字一致。
- 「未点开始不生成」「提示词全文可评审」有测试钉。

**Non-Goals：**
- 不做卡内提示词编辑（改提示词走对话重出卡）。
- 不改后端 write 端点、不改模型校验与记账口径（复用既有按次模型对）。
- 不改助手对话底栏的模型选择行为。
- 不引入新的模型选择组件或 `.mp-*` 词汇。

## Decisions

### D1｜复用既有 `ModelField`，抽成可复用导出
把 `ModelField`（含 `ModelPicker`）从 `modals.tsx` 抽到可导出位置（同文件导出或相邻共享组件），AiModal 改为引用同一实现，行为不变。方案卡直接复用，不新造第二个模型选择器。

- 替代方案：在 Aui2Dock 里重写一个选择器——会出现两套默认值/不渲染口径，判例是「面板按钮文案=chips 文案单一源」，选择器同理。

### D2｜默认值取本书模型，不读对话模型
`useModelStatus(projectId)` 的 `currentConfigId/currentModel` 就是本书模型；方案卡默认展示它，选本书模型时按 `null` 处理（不携带覆盖对）。SHALL NOT 读取 assistant 线程的模型选择。

- 为什么不在后端兜底：后端本来就不读对话模型；风险只在前端把对话状态带进 payload，所以在渲染层显式取本书模型即可。

### D3｜`model_selection` 是前端本地状态，渲染时合并进 payload
方案卡 payload 由 `draft_prose_plan` 产出，不含模型字段（agent 不应决定模型）。`Aui2Dock` 在卡内维护本地 `modelSel`，点「开始生成」时把 `{api_config_id, model}` 合并进交给宿主的 payload（选本书模型则不带）；`handleProsePlanStart` 解析 `model_selection`，经 `pendingStartRef` 传给 `startWriting(prompt, modelSelection, extras)`。

### D4｜评审闸靠测试钉，不新增按钮
现有「开始生成」即采纳动作；未点击不调用 write 已成立。本次补测试：卡出现后零 write 请求；点开始后请求带卡上 prompt 与所选模型。卡面不新增「采纳」第二步，避免双按钮语义。

### D5｜单模型/未就绪不渲染，与 AiModal 同口径
沿 `ModelField` 既有判定（`aiState !== "ready" || modelOptions.length < 2` 整行不渲染）。单模型用户零变化，也避免方案卡多一行空控件。

## Risks / Trade-offs

- [方案卡 payload 契约漂移] → `model_selection` 只在 `proseStart` 时由前端合并，不改 `draft_prose_plan` 的工具参数与卡片持久化结构；跨章作废判定仍只看 `chapter_ref`。
- [模型清单请求打在工作台常驻预算上] → 模型行只在方案卡出现时挂载取数（与 AiModal「打开弹窗才挂载」同例）。
- [对话模型被误带进正文] → 默认值取 `useModelStatus(projectId)`，测试断言对话底栏换模型后方案卡默认仍为本书模型。
- [抽 `ModelField` 影响 AiModal] → 抽取只改引用位置，AiModal 用例全量回归。

## Migration Plan

无数据库/接口迁移，无发布开关。前端随下一次构建生效；回滚还原 `Aui2Dock.tsx`、`NovelWorkspace.tsx`、`modals.tsx` 三处与新增测试。

## Open Questions

（无）
