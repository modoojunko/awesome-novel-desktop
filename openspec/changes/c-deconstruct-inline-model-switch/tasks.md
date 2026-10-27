# 拆书失败详情页原地换模型 — 实施任务

## 1. 组件泛化

- [x] 1.1 `ModelPicker` 从 `workbench/modals.tsx` 导出，加可选 props：`label`（无障碍名＋弹层标签）、`triggerLabel`（CTA 型触发位固定文案）、`triggerClass`（触发位类）、`flagLabel`（选项旗标文案）、`panelWidth`＋右缘对齐（触发位过窄场景）。全部缺省回现行为。验证：AiModal 既有泡泡用例全绿（testid/aria 逐字节不变）。

## 2. 详情页接线

- [x] 2.1 `TaskDetailPage`：瞬时故障＋内容审核出口在可选模型 ≥2 时渲染泡泡触发位（「去换模型」按钮），`fetchModelOptions` 懒加载（进失败态才取一次，失败/空回落 `/config` 链接）。验证：vitest 两臂（有模型出泡泡／无模型回落链接）。
- [x] 2.2 选定即暂存：页内透出「已选新模型 ×××，点『从断点续拆』以新模型继续」；选回原模型对清空暂存。验证：vitest 暂存行＋清空臂。
- [x] 2.3 「从断点续拆」携带暂存模型（`resumeDeconstructTask(id, {apiConfigId, model})`），未暂存请求体不变；toast 带新模型名。验证：vitest 断言 resume 调用参两臂。
- [x] 2.4 内容审核红色面板同款泡泡出口（与瞬时故障共用暂存状态与回落口径）；鉴权/配置类出口保持 `/config` 链接不动。验证：vitest 面板臂＋auth 出口仍为链接。

## 3. 门禁与归档

- [x] 3.1 `npx tsc --noEmit`＋全量 `vitest --coverage`（100% 分支覆盖新代码）＋AiModal/toolsCreate 相关回归。验证：本地全绿（1825 过、coverage 门禁过）。
- [ ] 3.2 `openspec validate c-deconstruct-inline-model-switch --strict` 通过（已过）；归档**排队在 `c-deconstruct-resilience` 归档之后**——活跃 resilience delta 与本变更 MODIFIED 同一 Requirement「任务清单与详情」（冲突面仅「失败面板出口」一句），先归本变更会被 resilience 归档时的旧文本盖掉。本 PR 只带 change 目录与 ADJUSTMENTS 登记，不 sync 主 spec。
