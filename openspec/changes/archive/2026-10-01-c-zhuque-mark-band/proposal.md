# c-zhuque-mark-band：朱雀正文标注降噪带化

## Why

真机首检（34 段章、上游并成 2 分段）暴露标注视觉噪音：当前**每个非空段都挂章**（人写段灰章＋常驻百分数），上游并段后长串段落重复同一判定——一屏徽章墙，重点反而看不见。标注的职责应当是「哪里可疑」，不是「逐段复读」。

## What Changes

- **人写段静默**：人写段 SHALL NOT 渲染任何章或底色（人工占比在标题区结果条已有，正文不复读）；stale 态人写带同样静默。
- **连续同判定聚合成带**：相邻同 label 的非空段（空段不计入、不打断）聚合为带，**只在带尾段挂一个章**；底色保留逐段荧光笔式现状（CSS 零改动）。
- **置信度收进悬停**：章文本只写判定词（「疑似」「AI」），百分数经**段落级 `title` 属性**悬停可查（ Decoration.node attrs 挂到带内每个着色段，零 CSS 变更、无点击截获）。
- stale 语义＝**维持现状**：stale 段落无底色（现状即如此——只挂 `zq-stale` 单类）、带尾章转灰变体；`book.css:1929` 复合选择器（`.zq-stale.zq-warn` 永不命中的死 CSS）同批清理并登记 ADJUSTMENTS。

## Capabilities

- **zhuque-workbench**（MODIFIED）：「正文段落标注覆盖层」Requirement——章的渲染从「每段一/confidence 常驻」改为「带尾单章/人写静默/置信度悬停」；底色、stale、不进导出、指纹失效条款保留原语义。

## 不动项

- 后端零改动：响应契约（`segments[{paragraph_index,label,confidence}]`）、对齐制（c-zhuque-seg-align）、结果条、右栏行全部不动（后端评审已核实：`align_segments` 构造性保证 index 连续 0..N-1，spec 条款＋test_zhuque.py 双钉）。
- 底色视觉零改动：`.editor p.zq-warn/.zq-err` 荧光笔式保留（用户拍板 2026-10-01）。
- 单段带＝现状形态（一段一个章），自然退化。

## Risks

- 章不再显示百分数：作者若依赖逐段数值对比会不适应——悬停可查，且逐段数值本就因上游并段共享、无段落级真实性。
- vitest 既有旧视觉钉（共四处）：`zhuqueWorkbench.test.tsx` 的「人写只灰章」(33)、「stale 3 章」(47)、「marks.length===3」(38)、「AI 86% 文本」(39) 全部按带语义同批改写。
- e2e `client/frontend/e2e/zhuque.spec.ts:36-38` 钉了 `.zq-warn`/`.zq-mark` 首个可见——带化后底色与带尾章仍存在，预计侥幸存活，但须实跑核对并在用例注明带语义（不做「无钉」假设）。
- 视觉语义变更无自动门禁兜底（design:lint 不查此类、design:check parity 不含 workbench 屏）——靠 ADJUSTMENTS.md 登记＋真机验收背书。
- 后端未来若改句级/分级返回，`paragraph_index` 语义重定义，带算法需重审（契约变更走 openspec，届时自然拦截）。
