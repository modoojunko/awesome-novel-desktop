## 1. ③步死锁修复

- [x] 1.1 `nextClick()` ③步分支：当前段 `ready 且 decision==="keep"`（零改稿/红线自动判保留）时前进（`fixIdx+1`，末段进④），不再走 `adopt()` 的 `undecided` 守卫。验证＝组件测试「零改稿段不再卡死」
- [x] 1.2 footer 主按钮禁用条件去掉 `decision !== "undecided"`（③步停留屏上的已定段只有自动判保留一种，采用段恒即时前进）；`nextLabel` 增「这段保留原文，看下一段」分支（`forcedKeep` 且非 allDecided）
- [x] 1.3 「这段保留原文」按钮渲染条件扩到 `status==="empty"`（`keep()` 本就放行 empty 态）。验证＝组件测试「空产出段可保留跳过」
- [x] 1.4 红线强行采用入口恢复可达：③步放行前进→④步既有终选翻转。验证＝组件测试「红线段自动判保留后可前进，④步终选翻转仍可强行采用」

## 2. 回归与门禁

- [x] 2.1 `PolishWizard.test.tsx` 新增 4 条回归钉（零改稿前进／红线前进+④强行采用／空产出保留／全队列自动判保留走完④且应用禁用）
- [x] 2.2 `npx tsc --noEmit` 0 error；`npx vitest run src/__tests__/PolishWizard.test.tsx` 全绿
- [x] 2.3 存量用例全绿（四步走完／全保留禁用／失败重试／漂移拒写／关闭保护）
