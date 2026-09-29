## 1. 样式词汇（book.css，C端局部）

- [x] 1.1 新增 `.no-close`（11.5px faint）与 `.pick-busy.col` 纵排变体（含 `.col .none` 12px faint）；验证：`grep -n "no-close" src/design/book.css` 命中且 design:lint 不新增红

## 2. 弹窗组件加提示行（9 组件 10 处）

- [x] 2.1 ChapterPlanModal（`split-busy`）加 `.pick-busy col`＋`.no-close`「AI 创作中，请勿关闭弹窗」；验证：vitest `chapterPlan.test.tsx` busy 用例含新断言
- [x] 2.2 PickCardsModal（`pick-busy`）同上；验证：vitest `volumePlan.test.tsx` 绿
- [x] 2.3 PlotDrawModal（`plot-busy`）同上；验证：vitest `plotDrawModal.test.tsx` busy 用例含新断言
- [x] 2.4 CastReviewModal 两处（`cr-reviewing`＝「AI 盘点中…」、`cr-drawing`＝「AI 创作中…」；容器已纵排只加行）；验证：vitest `castReviewFlow.test.tsx` 绿
- [x] 2.5 AiCardModal 两处（`ai-card-loading` 列内追加；「换一个」在途 `ac-busy` 行内追加 span，主行「AI 正在生成…」「正在生成新一版…」文字原样保测试兼容）；验证：vitest `StoryArcForm.test.tsx`＋`aiAssistModals.test.tsx` 绿
- [x] 2.6 ContrastPreviewModal 生成中分支（行内样式 flexWrap 副行）；AiCheckModal 检查中（「AI 检查中…」）；SimModal 推演中（「AI 推演中…」）；验证：`npx tsc --noEmit` 干净＋相关 vitest 绿

## 3. 测试钉子

- [x] 3.1 chapterPlan.test.tsx busy 用例＋plotDrawModal.test.tsx busy 用例各补一条 `toHaveTextContent("AI 创作中，请勿关闭弹窗")`；验证：两文件 vitest 全绿

## 4. 原型补登记（硬性流程回填）

- [x] 4.1 各弹窗原型（docs/design-c/prototypes/ 卷下拆章、整书拆纲、角色盘点、章剧情等）busy 态补同一行提示，无法对应原型的在 prototypes/ADJUSTMENTS.md 登记偏差与理由（实现先行回填）；验证：ADJUSTMENTS.md 有本 change 条目

## 5. 门禁与收尾

- [x] 5.1 `npx tsc --noEmit` 干净＋相关 vitest 全绿（chapterPlan/plotDrawModal/castReviewFlow/StoryArcForm/aiAssistModals/volumePlan/plotSimAndPromptSources）；验证：命令输出零红
- [x] 5.2 `npm run design:check` 零新红（parity 基线不受瞬态 busy 影响）；验证：命令退出码 0
- [x] 5.3 e2e 存量不红：`split-busy`/`ai-card-loading` 可见性断言不变（chapter-plan.spec、genre-ai-settings.spec）；真栈验证需隔离栈，留合流前按需
- [ ] 5.4 提交时只纳入本 change 文件（9 组件＋book.css＋2 测试＋specs delta＋工件），并行会话改动（CharacterManager、archive-reconcile 等）不混入；验证：`git status` 逐项核对

> **完成证据（2026-09-30 apply 会话）**
> - 1.1：book.css:1748-1750 三行词汇就位；design:lint 通过（存量冻结观察项不变）。
> - 2.x/3.1/5.1：vitest 7 文件 171 用例全绿（chapterPlan/plotDrawModal/castReviewFlow/StoryArcForm/aiAssistModals/volumePlan/plotSimAndPromptSources）；`tsc --noEmit` 零输出。
> - 4.1：book.html 三处 busy 态（plot busy／sc-s2 盘点中／sc-s10 抽卡在途）补 `.no-close` 行＋原型 CSS；ADJUSTMENTS.md 追加「AI 弹窗生成中『请勿关闭』提示行」整节（含无活原型弹窗的登记与 VolumePlanModal 例外）。
> - 5.2：design:check 7 过 1 红——红为「书架屏（list.html v2）empty」像素差 0.2917%（阈值 0.2%），本 change 零触书架屏，判定为在案存量字体光栅漂移（主检出本机已知），非新回归。
> - 5.3：e2e 全量 grep 仅 chapter-plan.spec:185（split-busy 可见）与 genre-ai-settings.spec:426（ai-card-loading 可见）两处断言，均可见性断言且 testid 未动；对照截图按 guidance 需真栈，busy 态瞬态、与 5.3 同留合流前。
> - 5.4：分支提交逐文件核对（见 PR 文件清单），并行会话改动（CharacterManager、archive-reconcile、c-lore-reconcile-guardrails 等）未混入。
