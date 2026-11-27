## 1. 原型先行

- [x] 1.1 `docs/design-c/prototypes/book.html` 新增 `#modalProsePlan`「正文方案（对话内卡）」演示壳（从 AI 生成正文弹窗底部「看方案卡形态」进入）：卡面＝标题/选中条目/提示词折叠/生成模型行/开始生成；模型行复用 `.mp-wrap/.mp-trigger/.mp-panel/.mp-list/.mp-item` 族，默认本书模型、弹层内「本书模型」标记。`ADJUSTMENTS.md` 已登记（单模型/未就绪不渲染、默认不继承对话模型、无新词汇档位）
- [x] 1.2 原型自查：未触共享段（base.css 令牌/共享组件类零改动）；新增 `.cd-plan*` 仅用于该演示块（实现侧沿用 chat.css 既有类）；无新字号档/胶囊形态。`design:lint` 通过（唯一严格违规 `preview.html:1 emoji` 为存量，主检出同样存在，exit 0）

## 2. 复用既有选择器

- [x] 2.1 复用已导出的 `ModelPicker`（`modals.tsx:448`）＋`useModelStatus`，方案卡按语境自带标签组装，未额外抽 `ModelField`（AiModal 行为未动）；`npx tsc --noEmit` 通过，`AiModal.test.tsx` 回归通过（合计 41 passed）
- [x] 2.2 `useModelStatus` 默认值语义确认：`currentConfigId/currentModel`＝本书模型；单模型/未就绪不渲染由方案卡 `showModel` 判定（单测覆盖）

## 3. 方案卡模型行

- [x] 3.1 `Aui2Dock.tsx` 的 `prose_plan` 卡在提示词块之后渲染「生成模型」行：默认本书模型、卡内本地 state、选本书模型时 `null`；可选 <2 或未就绪不渲染
- [x] 3.2 点「开始生成」时把 `{api_config_id, model}` 合并进交给宿主的 payload（`model_selection`；选本书模型不带）；提示词与 picks 字段不变
- [x] 3.3 前端单测（`dialogProse.test.tsx` 新增 4 用例）：默认本书模型且未换模型 payload 不带 `model_selection`；卡上换模型 → payload 带按次模型对；单模型不渲染模型行；未点开始零调用宿主。`npx vitest run dialogProse + AiModal` → 13+28=41 passed

## 4. 宿主桥接透传

- [x] 4.1 `NovelWorkspace.tsx` 的 `handleProsePlanStart` 解析 `payload.model_selection`，经 `pendingStartRef` 传到 `doProseStart` 的 `startWriting(prompt, modelSelection, extras)`；跨章作废判定仍只看 `chapter_ref`
- [x] 4.2 回归：选本书模型时请求体与现状逐字一致（不带 `api_config_id/model`）；选覆盖对时 `lib/ai.ts` 既有契约带两字段（未改契约）；测试覆盖两种分支

## 5. 评审闸与回归

- [x] 5.1 测试钉「未点开始不生成」：方案卡出现后 `onProsePlanStart` 零调用；点开始后宿主收到卡上 prompt 全文与所选模型对（既有宿主桥断言＋新用例）
- [x] 5.2 C端门禁：`design:lint` 通过（preview.html emoji 为预存违规，主检出同样存在，exit 0）；`design:check` → **7 passed / 1 failed**，唯一红 `preview · 三栏阅读器`（像素差 4.598%）；`git stash` 回基线同跑**同样失败**→预存/环境问题，与本改动无关（本改动不触 preview 屏）。`npx tsc --noEmit` 通过。方案卡无专用 e2e 用例（vitest 覆盖交互链）
- [ ] 5.3 真机走查（当前 0.49.x 构建）：对话底栏换模型 → 开方案卡确认默认本书模型 → 卡上换模型 → 生成后记账为覆盖对；本书绑定未变。待装新包后做

## 6. 挂账

- [x] 6.1 `c-agent-dialog-prose` 归档时，把「方案卡模型行＋评审闸」并入 `assistant-dialog-prose` 规格的结论卡条款（当前该 capability 未入主 specs）
- [x] 6.2 卡内提示词编辑（如后续需要）另行立项；本次明确 Non-Goal
