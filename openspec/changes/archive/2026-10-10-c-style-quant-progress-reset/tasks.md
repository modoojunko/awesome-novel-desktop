# c-style-quant-progress-reset 任务清单

## 1. 实现

- [x] 1.1 `StyleSettingForm.tsx` `runSteps`：`opts.startStep === 0`（显式重启）时
  `setDistillStep(0)`。验证：新 vitest 3 条绿（在飞三步未开始、失败后归零）。
- [x] 1.2 进度条渲染条件改为 `distillStep > 0 || distillBusy`——重启在飞期可见且三步
  全未开始。验证：vitest 断言 `.ds-ok` 0 个 / `.dist-step.pending` 3 个。
- [x] 1.3 复位连带口径：`disabled` 与样本说明两处加 `!pasteText` 门——粘贴链重试不被
  「样本不齐」拦死。验证：vitest 第 3 条（样本不齐→无粘贴时禁用→粘贴失败后仍可重试）。
- [x] 1.4 续跑语义零改动（`closeDistill`/`openDistill` 未碰）。验证：既有 e2e ⑥
  「取消，稍后再说 → 重开恢复确认卡」断言保持原样。

## 2. 测试

- [x] 2.1 新增 `src/__tests__/StyleSettingForm.distillReset.test.tsx`（3 条）。
  证据：`3 passed`。
- [x] 2.2 `e2e/style-quant.spec.ts` 用例⑥补进度复位断言（旧现场 2 个完成 → 502 后
  归零＋「开始蒸馏」→ 重试在飞 3 个 pending＋「蒸馏中…」；step1 重试桩留 900ms 窗口）。
  验证：本会话未起 docker 栈（见 3.3）。

## 3. 门禁与回归

- [x] 3.1 前端全量：`npx vitest run --coverage` → **115 文件 / 1368 例全绿**
  （契约文件清单未变，无新增 lib 文件）。
- [x] 3.2 `npx tsc --noEmit` 零错；`npm run build` 零错。
- [ ] 3.3 e2e `style-quant.spec.ts` 起栈跑（本会话未起 docker 栈）：改动含新增断言与
  桩内 900ms 延迟——随常规 e2e 跑批复核（若「在飞」断言在慢机抖动，优先加大延迟
  而不是删断言）。
- [x] 3.4 后端零改动（`git diff --stat` 无 client/backend 命中）。

## 4. 用户复测口径（发版后）

- [ ] 4.1 旧 draft 停在 step2 的书：粘贴新样本重启 → 进度条从零推进（不再三步全绿）、
  按钮在飞「蒸馏中…」/失败「开始蒸馏」。
- [ ] 4.2 取消后重开：仍按 draft 续跑（确认卡照旧）。
