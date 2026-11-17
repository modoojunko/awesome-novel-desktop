# c-chapter-volume-gate-retire — tasks

## 1. 后端撤闸

- [ ] 1.1 `chapters/service.py` `create_chapter`：删除主线末端门禁段（frontier_info 调用＋409 分支＋注释），孤儿 import 随清。
- [ ] 1.2 `tests/test_chapter_plan_ai_t3.py`：门禁用例翻转——「写作位在第 2 卷时第 1 卷不许排新章」改为「第 1 卷可排、新章成为 frontier」；补回归用例：全归档＋后续空卷（拆书预建卷时序）→ 旧卷建章成功。
- [ ] 1.3 后端全量 pytest 绿（含既有 test_volume_chapter_crud 等）。

## 2. 前端撤闸＋吞错修复

- [ ] 2.1 `VolumeWorkspace.tsx`：删 `splitBlocked` 判据/置灰/提示段；「在本卷新增一章」恒可用（删 `canAdd` 卷等值判据与说明文案分支）；catch 改 `errMessage` 透出。
- [ ] 2.2 `VolumeAssistPanel.tsx`：删 `splitBlocked` 及「拆下一章（AI）」行 desc/hint/disabled 卷序分支与右栏拦截段；卷纲空门槛/档位锁/checking 保留。
- [ ] 2.3 `useWorkbench.ts` `createChapter`：catch 改 `errMessage` 透出。
- [ ] 2.4 孤儿清理：railData `frontierVol`、`VolumeWorkspace` props/消费点里因撤闸不再使用的部分随之删除（git diff 逐行可追溯）。
- [ ] 2.5 `__tests__/volumeWorkspace.test.tsx`、`__tests__/volumePlanCoverage.test.tsx`：门禁用例翻转＋新增「4xx detail 透出」断言；新增「空卷存在时旧卷入口可用」用例。
- [ ] 2.6 前端 tsc --noEmit ＋ vitest 全量（含 coverage 阈值）绿。

## 3. e2e

- [ ] 3.1 `e2e/chapter-plan.spec.ts`「非末端卷：拆章两入口置灰」翻转：手写入口可点、建章成功、无 `volume-split-blocked` 段；`volume-split-ai` 断言撤（右栏已随 c-agent-fleet 换 ChatDock，该元素真应用不再渲染）。
- [ ] 3.2 **挂账（非本 change scope）**：`chapter-plan.spec.ts` 全 17 用例在 main（d341c091）即存量红——`createNovelWithVolume` 依赖已退役的右栏入口 `plan-first-volume`（写作助手 dock 换装后该入口只在单测可达）；本机独立栈实跑 17/17 超时实锤。e2e 修复归 c-agent-fleet 会话/nightly owner。本 change 行为回归由后端 pytest（含空卷回归用例）＋前端 vitest 钉死。

## 4. 收口

- [ ] 4.1 `openspec validate --all` 与基线对拍放行（存量红对拍 main）。
- [ ] 4.2 delta 与主 spec 对拍：MODIFIED 段落零漂移（ Requirement 全量替换，删除的 Scenario 不在主 spec 残留）。
- [ ] 4.3 开 PR（base main），CI 双绿后合入。
