## 1. 原型先行（ADJUSTMENTS 登记替代）

- [x] 1.1 `docs/design-c/prototypes/ADJUSTMENTS.md` 新增本 change 段：登记「拆章族入口唯一页签＝本卷章节」的偏差与依据（卷视图事实源 storyline.html 已下线、不入 parity 基线，同 c-ai-rail-shared 口径无活原型可比对；设计工件＝实现侧自查）。完成证据＝登记段落入库 diff。

## 2. 中栏迁移（VolumeWorkspace.tsx ＋ book.css）

- [x] 2.1 卷纲页签查看态 `ol-top` 撤「拆下一章」按钮（`volume-split-manual`）与 `volume-split-blocked` 提示段；「重拆本卷」「编辑卷纲」原地保留；`onSplitManual` prop 链与 `frontier` prop 按 VolumeOutlinePane 实际残留清理（`frontier` 因「待写」列必须保留）。完成证据＝grep `volume-split-manual` 在 VolumeOutlinePane 段零命中、tsc 干净。
- [x] 2.2 本卷章节页签（ChapterLedgerPane）标题行加「拆下一章」按钮：book.css 增 `.seg-h` **修饰类**作用域规则（`.seg-h.push-row` flex＋`.push` 右推——既有 `.push` 只在 `.ol-top` 作用域生效，前端评审实勘；不动全局 `.seg-h`）；沿用松判据 `splitBlocked`（disabled＋title 补救），`volume-split-blocked` 提示段随迁；`onSplitManual` 下传 ChapterLedgerPane；「在本卷新增一章」旁补区分 hint（「只起标题，剧情后补——按四段关键剧情拆章用上方「拆下一章」」）。完成证据＝vitest 断言「卷纲页签 ol-top 仅剩两钮」「本卷章节页签按钮出现且右对齐（结构断言或截图自查）」＋置灰态＋点击开手写弹窗。
- [x] 2.3 卷纲页签零章空态文案改口（PM 评审翻案，design D8）：「还没有排章——去「本卷章节」拆下一章，这里会按章列出推进」，「本卷章节」为内联可点击出口（`setTab("chapters")`）。完成证据＝单测/e2e 断言新文案与出口点击切页签；主 spec 对应句已被本 change delta 覆盖。
- [x] 2.4 顺手口径修整：`VolumeWorkspace.tsx` tooltip（L578）与文件头注释的「五段」改「四段」或删计数（c-og-slim-v2 后口径）；非 frontier 卷同屏两条「还没轮到」提示对拍视觉，必要时合并措辞。完成证据＝grep「五段」在卷视图组件零残留＋视觉对拍结论。

## 3. 右栏迁移（VolumeAssistPanel.tsx）

- [x] 3.1 「拆下一章（AI）」行与 `volume-split-ai-locked`／`volume-split-ai-blocked` 两状态段的页签条件 `outline` → `chapters`；免费锁定文案定稿「AI 三方向需 PRO——手写拆章免费：用中栏「拆下一章」」；新增「卷纲未填」前置拦截段（`volume-split-ai-outline-gate`，判据＝`detail` 的主旨/冲突/卷末任一为空，带「去补卷纲」出口 `setTab("outline")`，点击 AI 行不发请求）；`VOL_TAB_LEAD`／`VOL_TAB_ORDER` 不动。完成证据＝volumePlan 单测**新增**用例（chapters 页签出 AI 行/锁定段、outline 页签不出、空卷纲出拦截段且出口可切页签——现有分页签断言只查 replan，无 split 钉可改）。
- [x] 3.2 接线核对＋stale 注释清理：`Rail.tsx:75`「卷纲页签 PRO 入口」、`VolumeAssistPanel.tsx:147`「卷纲页签的「拆下一章（AI）」」等注释随批改口；grep 范围扩到全仓 src＋e2e＋openspec/specs（散文档级提及）的「卷纲页/卷纲页签」×拆章组合。完成证据＝tsc 干净＋grep 零残留（openspec 归档与 ADJUSTMENTS 历史登记除外）。

## 4. 测试适配与门禁

- [x] 4.1 e2e 适配（`chapter-plan.spec.ts` 22 处、`plot.spec.ts` L107、`cast-review.spec.ts` L103）：**每处** `volume-split-*` testid 的点击**与断言**前机械插入 `getByRole("tab", { name: "本卷章节" })`（断言型前提同切——免费档锁定段 L306-315、末端拦截段 L463-470；重拆用例同例内两处点击 L409/L432 都要切）；免费锁定句全文断言随 3.1 新文案同批更新，其余断言文本与 testid 零改动。完成证据＝三文件适配 diff（覆盖处数清单）。
- [x] 4.2 门禁：C端 `npm run design:lint`（不触共享段，design-cross 不适用，判定依据＝proposal Design Impact；book.css 不在 vocab 扫描范围）＋ `tsc --noEmit`＋全量 vitest（存量红除外）。完成证据＝各命令实际输出结论。
- [x] 4.3 隔离栈 e2e 重跑 chapter-plan／plot／cast-review 三文件（per-session 隔离环境配方，E2E_BASE_URL 指向本会话栈）。完成证据＝三文件全绿输出。
- [ ] 4.4 `openspec validate --strict` 全绿；PR（标题不带硬编码 PR 号）＋合并后按归档流程 sync specs。
