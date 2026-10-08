## Why

内测用户投诉：章工作台底部的黑色 toast 泡泡「不会消失，也无法关闭」。定诊（2026-10-07）：
`lib/toast` 的 `sticky` 机制让两条回执 toast 永不自动消失——剧情抽卡采纳回执（撤销入口须活到下次编辑，
spec 钉死）与人物精盘写入回执（照抄 sticky 先例却**没有任何收回路径**，SPA 内切页也不清，只有重启应用才消失）；
而 `Toaster` 渲染时**不提供任何关闭按钮**，用户毫无出口。拍板（2026-10-07）：泡泡默认 3 秒自动关闭，
并且要有 × 让用户可以点。

## What Changes

- C端 全站 toast（`lib/toast.tsx`）默认自动消失时长 4 秒 → **3 秒**（多条叠放各自计时）。
- `Toaster` 每条 toast 尾部加 **× 关闭钮**（aria-label「关闭」，点击即 `toast.dismiss`）。
- **`sticky` 选项整体退役**（类型、实现、全部调用点）：不再存在永不自动消失的 toast。
  两处调用点改为普通 toast——
  - 剧情抽卡采纳回执（`ChapterWorkspace.tsx`）；
  - 人物精盘写入回执（`useCastReview.ts`）。
- 行为后果（拍板接受，spec 同步改）：剧情采纳回执的「撤销 · 恢复填写前的列表」入口
  **随 toast 存活**——3 秒窗口内可点，超时或点 × 后撤销入口不再可得；
  既有「编辑剧情即收」「切章即收」清理保留为提前收口（toast 已自动消失时为无害 no-op）。
- 原型先行：`list.html` toast 示例补 × 关闭钮（原型侧 `.toast-x` 样式）＋ ADJUSTMENTS.md 登记
  （实现侧 × 走内联样式——与 toast 内撤销按钮同法——不触两端共享段）。
- **不动**（明确出界）：api-config 删除撤销的 `UndoToast`（8 秒软删除窗口，标准 §12 L4 口径）与
  `HooksSettingForm` 面板回执（8 秒自清）——均为面板内自管组件，不属 `lib/toast` 系统；
  S端 toast 运行时（私有仓）本轮不动。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `design-system`：新增 requirement「C端 toast 自动消失与可关闭基线」——全站 toast 默认 3 秒自动消失＋× 手动关闭；
  toast SHALL NOT 常驻；撤销类入口随所在 toast 存活。
- `chapter-plot-items`：「采纳替换与撤销语义」requirement MODIFIED——撤销入口从「常驻到下一次编辑动作、
  不得挂自动消失的提示条」翻转为「随回执 toast 存活（3 秒窗口内可点，超时/× 即失）」。
- `chapter-cast-review`：主 spec 只钉回执**内容**口径（「还有 N 个」/全清文案、回盘点结果页），未钉 toast 持续性；
  去 sticky 是实现层对齐，无 requirement 变化，不加 delta。

## Impact

- 代码（全部 C端 `client/frontend`，后端零改动）：
  - `src/lib/toast.tsx`：时长 3 秒；× 关闭钮；删 `sticky` 类型与分支；
  - `src/components/novel/workbench/ChapterWorkspace.tsx`：plot 回执去 `sticky: true`（`plotReceiptRef`/
    `killPlotReceipt` 生命周期保留）；
  - `src/hooks/useCastReview.ts`：cast 回执去 `sticky: true`。
- 测试：
  - `chapterWorkspace.plotFlow.test.tsx`、`castReviewFlow.test.tsx` 两处 `sticky: true` 断言改普通 toast 断言；
  - `lib/toast` 无既有单测，新增 `toast.test.tsx` 盖到 `toast.tsx` 四项 100%（`toast.tsx` 追加进
    `src/coverage-contract.ts` 契约清单，CI `--coverage` 门禁对齐）；
  - e2e `plot.spec.ts` 必改时序：断言回执可见后**立即**点「撤销」，中间的落库 `expect.poll` 删除/后移
    （末尾轮询已传递性证明全链），复跑 3-5 遍；顺手补「回执 3 秒自动消失」断言。
- 门禁：`npm run design:lint`／`design:check`（toast 为瞬态浮层、不入 parity 页集；× 不新增共享段 CSS）；
  `tsc --noEmit`；相关 vitest。
- S端：零改动（× 走内联样式，不触 `@cross` 共享段；`design-cross` 维持零差异）。

## Design Impact

- 受影响端：仅 C端。
- 受影响的屏/弹层：全站所有出 toast 的面（书架/工作台/设定/AI 四域；含章工作台两处回执、
  AI 弹窗错误提示、保存失败提示、模型配置提示等）；无弹窗本体改动。
- 用到/新增的对象状态：零新增状态档位、零新增语气（仍 info/ok/warn/err）、零新增胶囊形态——
  × 是既有 toast 组件的关闭出口（按钮词为动词「关闭」，合 §13）。
- 是否触碰两端共享段：否（× 内联样式，先例＝toast 内撤销按钮 inline style；`base.css` 零改动）。
- 是否需要原型先行：需要——`list.html`（toast 设计事实源）toast 示例补 × ＋ ADJUSTMENTS.md 登记偏差原因。
- 设计工件由谁产出：实现侧自查（复用 `model-config.html` undoToast 的「toast 内按钮」原型先例，无新视觉词汇）。
