# c-style-quant-progress-reset

## Why

内测反馈 #13（「二次蒸馏进度显示没有退回，直接都是已完成状态」）逐条核对后的残余缺口
（issue #783）：执行层已正确重启（step1 带 `text` 即清 draft 重跑；按钮显式传
`startStep: 0`），但**进度 UI 不复位**——`startPasteDistill` 启动新一轮不重置
`distillStep`，进度条（`done = distillStep >= no`）仍显示上一轮已完成，按钮显示
「继续蒸馏」；用户看到的进度与本轮实际进度不符。

## What Changes

- `runSteps`：显式重启（`opts.startStep === 0`，即粘贴链/带 `text` 重跑）时
  `setDistillStep(0)`——上一轮/旧 draft 的步数不再冒充本轮。
- 进度条渲染条件 `distillStep > 0` → `distillStep > 0 || distillBusy`：重启在飞期
  以「三步全未开始」呈现（进度归零可见，而不是整块消失）。
- 复位到 0 后的两个连带口径：活动粘贴样本（`pasteText`）存在时，「样本不齐」门槛
  SHALL NOT 禁用重试按钮、样本说明 SHALL NOT 显示——否则粘贴链的重试会被刚复位的
  区间门槛拦死（粘贴本就是样本不齐时的出路）。
- 「关弹窗保留草稿、重开按 draft 续跑」的现有语义不动（`closeDistill`/`openDistill`
  零改动）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `style-quant`：MODIFIED Requirement「蒸馏三步端点与 draft 续跑」——补前端进度 UI
  的本轮口径（显式重启归零、在飞三步未开始、复位不拦死粘贴重试、不改变续跑语义）；
  新增三个 Scenario（进度复位 / 复位不改续跑语义 / 复位不拦死粘贴重试）。

## Impact

- 代码：`client/frontend/src/components/novel/settings/StyleSettingForm.tsx`
  （`runSteps` 复位、进度条渲染条件、按钮禁用与样本说明两处 `!pasteText` 门）。
- 测试：`src/__tests__/StyleSettingForm.distillReset.test.tsx`（新，3 条：在飞三步
  未开始＋按钮文案 / 失败后归零＋「开始蒸馏」/ 样本不齐＋粘贴重试不被拦死）；
  `e2e/style-quant.spec.ts` 用例⑥补进度复位断言（旧现场两步已完成 → 重启归零 →
  在飞三步未开始；重试桩留 900ms 窗口）。
- 用户面：二次蒸馏（粘贴重启）进度条从零推进、按钮文案随状态正确；取消/重开仍是
  续跑。
- **Design Impact**：受影响端＝C端（纯 C端，不触两端共享段）。受影响面板＝设定域
  「文风」页签的蒸馏面板（`distill-steps` / `pz-act` 既有词汇与结构零新增，仅渲染
  条件与按钮状态变化）。对象状态无新增（无新胶囊/toast/门控语义）。无需原型先行：
  形态与文案均沿用既有元素（「开始蒸馏/继续蒸馏/蒸馏中…」既有三态），仅修正呈现时机。
