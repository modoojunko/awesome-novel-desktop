# settings-done-entry · Tasks

> 单批可交付（纯前端展示层，约 30 行实现＋e2e 断言）。

## 1. 原型转正

- [ ] 1.1 设计稿 `docs/design-c/drafts/ai-novel-c端-设定完成去写作.html`（v2 合一版）转正 `docs/design-c/prototypes/settings-done-entry.html`；ADJUSTMENTS #23 登记（settings-progress.done 变体词表、pb-check/pb-badge/done-btn/done-foot、「完成入口不用普通主按钮」口径）；design-vocab strictGlobs 增补；design:lint 通过

## 2. 实现

- [ ] 2.1 `SettingsView.tsx`：done 分支改造——进度行挂 `done` 类，条件渲染对勾/「设定完成 8/8」标签/「全部就绪」徽标/「去写作」CTA（data-od-id="btn-go-write"）/小字；删除旧全宽按钮；CHECK_PATH 对勾复用
- [ ] 2.2 `book.css` settings-v 段：done 变体样式（ok-soft 底、ok 描边、满格绿条、CTA/小字）；非 done 态零像素变化
- [ ] 2.3 e2e：`creation-flow.spec.ts` 设定全确认用例尾部断言完成卡（对勾/徽标/CTA）与「去写作」→ 写作视图；`settings-forms.spec.ts` 文风用例（7/8 态）补「完成卡不出现」断言

## 3. 验收

- [ ] 3.1 全量：tsc／vitest／design:lint／design:check 绿；e2e 本地 docker 栈全量绿（含 creation-flow 与 settings-forms 回归）
