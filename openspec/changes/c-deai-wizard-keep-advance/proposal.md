# c-deai-wizard-keep-advance — 修稿向导③步死锁收口：关闭保护回归修复＋列表版行为钉

## Why

用户反馈（2026-10-11 问题反馈表，reczz28M59JOMKIL）：**「采用改稿这边点一两次后就点不动了，重新生成也没用」**。

定诊（对 v0.32 单段版）：③步逐段取舍存在**死锁**——某段改稿「确诊为零逐字原样」或「命中红线」时被自动判 `keep` 但不前进，主按钮被 `decision !== "undecided"` 禁用、「这段保留原文」按钮不渲染、「重新生成」产出相同即死循环；末段卡死时④不可达，红线「作家可强行采用」（④终选翻转）名存实亡。

同日 #832 合并把列表式重构带入 main（③步改同屏逐段取舍、footer 恒可进④、行内「采用改稿」对自动判保留段可用）——**死锁已被结构性修复**。但该合并把旧测试套件**整删未补**（`PolishWizard.test.tsx` 163 行删除、无新增），且引入两处回归：

1. **关闭保护丢臂**：`requestClose` 只对「未取舍」候选弹确认，「已采用未应用」的取舍点取消/遮罩会**静默丢弃**——违反本能力 spec「作家关闭弹窗且有未应用候选时 SHALL 先弹确认（丢弃须显式确认）」；
2. **空产出段可采用**：行内「采用改稿」对 `empty` 候选可点，点后显示「已采用」但无产出可写——误导性状态（旧版 adopt 有 `ready` 守卫）。

## What Changes

- `requestClose` 恢复「已采用 N 段但未应用」优先确认臂（先于「尚未取舍」臂，丢面更大者先问）；
- 行内「采用改稿」按钮对 `empty` 候选禁用（保留原文/重新生成仍可用）；
- **复活并补全列表版测试套件**（11 条）：四步流程基本钉＋死锁回归钉逐条封死——零改稿段默认保留但可采用、红线段可强行采用、空产出段可保留跳过、footer 恒可前进、全自动判保留走完④应用禁用；
- spec delta：把「③步不因段状态卡死」钉进规格（自动判保留段 SHALL 可采用/可保留、footer SHALL 恒可前进、空产出段 SHALL 有保留入口），防再次重构时无牙。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `polish-wizard`: ③步「自动判保留段不卡死」三保证入 spec（可采用/可保留/恒可前进）＋空产出段入口＋关闭保护双臂口径。

## Impact

- `client/frontend/src/components/novel/workbench/polishWizard/PolishWizard.tsx`（`requestClose`＋行内采用按钮 disabled）；
- `client/frontend/src/__tests__/PolishWizard.test.tsx`（复活＋新增，共 11 条）；
- 不触碰④步写回事务、上下文保鲜、请求编排与后端。

## Design Impact

- 纯交互收口，无 UI 视觉稿变化、无原型需求、不触共享段。
