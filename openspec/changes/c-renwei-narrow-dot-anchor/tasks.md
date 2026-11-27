# Tasks — c-renwei-narrow-dot-anchor

## 1. 原型先行 / 设计登记

- [x] 1.1 原型影响判定：`docs/design-c/prototypes/book.html` 无 `rw-mnote`/人味边注（grep 0 命中）→ 原型基线未涵盖本形态、不新增视觉形态、不改像素基线；`docs/design-c/prototypes/ADJUSTMENTS.md` 已追加「2026-11-27 · 锚点＝段尾实测」登记
- [x] 1.2 锚点语义溯源：drafts 人味检测原型「段角胶囊跟段尾走」口径（段角胶囊后因右栏简述退役）；本屏不在 `design:check` 像素矩阵（只跑 list.html / preview.html），视觉由组件单测＋真 Chromium 几何探针覆盖

## 2. 实现（承接 PR #1128，分支 c-renwei-dot-anchor-text）

- [x] 2.1 `RenweiMarginNotes` 段尾锚落地：`textEndRect()` 取最后一个文本节点末字后缘 Range；`DOT_BOX_H=18`/`DOT_GAP_TO_BOX=3`；`dots`/`narrow` 状态；窄栏内联 `left/top`（短行跟末字、满行贴列缘外侧）；验证＝单测 13/13＋真 Chromium 探针
- [x] 2.2 量测缺席兜底：`textEndRect()` 返回 null 时不给内联 left，回落 `book.css` 窄栏 `left: min(var(--rw-notes-left), calc(100% - 20px))`；`right:2px` 已删除；验证＝新增单测「量测缺席…不给内联 left」
- [x] 2.3 RO stale 收口：`groupsRef.current = groups`，`measure()` 从 ref 取当轮问题段（ResizeObserver deps 仍只挂 `editorEl`）；验证＝实现审读＋全量单测绿
- [x] 2.4 注释与常量互指：组件头注释写「圆点跟段尾走，不钉层缘/列缘」两连判例；CSS 注释写 `min()` 仅为量测兜底；验证＝实现审读

## 3. 测试

- [x] 3.1 `src/__tests__/renweiCheck.test.tsx`：新增「窄栏圆点锚＝段尾实测」用例（stub jsdom 缺失的 `Range.getBoundingClientRect`，断言 left=末字后缘+3px、top=末行中点）＋「量测缺席不给内联 left」用例；验证＝`npx vitest run src/__tests__/renweiCheck.test.tsx` **13/13 绿**
- [x] 3.2 真 Chromium 几何探针（900px 中栏）：短行「“熬的。”他说。」→ 点距末字 **6.39px**、点中心＝末行中心（109px）、距纸右缘 580px、距中栏右缘 626px；满行 → 文本末缘＝列缘（790）、点距末字 **6px**、距纸右缘 50px、距中栏右缘 96px；验证＝`/tmp/renwei-range-probe/probe.mjs` 输出
- [x] 3.3 变异验证：把锚临时改回列缘（`editorEl.right`）→ 段尾断言应红；实测 **Expected 433px / Received 628px**，1 failed；恢复后 13/13 绿；验证＝红绿记录

## 4. 回归

- [x] 4.1 C端门禁：`npx tsc --noEmit` **exit 0**；`npm run design:lint` exit 1 但唯一违规＝存量 `docs/design-c/prototypes/preview.html` emoji（主检出同一条，非本改动引入）；`DESIGN_PARITY=1` 两 spec **7 passed / 1 failed**，失败项＝preview 阅读屏像素差 **4.598%**（主检出同栈 A/B＝**4.596%**，同一存量环境差异；本改动不触 list/preview）
- [x] 4.2 共享段判定：不触 base.css 令牌/基础组件类/pill/notice/sk/panel/f-err 家族，`node scripts/design-cross.mjs` 不适用（引用 proposal Design Impact）；renwei 相关存量单测 `renweiCheck` 13/13、`renweiChapterMemory` 3/3、`renweiChapterReset` 2/2；前端全量 **2349 passed / 1 skipped（187 files）**

## 5. 交付与归档

- [ ] 5.1 只报 diff 等老板批准；批准后才 commit/push 更新 PR #1128；CI 绿后再逐次请示合入（不得自行 merge/打包/发版）
- [ ] 5.2 合入后归档：`renwei-check` 主 spec「正文左右分边注与覆盖层」按本 change 同步；`openspec validate --specs` 通过
