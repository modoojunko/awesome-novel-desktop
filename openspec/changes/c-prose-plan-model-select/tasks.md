# 任务：正文方案卡按次选择生成模型（c-prose-plan-model-select）

## 1 前端·方案卡选择位

- [x] 1.1 `Aui2Dock.tsx`：`prose_plan` 卡增「生成模型」选择位（复用 `ModelPicker`；默认本书模型；候选 <2／本书模型未就绪／已开始生成时不渲染；失效选择回退本书模型）
- [x] 1.2 `Aui2Dock.tsx`：宿主桥 `onProsePlanStart(payload, onStarted?, modelSelection?)`——仅「≠ 本书模型」时携带按次模型对
- [x] 1.3 `NovelWorkspace.tsx`：`pendingStartRef` 携带 `modelSelection` → `proseRef.startWriting(prompt, modelSelection, extras)`（再生成确认后仍按所选模型）
- [x] 1.4 `chat.css`：`.cd-plan-prompt-text.full` 展开为全文（去掉 320px 限高内滚动）＋选择位样式

## 2 测试

- [x] 2.1 `dialogProse.test.tsx`：默认本书模型不带对／换模型带对／单选不渲染／未就绪不渲染／已开始生成后隐藏
- [x] 2.2 `tsc --noEmit` 零错＋vitest 全量绿（187 文件 2352 通过）
- [ ] 2.3 真机走查：多模型书方案卡换模型 → 生成按所选模型；长提示词「展开全部」见全文（随装包）
