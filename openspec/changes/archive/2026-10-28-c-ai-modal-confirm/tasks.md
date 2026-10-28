# c-ai-modal-confirm — Tasks

## 1. 封面/头像提取出卡化

- [x] 1.1 `ImageWorkshopModal.tsx`：`extractDraft` state＋采纳/换一个；封面/头像提取不再直填输入框；出卡 Modal（关闭即弃）。验证：tsc。
- [x] 1.2 `imageWorkshop.test.tsx` 两用例改钉：出卡过目（输入框未写）→关闭即弃→再提取→采纳才写入；头像出卡采纳。验证：vitest 定向绿。

## 2. 章纲缺项补全出卡化

- [x] 2.1 `chapterForm.ts` 增 `FILL_FIELD_LABELS`（出卡标签单源）；`ChapterWorkspace.tsx` 拆 `runFillGaps`（只取数置 `gapsDraft`）与 `adoptGapsDraft`（采纳才 setOgForm＋编辑态）；出卡 Modal（逐字段、换一个、关闭即弃）。验证：tsc。
- [x] 2.2 `chapterWorkspace.plotFlow.test.tsx` 新增 2 例：采纳写入进编辑态＋toast；关闭即弃不写不发保存。验证：22/22 绿。

## 3. 卷纲铺空缺出卡化

- [x] 3.1 `VolumePlanModal.tsx` 完成态渲染产物全文（七字段＋plants/reveals＋checks，可滚动）；按钮改「采纳 · 回填卷纲」；生成中关掉文案改「完成后提醒，不会自己写进书里」。验证：tsc。
- [x] 3.2 `NovelWorkspace.tsx` 删「关弹窗即 takeAutoBackfill 自动回填」effect，改未采纳载荷 toast 提醒。验证：volumePlan 钩子层用例不受影响（显式采纳仍走 takeAutoBackfill）。

## 4. 收尾

- [ ] 4.1 `openspec validate --all` 与 main 存量基线对拍；delta sync 进主 spec＋归档随 PR。
- [ ] 4.2 demo 换包实拍四处新交互（截图给 boss 过目）；**PR 不合入，等拍板**。
- [x] 4.3 拍板落定（2026-10-28）：#3 卷纲抽卡「确认成卷」**不动**（不加产物过目步）；正文流式写作按「写作面本体」豁免。
