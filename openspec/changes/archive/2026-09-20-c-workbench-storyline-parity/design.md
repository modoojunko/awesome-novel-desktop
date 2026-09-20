# Design: c-workbench-storyline-parity

## 决策

1. **控件去向（不删功能）**：editor-toolbar 的排版 seg/专注/版本历史/归档本章并入
   e-head 右侧 `.prose-ctrls`（`.e-head-row` flex 行）；AI 生成正文按钮不迁移——
   右栏顶部本就有同链路卡（同一条页面级解锁链：归档章先弹解除只读→AiModal）。
   依据 ADJUSTMENTS 条13修订。
2. **文风建议的右栏触发通道**：建议状态（baseline/shadow/suggestions）留在
   StyleShadowPane（结果与逐项采纳仍在页签内），右栏动作经 `suggestSignal` 计数器
   信号触发（railData 上抛 onStyleSuggest）；busyRef 挡并发、mountedRef 挡重挂载
   误触发（切页签往返不重拉）。
3. **免费态语义**：raActs locked（rail-locked 置灰＋禁点）取代「不渲染」，与右栏
   生成正文卡免费态口径一致；两处 e2e 免费态断言从 count 0 改 visible+disabled。
4. **卷视图衬垫**：scoped `.wb .view.on.three-col .vol-shell .e-pad`（.e-pad 仅
   VolumeWorkspace 使用，零外溢）；顺带删同段 tpl-row/.field 死选择器（旧版卷表单
   残留，fro/fgrid 的 76ch 约束已由皮肤段承担）。
5. **testid 随迁**：og-ai-draft/og-simulate 落到右栏动作按钮（e2e 锚点不断），
   右栏生成正文卡补 `ai-write-btn`。

## 风险与守卫

- ChapterWorkspace 同时承载两批改动（页签结构＋AI 收口），拆分边界＝按文件归属
  两个 commit（8c48f01 / 3aeafe4），PR #445 squash 合入。
- `.prose-ctrls` 原有 `hidden` 属性一直被自身 `display:inline-flex` 压掉（控件本就
  全页签可见），迁移后删除该失效属性、保持实际行为不变。
- workbench-3-label spec（旧三代 label 时代）的「正文/章纲/提示词」顺序句为存量
  过时口径，storyline 八页签换代时未同步——本卷宗不扩科处理，登记于此待后续
  specs 清理 change 收编。
