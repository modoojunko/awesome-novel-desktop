# c-deai-wizard-keep-advance — 修稿向导③步自动判保留段放行（反馈死锁修复）

## Why

用户反馈（2026-10-11 问题反馈表，reczz28M59JOMKIL）：「采用改稿这边点一两次后就点不动了，重新生成也没用」。定诊＝③步逐段取舍的**死锁**：

- 某段改稿结果「确诊为零逐字原样」（`changed=false`）或「命中结构红线」时，代码把该段自动判成 `decision="keep"`，但**不前进到下一段**；
- 此时主按钮被 `decision !== "undecided"` 禁用（点不动）、「这段保留原文」按钮只在 `undecided` 时渲染（消失），唯一可点的「重新生成」产出再次相同 → 再次强制判保留 → 死循环；
- 若发生在最后一段，连④应用确认都进不去（按钮文案已是「下一步：应用确认」但恒禁用）。

连带违约：规格「改稿引入结构红线被降级」明确要求**作家仍可强行采用**（④步终选翻转提供该入口），但③步死锁使④步不可达——入口名存实亡。

同族缺口：模型吐空串（`status="empty"`）段，面板文案承诺「可重新生成，**或保留原文**」，但「这段保留原文」按钮不渲染——同一样卡在段上。

## What Changes

- ③步对「已自动判保留」（零改稿/红线）的就绪段：主按钮放行为**「这段保留原文，看下一段」**——点击前进（末段则进④应用确认），不再要求 `undecided`；
- 红线段的强行采用入口恢复可达：前进到④后在应用确认步用既有终选翻转（本 change 不新增③步强行采用按钮——与「候选标红且默认保留」的降级语义一致）；
- 空产出段补齐「这段保留原文」按钮渲染（`keep()` 本就放行 empty 态，只是按钮没画）；
- 全队列自动判保留时流程可走完：④应用禁用（0 段采用）＝既有「全保留原文」收尾态，不属卡死。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `polish-wizard`: ③步「自动判保留段放行」——零改稿/红线强制判保留的段与空产出段 SHALL 提供前进/保留入口，SHALL NOT 卡死在段上；红线强行采用入口 SHALL 经④步终选翻转可达。

## Impact

- `client/frontend/src/components/novel/workbench/polishWizard/PolishWizard.tsx`（③步按钮状态机：footer 禁用条件、nextLabel、nextClick 前进分支、keep 按钮渲染条件）；
- `client/frontend/src/__tests__/PolishWizard.test.tsx`（4 条回归钉）；
- 不触碰后端、④步写回事务、上下文保鲜与请求编排。

## Design Impact

- 纯交互状态机修复，无 UI 视觉稿变化、无原型需求、不触共享段。
