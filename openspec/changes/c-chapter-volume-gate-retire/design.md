# c-chapter-volume-gate-retire — design

## 方向

撤闸，不换闸。排队模型（frontier）保持单源不变；建章路径删掉卷序判据，写正文路径（`is_writable`）一行不动。

## 后端

`client/backend/chapters/service.py` `create_chapter`：

- 删除「主线末端门禁」整段（`frontier_info` 调用＋`vol.volume_no < front["volume_no"]` 的 409 分支及其两段注释）。`frontier_info` 的 import 一并撤（该函数仅此处使用时再确认）。
- 其余逻辑不动：幂等 token、卷定位、`max_chapter_no+1`、五段同事务装配。
- 删守则：门禁删掉后若 `from chapters.frontier import frontier_info` 成孤儿 import，随之删除（只清自己留下的）。

新章成为写作位由既有派生逻辑自动成立（`_pick_frontier` 取首个未归档章），无需新代码。

## 前端

- `workbench/VolumeWorkspace.tsx`（ChapterLedgerPane）：
  - 删 `splitBlocked`（卷序判据）及「拆下一章」的 `disabled`/`title` 拦截文案、`volume-split-blocked` 提示段。
  - `canAdd` 由 `frontier.vol === detail.volume` 改为恒真（整段新增行常驻）；删 `!canAdd` 时的「新增章节排在主线末端；这一卷要等前面写到这里。」提示分支。
  - `create` 的 catch 改 `toast.error(errMessage(e, "创建章失败"))`（`lib/api.ts` 既有 helper，4xx 透出后端中文、其余回落兜底）。
  - `frontier` 内部 state 若仅剩写作位展示用途则保留展示用途，卷序判据相关消费点清理；props `frontierVol`（railData）撤除卷序消费点后如无他处使用则随删（只清自己造成的孤儿）。
- `workbench/VolumeAssistPanel.tsx`：
  - 删 `splitBlocked` 与其在「拆下一章（AI）」行的 desc/hint/disabled 分支（卷纲空门槛、`ai-plan` 档位锁、`checking` 保留）；防御分支注释里的 splitBlocked 说法同步收敛；右栏 `splitBlocked` 拦截段（tab==="chapters" && aiPlan && splitBlocked）删除。
- `hooks/useWorkbench.ts`：`createChapter` catch 改 `errMessage` 透出（同上口径）。

## 文案

无新增固定文案。被删文案：`写作位在第N卷——这一卷还没轮到（先去第N卷拆章）`、`新增章节排在主线末端；这一卷要等前面写到这里。`。失败兜底「创建章失败」保留（网络层回落）。

## 测试策略

- 后端：翻转 `test_chapter_plan_ai_t3.py` 门禁用例（409 → 建章成功且新章成为 frontier）；新增回归用例「全归档＋后续空卷 → 旧卷建章成功」（复现用户时序：拆书预建空卷）。
- 前端：`volumeWorkspace.test.tsx` 两条门禁用例翻转（入口恒在、建章成功）；`volumePlanCoverage.test.tsx` 右栏拦截用例改为「空门槛照拦、卷序不再拦」；吞错用例：mock 4xx detail 断言 toast 透出原文。
- e2e：`chapter-plan.spec.ts`「非末端卷」用例翻转（两入口可点、建章成功、无 blocked 段）。

## 兼容与回滚

- 无迁移、无契约变化；回滚＝恢复该判据即可。存量书不受影响（只是多出原本被拦的操作能力）。
